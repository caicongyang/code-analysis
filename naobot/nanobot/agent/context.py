"""
================================================================================
NanoBot Context Builder - 上下文构建器模块
================================================================================

功能描述:
    负责为 LLM 构建完整的上下文信息，包括系统提示词、对话历史、
    记忆、技能等。这是一个消息组装工厂，将各种来源的信息整合成
    LLM 可以理解的格式。

核心职责:
    1. build_system_prompt(): 构建系统提示词
    2. build_messages(): 构建完整的消息列表
    3. add_tool_result(): 添加工具执行结果
    4. add_assistant_message(): 添加助手消息

上下文组成:
    1. 系统提示词：
       - 核心身份信息（nanobot）
       - 引导文件（AGENTS.md, SOUL.md 等）
       - 记忆上下文
       - 技能信息
    2. 对话历史：
       - 用户历史消息
       - 助手历史消息
       - 工具调用和结果
    3. 当前消息：
       - 用户的新请求
       - 附件（图片等）

相关模块:
    - MemoryStore: 记忆存储
    - SkillsLoader: 技能加载器

================================================================================
"""

import base64
import mimetypes
import platform
from pathlib import Path
from typing import Any

from nanobot.agent.memory import MemoryStore
from nanobot.agent.skills import SkillsLoader


class ContextBuilder:
    """
    ========================================================================
    ContextBuilder - 上下文构建器类
    ========================================================================
    
    负责将各种来源的信息整合成 LLM 可以理解的格式。
    
    上下文类型:
        1. System Prompt: 系统提示词，包含 Agent 的身份、能力和工作空间信息
        2. History Messages: 对话历史，包含用户和助手的往来消息
        3. Tool Results: 工具执行结果，让 LLM 知道工具调用的输出
    
    引导文件（Bootstrap Files）:
        - AGENTS.md: Agent 的配置和指令
        - SOUL.md: Agent 的灵魂和性格
        - USER.md: 用户的信息和偏好
        - TOOLS.md: 可用工具的说明
        - IDENTITY.md: Agent 的身份标识
    
    渐进式技能加载:
        - 始终加载的技能（Always Skills）：总是包含在系统提示词中
        - 可用技能（Available Skills）：只显示摘要，Agent 按需读取
    
    ========================================================================
    """
    
    # 引导文件名常量
    # 这些文件在 Agent 启动时会被加载到系统提示词中
    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md"]
    
    def __init__(self, workspace: Path):
        """
        初始化上下文构建器
        
        参数:
            workspace: Path，工作空间目录路径
        
        初始化组件:
            - memory: MemoryStore，记忆存储
            - skills: SkillsLoader，技能加载器
        """
        self.workspace = workspace
        self.memory = MemoryStore(workspace)
        self.skills = SkillsLoader(workspace)
    
    def build_system_prompt(self, skill_names: list[str] | None = None) -> str:
        """
        构建完整的系统提示词
        
        系统提示词组成（按顺序）:
            1. 核心身份信息：Agent 的基本介绍
            2. 引导文件内容：配置、偏好、能力说明
            3. 记忆上下文：长期记忆中的重要信息
            4. 始终加载的技能：Agent 始终可以使用的技能完整内容
            5. 可用技能摘要：其他技能的简短描述
        
        参数:
            skill_names: list[str] | None，可选的技能列表
                - 如果提供，只包含指定的技能
                - 如果为 None，包含所有"始终加载"的技能
        
        返回:
            str，完整的系统提示词
        
        使用示例:
            # 构建不包含任何技能的系统提示词
            prompt = builder.build_system_prompt()
            
            # 构建只包含特定技能的系统提示词
            prompt = builder.build_system_prompt(["python", "git"])
        """
        parts = []
        
        # ====================================================================
        # 1. 核心身份信息
        # ====================================================================
        # 包括 Agent 的名称、当前时间、运行环境、工作空间路径等
        parts.append(self._get_identity())
        
        # ====================================================================
        # 2. 引导文件内容
        # ====================================================================
        # 从工作空间读取 AGENTS.md、SOUL.md 等引导文件
        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            parts.append(bootstrap)
        
        # ====================================================================
        # 3. 记忆上下文
        # ====================================================================
        # 从 MemoryStore 获取长期记忆中的相关信息
        memory = self.memory.get_memory_context()
        if memory:
            parts.append(f"# Memory\n\n{memory}")
        
        # ====================================================================
        # 4. 始终加载的技能（完整内容）
        # ====================================================================
        # 这些技能会一直包含在系统提示词中
        always_skills = self.skills.get_always_skills()
        if always_skills:
            always_content = self.skills.load_skills_for_context(always_skills)
            if always_content:
                parts.append(f"# Active Skills\n\n{always_content}")
        
        # ====================================================================
        # 5. 可用技能摘要（仅标题）
        # ====================================================================
        # 其他技能只显示摘要，Agent 可以使用 read_file 工具按需读取
        skills_summary = self.skills.build_skills_summary()
        if skills_summary:
            skills_section = f"""# Skills

The following skills extend your capabilities. To use a skill, read its SKILL.md file using the read_file tool.
Skills with available="false" need dependencies installed first - you can try installing them with apt/brew.

{skills_summary}"""
            parts.append(skills_section)
        
        # 使用分隔符连接各个部分
        return "\n\n---\n\n".join(parts)
    
    def _get_identity(self) -> str:
        """
        获取核心身份信息部分
        
        包含内容:
            1. Agent 介绍（nanobot 🐈）
            2. 可用工具列表
            3. 当前时间
            4. 运行时环境（操作系统、CPU 架构、Python 版本）
            5. 工作空间路径
            6. 重要文件的位置
            7. 使用指南
        
        返回:
            str，格式化的身份信息文本
        """
        from datetime import datetime
        
        # 获取当前时间，格式化为易读的格式
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        
        # 获取工作空间的绝对路径
        workspace_path = str(self.workspace.expanduser().resolve())
        
        # 获取系统信息
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"
        
        # 构建并返回身份信息文本
        return f"""# nanobot 🐈

You are nanobot, a helpful AI assistant. You have access to tools that allow you to:
- Read, write, and edit files
- Execute shell commands
- Search the web and fetch web pages
- Send messages to users on chat channels
- Spawn subagents for complex background tasks

## Current Time
{now}

## Runtime
{runtime}

## Workspace
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
        """
        加载所有引导文件
        
        引导文件的作用:
            - AGENTS.md: 定义 Agent 的行为准则和工作方式
            - SOUL.md: 定义 Agent 的性格和说话风格
            - USER.md: 记录用户的偏好和背景
            - TOOLS.md: 说明可用的工具
            - IDENTITY.md: 定义 Agent 的身份
        
        处理逻辑:
            1. 遍历 BOOTSTRAP_FILES 列表
            2. 检查每个文件是否存在
            3. 读取文件内容
            4. 用文件名作为标题格式化
        
        返回:
            str，所有引导文件的格式化内容
            如果没有引导文件，返回空字符串
        """
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
        构建完整的消息列表用于 LLM 调用
        
        消息列表结构:
            [
                {{"role": "system", "content": "..."}},  # 系统提示词
                {{"role": "user", "content": "..."}},    # 历史消息
                {{"role": "assistant", "content": "..."}},  # 历史消息
                {{"role": "user", "content": "..."}},    # 当前消息
            ]
        
        参数:
            history: list[dict]，之前的对话历史
            current_message: str，用户的新消息
            skill_names: list[str] | None，要包含的技能列表
            media: list[str] | None，附件文件路径列表（图片等）
            channel: str | None，当前频道标识
            chat_id: str | None，当前聊天 ID
        
        返回:
            list[dict]，格式化的消息列表
        
        处理步骤:
            1. 添加系统提示词消息
            2. 扩展历史消息
            3. 处理附件（图片需要 base64 编码）
            4. 添加当前用户消息
        """
        messages = []
        
        # ====================================================================
        # 1. 系统提示词
        # ====================================================================
        system_prompt = self.build_system_prompt(skill_names)
        if channel and chat_id:
            system_prompt += f"\n\n## Current Session\nChannel: {channel}\nChat ID: {chat_id}"
        messages.append({"role": "system", "content": system_prompt})
        
        # ====================================================================
        # 2. 历史消息
        # ====================================================================
        messages.extend(history)
        
        # ====================================================================
        # 3. 当前消息（支持图片附件）
        # ====================================================================
        user_content = self._build_user_content(current_message, media)
        messages.append({"role": "user", "content": user_content})
        
        return messages
    
    def _build_user_content(self, text: str, media: list[str] | None) -> str | list[dict[str, Any]]:
        """
        构建用户消息内容，支持图片附件
        
        图片处理流程:
            1. 检查文件是否存在
            2. 检查是否为图片类型
            3. 读取文件并 base64 编码
            4. 构建 OpenAI 格式的图片 URL
        
        支持的图片格式:
            - image/jpeg
            - image/png
            - image/gif
            - image/webp
        
        参数:
            text: str，文本内容
            media: list[str] | None，附件文件路径列表
        
        返回:
            str | list[dict]，纯文本或混合内容
        """
        # 没有附件，直接返回文本
        if not media:
            return text
        
        images = []
        for path in media:
            p = Path(path)
            mime, _ = mimetypes.guess_type(path)
            
            # 检查文件是否存在且是图片类型
            if not p.is_file() or not mime or not mime.startswith("image/"):
                continue
            
            # 读取图片并 base64 编码
            b64 = base64.b64encode(p.read_bytes()).decode()
            
            # 构建 OpenAI 格式的图片 URL
            images.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime};base64,{b64}"
                }
            })
        
        # 如果没有有效的图片，返回文本
        if not images:
            return text
        
        # 返回混合内容（图片 + 文本）
        return images + [{"type": "text", "text": text}]
    
    def add_tool_result(
        self,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        tool_name: str,
        result: str
    ) -> list[dict[str, Any]]:
        """
        将工具执行结果添加到消息列表
        
        工具结果消息格式:
            {{
                "role": "tool",
                "tool_call_id": "call_123",
                "name": "read_file",
                "content": "文件内容..."
            }}
        
        这让 LLM 能够看到工具的输出，从而继续处理
        
        参数:
            messages: list[dict]，当前消息列表
            tool_call_id: str，工具调用的 ID（来自 LLM 的响应）
            tool_name: str，被调用的工具名称
            result: str，工具执行的结果
        
        返回:
            list[dict]，添加了工具结果的新消息列表
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
        将助手消息添加到消息列表
        
        助手消息格式:
            {{
                "role": "assistant",
                "content": "我可以帮你...",
                "tool_calls": [...],  # 可选
                "reasoning_content": "思考过程..."  # 可选（思考模型）
            }}
        
        参数:
            messages: list[dict]，当前消息列表
            content: str | None，助手回复内容
            tool_calls: list[dict] | None，工具调用列表
            reasoning_content: str | None，思考模型的思考过程
        
        返回:
            list[dict]，添加了助手消息的新消息列表
        """
        msg: dict[str, Any] = {"role": "assistant", "content": content or ""}
        
        # 添加工具调用（如果有）
        if tool_calls:
            msg["tool_calls"] = tool_calls
        
        # 添加思考内容（对于 Kimi、DeepSeek-R1 等思考模型）
        if reasoning_content:
            msg["reasoning_content"] = reasoning_content
        
        messages.append(msg)
        return messages