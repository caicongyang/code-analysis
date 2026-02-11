# -*- coding: utf-8 -*-
"""
================================================================================
Cron Tool - 定时任务工具模块
================================================================================

功能描述:
    提供定时任务和提醒的调度功能。Agent 可以创建一次性提醒或周期性任务，
    在指定时间发送消息通知用户。

核心概念:
    1. Cron 表达式: 标准的时间调度格式（如 "0 9 * * *" 表示每天 9 点）
    2. 周期性任务: 每隔固定时间执行（如每 60 秒一次）
    3. 一次性提醒: 在指定时间发送一次消息

主要组件:
    - CronTool: 定时任务工具类

支持的操作:
    - add: 添加新的定时任务或提醒
    - list: 列出所有已调度的任务
    - remove: 删除指定的定时任务

================================================================================
"""

from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.cron.service import CronService
from nanobot.cron.types import CronSchedule


class CronTool(Tool):
    """
    ========================================================================
    CronTool - 定时任务工具类
    ========================================================================
    
    负责管理定时任务和提醒。
    
    功能特点:
        1. 支持 cron 表达式调度
        2. 支持固定间隔周期任务
        3. 自动使用当前会话上下文发送消息
        4. 任务持久化存储
    
    Cron 表达式格式:
        ┌───────────── 分钟 (0 - 59)
        │ ┌───────────── 小时 (0 - 23)
        │ │ ┌───────────── 月份中的某天 (1 - 31)
        │ │ │ ┌───────────── 月份 (1 - 12)
        │ │ │ │ ┌───────────── 星期几 (0 - 6) (星期天=0)
        │ │ │ │ │
        * * * * *
    
    示例:
        "0 9 * * *"     → 每天 9:00
        "30 8 * * 1-5"  → 工作日 8:30
        "0 */2 * * *"   → 每隔 2 小时
    
    ========================================================================
    """
    
    def __init__(self, cron_service: CronService):
        """
        初始化定时任务工具
        
        参数说明:
            cron_service: CronService，定时任务服务实例
        """
        self._cron = cron_service
        self._channel = ""
        self._chat_id = ""
    
    def set_context(self, channel: str, chat_id: str) -> None:
        """
        设置当前会话上下文
        
        功能描述:
            设置定时任务消息应该发送到的目标。
        
        参数说明:
            channel: str，频道标识
            chat_id: str，聊天会话 ID
        """
        self._channel = channel
        self._chat_id = chat_id
    
    @property
    def name(self) -> str:
        """
        获取工具名称
        
        返回值:
            str，工具名称为 "cron"
        """
        return "cron"
    
    @property
    def description(self) -> str:
        """
        获取工具描述
        
        返回值:
            str，工具描述信息
        """
        return "Schedule reminders and recurring tasks. Actions: add, list, remove."
    
    @property
    def parameters(self) -> dict[str, Any]:
        """
        获取工具参数定义
        
        返回值:
            dict，OpenAI 格式的工具参数定义
        
        参数说明:
            - action: 要执行的操作（add/list/remove）
            - message: 提醒消息（add 操作需要）
            - every_seconds: 间隔秒数（周期性任务）
            - cron_expr: cron 表达式（定时任务）
            - job_id: 任务 ID（remove 操作需要）
        """
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "list", "remove"],
                    "description": "Action to perform"
                },
                "message": {
                    "type": "string",
                    "description": "Reminder message (for add)"
                },
                "every_seconds": {
                    "type": "integer",
                    "description": "Interval in seconds (for recurring tasks)"
                },
                "cron_expr": {
                    "type": "string",
                    "description": "Cron expression like '0 9 * * *' (for scheduled tasks)"
                },
                "job_id": {
                    "type": "string",
                    "description": "Job ID (for remove)"
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
        """
        执行定时任务操作
        
        功能描述:
            根据指定的 action 执行相应的操作。
        
        参数说明:
            action: str，操作类型（add/list/remove）
            message: str，提醒消息
            every_seconds: int | None，间隔秒数
            cron_expr: str | None，cron 表达式
            job_id: str | None，任务 ID
            **kwargs: 额外的关键字参数
        
        返回值:
            str，操作结果
        """
        if action == "add":
            return self._add_job(message, every_seconds, cron_expr)
        elif action == "list":
            return self._list_jobs()
        elif action == "remove":
            return self._remove_job(job_id)
        return f"Unknown action: {action}"
    
    def _add_job(self, message: str, every_seconds: int | None, cron_expr: str | None) -> str:
        """
        添加定时任务
        
        参数说明:
            message: str，提醒消息
            every_seconds: int | None，间隔秒数
            cron_expr: str | None，cron 表达式
        
        返回值:
            str，操作结果
        """
        # 验证参数
        if not message:
            return "Error: message is required for add"
        if not self._channel or not self._chat_id:
            return "Error: no session context (channel/chat_id)"
        
        # 构建调度计划
        if every_seconds:
            # 周期性任务
            schedule = CronSchedule(kind="every", every_ms=every_seconds * 1000)
        elif cron_expr:
            # Cron 定时任务
            schedule = CronSchedule(kind="cron", expr=cron_expr)
        else:
            return "Error: either every_seconds or cron_expr is required"
        
        # 添加任务
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
        """
        列出所有定时任务
        
        返回值:
            str，任务列表
        """
        jobs = self._cron.list_jobs()
        if not jobs:
            return "No scheduled jobs."
        
        lines = [f"- {j.name} (id: {j.id}, {j.schedule.kind})" for j in jobs]
        return "Scheduled jobs:\n" + "\n".join(lines)
    
    def _remove_job(self, job_id: str | None) -> str:
        """
        删除定时任务
        
        参数说明:
            job_id: str | None，要删除的任务 ID
        
        返回值:
            str，操作结果
        """
        if not job_id:
            return "Error: job_id is required for remove"
        
        if self._cron.remove_job(job_id):
            return f"Removed job {job_id}"
        return f"Job {job_id} not found"
