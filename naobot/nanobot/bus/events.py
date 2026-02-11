"""Event types for the message bus."""
# 消息总线的事件类型定义模块

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class InboundMessage:
    """Message received from a chat channel."""
    # 从聊天频道接收到的消息
    
    channel: str  # telegram, discord, slack, whatsapp
    sender_id: str  # User identifier
    # 用户标识符
    chat_id: str  # Chat/channel identifier
    # 聊天/频道标识符
    content: str  # Message text
    # 消息文本
    timestamp: datetime = field(default_factory=datetime.now)
    # 时间戳
    media: list[str] = field(default_factory=list)  # Media URLs
    # 媒体URL列表
    metadata: dict[str, Any] = field(default_factory=dict)  # Channel-specific data
    # 频道特定数据
    
    @property
    def session_key(self) -> str:
        """Unique key for session identification."""
        # 用于会话识别的唯一键
        return f"{self.channel}:{self.chat_id}"


@dataclass
class OutboundMessage:
    """Message to send to a chat channel."""
    # 发送到聊天频道的消息
    
    channel: str
    # 频道类型
    chat_id: str
    # 聊天ID
    content: str
    # 消息内容
    reply_to: str | None = None
    # 回复的消息ID
    media: list[str] = field(default_factory=list)
    # 媒体URL列表
    metadata: dict[str, Any] = field(default_factory=dict)
    # 元数据


