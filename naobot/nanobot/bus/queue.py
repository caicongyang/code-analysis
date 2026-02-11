# -*- coding: utf-8 -*-
"""
================================================================================
Message Bus Queue - 消息总线队列模块
================================================================================

功能描述:
    实现异步消息队列，实现聊天频道与 Agent 核心之间的解耦通信。
    采用生产者-消费者模式，频道生产消息，Agent 消费并处理。

核心概念:
    1. 入站队列 (Inbound Queue): 存储从频道接收的消息
    2. 出站队列 (Outbound Queue): 存储要发送到频道的响应
    3. 订阅机制 (Subscription): 频道订阅出站消息并转发给用户

消息流:
    用户 → 频道 → 入站队列 → AgentLoop → 出站队列 → 频道 → 用户

主要组件:
    - MessageBus: 异步消息总线类

================================================================================
"""

import asyncio
from typing import Callable, Awaitable

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage


class MessageBus:
    """
    ========================================================================
    MessageBus - 异步消息总线类
    ========================================================================
    
    实现聊天频道与 Agent 核心之间的解耦通信。
    
    功能特点:
        1. 异步队列：使用 asyncio.Queue 实现异步消息传递
        2. 解耦设计：频道和 Agent 不直接依赖对方
        3. 订阅机制：支持多个频道订阅出站消息
        4. 超时控制：dispatch_outbound 使用超时避免阻塞
    
    消息流:
        入站流程:
            1. 频道接收到用户消息
            2. 调用 publish_inbound() 放入队列
            3. AgentLoop.consume_inbound() 获取并处理
        
        出站流程:
            1. AgentLoop 处理完消息
            2. 调用 publish_outbound() 放入队列
            3. dispatch_outbound() 分发给订阅的频道
            4. 频道调用回调函数发送给用户
    
    ========================================================================
    """
    
    def __init__(self):
        """
        初始化消息总线
        
        初始化组件:
            - inbound: 入站消息队列
            - outbound: 出站消息队列
            - _outbound_subscribers: 出站消息订阅者字典
            - _running: 运行状态标志
        """
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        """入站消息队列，存储从频道接收的消息"""
        
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()
        """出站消息队列，存储要发送到频道的响应"""
        
        self._outbound_subscribers: dict[str, list[Callable[[OutboundMessage], Awaitable[None]]]] = {}
        """出站消息订阅者字典，key 为频道名，value 为回调函数列表"""
        
        self._running = False
        """运行状态标志，控制 dispatch_outbound 循环"""
    
    async def publish_inbound(self, msg: InboundMessage) -> None:
        """
        发布入站消息
        
        功能描述:
            将从频道接收的消息放入入站队列。
        
        参数说明:
            msg: InboundMessage，要发布的入站消息
        
        使用场景:
            - Telegram 插件收到用户消息后调用
            - Discord 插件收到用户消息后调用
        """
        await self.inbound.put(msg)
    
    async def consume_inbound(self) -> InboundMessage:
        """
        消费入站消息
        
        功能描述:
            从入站队列获取下一条消息（阻塞直到可用）。
        
        返回值:
            InboundMessage，下一条入站消息
        
        使用场景:
            - AgentLoop.run() 循环中调用
        """
        return await self.inbound.get()
    
    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """
        发布出站消息
        
        功能描述:
            将 Agent 的响应放入出站队列。
        
        参数说明:
            msg: OutboundMessage，要发布的出站消息
        
        使用场景:
            - AgentLoop 生成响应后调用
        """
        await self.outbound.put(msg)
    
    async def consume_outbound(self) -> OutboundMessage:
        """
        消费出站消息
        
        功能描述:
            从出站队列获取下一条消息（阻塞直到可用）。
        
        返回值:
            OutboundMessage，下一条出站消息
        
        注意:
            - 通常不直接使用，而是通过订阅机制
        """
        return await self.outbound.get()
    
    def subscribe_outbound(
        self,
        channel: str,
        callback: Callable[[OutboundMessage], Awaitable[None]]
    ) -> None:
        """
        订阅出站消息
        
        功能描述:
            注册频道对出站消息的订阅。
        
        参数说明:
            channel: str，要订阅的频道名称
            callback: 异步回调函数，接收 OutboundMessage 并发送给用户
        
        使用场景:
            - 频道插件启动时注册
            - Telegram 插件注册 telegram_channel
            - Discord 插件注册 discord_channel
        
        注意:
            - 同一个频道可以注册多个回调
        """
        if channel not in self._outbound_subscribers:
            self._outbound_subscribers[channel] = []
        self._outbound_subscribers[channel].append(callback)
    
    async def dispatch_outbound(self) -> None:
        """
        分发出站消息
        
        功能描述:
            循环从出站队列获取消息，分发给订阅的频道。
            通常作为后台任务运行。
        
        处理流程:
            1. 从队列获取出站消息（超时 1 秒）
            2. 获取消息对应频道的订阅者
            3. 依次调用回调函数
            4. 处理回调中的异常
            5. 超时后继续循环
        
        使用示例:
            # 作为后台任务启动
            asyncio.create_task(message_bus.dispatch_outbound())
        """
        self._running = True
        
        while self._running:
            try:
                # 获取出站消息（超时 1 秒）
                msg = await asyncio.wait_for(self.outbound.get(), timeout=1.0)
                
                # 获取订阅者
                subscribers = self._outbound_subscribers.get(msg.channel, [])
                
                # 分发给所有订阅者
                for callback in subscribers:
                    try:
                        await callback(msg)
                    except Exception as e:
                        logger.error(f"Error dispatching to {msg.channel}: {e}")
                        
            except asyncio.TimeoutError:
                # 超时是预期行为，继续循环
                continue
    
    def stop(self) -> None:
        """
        停止分发器
        
        功能描述:
            设置运行标志为 False，停止 dispatch_outbound 循环。
        """
        self._running = False
    
    @property
    def inbound_size(self) -> int:
        """
        获取入站队列待处理消息数
        
        返回值:
            int，队列中的消息数量
        """
        return self.inbound.qsize()
    
    @property
    def outbound_size(self) -> int:
        """
        获取出站队列待处理消息数
        
        返回值:
            int，队列中的消息数量
        """
        return self.outbound.qsize()
