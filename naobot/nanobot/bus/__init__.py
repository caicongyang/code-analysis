"""Message bus module for decoupled channel-agent communication."""
# 消息总线模块
# 用于实现频道与代理之间的解耦通信

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
