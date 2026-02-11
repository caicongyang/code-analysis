# -*- coding: utf-8 -*-
"""
================================================================================
Spawn Tool - Spawn 工具模块
================================================================================

功能描述:
    提供创建后台运行子代理的功能。子代理可以独立处理复杂或耗时的任务，
    完成后再将结果报告给主 Agent。

核心概念:
    1.  Spawn: 启动一个新的子代理实例
    2. Subagent: 轻量级 Agent，有独立的上下文
    3. Announce: 子代理完成后将结果报告给主 Agent

主要组件:
    - SpawnTool: 子代理启动工具类

使用场景:
    - 执行耗时的搜索任务
    - 并行处理多个独立任务
    - 处理需要多步骤的复杂任务

与 SubagentManager 的关系:
    - SpawnTool 是前端接口
    - SubagentManager 是后端实现
    - SpawnTool 将任务委托给 SubagentManager 执行

================================================================================
"""

from typing import Any, TYPE_CHECKING

from nanobot.agent.tools.base import Tool

if TYPE_CHECKING:
    from nanobot.agent.subagent import SubagentManager


class SpawnTool(Tool):
    """
    ========================================================================
    SpawnTool - 子代理启动工具类
    ========================================================================
    
    负责启动后台子代理处理任务。
    
    功能特点:
        1. 异步启动：不阻塞主 Agent
        2. 结果回传：完成后自动通知主 Agent
        3. 上下文管理：继承当前的 channel 和 chat_id
    
    工作流程:
        1. Agent 调用 spawn 工具
        2. SpawnTool 委托 SubagentManager 创建子代理
        3. 子代理在后台运行
        4. 完成后，子代理将结果注入消息总线
        5. 主 Agent 收到结果，通知用户
    
    ========================================================================
    """
    
    def __init__(self, manager: "SubagentManager"):
        """
        初始化 Spawn 工具
        
        参数说明:
            manager: SubagentManager，子代理管理器实例
        """
        self._manager = manager
        self._origin_channel = "cli"
        self._origin_chat_id = "direct"
    
    def set_context(self, channel: str, chat_id: str) -> None:
        """
        设置原始上下文
        
        功能描述:
            设置子代理完成任务后结果应该发送到的目标。
            通常在处理用户消息时自动调用。
        
        参数说明:
            channel: str，频道标识
            chat_id: str，聊天会话 ID
        """
        self._origin_channel = channel
        self._origin_chat_id = chat_id
    
    @property
    def name(self) -> str:
        """
        获取工具名称
        
        返回值:
            str，工具名称为 "spawn"
        """
        return "spawn"
    
    @property
    def description(self) -> str:
        """
        获取工具描述
        
        返回值:
            str，工具描述信息
        """
        return (
            "Spawn a subagent to handle a task in the background. "
            "Use this for complex or time-consuming tasks that can run independently. "
            "The subagent will complete the task and report back when done."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        """
        获取工具参数定义
        
        返回值:
            dict，OpenAI 格式的工具参数定义
        
        参数说明:
            - task: 要执行的任务描述（必填）
            - label: 任务的可读标签（可选）
        """
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The task for the subagent to complete",
                },
                "label": {
                    "type": "string",
                    "description": "Optional short label for the task (for display)",
                },
            },
            "required": ["task"],
        }
    
    async def execute(self, task: str, label: str | None = None, **kwargs: Any) -> str:
        """
        启动子代理
        
        功能描述:
            创建一个新的子代理来处理指定任务。
        
        参数说明:
            task: str，子代理需要完成的任务描述
            label: str | None，任务的可读标签
            **kwargs: 额外的关键字参数（忽略）
        
        返回值:
            str，启动状态消息
        
        使用示例:
            # 启动子代理执行搜索
            result = await spawn_tool.execute(
                task="搜索最新的 Python 3.12 新特性",
                label="Python 3.12 新特性"
            )
        """
        return await self._manager.spawn(
            task=task,
            label=label,
            origin_channel=self._origin_channel,
            origin_chat_id=self._origin_chat_id,
        )
