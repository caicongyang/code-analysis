# -*- coding: utf-8 -*-
"""
================================================================================
NanoBot Message Bus - 消息总线模块
================================================================================

功能描述:
    实现频道与 Agent 之间的解耦通信。采用异步消息队列模式，
    频道负责消息的收发，Agent 负责消息的处理。

主要组件:
    - MessageBus: 异步消息总线
    - InboundMessage: 入站消息（用户 → 频道 → 消息总线 → Agent）
    - OutboundMessage: 出站消息（Agent → 消息总线 → 频道 → 用户）

模块关系:
    channels/ → message_bus → agent/core → message_bus → channels/
    
    - channels: 各个平台的适配器（Telegram、Discord 等）
    - message_bus: 消息队列，连接频道和 Agent
    - agent/core: Agent 核心，处理消息

================================================================================
"""

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
