"""
新闻推送服务

为AI交易决策提供最新的加密货币相关新闻资讯。
通过RSS源获取新闻并进行格式化处理，增强AI的市场理解能力。

核心功能：
1. 新闻获取：从可靠的加密货币新闻源获取最新资讯
2. 内容清理：去除HTML标签和无关内容，提取核心信息
3. 格式优化：为AI模型优化新闻内容的格式和长度
4. 时间处理：标准化新闻发布时间格式

新闻来源：
- CoinJournal: 专业的加密货币新闻网站
- RSS格式：标准化的新闻聚合格式
- 实时更新：获取最新的市场相关资讯

AI增强价值：
- 基本面分析：为AI提供市场情绪和基本面信息
- 上下文增强：帮助AI理解当前市场环境
- 决策支持：新闻事件可能影响价格走势
- 风险识别：重大事件可能带来额外的市场风险

技术特点：
- 容错处理：网络异常和解析错误的优雅处理
- 内容过滤：自动清理HTML标签和推广内容
- 长度控制：限制新闻内容长度，适配AI模型上下文窗口
- 编码安全：正确处理HTML实体和特殊字符
"""

import logging
import re
from datetime import timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import List
import xml.etree.ElementTree as ET

import requests


logger = logging.getLogger(__name__)

NEWS_FEED_URL = "https://coinjournal.net/news/feed/"
# 新闻RSS源URL
# CoinJournal是专业的加密货币新闻网站，提供：
# - 及时的市场资讯和分析
# - 高质量的原创内容
# - 稳定的RSS更新频率
# - 专注于加密货币和区块链领域


def _strip_html_tags(text: str) -> str:
    """
    清理HTML标签和格式化文本

    将包含HTML标签的新闻内容转换为纯文本格式，
    便于AI模型理解和处理。

    Args:
        text: 原始HTML格式的文本内容

    Returns:
        str: 清理后的纯文本内容

    清理步骤：
    1. HTML实体解码：将&amp;、&lt;等实体转换为正常字符
    2. 标签移除：使用正则表达式删除所有HTML标签
    3. 空格规范：将多个连续空格/换行合并为单个空格
    4. 首尾清理：去除开头和结尾的多余空白

    处理示例：
    输入："&lt;p&gt;Bitcoin &amp; Ethereum&lt;/p&gt;"
    输出："Bitcoin & Ethereum"

    技术要点：
    - 使用html.unescape处理HTML实体，确保字符正确显示
    - 正则表达式<[^>]+>匹配所有HTML标签并替换为空格
    - \s+匹配多个连续空白字符，统一替换为单空格
    """
    if not text:
        return ""
    cleaned = unescape(text)                      # HTML实体解码
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)    # 移除HTML标签
    return re.sub(r"\s+", " ", cleaned).strip()   # 规范空格并清理首尾


def fetch_latest_news(max_chars: int = 4000) -> str:
    """
    获取最新加密货币新闻

    从RSS源获取最新的加密货币相关新闻，格式化后返回给AI模型使用。
    该函数为AI交易决策提供重要的市场背景信息。

    Args:
        max_chars: 返回内容的最大字符数，默认4000字符

    Returns:
        str: 格式化的新闻内容字符串，多条新闻用换行分隔

    功能流程：
    1. HTTP请求：从CoinJournal获取RSS内容
    2. XML解析：解析RSS格式的新闻数据
    3. 内容提取：提取标题、发布时间、摘要等关键信息
    4. 格式清理：去除HTML标签和推广内容
    5. 长度控制：确保总内容不超过指定字符数

    异常处理：
    - 网络请求失败：记录警告并返回空字符串
    - XML解析错误：优雅处理格式错误
    - 时间解析异常：保留原始时间字符串

    AI应用价值：
    - 市场情绪：帮助AI理解当前市场情绪和趋势
    - 事件驱动：识别可能影响价格的重大事件
    - 基本面分析：为技术分析补充基本面信息
    - 风险评估：识别潜在的市场风险因素
    """
    try:
        response = requests.get(NEWS_FEED_URL, timeout=10)
        if response.status_code != 200:
            logger.warning("Failed to fetch news feed: status %s", response.status_code)
            return ""

        root = ET.fromstring(response.content)
        channel = root.find("channel")
        if channel is None:
            return ""

        entries: List[str] = []

        for item in channel.findall("item"):
            title = _strip_html_tags(item.findtext("title") or "")
            pub_date_raw = (item.findtext("pubDate") or "").strip()
            summary_raw = item.findtext("description") or ""

            summary = _strip_html_tags(summary_raw)
            summary = re.sub(r"The post .*? appeared first on .*", "", summary, flags=re.IGNORECASE).strip()

            formatted_time = pub_date_raw
            if pub_date_raw:
                try:
                    parsed = parsedate_to_datetime(pub_date_raw)
                    if parsed is not None:
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=timezone.utc)
                        else:
                            parsed = parsed.astimezone(timezone.utc)
                        formatted_time = parsed.strftime("%Y-%m-%d %H:%M:%SZ")
                except Exception:  # noqa: BLE001
                    formatted_time = pub_date_raw

            parts = []
            if formatted_time:
                parts.append(formatted_time)
            if title:
                parts.append(title)

            entry_text = " | ".join(parts)
            if summary:
                entry_text = f"{entry_text}: {summary}" if entry_text else summary

            entry_text = entry_text.strip()
            if not entry_text:
                continue

            existing_text = "\n".join(entries)
            candidate_text = f"{existing_text}\n{entry_text}" if existing_text else entry_text
            if len(candidate_text) > max_chars:
                remaining = max_chars - len(existing_text)
                if existing_text:
                    remaining -= 1
                if remaining <= 0:
                    break
                truncated = entry_text[:remaining].rstrip()
                if truncated:
                    if len(truncated) < len(entry_text):
                        truncated = truncated.rstrip(" .,;:-") + "..."
                    entries.append(truncated)
                break

            entries.append(entry_text)

        return "\n".join(entries)

    except Exception as err:  # noqa: BLE001
        logger.warning("Failed to process news feed: %s", err)
        return ""
