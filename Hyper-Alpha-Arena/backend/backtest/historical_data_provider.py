"""
回测历史数据提供器 (Historical Data Provider for Backtest)

为回测提供历史市场数据。
接口与DataProvider兼容，以便策略代码复用。

主要区别：
- 从数据库读取数据而非实时API
- 根据current_time_ms过滤数据（仅返回该时间之前的数据）
- 用于回测引擎模拟历史市场状态
- 追踪数据查询用于日志记录
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


class HistoricalDataProvider:
    """
    Provides historical data for backtesting.

    Key differences from DataProvider:
    - Reads from database instead of real-time API
    - Filters data by current_time_ms (only data before this time)
    - Used by backtest engine to simulate historical market state
    - Tracks data queries for logging

    为回测提供历史数据。

    与DataProvider的主要区别：
    - 从数据库读取数据而非实时API
    - 根据current_time_ms过滤数据（仅返回该时间之前的数据）
    - 用于回测引擎模拟历史市场状态
    - 追踪数据查询用于日志记录
    """

    def __init__(
        self,
        db: Session,
        symbols: List[str],
        start_time_ms: int,
        end_time_ms: int,
    ):
        """
        Initialize historical data provider.

        初始化历史数据提供器。

        Args:
            db: 数据库会话
            symbols: 要加载数据的标的列表
            start_time_ms: 回测开始时间（毫秒）
            end_time_ms: 回测结束时间（毫秒）
        """
        self.db = db
        self.symbols = symbols
        self.start_time_ms = start_time_ms
        self.end_time_ms = end_time_ms
        self.current_time_ms = start_time_ms  # 当前模拟时间

        # Caches 缓存
        self._kline_cache: Dict[str, List[Dict]] = {}  # K线缓存 {标的_周期: K线列表}
        self._flow_cache: Dict[str, Dict] = {}          # 流量数据缓存
        self._price_cache: Dict[str, float] = {}        # 价格缓存

        # Query tracking for logging 查询追踪用于日志记录
        self._query_log: List[Dict[str, Any]] = []

        # Preload data for better performance 预加载数据以提高性能
        self._preload_data()

    def _preload_data(self):
        """
        Preload all kline data for symbols to avoid repeated DB queries.
        
        预加载所有标的的K线数据，避免重复数据库查询。
        """
        logger.info(f"Preloading data for {len(self.symbols)} symbols...")

        for symbol in self.symbols:
            # Preload common periods
            for period in ["5m", "15m", "1h", "4h", "1d"]:
                self._load_klines_to_cache(symbol, period)

        logger.info(f"Preload complete. Cache size: {len(self._kline_cache)} entries")

    def set_current_time(self, timestamp_ms: int):
        """
        Set current simulation time.
        
        设置当前模拟时间。
        
        Args:
            timestamp_ms: 时间戳（毫秒）
        """
        self.current_time_ms = timestamp_ms
        # Clear price cache when time changes 时间变化时清空价格缓存
        self._price_cache = {}

    def clear_query_log(self):
        """
        Clear query log for new trigger.
        
        清空查询日志，用于新的触发事件。
        """
        self._query_log = []

    def get_query_log(self) -> List[Dict[str, Any]]:
        """
        Get list of data queries made since last clear.
        
        获取自上次清空以来的数据查询列表。
        
        Returns:
            查询日志列表
        """
        return self._query_log.copy()

    def _log_query(self, method: str, args: Dict[str, Any], result: Any):
        """Log a data query with full result for debugging.

        Args:
            method: Query method name (e.g., 'get_klines', 'get_indicator')
            args: Query arguments dict
            result: Query result (will be serialized)
        """
        self._query_log.append({
            "method": method,
            "args": args,
            "result": result
        })

    def get_current_prices(self, symbols: List[str] = None) -> Dict[str, float]:
        """
        Get current prices for symbols at current_time_ms.
        
        获取指定标的在当前模拟时间的价格。
        
        Args:
            symbols: 标的列表，如果为None则使用所有标的
            
        Returns:
            价格字典 {标的: 价格}
        """
        target_symbols = symbols or self.symbols
        prices = {}

        for symbol in target_symbols:
            if symbol in self._price_cache:
                prices[symbol] = self._price_cache[symbol]
                continue

            price = self._get_price_at_time(symbol, self.current_time_ms)
            if price:
                prices[symbol] = price
                self._price_cache[symbol] = price

        return prices

    def _get_price_at_time(self, symbol: str, timestamp_ms: int) -> Optional[float]:
        """Get price at specific timestamp from cached klines."""
        timestamp_sec = timestamp_ms // 1000
        cache_key = f"{symbol}_5m"

        # Try to get from cache first
        if cache_key in self._kline_cache:
            klines = self._kline_cache[cache_key]
            # Binary search for the closest kline <= timestamp
            for k in reversed(klines):
                if k["timestamp"] <= timestamp_sec:
                    return k["close"]
            # If no kline found before timestamp, return first available
            if klines:
                return klines[0]["close"]

        # Fallback to DB query if not in cache
        try:
            result = self.db.execute(text("""
                SELECT close_price FROM crypto_klines
                WHERE symbol = :symbol AND period = '5m'
                AND timestamp <= :ts
                ORDER BY timestamp DESC LIMIT 1
            """), {"symbol": symbol, "ts": timestamp_sec})
            row = result.fetchone()
            if row:
                return float(row[0])
        except Exception as e:
            logger.warning(f"Failed to get price for {symbol}: {e}")

        return None

    def get_klines(self, symbol: str, period: str, count: int = 50) -> List[Any]:
        """
        Get historical K-line data up to current_time_ms.

        Returns Kline objects compatible with DataProvider.

        获取截至current_time_ms的历史K线数据。

        返回与DataProvider兼容的Kline对象。

        Args:
            symbol: 交易标的
            period: K线周期（如 "5m", "1h"）
            count: 返回的K线数量
            
        Returns:
            Kline对象列表
        """
        from program_trader.models import Kline

        timestamp_sec = self.current_time_ms // 1000
        cache_key = f"{symbol}_{period}"

        # Load and cache all klines for this symbol/period if not cached
        if cache_key not in self._kline_cache:
            self._load_klines_to_cache(symbol, period)

        # Filter klines up to current time and return last 'count'
        all_klines = self._kline_cache.get(cache_key, [])
        filtered = [k for k in all_klines if k["timestamp"] <= timestamp_sec]

        # Convert to Kline objects
        result = []
        for k in filtered[-count:]:
            result.append(Kline(
                timestamp=k["timestamp"],
                open=k["open"],
                high=k["high"],
                low=k["low"],
                close=k["close"],
                volume=k["volume"],
            ))

        # Log query with result summary (last kline info)
        result_summary = None
        if result:
            last_k = result[-1]
            result_summary = {
                "count": len(result),
                "last": {"timestamp": last_k.timestamp, "close": last_k.close}
            }
        self._log_query("get_klines", {"symbol": symbol, "period": period, "count": count}, result_summary)

        return result

    def _load_klines_to_cache(self, symbol: str, period: str):
        """Load all klines for symbol/period into cache."""
        cache_key = f"{symbol}_{period}"

        # Calculate time range with buffer for indicator calculation
        # Need enough history for longest period (1d) with 500 candles
        # 500 * 86400 = 43200000 seconds = 500 days for daily candles
        # For hourly: 500 * 3600 = 1800000 seconds = ~20.8 days
        # Use period-aware buffer calculation
        period_seconds = {
            "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
            "1h": 3600, "4h": 14400, "1d": 86400
        }
        period_sec = period_seconds.get(period, 300)  # default to 5m
        buffer_seconds = 500 * period_sec

        start_sec = (self.start_time_ms // 1000) - buffer_seconds
        end_sec = self.end_time_ms // 1000

        try:
            result = self.db.execute(text("""
                SELECT timestamp, open_price, high_price, low_price, close_price, volume
                FROM crypto_klines
                WHERE symbol = :symbol AND period = :period
                AND timestamp >= :start_ts AND timestamp <= :end_ts
                ORDER BY timestamp ASC
            """), {"symbol": symbol, "period": period, "start_ts": start_sec, "end_ts": end_sec})

            klines = []
            for row in result:
                klines.append({
                    "timestamp": int(row[0]),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]) if row[5] else 0.0,
                })

            self._kline_cache[cache_key] = klines
            logger.debug(f"Loaded {len(klines)} klines for {symbol} {period}")

        except Exception as e:
            logger.error(f"Failed to load klines for {symbol} {period}: {e}")
            self._kline_cache[cache_key] = []

    def get_indicator(self, symbol: str, indicator: str, period: str) -> Dict[str, Any]:
        """
        Calculate technical indicator from historical klines.

        Uses same calculation as DataProvider for consistency.

        从历史K线计算技术指标。

        使用与DataProvider相同的计算方法以确保一致性。

        Args:
            symbol: 交易标的
            indicator: 指标名称（如 "RSI14", "MACD"）
            period: K线周期
            
        Returns:
            指标值字典
        """
        from services.technical_indicators import calculate_indicators

        # Get klines (enough for indicator calculation)
        klines = self.get_klines(symbol, period, 500)
        if not klines:
            self._log_query("get_indicator", {"symbol": symbol, "indicator": indicator, "period": period}, {})
            return {}

        # Convert to format expected by calculate_indicators
        kline_data = [
            {
                "timestamp": k.timestamp,
                "open": k.open,
                "high": k.high,
                "low": k.low,
                "close": k.close,
                "volume": k.volume,
            }
            for k in klines
        ]

        result = {}
        try:
            indicator_upper = indicator.upper()
            calculated = calculate_indicators(kline_data, [indicator_upper])

            if indicator_upper in calculated and calculated[indicator_upper] is not None:
                value = calculated[indicator_upper]
                if isinstance(value, list):
                    result = {'value': value[-1] if value else None, 'series': value}
                elif isinstance(value, dict):
                    latest = {}
                    for k, v in value.items():
                        if isinstance(v, list) and v:
                            latest[k] = v[-1]
                        else:
                            latest[k] = v
                    result = latest
                else:
                    result = {'value': value}
        except Exception as e:
            logger.warning(f"Failed to calculate {indicator} for {symbol}: {e}")

        # Log with result (exclude series to save space)
        log_result = {k: v for k, v in result.items() if k != 'series'} if result else {}
        self._log_query("get_indicator", {"symbol": symbol, "indicator": indicator, "period": period}, log_result)

        return result

    def get_flow(self, symbol: str, metric: str, period: str) -> Dict[str, Any]:
        """
        Get historical flow data (CVD, OI, TAKER, etc.).

        Queries aggregated market data tables.

        获取历史流量数据（CVD、OI、TAKER等）。

        查询聚合的市场数据表。

        Args:
            symbol: 交易标的
            metric: 指标名称（如 "CVD", "OI", "TAKER"）
            period: 时间周期
            
        Returns:
            流量数据字典
        """
        from services.market_flow_indicators import get_flow_indicators_for_prompt

        result = {}
        try:
            results = get_flow_indicators_for_prompt(
                self.db, symbol, period, [metric.upper()], self.current_time_ms
            )
            result = results.get(metric.upper(), {}) or {}
        except Exception as e:
            logger.warning(f"Failed to get flow {metric} for {symbol}: {e}")

        self._log_query("get_flow", {"symbol": symbol, "metric": metric, "period": period}, result)
        return result

    def get_regime(self, symbol: str, period: str) -> Any:
        """
        Get market regime at current time.

        Uses historical data to calculate regime.
        """
        from program_trader.models import RegimeInfo
        from services.market_regime_service import get_market_regime

        regime_info = RegimeInfo(regime="noise", conf=0.0)
        log_result = {"regime": "noise", "conf": 0.0}

        try:
            result = get_market_regime(
                self.db, symbol, period,
                use_realtime=True,
                timestamp_ms=self.current_time_ms
            )
            if result:
                regime_info = RegimeInfo(
                    regime=result.get("regime", "noise"),
                    conf=result.get("confidence", 0.0),
                    direction=result.get("direction", "neutral"),
                    reason=result.get("reason", ""),
                    indicators=result.get("indicators", {}),
                )
                log_result = {
                    "regime": regime_info.regime,
                    "conf": regime_info.conf,
                    "direction": regime_info.direction,
                    "indicators": regime_info.indicators,
                }
        except Exception as e:
            logger.warning(f"Failed to get regime for {symbol}: {e}")

        self._log_query("get_regime", {"symbol": symbol, "period": period}, log_result)
        return regime_info

    def get_price_change(self, symbol: str, period: str) -> Dict[str, float]:
        """Get price change over period.

        Returns:
            Dict with change_percent (percentage) and change_usd (absolute USD change)
        """
        from services.market_flow_indicators import get_flow_indicators_for_prompt

        result = {"change_percent": 0.0, "change_usd": 0.0}
        try:
            results = get_flow_indicators_for_prompt(
                self.db, symbol, period, ["PRICE_CHANGE"], self.current_time_ms
            )
            data = results.get("PRICE_CHANGE")
            if data:
                change_pct = data.get("current", 0.0)
                start_price = data.get("start_price", 0.0)
                end_price = data.get("end_price", 0.0)
                change_usd = (end_price - start_price) if start_price and end_price else 0.0
                result = {
                    "change_percent": change_pct,
                    "change_usd": change_usd,
                }
        except Exception:
            pass

        self._log_query("get_price_change", {"symbol": symbol, "period": period}, result)
        return result

    def get_market_data(self, symbol: str) -> Dict[str, Any]:
        """Get market data snapshot at current time."""
        price = self._get_price_at_time(symbol, self.current_time_ms)
        result = {"symbol": symbol, "price": price or 0.0}

        # Get additional data from market_asset_metrics if available
        try:
            db_result = self.db.execute(text("""
                SELECT mark_price, funding_rate, open_interest
                FROM market_asset_metrics
                WHERE symbol = :symbol AND timestamp <= :ts
                ORDER BY timestamp DESC LIMIT 1
            """), {"symbol": symbol, "ts": self.current_time_ms})
            row = db_result.fetchone()
            if row:
                result = {
                    "symbol": symbol,
                    "price": price or float(row[0] or 0),
                    "mark_price": float(row[0] or 0),
                    "funding_rate": float(row[1] or 0),
                    "open_interest": float(row[2] or 0),
                }
        except Exception as e:
            logger.warning(f"Failed to get market data for {symbol}: {e}")

        self._log_query("get_market_data", {"symbol": symbol}, result)
        return result

    def get_klines_between(
        self,
        symbol: str,
        start_time_ms: int,
        end_time_ms: int,
        period: str = "5m"
    ) -> List[Dict[str, Any]]:
        """
        Get K-lines between two timestamps for TP/SL checking.

        Returns raw dict format with high/low for checking price extremes.

        Args:
            symbol: Trading symbol
            start_time_ms: Start timestamp (exclusive, after this time)
            end_time_ms: End timestamp (inclusive, up to this time)
            period: K-line period (default 5m for balance of accuracy and performance)

        Returns:
            List of kline dicts with timestamp, high, low, close
        """
        cache_key = f"{symbol}_{period}"

        # Load cache if not exists
        if cache_key not in self._kline_cache:
            self._load_klines_to_cache(symbol, period)

        all_klines = self._kline_cache.get(cache_key, [])

        # Convert to seconds for comparison
        start_sec = start_time_ms // 1000
        end_sec = end_time_ms // 1000

        # Filter klines in range (start exclusive, end inclusive)
        result = [
            k for k in all_klines
            if start_sec < k["timestamp"] <= end_sec
        ]

        return result


