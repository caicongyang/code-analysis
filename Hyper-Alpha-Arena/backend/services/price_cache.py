"""
Price caching service to reduce API calls and provide short-term history.
"""
"""
价格缓存服务 - 减少API调用并提供短期历史数据

为交易系统提供高效的价格数据缓存机制，显著减少对外部API的调用频率，
同时维护短期价格历史用于技术指标计算和市场分析。

核心功能：
1. 短期缓存：TTL机制的价格缓存，避免重复API调用
2. 历史数据：维护滚动的价格历史队列，支持技术分析
3. 多环境支持：测试网和主网价格数据独立缓存
4. 线程安全：支持多线程并发访问的安全机制
5. 自动清理：过期数据的自动清理和内存管理

设计特点：
- **双层结构**：短期缓存 + 长期历史的分层设计
- **TTL机制**：基于时间的缓存失效策略
- **滚动历史**：固定时间窗口的历史数据保留
- **环境隔离**：测试网和主网数据完全分离

技术架构：
- **内存存储**：纯内存缓存，微秒级访问性能
- **线程安全**：使用锁机制保护并发访问
- **双端队列**：使用deque实现高效的滚动历史
- **复合键值**：支持多维度的数据索引

缓存策略：
1. **短期缓存**：
   - TTL：30秒（可配置）
   - 用途：减少API调用，提供实时价格
   - 清理：TTL过期时自动清除

2. **历史数据**：
   - 保留：1小时（可配置）
   - 用途：技术指标计算、趋势分析
   - 清理：滚动窗口，自动淘汰旧数据

应用场景：
- **实时价格获取**：为UI界面提供快速价格查询
- **技术指标计算**：为RSI、MACD等指标提供历史价格
- **API节流**：减少对交易所API的频繁调用
- **性能优化**：提升系统整体响应速度

性能特点：
- **低延迟**：内存访问，亚毫秒级响应
- **高并发**：支持多线程并发访问
- **内存高效**：自动清理过期数据，控制内存使用
- **扩展性好**：支持多标的、多环境的横向扩展
"""

import time
from typing import Deque, Dict, List, Optional, Tuple
import logging
from threading import Lock
from collections import deque

logger = logging.getLogger(__name__)


class PriceCache:
    """In-memory price cache with TTL and rolling history retention."""
    """
    内存价格缓存类

    实现带TTL（生存时间）的价格缓存和滚动历史数据保留机制。
    采用双层存储结构，同时满足实时查询和历史分析的需求。

    存储结构：
    1. 短期缓存（cache）：
       - 键格式：(symbol, market, environment)
       - 值格式：(price, timestamp)
       - 用途：快速价格查询，减少API调用

    2. 历史数据（history）：
       - 键格式：(symbol, market, environment)
       - 值格式：deque[(timestamp, price), ...]
       - 用途：技术指标计算，趋势分析

    线程安全：
    - 使用threading.Lock保护所有数据结构
    - 确保多线程环境下的数据一致性
    - 避免并发访问导致的数据竞争

    配置参数：
    - ttl_seconds: 短期缓存的生存时间（默认30秒）
    - history_seconds: 历史数据的保留时间（默认1小时）
    """

    def __init__(self, ttl_seconds: int = 30, history_seconds: int = 3600):
        """
        初始化价格缓存实例

        Args:
            ttl_seconds: 短期缓存TTL时间（秒），默认30秒
            history_seconds: 历史数据保留时间（秒），默认3600秒（1小时）

        设计考虑：
        - TTL 30秒：平衡数据实时性和API调用频率
        - 历史1小时：足够计算常用的技术指标
        - 可配置性：支持根据需求调整缓存参数
        """
        # key: (symbol, market, environment), value: (price, timestamp)
        # 短期价格缓存：存储最新价格和时间戳
        self.cache: Dict[Tuple[str, str, str], Tuple[float, float]] = {}

        # key: (symbol, market, environment), deque of (timestamp, price)
        # 历史价格队列：按时间顺序存储价格历史
        self.history: Dict[Tuple[str, str, str], Deque[Tuple[float, float]]] = {}

        self.ttl_seconds = ttl_seconds       # 短期缓存TTL时间
        self.history_seconds = history_seconds  # 历史数据保留时间
        self.lock = Lock()                   # 线程安全锁

    def get(self, symbol: str, market: str, environment: str = "mainnet") -> Optional[float]:
        """Get cached price if still within TTL."""
        """
        获取缓存中的价格数据

        从缓存中获取指定标的的价格，仅当数据在TTL时间内有效时才返回。
        超过TTL的数据会被自动清除。

        Args:
            symbol: 交易标的符号（如"BTC"、"ETH"）
            market: 市场类型（如"CRYPTO"）
            environment: 环境标识（"mainnet"或"testnet"）

        Returns:
            Optional[float]: 有效的缓存价格，如无有效缓存则返回None

        执行逻辑：
        1. 构建复合键标识特定的价格数据
        2. 获取线程锁，确保数据访问的原子性
        3. 检查缓存中是否存在对应数据
        4. 验证数据是否在TTL时间内有效
        5. 返回有效价格或None，自动清理过期数据

        性能特点：
        - 缓存命中：O(1)时间复杂度，微秒级响应
        - 自动清理：TTL过期时立即删除，控制内存使用
        - 线程安全：使用锁保护，支持并发访问
        - 调试友好：详细的日志记录缓存状态

        使用场景：
        - 实时价格查询：UI界面的价格显示
        - API节流：减少对外部API的重复调用
        - 性能优化：加速价格相关的计算操作
        """
        key = (symbol, market, environment)  # 构建复合键
        current_time = time.time()           # 获取当前时间戳

        with self.lock:  # 获取线程锁，确保原子操作
            entry = self.cache.get(key)
            if not entry:
                return None  # 缓存中无数据

            price, timestamp = entry
            if current_time - timestamp < self.ttl_seconds:
                # 数据在TTL时间内，返回缓存价格
                logger.debug("Cache hit for %s.%s.%s: %s", symbol, market, environment, price)
                return price

            # TTL expired – purge entry
            # TTL过期，删除缓存条目
            del self.cache[key]
            logger.debug("Cache expired for %s.%s.%s", symbol, market, environment)
            return None

    def record(self, symbol: str, market: str, price: float, timestamp: Optional[float] = None, environment: str = "mainnet") -> None:
        """Record price into short cache and long-term history."""
        """
        记录价格到缓存和历史数据

        将最新的价格数据同时存储到短期缓存和长期历史队列中。
        短期缓存用于快速查询，历史队列用于技术分析。

        Args:
            symbol: 交易标的符号
            market: 市场类型
            price: 价格数据
            timestamp: 可选的时间戳，默认使用当前时间
            environment: 环境标识

        存储机制：
        1. 更新短期缓存：存储最新价格和时间戳
        2. 追加历史队列：按时间顺序添加到历史数据
        3. 清理过期历史：删除超过保留时间的旧数据
        4. 内存管理：控制历史队列的大小

        数据结构：
        - 短期缓存：(price, timestamp) 元组
        - 历史队列：deque[(timestamp, price), ...] 按时间排序

        性能优化：
        - 使用deque实现O(1)的队列操作
        - 滚动窗口自动清理过期数据
        - 线程安全的并发写入支持

        应用价值：
        - 为技术指标计算提供历史价格序列
        - 支持短期趋势分析和图表绘制
        - 维护系统的价格数据完整性
        """
        key = (symbol, market, environment)  # 构建复合键
        event_time = timestamp or time.time()  # 使用提供的时间戳或当前时间

        with self.lock:
            self.cache[key] = (price, event_time)

            history_queue = self.history.setdefault(key, deque())
            history_queue.append((event_time, price))

            cutoff = event_time - self.history_seconds
            while history_queue and history_queue[0][0] < cutoff:
                history_queue.popleft()

        logger.debug("Recorded price update for %s.%s.%s: %s @ %s", symbol, market, environment, price, event_time)

    def clear_expired(self) -> None:
        """Remove expired cache entries and prune history."""
        current_time = time.time()
        cutoff = current_time - self.history_seconds

        with self.lock:
            expired_keys = [
                key for key, (_, ts) in self.cache.items() if current_time - ts >= self.ttl_seconds
            ]
            for key in expired_keys:
                self.cache.pop(key, None)
                self.history.pop(key, None)

            for key, queue in list(self.history.items()):
                while queue and queue[0][0] < cutoff:
                    queue.popleft()
                if not queue:
                    self.history.pop(key, None)

        if expired_keys:
            logger.debug("Cleared %d expired cache entries", len(expired_keys))

    def get_cache_stats(self) -> Dict:
        """Get short-term cache and history stats."""
        current_time = time.time()

        with self.lock:
            valid_entries = sum(
                1 for _, ts in self.cache.values() if current_time - ts < self.ttl_seconds
            )
            history_entries = sum(len(q) for q in self.history.values())
            total_entries = len(self.cache)

        return {
            "total_entries": total_entries,
            "valid_entries": valid_entries,
            "ttl_seconds": self.ttl_seconds,
            "history_entries": history_entries,
            "history_seconds": self.history_seconds,
        }

    def get_history(self, symbol: str, market: str, environment: str = "mainnet") -> List[Tuple[float, float]]:
        """Return rolling history for symbol within retention window."""
        key = (symbol, market, environment)
        with self.lock:
            queue = self.history.get(key)
            if not queue:
                return []
            return list(queue)


# Global price cache instance
price_cache = PriceCache(ttl_seconds=30, history_seconds=3600)


def get_cached_price(symbol: str, market: str = "CRYPTO", environment: str = "mainnet") -> Optional[float]:
    """Get price from cache if available."""
    return price_cache.get(symbol, market, environment)


def cache_price(symbol: str, market: str, price: float, environment: str = "mainnet") -> None:
    """Legacy API – record price with current timestamp."""
    price_cache.record(symbol, market, price, environment=environment)


def record_price_update(symbol: str, market: str, price: float, timestamp: Optional[float] = None, environment: str = "mainnet") -> None:
    """Explicitly record price update with optional timestamp."""
    price_cache.record(symbol, market, price, timestamp, environment)


def get_price_history(symbol: str, market: str = "CRYPTO", environment: str = "mainnet") -> List[Tuple[float, float]]:
    """Return recent price history (timestamp, price)."""
    return price_cache.get_history(symbol, market, environment)


def clear_expired_prices() -> None:
    """Clear expired price entries."""
    price_cache.clear_expired()


def get_price_cache_stats() -> Dict:
    """Get cache statistics for diagnostics."""
    return price_cache.get_cache_stats()
