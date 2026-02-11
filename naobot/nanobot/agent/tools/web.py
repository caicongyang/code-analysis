# -*- coding: utf-8 -*-
"""
================================================================================
Web Tools - Web 工具模块
================================================================================

功能描述:
    提供网络搜索和网页内容抓取功能，是 Agent 获取实时网络信息的主要方式。

主要组件:
    - WebSearchTool: 使用 Brave Search API 进行网页搜索
    - WebFetchTool: 使用 Readability 提取网页可读内容

安全措施:
    - URL 验证：只允许 http/https 协议
    - 重定向限制：最多 5 次重定向，防止 DoS 攻击
    - User-Agent：模拟真实浏览器请求

依赖:
    - httpx: HTTP 客户端
    - readability-lxml: HTML 内容提取

================================================================================
"""

import html
import json
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from nanobot.agent.tools.base import Tool

# ========================================================================
# 共享常量
# ========================================================================
# User-Agent 请求头，模拟真实浏览器
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36"

# 最大重定向次数，防止 DoS 攻击
MAX_REDIRECTS = 5


def _strip_tags(text: str) -> str:
    """
    移除 HTML 标签并解码实体
    
    功能描述:
        从 HTML 文本中提取纯文本内容。
    
    处理步骤:
        1. 移除 <script> 标签及其内容
        2. 移除 <style> 标签及其内容
        3. 移除所有其他 HTML 标签
        4. 解码 HTML 实体（如 &amp; → &）
    
    参数:
        text: str，原始 HTML 文本
    
    返回值:
        str，纯文本内容
    """
    # 移除 script 标签
    text = re.sub(r'<script[\s\S]*?</script>', '', text, flags=re.I)
    # 移除 style 标签
    text = re.sub(r'<style[\s\S]*?</style>', '', text, flags=re.I)
    # 移除所有 HTML 标签
    text = re.sub(r'<[^>]+>', '', text)
    # 解码 HTML 实体并去除首尾空白
    return html.unescape(text).strip()


def _normalize(text: str) -> str:
    """
    规范化空白字符
    
    功能描述:
        将多个空白字符合并为一个，空格规范化。
    
    处理步骤:
        1. 将多个空格/制表符合并为一个空格
        2. 将 3 个以上连续换行符减少为 2 个
        3. 去除首尾空白
    
    参数:
        text: str，输入文本
    
    返回值:
        str，规范化的文本
    """
    # 规范化空格
    text = re.sub(r'[ \t]+', ' ', text)
    # 减少连续换行
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def _validate_url(url: str) -> tuple[bool, str]:
    """
    验证 URL 格式
    
    功能描述:
        检查 URL 是否为有效的 http/https 协议。
    
    检查项目:
        1. 协议必须为 http 或 https
        2. 必须有有效的域名
    
    参数:
        url: str，要验证的 URL
    
    返回值:
        tuple[bool, str]：(是否有效, 错误信息)
    """
    try:
        p = urlparse(url)
        # 检查协议
        if p.scheme not in ('http', 'https'):
            return False, f"Only http/https allowed, got '{p.scheme or 'none'}'"
        # 检查域名
        if not p.netloc:
            return False, "Missing domain"
        return True, ""
    except Exception as e:
        return False, str(e)


class WebSearchTool(Tool):
    """
    ========================================================================
    WebSearchTool - 网页搜索工具类
    ========================================================================
    
    使用 Brave Search API 进行网页搜索。
    
    功能特点:
        - 返回搜索结果标题、URL 和摘要
        - 支持指定返回结果数量（1-10）
        - 需要配置 BRAVE_API_KEY
    
    ========================================================================
    """
    
    name = "web_search"
    description = "Search the web. Returns titles, URLs, and snippets."
    
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query"
            },
            "count": {
                "type": "integer",
                "description": "Results (1-10)",
                "minimum": 1,
                "maximum": 10
            }
        },
        "required": ["query"]
    }
    
    def __init__(self, api_key: str | None = None, max_results: int = 5):
        """
        初始化网页搜索工具
        
        参数说明:
            api_key: str | None，Brave API Key
            max_results: int，默认返回结果数量
        """
        # 获取 API Key（优先使用传入的，其次使用环境变量）
        self.api_key = api_key or os.environ.get("BRAVE_API_KEY", "")
        self.max_results = max_results
    
    async def execute(self, query: str, count: int | None = None, **kwargs: Any) -> str:
        """
        执行网页搜索
        
        功能描述:
            使用 Brave Search API 搜索查询内容。
        
        参数说明:
            query: str，搜索查询
            count: int | None，返回结果数量（1-10）
            **kwargs: 额外的关键字参数（忽略）
        
        返回值:
            str，格式化的搜索结果
                - 如果未配置 API Key，返回错误信息
                - 如果无结果，返回 "No results for: {query}"
                - 否则返回编号列表格式的结果
        
        使用示例:
            results = await web_search.execute("Python async await", count=5)
        """
        # 检查 API Key
        if not self.api_key:
            return "Error: BRAVE_API_KEY not configured"
        
        try:
            # 确定结果数量（限制在 1-10 之间）
            n = min(max(count or self.max_results, 1), 10)
            
            # 发送搜索请求
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": n},
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": self.api_key
                    },
                    timeout=10.0
                )
                r.raise_for_status()
            
            # 解析结果
            results = r.json().get("web", {}).get("results", [])
            if not results:
                return f"No results for: {query}"
            
            # 格式化输出
            lines = [f"Results for: {query}\n"]
            for i, item in enumerate(results[:n], 1):
                lines.append(f"{i}. {item.get('title', '')}\n   {item.get('url', '')}")
                if desc := item.get("description"):
                    lines.append(f"   {desc}")
            
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"


class WebFetchTool(Tool):
    """
    ========================================================================
    WebFetchTool - 网页抓取工具类
    ========================================================================
    
    使用 Readability 库提取网页可读内容。
    
    功能特点:
        - 支持 markdown 和纯文本两种输出格式
        - 自动提取标题和正文内容
        - 返回 JSON 格式的详细信息
        - 支持内容截断
    
    ========================================================================
    """
    
    name = "web_fetch"
    description = "Fetch URL and extract readable content (HTML → markdown/text)."
    
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to fetch"
            },
            "extractMode": {
                "type": "string",
                "enum": ["markdown", "text"],
                "default": "markdown",
                "description": "Extraction mode"
            },
            "maxChars": {
                "type": "integer",
                "minimum": 100,
                "description": "Maximum characters"
            }
        },
        "required": ["url"]
    }
    
    def __init__(self, max_chars: int = 50000):
        """
        初始化网页抓取工具
        
        参数说明:
            max_chars: int，最大返回字符数
        """
        self.max_chars = max_chars
    
    async def execute(
        self,
        url: str,
        extractMode: str = "markdown",
        maxChars: int | None = None,
        **kwargs: Any
    ) -> str:
        """
        获取并提取网页内容
        
        功能描述:
            获取指定 URL 的内容，使用 Readability 提取可读部分。
        
        参数说明:
            url: str，要获取的 URL
            extractMode: str，提取模式（"markdown" 或 "text"）
            maxChars: int | None，最大字符数限制
            **kwargs: 额外的关键字参数（忽略）
        
        返回值:
            str，JSON 格式的结果，包含：
                - url: 原始 URL
                - finalUrl: 最终 URL（跟随重定向后）
                - status: HTTP 状态码
                - extractor: 使用的提取器（readability/json/raw）
                - truncated: 是否被截断
                - length: 内容长度
                - text: 提取的文本内容
        
        使用示例:
            result = await web_fetch.execute(
                url="https://example.com/article",
                extractMode="markdown",
                maxChars=10000
            )
        """
        from readability import Document

        # 确定最大字符数
        max_chars = maxChars or self.max_chars

        # URL 验证
        is_valid, error_msg = _validate_url(url)
        if not is_valid:
            return json.dumps({
                "error": f"URL validation failed: {error_msg}",
                "url": url
            })

        try:
            # 发送 HTTP 请求
            async with httpx.AsyncClient(
                follow_redirects=True,
                max_redirects=MAX_REDIRECTS,
                timeout=30.0
            ) as client:
                r = await client.get(url, headers={"User-Agent": USER_AGENT})
                r.raise_for_status()
            
            # 获取内容类型
            ctype = r.headers.get("content-type", "")
            
            # ====================================================================
            # 处理不同类型的内容
            # ====================================================================
            # JSON 内容
            if "application/json" in ctype:
                text, extractor = json.dumps(r.json(), indent=2), "json"
            
            # HTML 内容
            elif "text/html" in ctype or r.text[:256].lower().startswith(("<!doctype", "<html")):
                # 使用 Readability 提取
                doc = Document(r.text)
                
                # 根据提取模式转换
                if extractMode == "markdown":
                    content = self._to_markdown(doc.summary())
                else:
                    content = _strip_tags(doc.summary())
                
                # 添加标题
                if doc.title():
                    text = f"# {doc.title()}\n\n{content}"
                else:
                    text = content
                
                extractor = "readability"
            
            # 其他类型（纯文本等）
            else:
                text, extractor = r.text, "raw"
            
            # 检查是否需要截断
            truncated = len(text) > max_chars
            if truncated:
                text = text[:max_chars]
            
            # 返回 JSON 格式结果
            return json.dumps({
                "url": url,
                "finalUrl": str(r.url),
                "status": r.status_code,
                "extractor": extractor,
                "truncated": truncated,
                "length": len(text),
                "text": text
            })
        except Exception as e:
            return json.dumps({"error": str(e), "url": url})
    
    def _to_markdown(self, html: str) -> str:
        """
        将 HTML 转换为 Markdown
        
        功能描述:
            将 HTML 内容转换为 Markdown 格式。
        
        转换规则:
            - <a href="...">text</a> → [text](...)
            - <h1> → # ...
            - <h2> → ## ...
            - <li> → - ...
            - <br> → 换行
            - <hr> → ---（段落分隔）
        
        参数:
            html: str，原始 HTML
        
        返回值:
            str，Markdown 格式的文本
        """
        # 转换链接: <a href="url">text</a> → [text](url)
        text = re.sub(
            r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
            lambda m: f'[{_strip_tags(m[2])}]({m[1]})',
            html,
            flags=re.I
        )
        
        # 转换标题: <h1> → # ...
        text = re.sub(
            r'<h([1-6])[^>]*>([\s\S]*?)</h\1>',
            lambda m: f'\n{"#" * int(m[1])} {_strip_tags(m[2])}\n',
            text,
            flags=re.I
        )
        
        # 转换列表项: <li> → - ...
        text = re.sub(
            r'<li[^>]*>([\s\S]*?)</li>',
            lambda m: f'\n- {_strip_tags(m[1])}',
            text,
            flags=re.I
        )
        
        # 转换块级元素为换行
        text = re.sub(r'</(p|div|section|article)>', '\n\n', text, flags=re.I)
        
        # 转换 <br> 和 <hr>
        text = re.sub(r'<(br|hr)\s*/?>', '\n', text, flags=re.I)
        
        # 规范化并返回
        return _normalize(_strip_tags(text))
