# -*- coding: utf-8 -*-
"""
================================================================================
Message Bus Events - 消息总线事件类型模块
================================================================================

功能描述:
    定义消息总线中使用的事件类型，包括入站消息和出站消息。
    这些数据类型用于在消息总线中传递消息。

主要组件:
    - InboundMessage: 从聊天频道接收的消息
    - OutboundMessage: 发送到聊天频道的消息

核心概念:
    1. Channel: 消息平台类型（telegram、discord、slack、whatsapp 等）
    2. Sender ID: 发送者的唯一标识
    3. Chat ID: 聊天会话的唯一标识
    4. Session Key: 用于识别会话的唯一键（格式: channel:chat_id）

================================================================================
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class InboundMessage:
    """
    ========================================================================
    InboundMessage - 入站消息类
    ========================================================================
    
    表示从聊天频道接收到的消息。
    
    属性说明:
        - channel: 消息来源的平台（telegram、discord、qq 等）
        - sender_id: 发送消息的用户唯一标识
        - chat_id: 聊天会话的唯一标识
        - content: 消息的文本内容
        - timestamp: 消息接收时间
        - media: 消息中的媒体附件 URL 列表
        - metadata: 平台特定的其他数据
    
    使用场景:
        - 频道插件接收用户消息后创建
        - 传递给 AgentLoop.process_message() 处理
    
    ========================================================================
    """
    
    channel: str
    """消息来源频道（如 telegram、discord、qq）"""
    
    sender_id: str
    """发送者用户标识符"""
    
    chat_id: str
    """聊天会话标识符"""
    
    content: str
    """消息文本内容"""
    
    timestamp: datetime = field(default_factory=datetime.now)
    """消息接收时间戳"""
    
    media: list[str] = field(default_factory=list)
    """媒体附件 URL 列表（图片、音频等）"""
    
    metadata: dict[str, Any] = field(default_factory=dict)
    """频道特定数据（如 Telegram 的 message_id）"""

    @property
    def session_key(self) -> str:
        """
        获取会话唯一键
        
        功能描述:
            生成用于识别会话的唯一键。
        
        返回值:
            str，格式为 "channel:chat_id"
        
        使用示例:
            session_key = "telegram:123456789"
        """
        return f"{self.channel}:{self.chat_id}"


@dataclass
class OutboundMessage:
    """
    ========================================================================
    OutboundMessage - 出站消息类
    ========================================================================
    
    表示要发送到聊天频道的消息。
    
    属性说明:
        - channel: 目标平台
        - chat_id: 目标聊天会话
        - content: 消息内容
        - reply_to: 要回复的消息 ID（可选）
        - media: 媒体附件列表（可选）
        - metadata: 其他元数据（可选）
    
    使用场景:
        - Agent 生成响应后创建
        - 传递给 MessageBus.publish_outbound() 发送
    
    ========================================================================
    """
    
    channel: str
    """目标频道"""
    
    chat_id: str
    """目标聊天会话 ID"""
    
    content: str
    """消息内容"""
    
    reply_to: str | None = None
    """回复的消息 ID"""
    
    media: list[str] = field(default_factory=list)
    """媒体附件 URL 列表"""
    
    metadata: dict[str, Any] = field(default_factory=dict)
    """附加元数据"""
