"""Async message queue for decoupled channel-agent communication."""
# 异步消息队列模块
# 用于实现聊天频道与代理核心之间的解耦通信

import asyncio
from typing import Callable, Awaitable

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage


class MessageBus:
    """
    Async message bus that decouples chat channels from the agent core.
    # 异步消息总线，将聊天频道与代理核心解耦
    
    Channels push messages to the inbound queue, and the agent processes
    them and pushes responses to the outbound queue.
    # 频道将消息推送到入站队列，代理处理后把响应推送到出站队列
    """
    
    def __init__(self):
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        # 入站消息队列
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()
        # 出站消息队列
        self._outbound_subscribers: dict[str, list[Callable[[OutboundMessage], Awaitable[None]]]] = {}
        # 出站消息订阅者字典
        self._running = False
        # 运行状态标志
    
    async def publish_inbound(self, msg: InboundMessage) -> None:
        """Publish a message from a channel to the agent."""
        # 将频道的消息发布给代理
        await self.inbound.put(msg)
    
    async def consume_inbound(self) -> InboundMessage:
        """Consume the next inbound message (blocks until available)."""
        # 消费下一条入站消息（阻塞直到可用）
        return await self.inbound.get()
    
    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """Publish a response from the agent to channels."""
        # 将代理的响应发布到频道
        await self.outbound.put(msg)
    
    async def consume_outbound(self) -> OutboundMessage:
        """Consume the next outbound message (blocks until available)."""
        # 消费下一条出站消息（阻塞直到可用）
        return await self.outbound.get()
    
    def subscribe_outbound(
        self, 
        channel: str, 
        callback: Callable[[OutboundMessage], Awaitable[None]]
    ) -> None:
        """Subscribe to outbound messages for a specific channel."""
        # 订阅特定频道的出站消息
        if channel not in self._outbound_subscribers:
            self._outbound_subscribers[channel] = []
        self._outbound_subscribers[channel].append(callback)
    
    async def dispatch_outbound(self) -> None:
        """
        Dispatch outbound messages to subscribed channels.
        Run this as a background task.
        # 将出站消息分发到订阅的频道
        # 以后台任务方式运行
        """
        self._running = True
        while self._running:
            try:
                msg = await asyncio.wait_for(self.outbound.get(), timeout=1.0)
                subscribers = self._outbound_subscribers.get(msg.channel, [])
                for callback in subscribers:
                    try:
                        await callback(msg)
                    except Exception as e:
                        logger.error(f"Error dispatching to {msg.channel}: {e}")
            except asyncio.TimeoutError:
                continue
    
    def stop(self) -> None:
        """Stop the dispatcher loop."""
        # 停止分发器循环
        self._running = False
    
    @property
    def inbound_size(self) -> int:
        """Number of pending inbound messages."""
        # 待处理的入站消息数量
        return self.inbound.qsize()
    
    @property
    def outbound_size(self) -> int:
        """Number of pending outbound messages."""
        # 待处理的出站消息数量
        return self.outbound.qsize()
