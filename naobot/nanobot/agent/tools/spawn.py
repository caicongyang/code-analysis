"""Spawn tool for creating background subagents."""
# Spawn工具模块
# 用于创建后台运行的子代理任务

from typing import Any, TYPE_CHECKING

from nanobot.agent.tools.base import Tool

if TYPE_CHECKING:
    from nanobot.agent.subagent import SubagentManager


class SpawnTool(Tool):
    """
    Tool to spawn a subagent for background task execution.
    # 用于在后台任务执行的子代理生成工具
    
    The subagent runs asynchronously and announces its result back
    to the main agent when complete.
    # 子代理异步运行，完成后将结果报告给主代理
    """
    
    def __init__(self, manager: "SubagentManager"):
        self._manager = manager
        # 子代理管理器
        self._origin_channel = "cli"
        # 原始频道
        self._origin_chat_id = "direct"
        # 原始聊天ID
    
    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the origin context for subagent announcements."""
        # 设置子代理公告的原始上下文
        self._origin_channel = channel
        self._origin_chat_id = chat_id
    
    @property
    def name(self) -> str:
        return "spawn"
    
    @property
    def description(self) -> str:
        return (
            "Spawn a subagent to handle a task in the background. "
            "Use this for complex or time-consuming tasks that can run independently. "
            "The subagent will complete the task and report back when done."
        )
        # 生成一个子代理来处理后台任务
        # 适用于可以独立运行的复杂或耗时的任务
        # 子代理完成任务后会报告结果
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The task for the subagent to complete",
                    # 子代理要完成的任务
                },
                "label": {
                    "type": "string",
                    "description": "Optional short label for the task (for display)",
                    # 任务的可选简短标签（用于显示）
                },
            },
            "required": ["task"],
        }
    
    async def execute(self, task: str, label: str | None = None, **kwargs: Any) -> str:
        """Spawn a subagent to execute the given task."""
        # 生成一个子代理来执行给定任务
        return await self._manager.spawn(
            task=task,
            label=label,
            origin_channel=self._origin_channel,
            origin_chat_id=self._origin_chat_id,
        )
