"""
Market data event dispatcher for price updates.
"""
"""
市场数据事件分发器

实现发布-订阅模式的价格更新事件分发系统，是市场数据流与各个
消费者服务之间的解耦桥梁。

核心功能：
1. 事件订阅：允许服务注册价格更新事件处理器
2. 事件发布：将价格更新事件广播给所有订阅者
3. 订阅管理：支持动态添加和移除事件处理器
4. 错误隔离：单个处理器异常不影响其他订阅者

设计模式：
- 发布-订阅模式：解耦事件生产者和消费者
- 观察者模式：支持一对多的事件通知
- 线程安全：使用锁保护订阅者列表的并发访问

事件消费者：
- 策略管理器：触发AI交易策略执行
- 程序交易服务：触发程序交易者执行
- 资产快照服务：记录账户资产变化
- 价格缓存服务：更新内存价格缓存

事件格式：
{
    "symbol": "BTC",
    "price": 95000.0,
    "event_time": "2024-01-01T12:00:00Z"
}

应用场景：
- 实时价格更新通知
- 交易触发事件传递
- 系统组件间通信
"""

from typing import Callable, List, Dict, Any
from threading import Lock

PriceEventHandler = Callable[[Dict[str, Any]], None]


class MarketEventDispatcher:
    """Simple thread-safe publish/subscribe dispatcher for market events."""
    """
    线程安全的市场事件分发器

    实现简单高效的发布-订阅机制，用于市场数据事件的分发。
    支持多线程环境下的安全订阅和事件广播。

    核心组件：
    - _handlers: 事件处理器列表
    - _lock: 线程锁，保护订阅者列表

    线程安全保证：
    - 订阅/取消订阅操作受锁保护
    - 事件发布时复制处理器列表避免竞态条件
    - 单个处理器异常不会阻塞其他订阅者
    """

    def __init__(self) -> None:
        self._handlers: List[PriceEventHandler] = []
        self._lock = Lock()

    def subscribe(self, handler: PriceEventHandler) -> None:
        """Register a handler for price update events."""
        with self._lock:
            if handler not in self._handlers:
                self._handlers.append(handler)

    def unsubscribe(self, handler: PriceEventHandler) -> None:
        """Remove a previously registered handler."""
        with self._lock:
            if handler in self._handlers:
                self._handlers.remove(handler)

    def publish(self, event: Dict[str, Any]) -> None:
        """Broadcast an event to all handlers."""
        # Copy to avoid race conditions if handlers mutate list
        handlers_snapshot: List[PriceEventHandler]
        with self._lock:
            handlers_snapshot = list(self._handlers)

        for handler in handlers_snapshot:
            try:
                handler(event)
            except Exception:
                # Handler errors should not block other subscribers
                import logging

                logger = logging.getLogger(__name__)
                logger.exception("Market event handler failed")


# Global dispatcher instance
market_event_dispatcher = MarketEventDispatcher()


def subscribe_price_updates(handler: PriceEventHandler) -> None:
    market_event_dispatcher.subscribe(handler)


def unsubscribe_price_updates(handler: PriceEventHandler) -> None:
    market_event_dispatcher.unsubscribe(handler)


def publish_price_update(event: Dict[str, Any]) -> None:
    market_event_dispatcher.publish(event)
