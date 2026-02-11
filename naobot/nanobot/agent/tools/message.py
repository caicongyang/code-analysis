# -*- coding: utf-8 -*-
"""
================================================================================
Message Tool - 消息工具模块
================================================================================

功能描述:
    提供向用户发送消息的功能，是 Agent 与用户交流的主要方式。
    通过消息总线发送消息，支持多个平台（telegram、discord、qq 等）。

核心概念:
    1. 频道 (Channel): 消息平台类型（如 telegram、discord、qq）
    2. 聊天 ID (Chat ID): 特定聊天会话的标识
    3. 上下文 (Context): 当前消息的来源信息

主要组件:
    - MessageTool: 消息发送工具类

使用场景:
    - Agent 需要主动通知用户
    - 回答用户的问题
    - 执行完任务后返回结果

================================================================================
"""

from typing import Any, Callable, Awaitable

from nanobot.agent.tools.base import Tool
from nanobot.bus.events import OutboundMessage


class MessageTool(Tool):
    """
    ========================================================================
    MessageTool - 消息发送工具类
    ========================================================================
    
    负责将消息发送到指定的聊天频道。
    
    功能特点:
        1. 支持多个平台（telegram、discord、qq 等）
        2. 支持设置默认上下文（自动填充 channel 和 chat_id）
        3. 异步发送，不阻塞处理流程
    
    上下文管理:
        - Agent 处理消息时，会自动设置当前消息的上下文
        - 后续的 message 工具调用会使用此上下文
        - 可以显式指定 channel 和 chat_id 覆盖默认值
    
    ========================================================================
    """
    
    def __init__(
        self,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
        default_channel: str = "",
        default_chat_id: str = ""
    ):
        """
        初始化消息工具
        
        参数说明:
            send_callback: 发送消息的回调函数
            default_channel: 默认频道
            default_chat_id: 默认聊天 ID
        """
        # 发送消息的回调函数
        self._send_callback = send_callback
        
        # 默认频道
        self._default_channel = default_channel
        
        # 默认聊天 ID
        self._default_chat_id = default_chat_id
    
    def set_context(self, channel: str, chat_id: str) -> None:
        """
        设置当前消息上下文
        
        功能描述:
            设置工具使用的默认 channel 和 chat_id。
            通常在处理用户消息时自动调用。
        
        参数说明:
            channel: str，频道标识（如 telegram、discord）
            chat_id: str，聊天会话 ID
        """
        self._default_channel = channel
        self._default_chat_id = chat_id
    
    def set_send_callback(self, callback: Callable[[OutboundMessage], Awaitable[None]]) -> None:
        """
        设置发送消息的回调函数
        
        功能描述:
            配置消息发送的回调函数。
        
        参数说明:
            callback: 异步回调函数，接收 OutboundMessage 并发送
        """
        self._send_callback = callback
    
    @property
    def name(self) -> str:
        """
        获取工具名称
        
        返回值:
            str，工具名称为 "message"
        """
        return "message"
    
    @property
    def description(self) -> str:
        """
        获取工具描述
        
        返回值:
            str，工具描述信息
        """
        return "Send a message to the user. Use this when you want to communicate something."
    
    @property
    def parameters(self) -> dict[str, Any]:
        """
        获取工具参数定义
        
        返回值:
            dict，OpenAI 格式的工具参数定义
        
        参数说明:
            - content: 要发送的消息内容（必填）
            - channel: 目标频道（可选，默认使用上下文）
            - chat_id: 目标聊天 ID（可选，默认使用上下文）
        """
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The message content to send"
                },
                "channel": {
                    "type": "string",
                    "description": "Optional: target channel (telegram, discord, etc.)"
                },
                "chat_id": {
                    "type": "string",
                    "description": "Optional: target chat/user ID"
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
        """
        发送消息
        
        功能描述:
            向指定的频道和聊天发送消息。
        
        参数说明:
            content: str，消息内容
            channel: str | None，指定频道（可选）
            chat_id: str | None，指定聊天 ID（可选）
            **kwargs: 额外的关键字参数（忽略）
        
        返回值:
            str，发送结果
                - 成功："Message sent to {channel}:{chat_id}"
                - 未配置回调："Error: Message sending not configured"
                - 未指定目标："Error: No target channel/chat specified"
                - 发送失败："Error sending message: {错误信息}"
        
        处理流程:
            1. 确定目标频道和聊天 ID
            2. 验证回调函数已设置
            3. 创建 OutboundMessage
            4. 调用回调函数发送
            5. 返回结果
        
        使用示例:
            # 使用当前上下文发送
            await message_tool.execute("Hello, world!")
            
            # 指定目标发送
            await message_tool.execute(
                content="Hello from CLI!",
                channel="telegram",
                chat_id="123456789"
            )
        """
        # 确定目标
        channel = channel or self._default_channel
        chat_id = chat_id or self._default_chat_id
        
        # 验证目标
        if not channel or not chat_id:
            return "Error: No target channel/chat specified"
        
        # 验证回调
        if not self._send_callback:
            return "Error: Message sending not configured"
        
        # 创建消息
        msg = OutboundMessage(
            channel=channel,
            chat_id=chat_id,
            content=content
        )
        
        try:
            # 发送消息
            await self._send_callback(msg)
            return f"Message sent to {channel}:{chat_id}"
        except Exception as e:
            return f"Error sending message: {str(e)}"
