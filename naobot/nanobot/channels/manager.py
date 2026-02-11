# -*- coding: utf-8 -*-
"""
================================================================================
Channel Manager - 频道管理器模块
================================================================================

功能描述:
    管理和协调所有聊天频道，负责频道的初始化、启动、停止和消息路由。

核心功能:
    1. 频道初始化：根据配置初始化启用的频道
    2. 启动管理：启动/停止所有频道
    3. 消息路由：将出站消息分发到对应频道

支持的频道:
    - Telegram
    - WhatsApp
    - Discord
    - Feishu (飞书)
    - Mochat
    - DingTalk (钉钉)
    - Email
    - Slack
    - QQ

消息流:
    Agent Loop → MessageBus → ChannelManager → Channel → 用户

================================================================================
"""

from __future__ import annotations

import asyncio
from typing import Any, TYPE_CHECKING

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import Config

if TYPE_CHECKING:
    from nanobot.session.manager import SessionManager


class ChannelManager:
    """
    ========================================================================
    ChannelManager - 频道管理器类
    ========================================================================
    
    负责管理和协调所有聊天频道。
    
    功能特点:
        1. 动态初始化：根据配置启用/禁用频道
        2. 统一管理：集中启动、停止所有频道
        3. 消息路由：自动将消息分发到对应频道
    
    生命周期:
        1. 初始化：根据配置创建频道实例
        2. start_all(): 启动所有频道
        3. 运行时：频道独立监听消息
        4. stop_all(): 停止所有频道
    
    ========================================================================
    """
    
    def __init__(
        self,
        config: Config,
        bus: MessageBus,
        session_manager: "SessionManager | None" = None
    ):
        """
        初始化频道管理器
        
        参数说明:
            config: Config，配置对象
            bus: MessageBus，消息总线
            session_manager: SessionManager | None，会话管理器
        """
        self.config = config
        self.bus = bus
        self.session_manager = session_manager
        self.channels: dict[str, BaseChannel] = {}
        self._dispatch_task: asyncio.Task | None = None
        
        # 初始化频道
        self._init_channels()
    
    def _init_channels(self) -> None:
        """
        根据配置初始化频道
        
        功能描述:
            遍历配置中的频道设置，初始化所有启用的频道。
        
        处理流程:
            1. 检查每个频道的 enabled 设置
            2. 尝试导入频道类
            3. 创建频道实例并添加到字典
            4. 如果导入失败，记录警告日志
        """
        # ====================================================================
        # Telegram 频道
        # ====================================================================
        if self.config.channels.telegram.enabled:
            try:
                from nanobot.channels.telegram import TelegramChannel
                self.channels["telegram"] = TelegramChannel(
                    self.config.channels.telegram,
                    self.bus,
                    groq_api_key=self.config.providers.groq.api_key,
                    session_manager=self.session_manager,
                )
                logger.info("Telegram channel enabled")
            except ImportError as e:
                logger.warning(f"Telegram channel not available: {e}")
        
        # ====================================================================
        # WhatsApp 频道
        # ====================================================================
        if self.config.channels.whatsapp.enabled:
            try:
                from nanobot.channels.whatsapp import WhatsAppChannel
                self.channels["whatsapp"] = WhatsAppChannel(
                    self.config.channels.whatsapp, self.bus
                )
                logger.info("WhatsApp channel enabled")
            except ImportError as e:
                logger.warning(f"WhatsApp channel not available: {e}")

        # ====================================================================
        # Discord 频道
        # ====================================================================
        if self.config.channels.discord.enabled:
            try:
                from nanobot.channels.discord import DiscordChannel
                self.channels["discord"] = DiscordChannel(
                    self.config.channels.discord, self.bus
                )
                logger.info("Discord channel enabled")
            except ImportError as e:
                logger.warning(f"Discord channel not available: {e}")
        
        # ====================================================================
        # Feishu (飞书) 频道
        # ====================================================================
        if self.config.channels.feishu.enabled:
            try:
                from nanobot.channels.feishu import FeishuChannel
                self.channels["feishu"] = FeishuChannel(
                    self.config.channels.feishu, self.bus
                )
                logger.info("Feishu channel enabled")
            except ImportError as e:
                logger.warning(f"Feishu channel not available: {e}")

        # ====================================================================
        # Mochat 频道
        # ====================================================================
        if self.config.channels.mochat.enabled:
            try:
                from nanobot.channels.mochat import MochatChannel
                self.channels["mochat"] = MochatChannel(
                    self.config.channels.mochat, self.bus
                )
                logger.info("Mochat channel enabled")
            except ImportError as e:
                logger.warning(f"Mochat channel not available: {e}")

        # ====================================================================
        # DingTalk (钉钉) 频道
        # ====================================================================
        if self.config.channels.dingtalk.enabled:
            try:
                from nanobot.channels.dingtalk import DingTalkChannel
                self.channels["dingtalk"] = DingTalkChannel(
                    self.config.channels.dingtalk, self.bus
                )
                logger.info("DingTalk channel enabled")
            except ImportError as e:
                logger.warning(f"DingTalk channel not available: {e}")

        # ====================================================================
        # Email 频道
        # ====================================================================
        if self.config.channels.email.enabled:
            try:
                from nanobot.channels.email import EmailChannel
                self.channels["email"] = EmailChannel(
                    self.config.channels.email, self.bus
                )
                logger.info("Email channel enabled")
            except ImportError as e:
                logger.warning(f"Email channel not available: {e}")

        # ====================================================================
        # Slack 频道
        # ====================================================================
        if self.config.channels.slack.enabled:
            try:
                from nanobot.channels.slack import SlackChannel
                self.channels["slack"] = SlackChannel(
                    self.config.channels.slack, self.bus
                )
                logger.info("Slack channel enabled")
            except ImportError as e:
                logger.warning(f"Slack channel not available: {e}")

        # ====================================================================
        # QQ 频道
        # ====================================================================
        if self.config.channels.qq.enabled:
            try:
                from nanobot.channels.qq import QQChannel
                self.channels["qq"] = QQChannel(
                    self.config.channels.qq,
                    self.bus,
                )
                logger.info("QQ channel enabled")
            except ImportError as e:
                logger.warning(f"QQ channel not available: {e}")
    
    async def _start_channel(self, name: str, channel: BaseChannel) -> None:
        """
        启动单个频道
        
        功能描述:
            启动频道并处理可能的异常。
        
        参数说明:
            name: str，频道名称
            channel: BaseChannel，频道实例
        """
        try:
            await channel.start()
        except Exception as e:
            logger.error(f"Failed to start channel {name}: {e}")

    async def start_all(self) -> None:
        """
        启动所有频道和出站分发器
        
        功能描述:
            启动所有已启用的频道和消息分发器。
        
        处理流程:
            1. 如果没有启用的频道，记录警告
            2. 启动出站消息分发器
            3. 并发启动所有频道
            4. 等待所有频道运行
        """
        if not self.channels:
            logger.warning("No channels enabled")
            return
        
        # 启动出站分发器
        self._dispatch_task = asyncio.create_task(self._dispatch_outbound())
        
        # 启动所有频道
        tasks = []
        for name, channel in self.channels.items():
            logger.info(f"Starting {name} channel...")
            tasks.append(asyncio.create_task(self._start_channel(name, channel)))
        
        # 等待所有频道启动（它们应该永远运行）
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def stop_all(self) -> None:
        """
        停止所有频道和分发器
        
        功能描述:
            优雅地停止所有频道和消息分发器。
        
        处理流程:
            1. 停止出站分发器
            2. 停止所有频道
        """
        logger.info("Stopping all channels...")
        
        # 停止分发器
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass
        
        # 停止所有频道
        for name, channel in self.channels.items():
            try:
                await channel.stop()
                logger.info(f"Stopped {name} channel")
            except Exception as e:
                logger.error(f"Error stopping {name}: {e}")
    
    async def _dispatch_outbound(self) -> None:
        """
        分发出站消息到对应频道
        
        功能描述:
            从消息总线获取出站消息，分发到对应的频道。
        
        处理流程:
            1. 从消息总线获取出站消息（超时 1 秒）
            2. 查找对应的频道
            3. 调用频道的 send() 方法发送
            4. 处理异常
        """
        logger.info("Outbound dispatcher started")
        
        while True:
            try:
                # 获取出站消息
                msg = await asyncio.wait_for(
                    self.bus.consume_outbound(),
                    timeout=1.0
                )
                
                # 查找频道
                channel = self.channels.get(msg.channel)
                if channel:
                    try:
                        await channel.send(msg)
                    except Exception as e:
                        logger.error(f"Error sending to {msg.channel}: {e}")
                else:
                    logger.warning(f"Unknown channel: {msg.channel}")
                    
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
    
    def get_channel(self, name: str) -> BaseChannel | None:
        """
        根据名称获取频道
        
        参数说明:
            name: str，频道名称
        
        返回值:
            BaseChannel | None，频道实例或 None
        """
        return self.channels.get(name)
    
    def get_status(self) -> dict[str, Any]:
        """
        获取所有频道的状态
        
        返回值:
            dict，频道状态字典
        """
        return {
            name: {
                "enabled": True,
                "running": channel.is_running
            }
            for name, channel in self.channels.items()
        }
    
    @property
    def enabled_channels(self) -> list[str]:
        """
        获取已启用的频道名称列表
        
        返回值:
            list[str]，频道名称列表
        """
        return list(self.channels.keys())
