# -*- coding: utf-8 -*-
"""
================================================================================
Subagent Manager - 子代理管理器模块
================================================================================

功能描述:
    负责管理后台运行的子代理（Subagent）。子代理是轻量级的 Agent 实例，
    在后台并行处理特定任务，与主 Agent 共享同一个 LLM 提供者但拥有独立
    的上下文和专注的系统提示词。

核心功能:
    1. spawn(): 启动子代理执行后台任务
    2. _run_subagent(): 执行子代理的核心逻辑
    3. _announce_result(): 将结果公告回主 Agent
    4. get_running_count(): 获取正在运行的子代理数量

子代理的特点:
    - 轻量级：共享主 Agent 的 LLM 提供者
    - 隔离：有独立的上下文和工具集
    - 专注：针对特定任务优化的系统提示词
    - 后台运行：不会阻塞主 Agent 的消息处理

使用场景:
    - 并行处理多个独立任务
    - 执行耗时的搜索或分析任务
    - 处理需要多个步骤的复杂任务

================================================================================
"""

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.filesystem import ReadFileTool, WriteFileTool, ListDirTool
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.web import WebSearchTool, WebFetchTool


class SubagentManager:
    """
    ========================================================================
    SubagentManager - 子代理管理器类
    ========================================================================
    
    负责管理后台运行的子代理实例。
    
    子代理与主 Agent 的区别:
        1. 工具集限制：
           - 子代理没有 message 工具（不能直接发送消息给用户）
           - 子代理没有 spawn 工具（不能嵌套启动其他子代理）
           - 只能使用文件系统、Shell 执行、网络工具
        
        2. 上下文隔离：
           - 子代理有自己的消息历史
           - 子代理不访问主 Agent 的对话历史
           - 专注处理分配的任务
        
        3. 系统提示词：
           - 针对子代理任务定制的提示词
           - 强调专注、简洁、高效
    
    生命周期:
        1. spawn(): 创建并启动子代理任务
        2. _run_subagent(): 执行子代理的核心逻辑
        3. _announce_result(): 将结果注入回主 Agent
        4. 任务完成，清理资源
    
    属性说明:
        - provider: LLM 提供者，用于调用大语言模型
        - workspace: 工作空间路径
        - bus: 消息总线，用于与主 Agent 通信
        - model: 使用的模型名称
        - brave_api_key: Brave 搜索引擎 API Key
        - exec_config: Shell 执行配置
        - restrict_to_workspace: 是否限制在 workspace 内操作
        - _running_tasks: 正在运行的子代理任务字典
    
    ========================================================================
    """
    
    def __init__(
        self,
        provider: LLMProvider,
        workspace: Path,
        bus: MessageBus,
        model: str | None = None,
        brave_api_key: str | None = None,
        exec_config: "ExecToolConfig | None" = None,
        restrict_to_workspace: bool = False,
    ):
        """
        初始化子代理管理器
        
        参数说明:
            provider: LLMProvider 实例，负责调用大语言模型
            workspace: Path 对象，指定工作空间目录
            bus: MessageBus 实例，用于与主 Agent 通信
            model: str 或 None，子代理使用的模型名称
            brave_api_key: str 或 None，Brave 搜索引擎 API Key
            exec_config: ExecToolConfig 或 None，Shell 执行配置
            restrict_to_workspace: bool，是否限制文件操作在 workspace 内
        
        初始化过程:
            1. 保存 LLM 提供者引用
            2. 保存工作空间路径
            3. 保存消息总线引用
            4. 确定使用的模型
            5. 保存其他配置
            6. 初始化运行任务字典
        """
        from nanobot.config.schema import ExecToolConfig
        
        # 保存 LLM 提供者引用
        self.provider = provider
        
        # 保存工作空间路径
        self.workspace = workspace
        
        # 保存消息总线引用，用于将结果传回主 Agent
        self.bus = bus
        
        # 确定使用的模型
        self.model = model or provider.get_default_model()
        
        # 保存 Brave API Key
        self.brave_api_key = brave_api_key
        
        # Shell 执行配置
        self.exec_config = exec_config or ExecToolConfig()
        
        # 是否限制在 workspace 内操作
        self.restrict_to_workspace = restrict_to_workspace
        
        # 正在运行的子代理任务字典
        # key: 任务 ID，value: asyncio.Task
        self._running_tasks: dict[str, asyncio.Task[None]] = {}
    
    async def spawn(
        self,
        task: str,
        label: str | None = None,
        origin_channel: str = "cli",
        origin_chat_id: str = "direct",
    ) -> str:
        """
        启动子代理执行后台任务
        
        功能描述:
            创建一个新的子代理任务在后台运行，并返回任务启动信息。
            子代理会独立执行任务，完成后将结果公告回主 Agent。
        
        参数说明:
            task: str，子代理需要完成的任务描述
            label: str 或 None，任务的易读标签（用于显示）
            origin_channel: str，原始频道标识（结果将发送到此频道）
            origin_chat_id: str，原始聊天 ID
        
        返回值:
            str，任务启动状态消息，包含子代理 ID
        
        处理流程:
            1. 生成唯一的任务 ID
            2. 确定显示标签
            3. 创建后台任务
            4. 注册完成回调（自动清理）
            5. 返回启动消息
        
        使用示例:
            # 启动子代理执行搜索任务
            result = await manager.spawn(
                task="搜索最新的 AI 新闻",
                label="AI 新闻搜索",
                origin_channel="telegram",
                origin_chat_id="12345"
            )
            print(result)  # "Subagent [AI 新闻搜索] started (id: abc12345)."
        
        注意:
            - 这是异步方法，需要 await 调用
            - 任务在后台运行，不会阻塞当前代码
        """
        # 生成唯一的任务 ID（UUID 前 8 位）
        task_id = str(uuid.uuid4())[:8]
        
        # 确定显示标签
        display_label = label or task[:30] + ("..." if len(task) > 30 else "")
        
        # 构建原始目的地信息
        origin = {
            "channel": origin_channel,
            "chat_id": origin_chat_id,
        }
        
        # 创建后台任务
        bg_task = asyncio.create_task(
            self._run_subagent(task_id, task, display_label, origin)
        )
        
        # 添加到运行任务字典
        self._running_tasks[task_id] = bg_task
        
        # 注册完成回调：任务完成后自动从字典中移除
        bg_task.add_done_callback(lambda _: self._running_tasks.pop(task_id, None))
        
        # 记录日志
        logger.info(f"Spawned subagent [{task_id}]: {display_label}")
        
        # 返回启动消息
        return f"Subagent [{display_label}] started (id: {task_id}). I'll notify you when it completes."
    
    async def _run_subagent(
        self,
        task_id: str,
        task: str,
        label: str,
        origin: dict[str, str],
    ) -> None:
        """
        执行子代理的核心逻辑
        
        功能描述:
            子代理的主循环，处理任务并执行必要的工具调用。
        
        参数说明:
            task_id: str，任务的唯一标识
            task: str，需要完成的任务描述
            label: str，任务的易读标签
            origin: dict，包含原始目的地信息（channel 和 chat_id）
        
        处理流程:
            1. 构建子代理专用的工具集
            2. 构建子代理专用的系统提示词
            3. 执行 Agent 循环（最多 15 次迭代）
            4. 处理工具调用
            5. 公告结果回主 Agent
        
        工具集限制:
            - ReadFileTool: 读取文件
            - WriteFileTool: 写入文件
            - ListDirTool: 列出目录
            - ExecTool: 执行 Shell 命令
            - WebSearchTool: 网络搜索
            - WebFetchTool: 网页抓取
            - 无 message 工具（不能直接发送消息）
            - 无 spawn 工具（不能嵌套启动）
        
        注意:
            - 这是内部方法，通过 spawn() 间接调用
            - 完成后会自动调用 _announce_result() 公告结果
        """
        # 记录开始日志
        logger.info(f"Subagent [{task_id}] starting task: {label}")
        
        try:
            # ====================================================================
            # 1. 构建子代理工具集
            # ====================================================================
            tools = ToolRegistry()
            
            # 确定允许操作的目录
            allowed_dir = self.workspace if self.restrict_to_workspace else None
            
            # 注册文件操作工具
            tools.register(ReadFileTool(allowed_dir=allowed_dir))
            tools.register(WriteFileTool(allowed_dir=allowed_dir))
            tools.register(ListDirTool(allowed_dir=allowed_dir))
            
            # 注册 Shell 执行工具
            tools.register(ExecTool(
                working_dir=str(self.workspace),
                timeout=self.exec_config.timeout,
                restrict_to_workspace=self.restrict_to_workspace,
            ))
            
            # 注册网络工具
            tools.register(WebSearchTool(api_key=self.brave_api_key))
            tools.register(WebFetchTool())
            
            # ====================================================================
            # 2. 构建消息
            # ====================================================================
            system_prompt = self._build_subagent_prompt(task)
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task},
            ]
            
            # ====================================================================
            # 3. 执行 Agent 循环
            # ====================================================================
            max_iterations = 15  # 子代理的最大迭代次数
            iteration = 0
            final_result: str | None = None
            
            while iteration < max_iterations:
                iteration += 1
                
                # 调用 LLM
                response = await self.provider.chat(
                    messages=messages,
                    tools=tools.get_definitions(),
                    model=self.model,
                )
                
                # 如果有工具调用
                if response.has_tool_calls:
                    # 构建工具调用字典
                    tool_call_dicts = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in response.tool_calls
                    ]
                    
                    # 添加助手消息（包含工具调用）
                    messages.append({
                        "role": "assistant",
                        "content": response.content or "",
                        "tool_calls": tool_call_dicts,
                    })
                    
                    # 执行每个工具调用
                    for tool_call in response.tool_calls:
                        args_str = json.dumps(tool_call.arguments)
                        logger.debug(f"Subagent [{task_id}] executing: {tool_call.name} with arguments: {args_str}")
                        result = await tools.execute(tool_call.name, tool_call.arguments)
                        
                        # 添加工具结果
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.name,
                            "content": result,
                        })
                else:
                    # 没有工具调用，任务完成
                    final_result = response.content
                    break
            
            # 如果达到最大迭代次数
            if final_result is None:
                final_result = "Task completed but no final response was generated."
            
            # 记录完成日志
            logger.info(f"Subagent [{task_id}] completed successfully")
            
            # 公告结果回主 Agent
            await self._announce_result(task_id, label, task, final_result, origin, "ok")
            
        except Exception as e:
            # 发生错误
            error_msg = f"Error: {str(e)}"
            logger.error(f"Subagent [{task_id}] failed: {e}")
            await self._announce_result(task_id, label, task, error_msg, origin, "error")
    
    async def _announce_result(
        self,
        task_id: str,
        label: str,
        task: str,
        result: str,
        origin: dict[str, str],
        status: str,
    ) -> None:
        """
        将子代理结果公告回主 Agent
        
        功能描述:
            将子代理的执行结果通过消息总线注入回主 Agent，
            触发主 Agent 进行自然的用户通知。
        
        参数说明:
            task_id: str，任务的唯一标识
            label: str，任务的易读标签
            task: str，原始任务描述
            result: str，子代理的执行结果
            origin: dict，包含原始目的地信息
            status: str，执行状态（"ok" 或 "error"）
        
        处理流程:
            1. 根据状态生成状态描述
            2. 构建公告内容（包含任务和结果）
            3. 将内容封装为 InboundMessage（channel="system"）
            4. 发送到消息总线
        
        消息格式:
            [Subagent 'xxx' completed/failed]
            
            Task: xxx
            
            Result:
            xxx
            
            Summarize this naturally for the user...
        
        注意:
            - 使用 channel="system" 标识为系统消息
            - sender_id="subagent" 标识来源为子代理
            - chat_id 格式为 "channel:chat_id"
        """
        # 生成状态描述
        status_text = "completed successfully" if status == "ok" else "failed"
        
        # 构建公告内容
        announce_content = f"""[Subagent '{label}' {status_text}]

Task: {task}

Result:
{result}

Summarize this naturally for the user. Keep it brief (1-2 sentences). Do not mention technical details like "subagent" or task IDs."""
        
        # 注入为系统消息，触发主 Agent
        msg = InboundMessage(
            channel="system",
            sender_id="subagent",
            chat_id=f"{origin['channel']}:{origin['chat_id']}",
            content=announce_content,
        )
        
        # 发送到消息总线
        await self.bus.publish_inbound(msg)
        
        # 记录日志
        logger.debug(f"Subagent [{task_id}] announced result to {origin['channel']}:{origin['chat_id']}")
    
    def _build_subagent_prompt(self, task: str) -> str:
        """
        构建子代理专用的系统提示词
        
        功能描述:
            根据任务生成专注、简洁的系统提示词，
            让子代理专注于完成特定任务。
        
        参数说明:
            task: str，子代理需要完成的任务描述
        
        返回值:
            str，完整的系统提示词
        
        提示词结构:
            1. 角色定义：子代理身份
            2. 任务描述：具体需要完成的任务
            3. 规则：行为准则（专注、不主动发起对话等）
            4. 能力：可用的工具和能力
            5. 限制：不能做的事情
            6. 工作空间：文件操作路径
        
        使用示例:
            prompt = manager._build_subagent_prompt("搜索最新的 AI 新闻")
        """
        return f"""# Subagent

You are a subagent spawned by the main agent to complete a specific task.

## Your Task
{task}

## Rules
1. Stay focused - complete only the assigned task, nothing else
2. Your final response will be reported back to the main agent
3. Do not initiate conversations or take on side tasks
4. Be concise but informative in your findings

## What You Can Do
- Read and write files in the workspace
- Execute shell commands
- Search the web and fetch web pages
- Complete the task thoroughly

## What You Cannot Do
- Send messages directly to users (no message tool available)
- Spawn other subagents
- Access the main agent's conversation history

## Workspace
Your workspace is at: {self.workspace}

When you have completed the task, provide a clear summary of your findings or actions."""
    
    def get_running_count(self) -> int:
        """
        获取正在运行的子代理数量
        
        功能描述:
            返回当前正在后台运行的子代理任务数量。
        
        返回值:
            int，正在运行的子代理数量
        
        使用示例:
            count = manager.get_running_count()
            print(f"正在运行 {count} 个子代理")
        
        注意:
            - 这是同步方法，不需要 await
            - 返回的是_tasks字典的长度
        """
        return len(self._running_tasks)
