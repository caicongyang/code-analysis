"""Cron tool for scheduling reminders and tasks."""
# Cron工具模块
# 提供定时任务和提醒的调度功能

from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.cron.service import CronService
from nanobot.cron.types import CronSchedule


class CronTool(Tool):
    """Tool to schedule reminders and recurring tasks."""
    # 用于调度提醒和周期性任务的工具
    
    def __init__(self, cron_service: CronService):
        self._cron = cron_service
        # Cron服务实例
        self._channel = ""
        # 默认频道
        self._chat_id = ""
        # 默认聊天ID
    
    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the current session context for delivery."""
        # 设置当前会话的上下文用于消息投递
        self._channel = channel
        self._chat_id = chat_id
    
    @property
    def name(self) -> str:
        return "cron"
    
    @property
    def description(self) -> str:
        return "Schedule reminders and recurring tasks. Actions: add, list, remove."
        # 调度提醒和周期性任务，支持操作：add(添加), list(列表), remove(移除)
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "list", "remove"],
                    "description": "Action to perform"
                    # 要执行的操作
                },
                "message": {
                    "type": "string",
                    "description": "Reminder message (for add)"
                    # 提醒消息（用于add操作）
                },
                "every_seconds": {
                    "type": "integer",
                    "description": "Interval in seconds (for recurring tasks)"
                    # 间隔秒数（用于周期性任务）
                },
                "cron_expr": {
                    "type": "string",
                    "description": "Cron expression like '0 9 * * *' (for scheduled tasks)"
                    # Cron表达式如'0 9 * * *'（用于定时任务）
                },
                "job_id": {
                    "type": "string",
                    "description": "Job ID (for remove)"
                    # 任务ID（用于remove操作）
                }
            },
            "required": ["action"]
        }
    
    async def execute(
        self,
        action: str,
        message: str = "",
        every_seconds: int | None = None,
        cron_expr: str | None = None,
        job_id: str | None = None,
        **kwargs: Any
    ) -> str:
        if action == "add":
            return self._add_job(message, every_seconds, cron_expr)
        elif action == "list":
            return self._list_jobs()
        elif action == "remove":
            return self._remove_job(job_id)
        return f"Unknown action: {action}"
    
    def _add_job(self, message: str, every_seconds: int | None, cron_expr: str | None) -> str:
        if not message:
            return "Error: message is required for add"
        if not self._channel or not self._chat_id:
            return "Error: no session context (channel/chat_id)"
        
        # Build schedule
        # 构建调度计划
        if every_seconds:
            schedule = CronSchedule(kind="every", every_ms=every_seconds * 1000)
        elif cron_expr:
            schedule = CronSchedule(kind="cron", expr=cron_expr)
        else:
            return "Error: either every_seconds or cron_expr is required"
        
        job = self._cron.add_job(
            name=message[:30],
            schedule=schedule,
            message=message,
            deliver=True,
            channel=self._channel,
            to=self._chat_id,
        )
        return f"Created job '{job.name}' (id: {job.id})"
    
    def _list_jobs(self) -> str:
        jobs = self._cron.list_jobs()
        if not jobs:
            return "No scheduled jobs."
        lines = [f"- {j.name} (id: {j.id}, {j.schedule.kind})" for j in jobs]
        return "Scheduled jobs:\n" + "\n".join(lines)
    
    def _remove_job(self, job_id: str | None) -> str:
        if not job_id:
            return "Error: job_id is required for remove"
        if self._cron.remove_job(job_id):
            return f"Removed job {job_id}"
        return f"Job {job_id} not found"
