"""
Background market data polling to keep cache and event stream in sync.
"""
"""
后台市场数据轮询服务

在后台线程中定期从Hyperliquid获取市场数据，保持价格缓存和
事件流的同步。这是整个交易系统实时数据的核心来源。

核心功能：
1. 价格轮询：定期获取指定交易对的最新价格
2. 缓存更新：将价格数据写入内存缓存供快速访问
3. 事件发布：通过事件系统通知所有订阅者
4. 数据持久化：将价格数据写入数据库用于历史分析

工作流程：
1. 启动后台线程，按固定间隔循环执行
2. 遍历所有监控的交易对
3. 获取每个交易对的最新价格
4. 更新价格缓存并发布事件
5. 写入数据库持久化存储
6. 等待下一个轮询周期

配置参数：
- symbols: 监控的交易对列表
- interval_seconds: 轮询间隔（默认1.5秒）
- retention_seconds: 价格数据保留时间（默认1小时）

技术特点：
- 后台线程：不阻塞主应用运行
- 平滑退出：支持优雅停止
- 动态更新：支持运行时更新交易对列表
- 错误恢复：单个交易对失败不影响其他交易对
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from database.connection import SessionLocal
from database.models import CryptoPriceTick
from services.hyperliquid_market_data import get_default_hyperliquid_client
from services.price_cache import record_price_update
from services.market_events import publish_price_update

logger = logging.getLogger(__name__)


class MarketDataStream:
    """Background thread fetching market data at a steady cadence."""
    """
    市场数据流服务类

    后台线程实现，按固定节奏从交易所获取市场数据。
    作为系统的实时数据源，为其他服务提供最新的市场信息。

    核心属性：
    - symbols: 监控的交易对列表
    - market: 市场类型（默认CRYPTO）
    - interval_seconds: 轮询间隔
    - retention_seconds: 数据保留时间

    生命周期管理：
    - start(): 启动后台数据采集线程
    - stop(): 优雅停止服务
    - update_symbols(): 动态更新监控的交易对

    数据流向：
    交易所API → 本服务 → 价格缓存 + 事件发布 + 数据库
    """

    def __init__(
        self,
        symbols: Iterable[str],
        market: str = "CRYPTO",
        interval_seconds: float = 1.5,
        retention_seconds: int = 3600,
    ) -> None:
        self.symbols = list(symbols)
        self.market = market
        self.interval_seconds = interval_seconds
        self.retention_seconds = retention_seconds
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="market-data-stream", daemon=True)
        self._thread.start()
        logger.info(
            "Market data stream started for %d symbols (interval=%.2fs)",
            len(self.symbols),
            self.interval_seconds,
        )

    def stop(self) -> None:
        if not self._thread:
            return
        self._stop_event.set()
        self._thread.join(timeout=5)
        logger.info("Market data stream stopped")

    def update_symbols(self, symbols: Iterable[str]) -> None:
        self.symbols = list(symbols)
        logger.info("Market data stream symbol set updated: %s", ", ".join(self.symbols))

    def _run(self) -> None:
        while not self._stop_event.is_set():
            start_time = time.time()
            for symbol in self.symbols:
                if self._stop_event.is_set():
                    break
                self._process_symbol(symbol)
            elapsed = time.time() - start_time
            sleep_for = max(0.0, self.interval_seconds - elapsed)
            if sleep_for > 0:
                time.sleep(sleep_for)

    def _process_symbol(self, symbol: str) -> None:
        """Fetch ticker for symbol, update cache, persist tick, publish event."""
        try:
            print(f"Fetching price for {symbol}...")
            client = get_default_hyperliquid_client()
            ticker_price = client.get_last_price(symbol)
            print(f"Got price for {symbol}: {ticker_price}")
        except Exception as fetch_err:
            logger.warning("Failed to fetch price for %s: %s", symbol, fetch_err)
            return

        if ticker_price is None:
            logger.debug("No price returned for %s", symbol)
            return

        event_time = datetime.now(tz=timezone.utc)
        timestamp = event_time.timestamp()

        record_price_update(symbol, self.market, float(ticker_price), timestamp)
        self._persist_tick(symbol, float(ticker_price), event_time)

        publish_price_update(
            {
                "symbol": symbol,
                "market": self.market,
                "price": float(ticker_price),
                "event_time": event_time,
                "timestamp": timestamp,
            }
        )

    def _persist_tick(self, symbol: str, price: float, event_time: datetime) -> None:
        """Persist tick data and prune old entries beyond retention window."""
        # DISABLED: Price data not used anywhere, only causes DB locks
        # All trading uses real-time API prices instead
        logger.debug(f"Price tick for {symbol}: {price} (DB write disabled)")
        return


# Global stream holder (initialized in startup)
market_data_stream: Optional[MarketDataStream] = None


def start_market_stream(symbols: List[str], interval_seconds: float = 1.5) -> None:
    global market_data_stream
    if market_data_stream and market_data_stream._thread and market_data_stream._thread.is_alive():
        market_data_stream.update_symbols(symbols)
        return

    market_data_stream = MarketDataStream(symbols=symbols, interval_seconds=interval_seconds)
    market_data_stream.start()


def stop_market_stream() -> None:
    global market_data_stream
    if market_data_stream:
        market_data_stream.stop()
        market_data_stream = None
