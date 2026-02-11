"""Message tool for sending messages to users."""
# 消息工具模块
# 提供向用户发送消息的功能

from typing import Any, Callable, Awaitable

from nanobot.agent.tools.base import Tool
from nanobot.bus.events import OutboundMessage


class MessageTool(Tool):
    """Tool to send messages to users on chat channels."""
    # 用于在聊天频道向用户发送消息的工具
    
    def __init__(
        self, 
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
        default_channel: str = "",
        default_chat_id: str = ""
    ):
        self._send_callback = send_callback
        # 发送消息的回调函数
        self._default_channel = default_channel
        # 默认频道
        self._default_chat_id = default_chat_id
        # 默认聊天ID
    
    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the current message context."""
        # 设置当前消息上下文
        self._default_channel = channel
        self._default_chat_id = chat_id
    
    def set_send_callback(self, callback: Callable[[OutboundMessage], Awaitable[None]]) -> None:
        """Set the callback for sending messages."""
        # 设置发送消息的回调函数
        self._send_callback = callback
    
    @property
    def name(self) -> str:
        return "message"
    
    @property
    def description(self) -> str:
        return "Send a message to the user. Use this when you want to communicate something."
        # 向用户发送消息，当需要与用户交流时使用此工具
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The message content to send"
                    # 要发送的消息内容
                },
                "channel": {
                    "type": "string",
                    "description": "Optional: target channel (telegram, discord, etc.)"
                    # 可选：目标频道（telegram, discord等）
                },
                "chat_id": {
                    "type": "string",
                    "description": "Optional: target chat/user ID"
                    # 可选：目标聊天/用户ID
                }
            },
            "required": ["content"]
        }
    
    async def execute(
        self, 
        content: str, 
        channel: str | None = None, 
        chat_id: str | None = None,
        **kwargs: Any
    ) -> str:
        channel = channel or self._default_channel
        chat_id = chat_id or self._default_chat_id
        
        if not channel or not chat_id:
            return "Error: No target channel/chat specified"
        
        if not self._send_callback:
            return "Error: Message sending not configured"
        
        msg = OutboundMessage(
            channel=channel,
            chat_id=chat_id,
            content=content
        )
        
        try:
            await self._send_callback(msg)
            return f"Message sent to {channel}:{chat_id}"
        except Exception as e:
            return f"Error sending message: {str(e)}"
