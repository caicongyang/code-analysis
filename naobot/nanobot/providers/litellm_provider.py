# -*- coding: utf-8 -*-
"""
================================================================================
LiteLLM Provider - LiteLLM 提供者模块
================================================================================

功能描述:
    使用 LiteLLM 库实现的多模型支持。LiteLLM 提供统一的接口来调用
    多种 LLM 提供者（OpenRouter、Anthropic、OpenAI、Gemini 等）。

核心特点:
    1. 统一接口：通过 LiteLLM 调用多种 LLM
    2. 动态模型解析：根据模型名称自动添加提供者前缀
    3. 网关支持：支持本地部署和 API 网关
    4. 参数覆盖：支持特定模型的参数覆盖

支持的提供者:
    - OpenRouter
    - Anthropic
    - OpenAI
    - Gemini
    - 以及通过 LiteLLM 支持的更多提供者

================================================================================
"""

import json
import os
from typing import Any

import litellm
from litellm import acompletion

from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from nanobot.providers.registry import find_by_model, find_gateway


class LiteLLMProvider(LLMProvider):
    """
    ========================================================================
    LiteLLMProvider - LiteLLM 提供者类
    ========================================================================
    
    使用 LiteLLM 库实现的多模型 LLM 提供者。
    
    功能特点:
        1. 统一接口：通过 LiteLLM 调用多种 LLM
        2. 动态解析：自动添加提供者前缀（如 anthropic/、openai/）
        3. 网关支持：支持本地网关和自定义端点
        4. 参数覆盖：支持特定模型的参数自定义
    
    模型命名约定:
        - 标准格式: "{provider}/{model}"（如 "anthropic/claude-sonnet-4-5"）
        - 网关模式: 自动应用网关前缀
    
    ========================================================================
    """
    
    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str = "anthropic/claude-opus-4-5",
        extra_headers: dict[str, str] | None = None,
        provider_name: str | None = None,
    ):
        """
        初始化 LiteLLM 提供者
        
        参数说明:
            api_key: str | None，API 密钥
            api_base: str | None，API 基础 URL
            default_model: str，默认模型名称
            extra_headers: dict | None，额外的 HTTP 请求头
            provider_name: str | None，提供者名称（用于网关模式）
        
        初始化过程:
            1. 调用父类初始化
            2. 检测网关/本地部署
            3. 配置环境变量
            4. 设置 LiteLLM 参数
        """
        super().__init__(api_key, api_base)
        self.default_model = default_model
        self.extra_headers = extra_headers or {}
        
        # 检测网关/本地部署
        # provider_name 是主要信号，api_key/api_base 是自动检测的回退
        self._gateway = find_gateway(provider_name, api_key, api_base)
        
        # 配置环境变量
        if api_key:
            self._setup_env(api_key, api_base, default_model)
        
        if api_base:
            litellm.api_base = api_base
        
        # 禁用 LiteLLM 日志噪声
        litellm.suppress_debug_info = True
        # 对于不支持某些参数的提供者，删除这些参数
        litellm.drop_params = True
    
    def _setup_env(self, api_key: str, api_base: str | None, model: str) -> None:
        """
        根据检测到的提供者设置环境变量
        
        功能描述:
            根据模型和提供者配置相应的环境变量。
        
        参数说明:
            api_key: API 密钥
            api_base: API 基础 URL
            model: 模型名称
        """
        spec = self._gateway or find_by_model(model)
        if not spec:
            return

        # 网关/本地模式：覆盖现有环境变量
        if self._gateway:
            os.environ[spec.env_key] = api_key
        else:
            # 标准模式：只设置未存在的环境变量
            os.environ.setdefault(spec.env_key, api_key)

        # 解析环境变量占位符:
        #   {api_key}  → 用户的 API 密钥
        #   {api_base} → 用户的 api_base，回退到 spec.default_api_base
        effective_base = api_base or spec.default_api_base
        for env_name, env_val in spec.env_extras:
            resolved = env_val.replace("{api_key}", api_key)
            resolved = resolved.replace("{api_base}", effective_base)
            os.environ.setdefault(env_name, resolved)
    
    def _resolve_model(self, model: str) -> str:
        """
        解析模型名称，应用提供者/网关前缀
        
        功能描述:
            根据配置动态添加或修改模型名称前缀。
        
        参数说明:
            model: 原始模型名称
        
        返回值:
            str，解析后的模型名称
        
        处理逻辑:
            - 网关模式：应用网关前缀，移除提供者前缀
            - 标准模式：自动添加已知提供者前缀
        """
        if self._gateway:
            # 网关模式：应用网关前缀
            prefix = self._gateway.litellm_prefix
            if self._gateway.strip_model_prefix:
                model = model.split("/")[-1]
            if prefix and not model.startswith(f"{prefix}/"):
                model = f"{prefix}/{model}"
            return model
        
        # 标准模式：自动添加提供者前缀
        spec = find_by_model(model)
        if spec and spec.litellm_prefix:
            if not any(model.startswith(s) for s in spec.skip_prefixes):
                model = f"{spec.litellm_prefix}/{model}"
        
        return model
    
    def _apply_model_overrides(self, model: str, kwargs: dict[str, Any]) -> None:
        """
        应用模型特定的参数覆盖
        
        功能描述:
            根据注册表中的配置，为特定模型应用参数覆盖。
        
        参数说明:
            model: 模型名称
            kwargs: 参数字典（会被修改）
        """
        model_lower = model.lower()
        spec = find_by_model(model)
        if spec:
            for pattern, overrides in spec.model_overrides:
                if pattern in model_lower:
                    kwargs.update(overrides)
                    return
    
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
            通过 LiteLLM 发送消息列表，获取 LLM 响应。
        
        参数说明:
            messages: 消息列表（包含 role 和 content）
            tools: 工具定义列表（OpenAI 格式）
            model: 模型标识符
            max_tokens: 最大生成令牌数
            temperature: 采样温度
        
        返回值:
            LLMResponse，包含文本内容或工具调用
        
        处理流程:
            1. 解析模型名称
            2. 构建请求参数
            3. 应用模型特定覆盖
            4. 设置 API 密钥和基础 URL
            5. 调用 LiteLLM
            6. 解析响应
        """
        model = self._resolve_model(model or self.default_model)
        
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        
        # 应用模型特定覆盖（如 kimi-k2.5 的温度）
        self._apply_model_overrides(model, kwargs)
        
        # 直接传递 api_key（比仅使用环境变量更可靠）
        if self.api_key:
            kwargs["api_key"] = self.api_key
        
        # 传递 api_base 用于自定义端点
        if self.api_base:
            kwargs["api_base"] = self.api_base
        
        # 传递额外请求头（如 AiHubMix 的 APP-Code）
        if self.extra_headers:
            kwargs["extra_headers"] = self.extra_headers
        
        # 设置工具调用
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        
        try:
            # 调用 LiteLLM
            response = await acompletion(**kwargs)
            return self._parse_response(response)
        except Exception as e:
            # 将错误作为内容返回，进行优雅处理
            return LLMResponse(
                content=f"Error calling LLM: {str(e)}",
                finish_reason="error",
            )
    
    def _parse_response(self, response: Any) -> LLMResponse:
        """
        解析 LiteLLM 响应为标准格式
        
        功能描述:
            将 LiteLLM 返回的原始响应转换为 LLMResponse 对象。
        
        参数说明:
            response: LiteLLM 原始响应对象
        
        返回值:
            LLMResponse，标准化的响应对象
        
        处理内容:
            - 提取文本内容
            - 解析工具调用
            - 提取令牌使用统计
            - 提取思考内容（对于思考模型）
        """
        choice = response.choices[0]
        message = choice.message
        
        tool_calls = []
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tc in message.tool_calls:
                # 如果需要，从 JSON 字符串解析参数
                args = tc.function.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"raw": args}
                
                tool_calls.append(ToolCallRequest(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))
        
        usage = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        
        reasoning_content = getattr(message, "reasoning_content", None)
        
        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
            reasoning_content=reasoning_content,
        )
    
    def get_default_model(self) -> str:
        """
        获取默认模型名称
        
        返回值:
            str，默认模型名称
        """
        return self.default_model
