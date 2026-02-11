"""Base channel interface for chat platforms."""
# 聊天平台的基础频道接口模块
# 定义了所有聊天频道实现需要遵循的抽象基类

from abc import ABC, abstractmethod
from typing import Any

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus


class BaseChannel(ABC):
    """
    Abstract base class for chat channel implementations.
    # 聊天频道实现的抽象基类
    
    Each channel (Telegram, Discord, etc.) should implement this interface
    to integrate with the nanobot message bus.
    # 每个频道（Telegram、Discord等）应实现此接口以集成到nanobot消息总线
    """
    
    name: str = "base"
    # 频道名称
    
    def __init__(self, config: Any, bus: MessageBus):
        """
        Initialize the channel.
        # 初始化频道
        
        Args:
            config: Channel-specific configuration.
            # 频道特定配置
            bus: The message bus for communication.
            # 用于通信的消息总线
        """
        self.config = config
        self.bus = bus
        self._running = False
    
    @abstractmethod
    async def start(self) -> None:
        """
        Start the channel and begin listening for messages.
        # 启动频道并开始监听消息
        
        This should be a long-running async task that:
        # 这应该是一个长时间运行的异步任务：
        1. Connects to the chat platform
        #    连接到聊天平台
        2. Listens for incoming messages
        #    监听传入消息
        3. Forwards messages to the bus via _handle_message()
        #    通过_handle_message()将消息转发到总线
        """
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """Stop the channel and clean up resources."""
        # 停止频道并清理资源
        pass
    
    @abstractmethod
    async def send(self, msg: OutboundMessage) -> None:
        """
        Send a message through this channel.
        # 通过此频道发送消息
        
        Args:
            msg: The message to send.
            # 要发送的消息
        """
        pass
    
    def is_allowed(self, sender_id: str) -> bool:
        """
        Check if a sender is allowed to use this bot.
        # 检查发送者是否被允许使用此机器人
        
        Args:
            sender_id: The sender's identifier.
            # 发送者的标识符
        
        Returns:
            True if allowed, False otherwise.
            # 允许返回True，否则返回False
        """
        allow_list = getattr(self.config, "allow_from", [])
        
        # If no allow list, allow everyone
        # 如果没有允许列表，则允许所有人
        if not allow_list:
            return True
        
        sender_str = str(sender_id)
        if sender_str in allow_list:
            return True
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
        Handle an incoming message from the chat platform.
        # 处理来自聊天平台的传入消息
        
        This method checks permissions and forwards to the bus.
        # 此方法检查权限并转发到总线
        
        Args:
            sender_id: The sender's identifier.
            # 发送者的标识符
            chat_id: The chat/channel identifier.
            # 聊天/频道标识符
            content: Message text content.
            # 消息文本内容
            media: Optional list of media URLs.
            # 可选的媒体URL列表
            metadata: Optional channel-specific metadata.
            # 可选的频道特定元数据
        """
        if not self.is_allowed(sender_id):
            logger.warning(
                f"Access denied for sender {sender_id} on channel {self.name}. "
                f"Add them to allowFrom list in config to grant access."
            )
            return
        
        msg = InboundMessage(
            channel=self.name,
            sender_id=str(sender_id),
            chat_id=str(chat_id),
            content=content,
            media=media or [],
            metadata=metadata or {}
        )
        
        await self.bus.publish_inbound(msg)
    
    @property
    def is_running(self) -> bool:
        """Check if the channel is running."""
        # 检查频道是否正在运行
        return self._running
