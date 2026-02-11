"""
================================================================================
NanoBot Agent Loop - Agent 循环模块
================================================================================

功能描述:
    这是 NanoBot 的核心处理引擎，负责整个 Agent 的消息处理流程。
    它实现了消息接收、上下文构建、LLM 调用、工具执行和响应发送的完整闭环。

核心流程:
    1. 从消息总线接收入站消息 (InboundMessage)
    2. 构建包含历史记录、记忆、技能的上下文
    3. 调用 LLM 模型生成响应
    4. 执行工具调用（如果有）
    5. 发送响应回消息总线

与系统其他组件的交互:
    - MessageBus: 消息总线，负责消息的接收和发送
    - LLMProvider: LLM 提供者，负责调用大语言模型
    - SessionManager: 会话管理器，负责管理会话历史
    - ToolRegistry: 工具注册表，负责管理可用的工具
    - SubagentManager: 子代理管理器，负责管理子代理

主要类:
    - AgentLoop: 核心处理引擎类

使用示例:
    # 创建 AgentLoop 实例
    agent = AgentLoop(
        bus=message_bus,
        provider=llm_provider,
        workspace=Path("/path/to/workspace"),
        model="gpt-4",
        max_iterations=20,
    )
    
    # 启动 Agent 循环
    await agent.run()

================================================================================
"""

# 导入异步处理相关模块
import asyncio
import json
from pathlib import Path
from typing import Any

# 导入日志模块
from loguru import logger

# 导入消息总线相关模块
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus

# 导入 LLM 提供者相关模块
from nanobot.providers.base import LLMProvider

# 导入上下文构建器
from nanobot.agent.context import ContextBuilder

# 导入工具注册表
from nanobot.agent.tools.registry import ToolRegistry

# 导入各种工具实现
from nanobot.agent.tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.web import WebSearchTool, WebFetchTool
from nanobot.agent.tools.message import MessageTool
from nanobot.agent.tools.spawn import SpawnTool
from nanobot.agent.tools.cron import CronTool

# 导入子代理管理器
from nanobot.agent.subagent import SubagentManager

# 导入会话管理器
from nanobot.session.manager import SessionManager


class AgentLoop:
    """
    ========================================================================
    AgentLoop - Agent 循环核心类
    ========================================================================
    
    这是 NanoBot Agent 的核心处理引擎，实现了完整的消息处理闭环。
    
    职责:
        1. 从消息总线接收用户消息
        2. 构建包含历史、记忆、技能的上下文
        3. 调用 LLM 生成响应
        4. 执行工具调用
        5. 返回响应给用户
    
    生命周期:
        1. __init__: 初始化，配置各种组件和工具
        2. run: 启动主循环，持续处理消息
        3. stop: 停止循环
    
    属性说明:
        - bus: 消息总线，用于接收和发送消息
        - provider: LLM 提供者，负责调用大语言模型
        - workspace: 工作空间路径，Agent 的文件操作基准目录
        - model: 使用的模型名称
        - max_iterations: 单次消息处理的最大迭代次数（防止无限循环）
        - context: 上下文构建器，负责组装 LLM 所需的上下文信息
        - sessions: 会话管理器，负责管理对话历史
        - tools: 工具注册表，负责管理可用的工具
        - subagents: 子代理管理器，负责管理子代理
        - _running: 循环运行状态标志
    
    ========================================================================
    """
    
    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 20,
        brave_api_key: str | None = None,
        exec_config: "ExecToolConfig | None" = None,
        cron_service: "CronService | None" = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
    ):
        """
        初始化 AgentLoop 实例
        
        参数说明:
            bus: MessageBus 实例，负责消息的接收和发送
            provider: LLMProvider 实例，负责调用大语言模型
            workspace: Path 对象，指定 Agent 的工作空间目录
            model: str 或 None，要使用的模型名称，如果为 None 则使用默认模型
            max_iterations: int，单次消息处理的最大迭代次数，默认为 20
            brave_api_key: str 或 None，Brave 搜索引擎的 API Key
            exec_config: ExecToolConfig 或 None，Shell 命令执行工具的配置
            cron_service: CronService 或 None，定时任务服务实例
            restrict_to_workspace: bool，是否限制文件操作在 workspace 内
            session_manager: SessionManager 或 None，自定义的会话管理器
        
        初始化过程:
            1. 保存所有传入的配置参数
            2. 获取默认模型（如果未指定）
            3. 创建上下文构建器
            4. 创建或使用会话管理器
            5. 创建工具注册表
            6. 创建子代理管理器
            7. 注册默认工具集
        """
        from nanobot.config.schema import ExecToolConfig
        from nanobot.cron.service import CronService
        
        # 保存消息总线引用，用于消息的接收和发送
        self.bus = bus
        
        # 保存 LLM 提供者引用，用于调用大语言模型
        self.provider = provider
        
        # 保存工作空间路径，这是 Agent 文件操作的基准目录
        self.workspace = workspace
        
        # 确定使用的模型：如果未指定则使用提供者的默认模型
        self.model = model or provider.get_default_model()
        
        # 设置最大迭代次数，防止 Agent 在处理复杂请求时无限循环
        self.max_iterations = max_iterations
        
        # 保存 Brave 搜索引擎 API Key（用于网络搜索工具）
        self.brave_api_key = brave_api_key
        
        # 配置 Shell 执行工具：如果未提供则使用默认配置
        self.exec_config = exec_config or ExecToolConfig()
        
        # 保存定时任务服务引用
        self.cron_service = cron_service
        
        # 是否限制所有文件操作在 workspace 目录内
        # True 表示只能操作 workspace 内的文件，更安全
        self.restrict_to_workspace = restrict_to_workspace
        
        # 创建上下文构建器，负责组装 LLM 所需的上下文信息
        self.context = ContextBuilder(workspace)
        
        # 创建或使用会话管理器，负责管理对话历史和状态
        # 如果未提供则创建一个新的会话管理器
        self.sessions = session_manager or SessionManager(workspace)
        
        # 创建工具注册表，用于管理所有可用的工具
        self.tools = ToolRegistry()
        
        # 创建子代理管理器
        # 子代理是独立的 Agent，可以并行处理任务
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            brave_api_key=brave_api_key,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
        )
        
        # 初始化运行状态标志，初始为 False
        self._running = False
        
        # 注册所有默认工具集
        self._register_default_tools()
    
    def _register_default_tools(self) -> None:
        """
        注册默认的工具集到工具注册表
        
        注册的工具类型:
            1. 文件操作工具：读取、写入、编辑、列出目录
            2. Shell 执行工具：执行系统命令
            3. 网络工具：网页搜索、网页抓取
            4. 消息工具：发送消息到各个平台
            5. 工具调用工具：调用子代理
            6. 定时任务工具：管理定时任务
        
        安全考虑:
            - 如果 restrict_to_workspace 为 True，文件工具只能操作工作空间内的文件
            - Shell 命令执行有时间限制和权限控制
        """
        # 确定文件工具允许操作的目录
        # 如果限制在 workspace 内，则只能操作 workspace 目录
        # 否则可以操作任何目录
        allowed_dir = self.workspace if self.restrict_to_workspace else None
        
        # ========================================================================
        # 注册文件操作工具
        # ========================================================================
        # ReadFileTool: 读取文件内容
        # 用途：让 Agent 可以阅读代码、文档等内容
        self.tools.register(ReadFileTool(allowed_dir=allowed_dir))
        
        # WriteFileTool: 写入文件内容
        # 用途：让 Agent 可以创建新文件、修改现有文件
        self.tools.register(WriteFileTool(allowed_dir=allowed_dir))
        
        # EditFileTool: 编辑文件内容
        # 用途：让 Agent 可以精确修改文件的某一部分
        self.tools.register(EditFileTool(allowed_dir=allowed_dir))
        
        # ListDirTool: 列出目录内容
        # 用途：让 Agent 可以查看目录结构、了解项目布局
        self.tools.register(ListDirTool(allowed_dir=allowed_dir))
        
        # ========================================================================
        # 注册 Shell 执行工具
        # ========================================================================
        # ExecTool: 执行系统命令
        # 用途：让 Agent 可以运行任何系统命令
        # 例如：git 操作、编译代码、管理进程等
        self.tools.register(ExecTool(
            working_dir=str(self.workspace),  # 命令执行的工作目录
            timeout=self.exec_config.timeout,  # 命令超时时间
            restrict_to_workspace=self.restrict_to_workspace,  # 是否限制在 workspace 内
        ))
        
        # ========================================================================
        # 注册网络工具
        # ========================================================================
        # WebSearchTool: 网络搜索工具
        # 用途：使用 Brave 搜索引擎搜索网络内容
        self.tools.register(WebSearchTool(api_key=self.brave_api_key))
        
        # WebFetchTool: 网页抓取工具
        # 用途：获取网页内容、解析 HTML
        self.tools.register(WebFetchTool())
        
        # ========================================================================
        # 注册消息工具
        # ========================================================================
        # MessageTool: 发送消息到各个平台
        # 用途：让 Agent 可以通过消息总线发送消息给用户
        message_tool = MessageTool(send_callback=self.bus.publish_outbound)
        self.tools.register(message_tool)
        
        # ========================================================================
        # 注册子代理工具
        # ========================================================================
        # SpawnTool: 启动子代理
        # 用途：让 Agent 可以并行启动其他 Agent 处理任务
        spawn_tool = SpawnTool(manager=self.subagents)
        self.tools.register(spawn_tool)
        
        # ========================================================================
        # 注册定时任务工具
        # ========================================================================
        # 如果配置了定时任务服务，则注册定时任务工具
        # CronTool: 管理定时任务
        # 用途：让 Agent 可以创建、查看、删除定时任务
        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))
    
    async def run(self) -> None:
        """
        启动 Agent 循环，持续处理来自消息总线的消息
        
        循环逻辑:
            1. 调用 bus.consume_inbound() 等待接收消息
            2. 如果超时（1秒），继续等待
            3. 收到消息后，调用 _process_message() 处理
            4. 如果处理产生响应，发送到消息总线
            5. 如果处理出错，发送错误消息给用户
            6. 重复步骤 1-5
        
        异常处理:
            - 消息处理异常：捕获异常，发送错误消息给用户
            - 超时异常：忽略，继续等待下一个消息
        
        退出条件:
            - 调用 stop() 方法将 _running 设为 False
            - 循环会检查此标志并在下次迭代时退出
        
        使用示例:
            # 在 asyncio 事件循环中启动
            agent = AgentLoop(...)
            await agent.run()
        """
        # 设置运行状态为 True
        self._running = True
        
        # 记录启动日志
        logger.info("Agent loop started - 开始接收和处理消息")
        
        # 主循环：持续运行直到 _running 变为 False
        while self._running:
            try:
                # ====================================================================
                # 等待接收消息
                # ====================================================================
                # 使用 asyncio.wait_for 设置超时，避免长时间阻塞
                # timeout=1.0 表示每 1 秒检查一次循环状态
                # 这样可以在收到 stop() 调用后及时退出
                msg = await asyncio.wait_for(
                    self.bus.consume_inbound(),
                    timeout=1.0
                )
                
                # ====================================================================
                # 处理消息
                # ====================================================================
                try:
                    # 调用消息处理函数
                    response = await self._process_message(msg)
                    
                    # 如果有响应，发送到消息总线
                    if response:
                        await self.bus.publish_outbound(response)
                except Exception as e:
                    # 处理消息时发生异常
                    logger.error(f"Error processing message: {e}")
                    
                    # 发送错误消息给用户
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel,  # 回复到相同的频道
                        chat_id=msg.chat_id,  # 回复到相同的聊天
                        content=f"Sorry, I encountered an error: {str(e)}"
                    ))
            
            except asyncio.TimeoutError:
                # 超时异常是预期的行为（每 1 秒触发一次）
                # 忽略此异常，继续循环
                continue
    
    def stop(self) -> None:
        """
        停止 Agent 循环
        
        实现方式:
            将 _running 标志设为 False
            下次循环迭代时会检测到此变化并退出
        
        注意:
            - 这是一个同步方法，可以在任何地方调用
            - 不会立即停止，而是在当前消息处理完成后退出
        """
        self._running = False
        logger.info("Agent loop stopping - 正在停止...")
    
    async def _process_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """
        处理单条入站消息的核心逻辑
        
        完整的消息处理流程:
            1. 系统消息处理：如果消息来自系统（子代理），调用特殊处理逻辑
            2. 会话管理：获取或创建会话，加载历史记录
            3. 工具上下文更新：设置消息工具的频道和聊天 ID
            4. 上下文构建：组装 LLM 所需的消息、历史、技能
            5. Agent 循环：调用 LLM，处理工具调用，直到完成
            6. 响应返回：将最终响应封装为 OutboundMessage
            7. 会话保存：将会话历史保存到磁盘
        
        参数:
            msg: InboundMessage，包含消息的所有信息
                - channel: 消息来源频道（telegram、qq、cli 等）
                - sender_id: 发送者 ID
                - chat_id: 聊天会话 ID
                - content: 消息内容
                - session_key: 会话唯一标识
        
        返回:
            OutboundMessage 或 None：
                - 如果需要响应，返回包含响应的 OutboundMessage
                - 如果不需要响应（如系统消息），返回 None
        
        异常处理:
            - 所有处理逻辑都在 try-except 块中
            - 错误会被记录并可能返回错误消息
        """
        # ========================================================================
        # 系统消息处理
        # ========================================================================
        # 系统消息来自子代理（subagent），格式为 channel="system"
        # 这种消息需要特殊处理，将响应路由回原始目的地
        if msg.channel == "system":
            return await self._process_system_message(msg)
        
        # 记录处理开始日志
        # 截取消息前 80 个字符作为预览
        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info(f"Processing message from {msg.channel}:{msg.sender_id}: {preview}")
        
        # ========================================================================
        # 会话管理
        # ========================================================================
        # 获取或创建会话
        # 会话存储了用户和 Agent 之间的对话历史
        session = self.sessions.get_or_create(msg.session_key)
        
        # ========================================================================
        # 更新工具上下文
        # ========================================================================
        # 设置消息工具的上下文，确保回复发送到正确的频道和聊天
        message_tool = self.tools.get("message")
        if isinstance(message_tool, MessageTool):
            message_tool.set_context(msg.channel, msg.chat_id)
        
        # 设置子代理工具的上下文
        spawn_tool = self.tools.get("spawn")
        if isinstance(spawn_tool, SpawnTool):
            spawn_tool.set_context(msg.channel, msg.chat_id)
        
        # 设置定时任务工具的上下文
        cron_tool = self.tools.get("cron")
        if isinstance(cron_tool, CronTool):
            cron_tool.set_context(msg.channel, msg.chat_id)
        
        # ========================================================================
        # 构建 LLM 上下文
        # ========================================================================
        # 组装 LLM 需要的所有信息：
        # - 历史消息（对话记录）
        # - 当前消息（用户的新请求）
        # - 媒体信息（如果有附件）
        # - 频道和聊天上下文
        messages = self.context.build_messages(
            history=session.get_history(),
            current_message=msg.content,
            media=msg.media if msg.media else None,
            channel=msg.channel,
            chat_id=msg.chat_id,
        )
        
        # ========================================================================
        # Agent 循环
        # ====================================================================
        # 核心循环：调用 LLM，处理工具调用
        # 最多迭代 max_iterations 次，防止无限循环
        iteration = 0
        final_content = None
        
        while iteration < self.max_iterations:
            iteration += 1
            
            # ====================================================================
            # 调用 LLM
            # ====================================================================
            # 发送消息列表、可用工具列表给 LLM
            # LLM 会决定是否需要调用工具
            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model
            )
            
            # ====================================================================
            # 处理工具调用
            # ====================================================================
            if response.has_tool_calls:
                # LLM 决定调用工具
                
                # 将工具调用信息添加到消息历史
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)
                        }
                    }
                    for tc in response.tool_calls
                ]
                
                # 添加助手消息（包含工具调用）
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                )
                
                # ====================================================================
                # 执行工具
                # ====================================================================
                # 遍历所有工具调用，逐一执行
                for tool_call in response.tool_calls:
                    # 记录工具调用日志（截取前 200 字符）
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info(f"Tool call: {tool_call.name}({args_str[:200]})")
                    
                    # 执行工具调用
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    
                    # 将工具执行结果添加到消息历史
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
            else:
                # LLM 没有调用工具，响应已完成
                final_content = response.content
                break
        
        # 如果达到最大迭代次数但没有完成
        if final_content is None:
            final_content = "I've completed processing but have no response to give."
        
        # ========================================================================
        # 保存和返回
        # ========================================================================
        # 记录响应日志
        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.info(f"Response to {msg.channel}:{msg.sender_id}: {preview}")
        
        # 保存会话历史到磁盘
        session.add_message("user", msg.content)
        session.add_message("assistant", final_content)
        self.sessions.save(session)
        
        # 返回响应消息
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content,
            metadata=msg.metadata or {},
        )
    
    async def _process_system_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """
        处理系统消息（子代理声明）
        
        系统消息的特殊性:
            - 来自子代理（subagent）的运行结果
            - 需要将响应路由回原始目的地
            - chat_id 格式为 "original_channel:original_chat_id"
        
        处理流程:
            1. 解析来源信息
            2. 获取或创建原始会话
            3. 更新工具上下文
            4. 构建消息
            5. 执行 Agent 循环
            6. 保存会话
            7. 返回响应（路由回原始目的地）
        
        参数:
            msg: 系统消息，包含子代理的声明内容
        
        返回:
            OutboundMessage 或 None
        """
        logger.info(f"Processing system message from {msg.sender_id}")
        
        # ========================================================================
        # 解析来源信息
        # ========================================================================
        # chat_id 格式为 "channel:chat_id"
        # 例如："telegram:123456789"
        if ":" in msg.chat_id:
            parts = msg.chat_id.split(":", 1)
            origin_channel = parts[0]
            origin_chat_id = parts[1]
        else:
            # 如果没有冒号，默认使用 CLI
            origin_channel = "cli"
            origin_chat_id = msg.chat_id
        
        # 构建会话键
        session_key = f"{origin_channel}:{origin_chat_id}"
        
        # ========================================================================
        # 获取会话
        # ========================================================================
        session = self.sessions.get_or_create(session_key)
        
        # ========================================================================
        # 更新工具上下文
        # ========================================================================
        message_tool = self.tools.get("message")
        if isinstance(message_tool, MessageTool):
            message_tool.set_context(origin_channel, origin_chat_id)
        
        spawn_tool = self.tools.get("spawn")
        if isinstance(spawn_tool, SpawnTool):
            spawn_tool.set_context(origin_channel, origin_chat_id)
        
        cron_tool = self.tools.get("cron")
        if isinstance(cron_tool, CronTool):
            cron_tool.set_context(origin_channel, origin_chat_id)
        
        # ========================================================================
        # 构建消息
        # ========================================================================
        messages = self.context.build_messages(
            history=session.get_history(),
            current_message=msg.content,
            channel=origin_channel,
            chat_id=origin_chat_id,
        )
        
        # ========================================================================
        # Agent 循环
        # ========================================================================
        iteration = 0
        final_content = None
        
        while iteration < self.max_iterations:
            iteration += 1
            
            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model
            )
            
            if response.has_tool_calls:
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)
                        }
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                )
                
                for tool_call in response.tool_calls:
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info(f"Tool call: {tool_call.name}({args_str[:200]})")
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
            else:
                final_content = response.content
                break
        
        if final_content is None:
            final_content = "Background task completed."
        
        # ========================================================================
        # 保存和返回
        # ========================================================================
        # 在历史中标记为系统消息
        session.add_message("user", f"[System: {msg.sender_id}] {msg.content}")
        session.add_message("assistant", final_content)
        self.sessions.save(session)
        
        # 路由回原始目的地
        return OutboundMessage(
            channel=origin_channel,
            chat_id=origin_chat_id,
            content=final_content
        )
    
    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
    ) -> str:
        """
        直接处理消息（用于 CLI 或定时任务）
        
        使用场景:
            - CLI 界面中用户直接输入消息
            - 定时任务触发的消息
            - 任何不需要通过消息总线的场景
        
        参数:
            content: str，消息内容
            session_key: str，会话键，默认为 "cli:direct"
            channel: str，频道标识，默认为 "cli"
            chat_id: str，聊天 ID，默认为 "direct"
        
        返回:
            str，Agent 的响应内容
        
        使用示例:
            # 在 CLI 中处理用户输入
            response = await agent.process_direct(
                content="帮我写一个 Python 函数",
                session_key="cli:user123",
                channel="cli",
                chat_id="direct"
            )
            print(response)
        """
        # 创建入站消息
        msg = InboundMessage(
            channel=channel,
            sender_id="user",
            chat_id=chat_id,
            content=content
        )
        
        # 处理消息
        response = await self._process_message(msg)
        
        # 返回响应内容
        return response.content if response else ""
