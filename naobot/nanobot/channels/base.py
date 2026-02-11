# -*- coding: utf-8 -*-
"""
================================================================================
Base Channel Interface - 基础频道接口模块
================================================================================

功能描述:
    定义所有聊天频道实现需要遵循的抽象基类。
    每个具体的频道（Telegram、Discord、QQ 等）都需要继承此类并实现抽象方法。

核心概念:
    1. Channel: 聊天平台适配器
    2. MessageBus: 消息总线
    3. InboundMessage: 入站消息
    4. OutboundMessage: 出站消息

主要组件:
    - BaseChannel: 抽象基类

子类实现要求:
    - start(): 启动频道并开始监听消息
    - stop(): 停止频道并清理资源
    - send(): 发送消息到平台
    - is_allowed(): 检查用户是否有权限

================================================================================
"""

from abc import ABC, abstractmethod
from typing import Any

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus


class BaseChannel(ABC):
    """
    ========================================================================
    BaseChannel - 聊天频道抽象基类
    ========================================================================
    
    所有聊天频道实现的基类。
    
    功能特点:
        1. 定义频道的通用接口
        2. 提供权限检查功能
        3. 提供消息处理功能
    
    子类需要实现的方法:
        - start(): 启动频道
        - stop(): 停止频道
        - send(): 发送消息
        - is_allowed(): 权限检查（可选重写）
    
    属性说明:
        - name: 频道名称
        - config: 频道配置
        - bus: 消息总线
        - _running: 运行状态
    
    ========================================================================
    """
    
    name: str = "base"
    """频道名称（子类应覆盖此值）"""
    
    def __init__(self, config: Any, bus: MessageBus):
        """
        初始化频道
        
        参数说明:
            config: Any，频道特定配置
            bus: MessageBus，消息总线实例
        """
        self.config = config
        self.bus = bus
        self._running = False
    
    @abstractmethod
    async def start(self) -> None:
        """
        启动频道并开始监听消息
        
        功能描述:
            连接到聊天平台并开始监听传入消息。
            这应该是一个长时间运行的异步任务。
        
        处理流程:
            1. 连接到聊天平台
            2. 监听传入消息
            3. 收到消息后调用 _handle_message() 转发到总线
        
        注意:
            - 这是抽象方法，子类必须实现
            - 应该设置 _running = True
        """
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """
        停止频道并清理资源
        
        功能描述:
            断开与聊天平台的连接并释放资源。
        
        注意:
            - 这是抽象方法，子类必须实现
            - 应该设置 _running = False
        """
        pass
    
    @abstractmethod
    async def send(self, msg: OutboundMessage) -> None:
        """
        通过此频道发送消息
        
        功能描述:
            将 OutboundMessage 发送到聊天平台。
        
        参数说明:
            msg: OutboundMessage，要发送的消息
        
        注意:
            - 这是抽象方法，子类必须实现
        """
        pass
    
    def is_allowed(self, sender_id: str) -> bool:
        """
        检查发送者是否被允许使用此机器人
        
        功能描述:
            根据配置中的 allow_from 列表检查权限。
        
        参数说明:
            sender_id: str，发送者的标识符
        
        返回值:
            bool，允许返回 True，否则返回 False
        
        权限检查逻辑:
            1. 如果没有配置 allow_from，允许所有人
            2. 如果 sender_id 在列表中，允许
            3. 如果 sender_id 包含 "|"（多值），检查每个部分
        """
        allow_list = getattr(self.config, "allow_from", [])
        
        # 如果没有允许列表，允许所有人
        if not allow_list:
            return True
        
        sender_str = str(sender_id)
        
        # 直接匹配
        if sender_str in allow_list:
            return True
        
        # 多值检查（sender_id 可能包含多个标识符）
        if "|" in sender_str:
            for part in sender_str.split("|"):
                if part and part in allow_list:
                    return True
        
        return False
    
    async def _handle_message(
        self,
        sender_id: str,
        chat_id: str,
        content: str,
        media: list[str] | None = None,
        metadata: dict[str, Any] | None = None
    ) -> None:
        """
        处理来自聊天平台的传入消息
        
        功能描述:
            检查权限并创建 InboundMessage 转发到消息总线。
        
        参数说明:
            sender_id: str，发送者标识符
            chat_id: str，聊天/频道标识符
            content: str，消息文本内容
            media: list[str] | None，媒体 URL 列表
            metadata: dict[str, Any] | None，频道特定元数据
        
        处理流程:
            1. 检查权限
            2. 如果被拒绝，记录警告日志并返回
            3. 创建 InboundMessage
            4. 发布到消息总线
        """
        # 权限检查
        if not self.is_allowed(sender_id):
            logger.warning(
                f"Access denied for sender {sender_id} on channel {self.name}. "
                f"Add them to allowFrom list in config to grant access."
            )
            return
        
        # 创建入站消息
        msg = InboundMessage(
            channel=self.name,
            sender_id=str(sender_id),
            chat_id=str(chat_id),
            content=content,
            media=media or [],
            metadata=metadata or {}
        )
        
        # 发布到消息总线
        await self.bus.publish_inbound(msg)
    
    @property
    def is_running(self) -> bool:
        """
        检查频道是否正在运行
        
        返回值:
            bool，运行状态
        """
        return self._running
