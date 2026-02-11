"""
In-memory cache for Hyperliquid account state and positions.

This cache is used to serve UI/analytics requests without repeatedly
calling Hyperliquid APIs. AI decision logic MUST continue to fetch
real-time data; after each successful fetch we update the cache.

Cache keys are tuples of (account_id, environment) to support multi-wallet
architecture where one account can have both testnet and mainnet wallets.
"""
"""
Hyperliquid账户状态内存缓存服务

为Hyperliquid账户状态和持仓信息提供高性能的内存缓存层，
显著减少对Hyperliquid API的重复调用，提升系统响应速度。

设计原则：
1. **UI优化专用**：主要服务于前端界面和分析请求，避免频繁API调用
2. **实时数据优先**：AI交易决策逻辑必须继续获取实时数据，不依赖缓存
3. **缓存更新机制**：每次成功获取实时数据后自动更新缓存
4. **环境隔离**：支持测试网和主网数据的独立缓存

技术架构：
- **内存存储**：使用Python字典实现的纯内存缓存，响应速度极快
- **线程安全**：使用线程锁确保多线程环境下的数据一致性
- **键值设计**：缓存键为(账户ID, 环境)元组，支持多钱包架构
- **时间戳管理**：记录缓存更新时间，支持过期检查和统计分析

缓存结构：
- **账户状态缓存**：保存账户余额、保证金、总权益等状态信息
- **持仓缓存**：保存当前所有持仓的详细信息（标的、方向、大小等）
- **时间戳记录**：记录每次缓存更新的时间戳

应用场景：
1. **前端仪表盘**：为用户界面提供快速的账户信息展示
2. **性能分析**：为资产曲线计算提供历史持仓数据
3. **监控告警**：为系统监控提供账户状态快照
4. **API节流**：减少对Hyperliquid API的调用频率

使用限制：
⚠️ **重要提醒**：
- AI交易决策逻辑不应依赖此缓存
- 所有交易相关的实时数据获取应直接调用API
- 缓存仅用于提升用户体验，不影响交易逻辑的准确性

性能特点：
- **极低延迟**：内存访问，微秒级响应时间
- **高并发**：支持多线程并发访问
- **内存效率**：仅缓存必要数据，控制内存使用
- **自动更新**：与实时数据获取流程无缝集成
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional, Tuple, TypedDict


class _CacheEntry(TypedDict):
    """
    缓存条目类型定义

    定义缓存中每个条目的标准结构，包含数据本身和时间戳信息。
    使用TypedDict确保类型安全，便于IDE智能提示和静态分析。

    字段说明：
    - data: 缓存的实际数据，可以是任意类型（账户状态字典、持仓列表等）
    - timestamp: 缓存更新的Unix时间戳，用于过期检查和统计分析
    """
    data: Any           # 缓存的实际数据
    timestamp: float    # 缓存时间戳（Unix时间）


# Global cache storage - 全局缓存存储
_ACCOUNT_STATE_CACHE: Dict[Tuple[int, str], _CacheEntry] = {}  # 账户状态缓存
_POSITIONS_CACHE: Dict[Tuple[int, str], _CacheEntry] = {}      # 持仓信息缓存
_cache_lock = threading.Lock()                                 # 线程安全锁

# 缓存存储说明：
# - _ACCOUNT_STATE_CACHE: 存储账户余额、保证金等状态信息
# - _POSITIONS_CACHE: 存储当前持仓的详细信息
# - 键格式: (account_id, environment) - 支持多账户多环境
# - _cache_lock: 确保多线程环境下的数据一致性


def _now() -> float:
    """
    获取当前时间戳

    返回当前的Unix时间戳（浮点数格式），用于记录缓存更新时间。
    统一时间获取方式，便于后续可能的时间处理逻辑修改。

    Returns:
        float: 当前Unix时间戳（秒，包含小数部分）
    """
    return time.time()


def _make_cache_key(account_id: int, environment: str) -> Tuple[int, str]:
    """Create cache key from account_id and environment."""
    """
    构建缓存键

    将账户ID和环境信息组合成缓存键，支持多钱包架构下的数据隔离。
    确保不同环境（测试网/主网）的数据不会相互干扰。

    Args:
        account_id: 账户ID，系统内部的唯一标识符
        environment: 环境标识，"testnet"或"mainnet"

    Returns:
        Tuple[int, str]: 缓存键元组，格式为(账户ID, 环境)

    设计优势：
    - 类型安全：使用元组确保键的结构一致性
    - 环境隔离：同一账户的不同环境数据独立存储
    - 高性能：元组作为字典键的哈希性能优异
    - 可读性强：键的结构清晰易懂
    """
    return (account_id, environment)


def update_account_state_cache(account_id: int, state: Dict[str, Any], environment: str = "testnet") -> None:
    """Store latest Hyperliquid account state for (account_id, environment)."""
    """
    更新账户状态缓存

    将最新的Hyperliquid账户状态信息存储到内存缓存中。
    该函数通常在成功获取实时账户数据后被调用。

    Args:
        account_id: 账户ID，用于标识特定的交易账户
        state: 账户状态字典，包含余额、保证金、权益等信息
        environment: 环境标识，默认"testnet"，可选"mainnet"

    数据结构示例：
    state = {
        "balance": 10000.0,           # 账户余额
        "total_equity": 10500.0,      # 总权益
        "margin_used": 2000.0,        # 已用保证金
        "margin_available": 8500.0,   # 可用保证金
        "unrealized_pnl": 500.0,      # 未实现盈亏
        "wallet_address": "0x...",    # 钱包地址
    }

    线程安全：
    - 使用全局锁保护缓存写入操作
    - 确保多线程环境下的数据一致性
    - 避免并发写入导致的数据竞争

    调用时机：
    1. AI交易决策获取账户状态后
    2. 定时账户状态同步完成后
    3. 用户手动刷新账户信息后
    4. 交易执行后账户状态更新时
    """
    cache_key = _make_cache_key(account_id, environment)  # 构建缓存键
    with _cache_lock:  # 获取线程锁，确保原子操作
        _ACCOUNT_STATE_CACHE[cache_key] = {
            "data": state,        # 存储账户状态数据
            "timestamp": _now()   # 记录更新时间戳
        }


def update_positions_cache(account_id: int, positions: List[Dict[str, Any]], environment: str = "testnet") -> None:
    """Store latest Hyperliquid positions for (account_id, environment)."""
    """
    更新持仓信息缓存

    将最新的Hyperliquid持仓信息存储到内存缓存中。
    该函数通常在成功获取实时持仓数据后被调用。

    Args:
        account_id: 账户ID，用于标识特定的交易账户
        positions: 持仓信息列表，每个元素包含一个持仓的详细信息
        environment: 环境标识，默认"testnet"，可选"mainnet"

    数据结构示例：
    positions = [
        {
            "symbol": "BTC",           # 交易标的
            "side": "long",           # 持仓方向（long/short）
            "size": 0.5,             # 持仓大小
            "entry_price": 45000.0,   # 开仓价格
            "mark_price": 46000.0,    # 标记价格
            "unrealized_pnl": 500.0,  # 未实现盈亏
            "leverage": 10,           # 杠杆倍数
            "liquidation_price": 40000.0,  # 强平价格
        },
        # ... 更多持仓
    ]

    缓存策略：
    - 完全替换：每次更新替换整个持仓列表
    - 时间戳记录：记录最后更新时间供过期检查
    - 环境隔离：测试网和主网持仓分别缓存

    性能考虑：
    - 内存高效：仅缓存当前有效持仓
    - 访问快速：O(1)时间复杂度的查找
    - 更新原子：使用锁保证更新的原子性
    """
    cache_key = _make_cache_key(account_id, environment)  # 构建缓存键
    with _cache_lock:  # 获取线程锁，确保原子操作
        _POSITIONS_CACHE[cache_key] = {
            "data": positions,    # 存储持仓列表数据
            "timestamp": _now()   # 记录更新时间戳
        }


def get_cached_account_state(
    account_id: int,
    environment: str = "testnet",
    max_age_seconds: Optional[int] = None,
) -> Optional[_CacheEntry]:
    """Return cached account state if present and within optional TTL."""
    cache_key = _make_cache_key(account_id, environment)
    with _cache_lock:
        entry = _ACCOUNT_STATE_CACHE.get(cache_key)
        if not entry:
            return None
        if max_age_seconds is not None and _now() - entry["timestamp"] > max_age_seconds:
            return None
        return entry


def get_cached_positions(
    account_id: int,
    environment: str = "testnet",
    max_age_seconds: Optional[int] = None,
) -> Optional[_CacheEntry]:
    """Return cached positions if present and within optional TTL."""
    cache_key = _make_cache_key(account_id, environment)
    with _cache_lock:
        entry = _POSITIONS_CACHE.get(cache_key)
        if not entry:
            return None
        if max_age_seconds is not None and _now() - entry["timestamp"] > max_age_seconds:
            return None
        return entry


def clear_account_cache(account_id: Optional[int] = None, environment: Optional[str] = None) -> None:
    """
    Clear cached entries.

    Args:
        account_id: If None, clear all accounts. If provided with environment, clear specific entry.
        environment: If None with account_id, clear both environments for that account.
    """
    with _cache_lock:
        if account_id is None:
            # Clear all caches
            _ACCOUNT_STATE_CACHE.clear()
            _POSITIONS_CACHE.clear()
        elif environment is None:
            # Clear both testnet and mainnet for this account
            for env in ["testnet", "mainnet"]:
                cache_key = _make_cache_key(account_id, env)
                _ACCOUNT_STATE_CACHE.pop(cache_key, None)
                _POSITIONS_CACHE.pop(cache_key, None)
        else:
            # Clear specific (account_id, environment) entry
            cache_key = _make_cache_key(account_id, environment)
            _ACCOUNT_STATE_CACHE.pop(cache_key, None)
            _POSITIONS_CACHE.pop(cache_key, None)


def clear_all_caches() -> None:
    """Clear all cached entries across all accounts."""
    clear_account_cache(account_id=None)


def get_cache_stats() -> Dict[str, Any]:
    """Return basic cache diagnostics."""
    with _cache_lock:
        return {
            "accounts_cached": len(_ACCOUNT_STATE_CACHE),
            "positions_cached": len(_POSITIONS_CACHE),
        }
