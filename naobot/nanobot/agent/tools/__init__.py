# -*- coding: utf-8 -*-
"""
================================================================================
NanoBot Agent Tools - Agent 工具模块
================================================================================

功能描述:
    聚合所有 Agent 可用的工具组件，包括工具基类和工具注册表。

主要组件:
    - Tool: 所有工具的基类，定义工具的通用接口
    - ToolRegistry: 工具注册表，管理所有可用工具

工具分类:
    1. 文件操作工具 (filesystem.py):
       - ReadFileTool: 读取文件
       - WriteFileTool: 写入文件
       - EditFileTool: 编辑文件
       - ListDirTool: 列出目录
    
    2. 系统工具 (shell.py):
       - ExecTool: 执行 Shell 命令
    
    3. 网络工具 (web.py):
       - WebSearchTool: 网页搜索
       - WebFetchTool: 网页抓取
    
    4. 消息工具 (message.py):
       - MessageTool: 发送消息
    
    5. 任务工具 (spawn.py):
       - SpawnTool: 启动子代理
    
    6. 调度工具 (cron.py):
       - CronTool: 管理定时任务

================================================================================
"""

from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.registry import ToolRegistry

__all__ = ["Tool", "ToolRegistry"]
