# -*- coding: utf-8 -*-
"""
================================================================================
NanoBot Providers - LLM 提供者模块
================================================================================

功能描述:
    封装 LLM 提供者，实现与不同大语言模型的统一交互。

主要组件:
    - LLMProvider: LLM 提供者抽象基类
    - LLMResponse: LLM 响应数据结构
    - LiteLLMProvider: 使用 LiteLLM 的多模型支持

提供者实现:
    - LiteLLMProvider: 通过 LiteLLM 支持多种模型

使用示例:
    from nanobot.providers import LiteLLMProvider
    
    provider = LiteLLMProvider(
        api_key="your-api-key",
        default_model="anthropic/claude-sonnet-4-5"
    )
    
    response = await provider.chat(
        messages=[{"role": "user", "content": "Hello!"}],
    )

================================================================================
"""

from nanobot.providers.base import LLMProvider, LLMResponse
from nanobot.providers.litellm_provider import LiteLLMProvider

__all__ = ["LLMProvider", "LLMResponse", "LiteLLMProvider"]
