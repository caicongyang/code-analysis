"""Agent tools module."""
# 代理工具模块
# 提供代理系统使用的工具基类和工具注册表

from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.registry import ToolRegistry

__all__ = ["Tool", "ToolRegistry"]
