"""Channel manager for coordinating chat channels."""
# 频道管理器模块
# 用于协调和管理多个聊天频道

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
    Manages chat channels and coordinates message routing.
    # 管理聊天频道并协调消息路由
    
    Responsibilities:
    # 职责：
    - Initialize enabled channels (Telegram, WhatsApp, etc.)
    #    初始化启用的频道（Telegram、WhatsApp等）
    - Start/stop channels
    #    启动/停止频道
    - Route outbound messages
    #    路由出站消息
    """
    
    def __init__(self, config: Config, bus: MessageBus, session_manager: "SessionManager | None" = None):
        self.config = config
        # 配置对象
        self.bus = bus
        # 消息总线
        self.session_manager = session_manager
        # 会话管理器
        self.channels: dict[str, BaseChannel] = {}
        # 频道字典
        self._dispatch_task: asyncio.Task | None = None
        # 分发任务
        
        self._init_channels()
    
    def _init_channels(self) -> None:
        """Initialize channels based on config."""
        # 根据配置初始化频道
        
        # Telegram channel
        # Telegram频道
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
        
        # WhatsApp channel
        # WhatsApp频道
        if self.config.channels.whatsapp.enabled:
            try:
                from nanobot.channels.whatsapp import WhatsAppChannel
                self.channels["whatsapp"] = WhatsAppChannel(
                    self.config.channels.whatsapp, self.bus
                )
                logger.info("WhatsApp channel enabled")
            except ImportError as e:
                logger.warning(f"WhatsApp channel not available: {e}")

        # Discord channel
        # Discord频道
        if self.config.channels.discord.enabled:
            try:
                from nanobot.channels.discord import DiscordChannel
                self.channels["discord"] = DiscordChannel(
                    self.config.channels.discord, self.bus
                )
                logger.info("Discord channel enabled")
            except ImportError as e:
                logger.warning(f"Discord channel not available: {e}")
        
        # Feishu channel
        # Feishu频道
        if self.config.channels.feishu.enabled:
            try:
                from nanobot.channels.feishu import FeishuChannel
                self.channels["feishu"] = FeishuChannel(
                    self.config.channels.feishu, self.bus
                )
                logger.info("Feishu channel enabled")
            except ImportError as e:
                logger.warning(f"Feishu channel not available: {e}")

        # Mochat channel
        # Mochat频道
        if self.config.channels.mochat.enabled:
            try:
                from nanobot.channels.mochat import MochatChannel

                self.channels["mochat"] = MochatChannel(
                    self.config.channels.mochat, self.bus
                )
                logger.info("Mochat channel enabled")
            except ImportError as e:
                logger.warning(f"Mochat channel not available: {e}")

        # DingTalk channel
        # DingTalk频道
        if self.config.channels.dingtalk.enabled:
            try:
                from nanobot.channels.dingtalk import DingTalkChannel
                self.channels["dingtalk"] = DingTalkChannel(
                    self.config.channels.dingtalk, self.bus
                )
                logger.info("DingTalk channel enabled")
            except ImportError as e:
                logger.warning(f"DingTalk channel not available: {e}")

        # Email channel
        # Email频道
        if self.config.channels.email.enabled:
            try:
                from nanobot.channels.email import EmailChannel
                self.channels["email"] = EmailChannel(
                    self.config.channels.email, self.bus
                )
                logger.info("Email channel enabled")
            except ImportError as e:
                logger.warning(f"Email channel not available: {e}")

        # Slack channel
        # Slack频道
        if self.config.channels.slack.enabled:
            try:
                from nanobot.channels.slack import SlackChannel
                self.channels["slack"] = SlackChannel(
                    self.config.channels.slack, self.bus
                )
                logger.info("Slack channel enabled")
            except ImportError as e:
                logger.warning(f"Slack channel not available: {e}")

        # QQ channel
        # QQ频道
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
        """Start a channel and log any exceptions."""
        # 启动频道并记录任何异常
        try:
            await channel.start()
        except Exception as e:
            logger.error(f"Failed to start channel {name}: {e}")

    async def start_all(self) -> None:
        """Start all channels and the outbound dispatcher."""
        # 启动所有频道和出站分发器
        if not self.channels:
            logger.warning("No channels enabled")
            return
        
        # Start outbound dispatcher
        # 启动出站分发器
        self._dispatch_task = asyncio.create_task(self._dispatch_outbound())
        
        # Start channels
        # 启动频道
        tasks = []
        for name, channel in self.channels.items():
            logger.info(f"Starting {name} channel...")
            tasks.append(asyncio.create_task(self._start_channel(name, channel)))
        
        # Wait for all to complete (they should run forever)
        # 等待所有完成（它们应该永远运行）
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def stop_all(self) -> None:
        """Stop all channels and the dispatcher."""
        # 停止所有频道和分发器
        logger.info("Stopping all channels...")
        
        # Stop dispatcher
        # 停止分发器
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass
        
        # Stop all channels
        # 停止所有频道
        for name, channel in self.channels.items():
            try:
                await channel.stop()
                logger.info(f"Stopped {name} channel")
            except Exception as e:
                logger.error(f"Error stopping {name}: {e}")
    
    async def _dispatch_outbound(self) -> None:
        """Dispatch outbound messages to the appropriate channel."""
        # 将出站消息分发到适当的频道
        logger.info("Outbound dispatcher started")
        
        while True:
            try:
                msg = await asyncio.wait_for(
                    self.bus.consume_outbound(),
                    timeout=1.0
                )
                
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
        """Get a channel by name."""
        # 根据名称获取频道
        return self.channels.get(name)
    
    def get_status(self) -> dict[str, Any]:
        """Get status of all channels."""
        # 获取所有频道的状态
        return {
            name: {
                "enabled": True,
                "running": channel.is_running
            }
            for name, channel in self.channels.items()
        }
    
    @property
    def enabled_channels(self) -> list[str]:
        """Get list of enabled channel names."""
        # 获取启用的频道名称列表
        return list(self.channels.keys())
