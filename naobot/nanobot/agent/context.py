"""Context builder for assembling agent prompts."""
# 用于组装 Agent 提示词的上下文构建器

import base64
import mimetypes
import platform
from pathlib import Path
from typing import Any

from nanobot.agent.memory import MemoryStore
from nanobot.agent.skills import SkillsLoader


class ContextBuilder:
    """
    Builds the context (system prompt + messages) for the agent.
    # 为 Agent 构建上下文（系统提示词 + 消息）
    
    Assembles bootstrap files, memory, skills, and conversation history
    into a coherent prompt for the LLM.
    # 将引导文件、记忆、技能和对话历史组合成连贯的 LLM 提示词
    """
    
    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md"]
    # 引导文件列表 - 这些文件在启动时会被加载到系统提示词中
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.memory = MemoryStore(workspace)
        self.skills = SkillsLoader(workspace)
    
    def build_system_prompt(self, skill_names: list[str] | None = None) -> str:
        """
        Build the system prompt from bootstrap files, memory, and skills.
        # 从引导文件、记忆和技能构建系统提示词
        
        Args:
            skill_names: Optional list of skills to include.
            # skill_names: 要包含的技能列表（可选）
        
        Returns:
            Complete system prompt.
            # 完整的系统提示词
        """
        parts = []
        
        # Core identity
        # 核心身份信息
        parts.append(self._get_identity())
        
        # Bootstrap files
        # 引导文件
        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            parts.append(bootstrap)
        
        # Memory context
        # 记忆上下文
        memory = self.memory.get_memory_context()
        if memory:
            parts.append(f"# Memory\n\n{memory}")
        
        # Skills - progressive loading
        # 技能 - 渐进式加载
        # 1. Always-loaded skills: include full content
        # 1. 始终加载的技能：包含完整内容
        always_skills = self.skills.get_always_skills()
        if always_skills:
            always_content = self.skills.load_skills_for_context(always_skills)
            if always_content:
                parts.append(f"# Active Skills\n\n{always_content}")
        
        # 2. Available skills: only show summary (agent uses read_file to load)
        # 2. 可用技能：仅显示摘要（Agent 使用 read_file 工具加载）
        skills_summary = self.skills.build_skills_summary()
        if skills_summary:
            parts.append(f"""# Skills

The following skills extend your capabilities. To use a skill, read its SKILL.md file using the read_file tool.
Skills with available="false" need dependencies installed first - you can try installing them with apt/brew.

{skills_summary}""")
        
        return "\n\n---\n\n".join(parts)
    
    def _get_identity(self) -> str:
        """Get the core identity section."""
        # 获取核心身份信息部分
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        workspace_path = str(self.workspace.expanduser().resolve())
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"
        
        return f"""# nanobot 🐈

You are nanobot, a helpful AI assistant. You have access to tools that allow you to:
- Read, write, and edit files
- Execute shell commands
- Search the web and fetch web pages
- Send messages to users on chat channels
- Spawn subagents for complex background tasks

## Current Time
# 当前时间
{now}

## Runtime
# 运行环境
{runtime}

## Workspace
# 工作空间
Your workspace is at: {workspace_path}
- Memory files: {workspace_path}/memory/MEMORY.md
- Daily notes: {workspace_path}/memory/YYYY-MM-DD.md
- Custom skills: {workspace_path}/skills/{{skill-name}}/SKILL.md

IMPORTANT: When responding to direct questions or conversations, reply directly with your text response.
Only use the 'message' tool when you need to send a message to a specific chat channel (like WhatsApp).
For normal conversation, just respond with text - do not call the message tool.

Always be helpful, accurate, and concise. When using tools, explain what you're doing.
When remembering something, write to {workspace_path}/memory/MEMORY.md"""
    
    def _load_bootstrap_files(self) -> str:
        """Load all bootstrap files from workspace."""
        # 从工作空间加载所有引导文件
        parts = []
        
        for filename in self.BOOTSTRAP_FILES:
            file_path = self.workspace / filename
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                parts.append(f"## {filename}\n\n{content}")
        
        return "\n\n".join(parts) if parts else ""
    
    def build_messages(
        self,
        history: list[dict[str, Any]],
        current_message: str,
        skill_names: list[str] | None = None,
        media: list[str] | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Build the complete message list for an LLM call.
        # 构建完整的消息列表用于 LLM 调用

        Args:
            history: Previous conversation messages.
            # history: 之前的对话消息
            current_message: The new user message.
            # current_message: 用户的新消息
            skill_names: Optional skills to include.
            # skill_names: 要包含的技能列表（可选）
            media: Optional list of local file paths for images/media.
            # media: 图片/媒体文件的本地路径列表（可选）
            channel: Current channel (telegram, feishu, etc.).
            # channel: 当前频道（telegram, feishu 等）
            chat_id: Current chat/user ID.
            # chat_id: 当前聊天/用户 ID

        Returns:
            List of messages including system prompt.
            # 包含系统提示词的消息列表
        """
        messages = []

        # System prompt
        # 系统提示词
        system_prompt = self.build_system_prompt(skill_names)
        if channel and chat_id:
            system_prompt += f"\n\n## Current Session\nChannel: {channel}\nChat ID: {chat_id}"
        messages.append({"role": "system", "content": system_prompt})

        # History
        # 历史消息
        messages.extend(history)

        # Current message (with optional image attachments)
        # 当前消息（可选带图片附件）
        user_content = self._build_user_content(current_message, media)
        messages.append({"role": "user", "content": user_content})

        return messages

    def _build_user_content(self, text: str, media: list[str] | None) -> str | list[dict[str, Any]]:
        """Build user message content with optional base64-encoded images."""
        # 构建用户消息内容，支持可选的 base64 编码图片
        if not media:
            return text
        
        images = []
        for path in media:
            p = Path(path)
            mime, _ = mimetypes.guess_type(path)
            if not p.is_file() or not mime or not mime.startswith("image/"):
                continue
            b64 = base64.b64encode(p.read_bytes()).decode()
            images.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
        
        if not images:
            return text
        return images + [{"type": "text", "text": text}]
    
    def add_tool_result(
        self,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        tool_name: str,
        result: str
    ) -> list[dict[str, Any]]:
        """
        Add a tool result to the message list.
        # 将工具执行结果添加到消息列表
        
        Args:
            messages: Current message list.
            # messages: 当前消息列表
            tool_call_id: ID of the tool call.
            # tool_call_id: 工具调用的 ID
            tool_name: Name of the tool.
            # tool_name: 工具名称
            result: Tool execution result.
            # result: 工具执行结果
        
        Returns:
            Updated message list.
            # 更新后的消息列表
        """
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result
        })
        return messages
    
    def add_assistant_message(
        self,
        messages: list[dict[str, Any]],
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None,
        reasoning_content: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Add an assistant message to the message list.
        # 将助手消息添加到消息列表
        
        Args:
            messages: Current message list.
            # messages: 当前消息列表
            content: Message content.
            # content: 消息内容
            tool_calls: Optional tool calls.
            # tool_calls: 可选的工具调用列表
            reasoning_content: Thinking output (Kimi, DeepSeek-R1, etc.).
            # reasoning_content: 思考输出（Kimi, DeepSeek-R1 等）
        
        Returns:
            Updated message list.
            # 更新后的消息列表
        """
        msg: dict[str, Any] = {"role": "assistant", "content": content or ""}
        
        if tool_calls:
            msg["tool_calls"] = tool_calls
        
        # Thinking models reject history without this
        # 思考模型会拒绝没有此字段的历史记录
        if reasoning_content:
            msg["reasoning_content"] = reasoning_content
        
        messages.append(msg)
        return messages
