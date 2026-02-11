# -*- coding: utf-8 -*-
"""
================================================================================
LLM Provider Base - LLM 提供者基类模块
================================================================================

功能描述:
    定义 LLM 提供者的抽象基类和通用数据结构。
    所有具体的 LLM 提供者（如 LiteLLM、OpenAI、Anthropic 等）都需要实现这些接口。

核心概念:
    1. LLMProvider: 抽象基类，定义 LLM 交互的通用接口
    2. LLMResponse: LLM 响应数据结构
    3. ToolCallRequest: 工具调用请求数据结构

主要组件:
    - ToolCallRequest: 工具调用请求
    - LLMResponse: LLM 响应
    - LLMProvider: 抽象基类

================================================================================
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCallRequest:
    """
    ========================================================================
    ToolCallRequest - 工具调用请求类
    ========================================================================
    
    表示 LLM 发起的工具调用请求。
    
    属性说明:
        - id: 工具调用的唯一标识
        - name: 要调用的工具名称
        - arguments: 工具参数（字典格式）
    
    使用场景:
        - LLM 决定需要调用工具时生成
        - Agent 执行工具时使用
    
    ========================================================================
    """
    
    id: str
    """工具调用的唯一标识"""
    
    name: str
    """要调用的工具名称"""
    
    arguments: dict[str, Any]
    """工具参数"""


@dataclass
class LLMResponse:
    """
    ========================================================================
    LLMResponse - LLM 响应类
    ========================================================================
    
    表示 LLM 的响应结果。
    
    属性说明:
        - content: LLM 生成的文本内容
        - tool_calls: 需要执行的工具调用列表
        - finish_reason: 结束原因（stop、tool_calls 等）
        - usage: 令牌使用统计
        - reasoning_content: 思考模型的思考过程（Kimi、DeepSeek-R1 等）
    
    ========================================================================
    """
    
    content: str | None
    """LLM 生成的文本内容"""
    
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    """需要执行的工具调用列表"""
    
    finish_reason: str = "stop"
    """结束原因（stop/tool_calls/等）"""
    
    usage: dict[str, int] = field(default_factory=dict)
    """令牌使用统计（prompt_tokens、completion_tokens 等）"""
    
    reasoning_content: str | None = None
    """思考模型的思考过程（用于 Kimi、DeepSeek-R1 等）"""
    
    @property
    def has_tool_calls(self) -> bool:
        """
        检查响应是否包含工具调用
        
        返回值:
            bool，如果工具调用列表不为空则返回 True
        """
        return len(self.tool_calls) > 0


class LLMProvider(ABC):
    """
    ========================================================================
    LLMProvider - LLM 提供者抽象基类
    ========================================================================
    
    定义与 LLM 交互的通用接口。
    具体实现需要继承此类并实现所有抽象方法。
    
    实现要求:
        - 实现 chat() 方法处理聊天补全请求
        - 实现 get_default_model() 返回默认模型名称
    
    已实现的提供者:
        - LiteLLMProvider: 支持多种模型的 LiteLLM 实现
    
    ========================================================================
    """
    
    def __init__(self, api_key: str | None = None, api_base: str | None = None):
        """
        初始化 LLM 提供者
        
        参数说明:
            api_key: str | None，API 密钥
            api_base: str | None，API 基础 URL
        """
        self.api_key = api_key
        self.api_base = api_base
    
    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """
        发送聊天补全请求
        
        功能描述:
            向 LLM 发送消息列表，获取响应。
        
        参数说明:
            messages: list[dict]，消息列表，每个消息包含 role 和 content
            tools: list[dict] | None，工具定义列表
            model: str | None，模型标识符
            max_tokens: int，最大生成令牌数
            temperature: float，采样温度
        
        返回值:
            LLMResponse，包含内容或工具调用
        
        异常:
            NotImplementedError: 子类未实现此方法
        """
        pass
    
    @abstractmethod
    def get_default_model(self) -> str:
        """
        获取默认模型名称
        
        功能描述:
            返回此提供者的默认模型名称。
        
        返回值:
            str，默认模型名称
        
        异常:
            NotImplementedError: 子类未实现此方法
        """
        pass
