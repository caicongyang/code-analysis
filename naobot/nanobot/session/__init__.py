# -*- coding: utf-8 -*-
"""
================================================================================
NanoBot Session - 会话管理模块
================================================================================

功能描述:
    负责对话会话的管理，包括会话的创建、保存、加载和删除。
    对话历史用于为 LLM 提供上下文。

主要组件:
    - Session: 单个对话会话
    - SessionManager: 会话管理器

会话生命周期:
    1. 用户发送消息
    2. SessionManager.get_or_create() 获取/创建会话
    3. Session.add_message() 添加用户消息
    4. Agent 处理消息
    5. Session.add_message() 添加助手响应
    6. SessionManager.save() 保存会话

================================================================================
"""

from nanobot.session.manager import SessionManager, Session

__all__ = ["SessionManager", "Session"]
