"""
AI Program Coding Service

Handles AI-assisted program code writing conversations using LLM.
Supports Function Calling for AI to query API docs, validate code, and test run.
"""
"""
AI程序编码服务

基于大语言模型的智能程序交易策略编码助手系统。
通过自然语言对话，帮助用户编写、调试和优化程序交易策略代码。

核心功能：
1. 智能编码助手：通过对话方式协助用户编写Python交易策略
2. 代码验证：自动检查代码语法、逻辑和API使用是否正确
3. API文档查询：AI可主动查询交易API文档和使用示例
4. 代码测试运行：在安全环境中测试代码执行效果
5. 策略优化建议：基于代码分析提供性能优化建议

设计特点：
- **对话式编程**：降低编程门槛，支持自然语言描述需求
- **智能补全**：AI理解用户意图，生成完整可用的策略代码
- **实时验证**：即时检查代码错误，减少调试时间
- **文档集成**：自动查询相关API文档，确保代码正确性
- **安全执行**：在沙盒环境中测试代码，保护系统安全

技术架构：
- LLM对话引擎：支持多轮编程对话和上下文理解
- Function Calling：AI可调用代码验证、文档查询等工具
- 代码沙盒：安全的代码执行和测试环境
- 策略管理：与数据库中的交易程序记录集成

支持的编程任务：
1. **策略逻辑编写**：基于交易思路生成策略代码
2. **指标计算实现**：编写技术指标和信号计算逻辑
3. **风险控制代码**：实现止损止盈和资金管理逻辑
4. **回测代码优化**：优化策略代码的回测性能
5. **API集成**：帮助集成市场数据和交易执行API

应用价值：
- **编程门槛降低**：非专业程序员也能开发交易策略
- **开发效率提升**：AI辅助大大加速编程进程
- **代码质量保证**：自动检查和优化确保代码质量
- **学习效果增强**：在编程过程中学习最佳实践
"""

import json
import logging
import random
import re
import requests
import time
import traceback
from typing import Dict, List, Optional, Any, Generator
from datetime import datetime

from sqlalchemy.orm import Session

from database.models import AiProgramConversation, AiProgramMessage, TradingProgram, Account
from services.ai_decision_service import build_chat_completion_endpoints, detect_api_format, _extract_text_from_message, get_max_tokens
from services.system_logger import system_logger
from services.ai_shared_tools import (
    SHARED_SIGNAL_TOOLS,
    execute_get_signal_pools,
    execute_run_signal_backtest
)

logger = logging.getLogger(__name__)

# Retry configuration for API calls
# API调用重试配置
API_MAX_RETRIES = 5                           # 最大重试次数：5次
API_BASE_DELAY = 1.0                         # 基础延迟时间：1秒
API_MAX_DELAY = 16.0                         # 最大延迟时间：16秒
RETRYABLE_STATUS_CODES = {502, 503, 504, 429} # 可重试的HTTP状态码

# 重试配置说明：
# - 最大重试5次：平衡可用性和响应时间
# - 指数退避策略：1s -> 2s -> 4s -> 8s -> 16s
# - 可重试状态码：
#   * 502 Bad Gateway: 上游服务器错误
#   * 503 Service Unavailable: 服务暂时不可用
#   * 504 Gateway Timeout: 网关超时
#   * 429 Too Many Requests: 请求频率限制


def _should_retry_api(status_code: Optional[int], error: Optional[str]) -> bool:
    """Check if API error is retryable."""
    """
    判断API错误是否应该重试

    根据HTTP状态码和错误信息判断是否为临时性错误，
    决定是否应该进行重试。避免对永久性错误的无效重试。

    Args:
        status_code: HTTP响应状态码
        error: 错误信息字符串

    Returns:
        bool: True表示应该重试，False表示不应重试

    重试判断逻辑：
    1. HTTP状态码判断：502/503/504/429为临时性错误
    2. 错误信息判断：包含网络相关关键词的错误
    3. 永久性错误：4xx客户端错误（除429外）不重试

    网络相关关键词：
    - timeout: 超时错误
    - connection: 连接错误
    - reset: 连接重置
    - eof: 文件结束/连接中断
    """
    if status_code and status_code in RETRYABLE_STATUS_CODES:
        return True  # 临时性HTTP错误，可以重试
    if error and any(x in error.lower() for x in ['timeout', 'connection', 'reset', 'eof']):
        return True  # 网络相关错误，可以重试
    return False     # 其他错误不重试


def _get_retry_delay(attempt: int) -> float:
    """Calculate retry delay with exponential backoff and jitter."""
    """
    计算重试延迟时间（指数退避 + 随机抖动）

    使用指数退避算法计算重试延迟，并加入随机抖动避免雷群效应。
    这种策略既能快速恢复，又能避免对服务器造成冲击。

    Args:
        attempt: 当前重试次数（从0开始）

    Returns:
        float: 延迟时间（秒）

    计算公式：
    1. 指数退避：delay = min(base_delay * (2^attempt), max_delay)
    2. 随机抖动：jitter = random(0, delay * 0.1)
    3. 最终延迟：delay + jitter

    示例延迟时间：
    - 第1次重试：~1.0s
    - 第2次重试：~2.1s
    - 第3次重试：~4.3s
    - 第4次重试：~8.7s
    - 第5次重试：~17.6s (max 16s + jitter)
    """
    delay = min(API_BASE_DELAY * (2 ** attempt), API_MAX_DELAY)  # 指数退避，有上限
    jitter = random.uniform(0, delay * 0.1)                     # 10%的随机抖动
    return delay + jitter


# System prompt for AI program coding
# AI程序编码系统提示词
PROGRAM_SYSTEM_PROMPT = """You are an expert Python developer for cryptocurrency trading programs.
You help users write trading strategy code that runs in a sandboxed environment.

# 该系统提示词设计了一个专业的加密货币交易程序开发专家角色
# 具有以下关键特点：
# 1. 专业身份：定位为Python交易程序开发专家
# 2. 沙盒安全：代码运行在安全的沙盒环境中
# 3. 实用导向：重点关注实际可用的交易策略代码
# 4. 标准化：提供标准的代码结构和接口规范

## CRITICAL: Query Market Data Before Writing Thresholds
**IMPORTANT**: Before writing ANY threshold comparisons in your code, you MUST use the `query_market_data` tool to check current market values. Indicator values vary significantly:
- RSI: 0-100 (oversold <30, overbought >70)
- CVD: Can range from -50M to +50M depending on market activity
- OI (Open Interest): Can be 100M to 500M+ for BTC
- ATR: Varies from 200 to 1500+ depending on volatility
- MACD: Typically -1000 to +1000 for BTC

**Example workflow**:
1. User asks for "RSI oversold strategy"
2. Call `query_market_data` with symbol="BTC" to see current RSI value (e.g., RSI14=45.2)
3. Now you know the scale and can write appropriate thresholds

## CODE STRUCTURE (REQUIRED)
Your code must define a strategy class with `should_trade` method:

```python
class MyStrategy:
    def init(self, params):
        # Initialize parameters (optional but recommended)
        self.threshold = params.get("threshold", 30)

    def should_trade(self, data):
        # Main decision logic - called when signal triggers
        # Must return a Decision object
        return Decision(
            operation="hold",
            symbol=data.trigger_symbol,
            reason="No trade condition met"
        )
```

## AVAILABLE IN SANDBOX

### Decision - Return value (REQUIRED)
```python
# For BUY (open long):
Decision(
    operation="buy",            # Required: "buy", "sell", "hold", or "close"
    symbol="BTC",               # Required: Trading symbol
    target_portion_of_balance=0.5,  # Required for buy/sell/close: 0.1-1.0
    leverage=10,                # Required for buy/sell/close: 1-50
    max_price=95000.0,          # Required for buy: maximum entry price
    time_in_force="Ioc",        # Optional: "Ioc", "Gtc", "Alo" (default: "Ioc")
    take_profit_price=100000.0, # Optional: TP trigger price
    stop_loss_price=90000.0,    # Optional: SL trigger price
    tp_execution="limit",       # Optional: "market" or "limit" (default: "limit")
    sl_execution="limit",       # Optional: "market" or "limit" (default: "limit")
    reason="RSI oversold",      # Optional: Reason for decision
    trading_strategy="..."      # Optional: Entry thesis, risk controls, exit plan
)

# For SELL (open short):
Decision(
    operation="sell",
    symbol="BTC",
    target_portion_of_balance=0.5,
    leverage=10,
    min_price=95000.0,          # Required for sell: minimum entry price
    ...
)

# For CLOSE (close position):
Decision(
    operation="close",
    symbol="BTC",
    target_portion_of_balance=1.0,  # Portion of position to close
    leverage=10,
    min_price=95000.0,          # Required for closing LONG position
    # OR max_price=95000.0,     # Required for closing SHORT position
    ...
)

# For HOLD (no action):
Decision(operation="hold", symbol="BTC", reason="No trade condition")
```

**IMPORTANT: Price Precision**
- All calculated prices (max_price, min_price, take_profit_price, stop_loss_price) should use round() to control decimal places
- Match the precision of market prices - different assets have different precision requirements
- BTC/ETH typically use 1-2 decimals, small-cap coins may need 4-8 decimals
- This ensures clean, readable prices and avoids floating-point precision issues (e.g., 93622.54776373146)

### data (MarketData) - Input parameter
```python
# Account info
data.available_balance    # float: Available balance in USD
data.total_equity         # float: Total equity (includes unrealized PnL)
data.used_margin          # float: Currently used margin
data.margin_usage_percent # float: Margin usage percentage (0-100 scale)
data.maintenance_margin   # float: Maintenance margin requirement
data.positions            # Dict[str, Position]: Current positions by symbol
data.recent_trades        # List[Trade]: Recent closed trades history
data.open_orders          # List[Order]: Current open orders (TP/SL, limit orders)

# Trigger info
data.trigger_symbol       # str: Symbol that triggered this execution (empty string "" for scheduled triggers)
data.trigger_type         # str: "signal" or "scheduled"

# Trigger context (detailed) - only populated for signal triggers
data.signal_pool_name     # str: Name of the signal pool that triggered (empty for scheduled)
data.pool_logic           # str: "OR" or "AND" - how signals in the pool are combined
data.triggered_signals    # List[Dict]: Full details of each triggered signal (see Signal section below)
data.trigger_market_regime  # RegimeInfo or None: Market regime snapshot at trigger time

# Environment info
data.environment          # str: "mainnet" or "testnet"
data.max_leverage         # int: Maximum allowed leverage for this account
data.default_leverage     # int: Default leverage setting

# Methods
data.get_indicator(symbol, indicator, period) -> dict  # Technical indicators
data.get_klines(symbol, period, count) -> list         # K-line data (default count=50)
                                                       # Example: [{"timestamp": 1768644000, "open": 95287.0, "high": 95296.0,
                                                       #            "low": 95119.0, "close": 95120.0, "volume": 259.17}, ...]
data.get_price_change(symbol, period) -> dict          # Price change info
                                                       # Example: {"change_percent": 0.0, "change_usd": 0.0}
data.get_market_data(symbol) -> dict                   # Complete market data (price, volume, OI, funding rate)
                                                       # Example: {"symbol": "BTC", "price": 95460.0, "oracle_price": 95251.0,
                                                       #           "change24h": 360.0, "volume24h": 1778510.45, "percentage24h": 0.378,
                                                       #           "open_interest": 10898599.47, "funding_rate": 0.0000425}
data.get_flow(symbol, metric, period) -> dict          # Market flow metrics
data.get_regime(symbol, period) -> RegimeInfo          # Market regime classification
```

### Position - Current position info (from data.positions)
```python
# Access: pos = data.positions.get("BTC")
pos.symbol            # str: Trading symbol
pos.side              # str: "long" or "short"
pos.size              # float: Position size
pos.entry_price       # float: Entry price
pos.unrealized_pnl    # float: Unrealized PnL
pos.leverage          # int: Leverage used
pos.liquidation_price # float: Liquidation price
# Example: Position(symbol="BTC", side="long", size=0.001, entry_price=95400.0,
#                   unrealized_pnl=0.03, leverage=1, liquidation_price=0.0)
```

### Trade - Recent trade record (from data.recent_trades)
```python
# Access: trades = data.recent_trades (list, most recent first)
trade.symbol      # str: Trading symbol
trade.side        # str: "Long" or "Short"
trade.size        # float: Trade size
trade.price       # float: Close price
trade.timestamp   # int: Close timestamp in milliseconds
trade.pnl         # float: Realized profit/loss in USD
trade.close_time  # str: Close time in UTC string format
# Example: Trade(symbol="BTC", side="Sell", size=0.001, price=95367.0,
#                timestamp=1768665292968, pnl=-0.033, close_time="2026-01-17 15:54:52 UTC")
```

### Order - Open order info (from data.open_orders)
```python
# Access: orders = data.open_orders (list of all open orders)
order.order_id       # int: Unique order ID
order.symbol         # str: Trading symbol
order.side           # str: "Buy" or "Sell"
order.direction      # str: "Open Long", "Open Short", "Close Long", "Close Short"
order.order_type     # str: Order type
                     # Possible values:
                     #   - "Market": Market order (immediate execution at best price)
                     #   - "Limit": Limit order (execute at specified price or better)
                     #   - "Stop Market": Stop loss market order (trigger → market execution)
                     #   - "Stop Limit": Stop loss limit order (trigger → limit order)
                     #   - "Take Profit Market": Take profit market order (trigger → market execution)
                     #   - "Take Profit Limit": Take profit limit order (trigger → limit order)
order.size           # float: Order size
order.price          # float: Limit price
order.trigger_price  # float: Trigger price (for stop/TP orders)
order.reduce_only    # bool: Whether this is a reduce-only order
order.timestamp      # int: Order placement timestamp in milliseconds
# Example: Order(order_id=46731293990, symbol="BTC", side="Sell", direction="Close Long",
#                order_type="Limit", size=0.001, price=76320.0, trigger_price=None,
#                reduce_only=True, timestamp=1768665293187)
```

### Kline - K-line data (from get_klines)
```python
# Access: klines = data.get_klines(symbol, "1h", 50)
kline.timestamp  # int: Unix timestamp in seconds
kline.open       # float: Open price
kline.high       # float: High price
kline.low        # float: Low price
kline.close      # float: Close price
kline.volume     # float: Volume
# Example: Kline(timestamp=1768658400, open=95673.0, high=95673.0, low=95160.0,
#                close=95400.0, volume=2.98375)
```

### RegimeInfo - Market regime (from get_regime or trigger_market_regime)
```python
# Access: regime = data.get_regime(symbol, "1h")
# Or: regime = data.trigger_market_regime (snapshot at trigger time, None for scheduled)
regime.regime     # str: "breakout", "absorption", "stop_hunt", "exhaustion", "trap", "continuation", "noise"
regime.conf       # float: Confidence 0.0-1.0
regime.direction  # str: "bullish", "bearish", "neutral"
regime.reason     # str: Human-readable explanation
regime.indicators # dict: Indicator values used for classification
# Example: RegimeInfo(regime="noise", conf=0.467, direction="neutral",
#           reason="No clear market regime detected",
#           indicators={"cvd_ratio": 0.9968, "oi_delta": 0.051, "taker_ratio": 627.585,
#                       "price_atr": -0.719, "rsi": 44.2})
```

### Signal - Triggered signal info (from data.triggered_signals)
```python
# Access: signals = data.triggered_signals (list, only populated for signal triggers)

# Supported metric types:
# - oi_delta: Open Interest change percentage
# - cvd: Cumulative Volume Delta
# - depth_ratio: Order book depth ratio (bid/ask)
# - order_imbalance: Order book imbalance (-1 to +1)
# - taker_ratio: Taker buy/sell ratio
# - funding: Funding rate change (bps)
# - oi: Open Interest change (USD)
# - price_change: Price change percentage
# - volatility: Price volatility
# - taker_volume: Taker volume (special composite signal)

# Standard signal format (all metrics except taker_volume):
signal["signal_id"]     # int: Signal ID
signal["signal_name"]   # str: Name of the signal
signal["description"]   # str: Description of what the signal detects
signal["metric"]        # str: Metric type (see list above)
signal["time_window"]   # str: Time window (e.g., "5m", "1h")
signal["operator"]      # str: Comparison operator ("<", ">", "<=", ">=", "abs_greater_than")
signal["threshold"]     # float: Threshold value
signal["current_value"] # float: Current value that triggered the signal
signal["condition_met"] # bool: Whether condition was met
# Example: {"signal_id": 31, "signal_name": "OI Delta Spike", "metric": "oi_delta",
#           "time_window": "5m", "operator": ">", "threshold": 1.0,
#           "current_value": 1.52, "condition_met": True}

# Taker volume signal format (special composite signal):
signal["signal_id"]        # int: Signal ID
signal["signal_name"]      # str: Name of the signal
signal["metric"]           # str: Always "taker_volume"
signal["time_window"]      # str: Time window
signal["direction"]        # str: "buy" or "sell" - dominant side
signal["buy"]              # float: Taker buy volume in USD
signal["sell"]             # float: Taker sell volume in USD
signal["total"]            # float: Total volume (buy + sell)
signal["ratio"]            # float: Buy/sell ratio
signal["ratio_threshold"]  # float: Threshold ratio that triggered
signal["volume_threshold"] # float: Minimum volume threshold
signal["condition_met"]    # bool: Whether condition was met
# Example: {"signal_id": 42, "signal_name": "Taker Buy Surge", "metric": "taker_volume",
#           "time_window": "5m", "direction": "buy", "buy": 5234567.89, "sell": 2345678.9,
#           "total": 7580246.79, "ratio": 2.23, "ratio_threshold": 1.5,
#           "volume_threshold": 1000000, "condition_met": True}
```

### Debug function
- log(message): Print debug message (visible in test run output)

### Available indicators for get_indicator():
- "RSI14", "RSI7" - RSI (returns {"value": float})
  Example: {"value": 46.76, "series": [50.0, 0.0, 0.0, 5.94, ...]}
- "MACD" - MACD (returns {"macd": float, "signal": float, "histogram": float})
  Example: {"macd": -73.27, "signal": -81.88, "histogram": 8.60}
- "EMA20", "EMA50", "EMA100" - EMA (returns {"value": float})
- "MA5", "MA10", "MA20" - Moving Average (returns {"value": float})
- "BOLL" - Bollinger Bands (returns {"upper": float, "middle": float, "lower": float})
- "ATR14" - Average True Range (returns {"value": float})
- "VWAP" - Volume Weighted Average Price (returns {"value": float})
- "STOCH" - Stochastic (returns {"k": float, "d": float})
- "OBV" - On Balance Volume (returns {"value": float})

### Available metrics for get_flow():
All flow metrics return a dict with `last_5` (historical values) and `period` fields for trend analysis.

**CVD** - Cumulative Volume Delta (taker buy - sell notional)
```python
data.get_flow("BTC", "CVD", "1h")
# Returns:
{
    "current": 14877256.20,      # Current period's delta (USD)
    "last_5": [11371465.41, 13850815.24, 319912.24, -13948838.70, 14877256.20],  # Last 5 periods
    "cumulative": 17906808.24,   # Cumulative sum over lookback window
    "period": "1h"
}
# Usage: Positive = net buying pressure, Negative = net selling pressure
# Trend check: if last_5[-1] > last_5[-2] > last_5[-3]: # CVD trending up
```

**OI** - Open Interest USD change
```python
data.get_flow("BTC", "OI", "1h")
# Returns:
{
    "current": 16826201.53,      # Current period's OI change (USD)
    "last_5": [-11304403.21, 974887.72, 12684888.56, -7948264.33, 16826201.53],
    "period": "1h"
}
# Usage: Positive = new positions opening, Negative = positions closing
```

**OI_DELTA** - Open Interest Change Percentage
```python
data.get_flow("BTC", "OI_DELTA", "1h")
# Returns:
{
    "current": 0.595,            # Current period's OI change (%)
    "last_5": [-0.398, 0.035, 0.449, -0.281, 0.595],
    "period": "1h"
}
# Usage: > 1% = significant new positions, < -1% = significant liquidations
```

**TAKER** - Taker Buy/Sell Volume
```python
data.get_flow("BTC", "TAKER", "1h")
# Returns:
{
    "buy": 18915411.13,          # Taker buy volume (USD)
    "sell": 4038154.92,          # Taker sell volume (USD)
    "ratio": 4.684,              # Buy/Sell ratio (>1 = buyers dominate)
    "ratio_last_5": [1.665, 2.580, 1.019, 0.663, 4.684],  # Historical ratios
    "volume_last_5": [45596648.74, 31381884.86, 34341736.69, 68742754.71, 22953566.05],
    "period": "1h"
}
# Usage: ratio > 1.5 = strong buying, ratio < 0.7 = strong selling
```

**FUNDING** - Funding Rate
```python
data.get_flow("BTC", "FUNDING", "1h")
# Returns:
{
    "current": 11.2,             # Current rate (display unit: raw × 1000000)
    "current_pct": 0.00112,      # Current rate as percentage (0.00112%)
    "change": 1.55,              # Rate change from previous period
    "change_pct": 0.000155,      # Rate change as percentage
    "last_5": [12.37, 12.5, 12.5, 9.65, 11.2],
    "annualized": 1.2264,        # Annualized rate percentage
    "period": "1h"
}
# Usage: Positive = longs pay shorts (bullish sentiment), Negative = shorts pay longs
# Signal triggers on rate CHANGE, not absolute value
```

**DEPTH** - Order Book Depth
```python
data.get_flow("BTC", "DEPTH", "1h")
# Returns:
{
    "bid": 28.34,                # Bid depth (USD millions)
    "ask": 0.04,                 # Ask depth (USD millions)
    "ratio": 635.07,             # Bid/Ask ratio (>1 = more buy orders)
    "ratio_last_5": [0.024, 0.907, 437.95, 0.033, 635.07],
    "spread": 1.0,               # Bid-ask spread
    "period": "1h"
}
# Usage: ratio > 1.5 = strong bid support, ratio < 0.7 = strong ask pressure
```

**IMBALANCE** - Order Book Imbalance
```python
data.get_flow("BTC", "IMBALANCE", "1h")
# Returns:
{
    "current": 0.997,            # Imbalance score (-1 to +1)
    "last_5": [-0.953, -0.049, 0.995, -0.936, 0.997],
    "period": "1h"
}
# Usage: > 0.3 = bullish imbalance, < -0.3 = bearish imbalance
```

### Periods: "1m", "5m", "15m", "1h", "4h"

### Multi-Timeframe Signal Pools
A single Signal Pool can contain signals with different time windows. When triggered, `data.triggered_signals` may include signals from various timeframes:

```python
# Example: Signal pool with mixed timeframes
# - CVD signal on 1m (quick momentum)
# - OI Delta signal on 5m (position building)
# - Funding signal on 1h (sentiment extreme)

for sig in data.triggered_signals:
    timeframe = sig.get("time_window")  # "1m", "5m", "1h", etc.
    metric = sig.get("metric")
    if timeframe == "1m" and metric == "cvd":
        # Fast signal - use for timing
        pass
    elif timeframe == "1h" and metric == "funding":
        # Slow signal - use for direction bias
        pass
```

### Scheduled vs Signal Trigger (IMPORTANT)
Your strategy may be triggered by signal pool or scheduled interval. Handle both cases:

| Field | Signal Trigger | Scheduled Trigger |
|-------|---------------|-------------------|
| `data.trigger_type` | `"signal"` | `"scheduled"` |
| `data.trigger_symbol` | `"BTC"` (triggered symbol) | `""` (empty string) |
| `data.triggered_signals` | `[{signal details...}]` | `[]` (empty list) |
| `data.trigger_market_regime` | `RegimeInfo(...)` | `None` |
| `data.signal_pool_name` | `"OI Surge Monitor"` | `""` (empty string) |

```python
# Example: Handle both trigger types
def should_trade(self, data):
    if data.trigger_type == "scheduled":
        # Scheduled trigger: only check exit conditions, no new entries
        # Must specify symbol explicitly since trigger_symbol is empty
        symbol = "BTC"
        if symbol in data.positions:
            # Check exit conditions...
            pass
        return Decision(operation="hold", symbol=symbol, reason="Scheduled check - no action")

    # Signal trigger: use trigger_symbol and triggered_signals
    symbol = data.trigger_symbol
    for sig in data.triggered_signals:
        if sig.get("metric") == "oi_delta" and sig.get("current_value", 0) > 1.0:
            # OI spike detected...
            pass
```

### Additional modules available
- `time`: For timestamp operations (e.g., `time.time()` returns current Unix timestamp)
- `math`: Mathematical functions (sqrt, log, exp, pow, floor, ceil, fabs)

## EXAMPLE STRATEGY
```python
class RSIStrategy:
    def init(self, params):
        self.threshold = params.get("threshold", 30)

    def should_trade(self, data):
        symbol = data.trigger_symbol
        market_data = data.get_market_data(symbol)
        price = market_data.get("price", 0)
        rsi = data.get_indicator(symbol, "RSI14", "5m")
        rsi_value = rsi.get("value", 50) if rsi else 50

        if rsi_value < self.threshold and price > 0:
            return Decision(
                operation="buy",
                symbol=symbol,
                target_portion_of_balance=0.5,
                leverage=10,
                max_price=price * 1.002,  # Allow 0.2% slippage
                take_profit_price=price * 1.05,
                stop_loss_price=price * 0.97,
                reason=f"RSI oversold: {rsi_value:.1f}"
            )

        return Decision(operation="hold", symbol=symbol)
```

## WORKFLOW
1. **FIRST**: Use `query_market_data` to check current indicator values for the target symbol
2. Use `get_current_code` to see existing code (if editing)
3. Use `get_api_docs` to check available methods if needed
4. Write code with appropriate thresholds based on queried data
5. Use `validate_code` to check syntax
6. Use `test_run_code` to test with real market data
7. If test passes, use `suggest_save_code` to propose saving

## IMPORTANT RULES
- Class must have `should_trade(self, data)` method
- `should_trade` must return a `Decision` object
- Use operation strings: "buy", "sell", "close", "hold"
- For buy/sell/close: must set target_portion_of_balance (0.1-1.0), leverage (1-50)
- For buy: must set max_price; For sell: must set min_price
- For close: set min_price (closing long) or max_price (closing short)
- Access trigger symbol via `data.trigger_symbol`
- Access balance via `data.available_balance`
- Always validate and test code before suggesting to save
"""

# Tools for AI program coding
PROGRAM_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_market_data",
            "description": "Query current market data for a symbol. MUST call this FIRST before writing any threshold comparisons to understand actual indicator value ranges.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Trading symbol (e.g., BTC, ETH)"
                    },
                    "period": {
                        "type": "string",
                        "enum": ["1m", "5m", "15m", "1h", "4h"],
                        "description": "Time period for indicators (default: 1h)"
                    }
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_api_docs",
            "description": "Get detailed documentation for MarketData properties/methods and Decision object.",
            "parameters": {
                "type": "object",
                "properties": {
                    "api_type": {
                        "type": "string",
                        "enum": ["market", "decision", "all"],
                        "description": "Which API documentation to retrieve (market=MarketData, decision=Decision/ActionType)"
                    }
                },
                "required": ["api_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_code",
            "description": "Get the current code of the program being edited. Returns empty if creating new program.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "validate_code",
            "description": "Validate Python code syntax and check for common errors.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to validate"
                    }
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "test_run_code",
            "description": "Test run code with real market data. Returns execution result or detailed error.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to test"
                    },
                    "symbol": {
                        "type": "string",
                        "description": "Symbol for market data context (e.g., BTC, ETH)"
                    }
                },
                "required": ["code", "symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_save_code",
            "description": "Propose code to save. Does NOT save directly - returns suggestion for user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Final Python code to suggest saving"
                    },
                    "name": {
                        "type": "string",
                        "description": "Suggested program name"
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of what the program does"
                    }
                },
                "required": ["code", "name", "description"]
            }
        }
    }
] + SHARED_SIGNAL_TOOLS  # Add shared signal pool tools


def _convert_tools_to_anthropic(openai_tools: List[Dict]) -> List[Dict]:
    """Convert OpenAI format tools to Anthropic format."""
    """
    将OpenAI格式的工具定义转换为Anthropic格式

    不同的AI API提供商使用不同的工具定义格式，此函数负责格式转换
    以确保Function Calling功能在不同API后端之间的兼容性。

    Args:
        openai_tools: OpenAI格式的工具定义列表
                     格式：[{"type": "function", "function": {...}}, ...]

    Returns:
        List[Dict]: Anthropic格式的工具定义列表
                   格式：[{"name": str, "description": str, "input_schema": {...}}, ...]

    格式转换对照：
    OpenAI格式：
    {
        "type": "function",
        "function": {
            "name": "tool_name",
            "description": "tool description",
            "parameters": {"type": "object", "properties": {...}}
        }
    }

    Anthropic格式：
    {
        "name": "tool_name",
        "description": "tool description",
        "input_schema": {"type": "object", "properties": {...}}
    }

    应用场景：
    - 跨API兼容：支持同一套工具在不同API后端使用
    - 动态切换：运行时根据配置的API类型进行格式转换
    - 维护简化：只需维护一套工具定义，自动转换格式
    """
    anthropic_tools = []
    for tool in openai_tools:
        if tool.get("type") == "function":
            func = tool["function"]
            anthropic_tools.append({
                "name": func["name"],
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {"type": "object", "properties": {}})
            })
    return anthropic_tools


def _convert_messages_to_anthropic(openai_messages: List[Dict]) -> tuple:
    """Convert OpenAI format messages to Anthropic format.

    Returns: (system_prompt, anthropic_messages)
    Anthropic requires system prompt to be separate from messages.
    Also, multiple consecutive tool results must be merged into one user message.
    """
    """
    将OpenAI格式的消息历史转换为Anthropic格式

    不同的AI API提供商对消息历史的格式要求不同，此函数处理格式转换
    以确保对话历史在不同API后端之间的兼容性。

    Args:
        openai_messages: OpenAI格式的消息列表
                        格式：[{"role": "system/user/assistant/tool", "content": "..."}, ...]

    Returns:
        tuple: (system_prompt: str, anthropic_messages: List[Dict])
               - system_prompt: 提取的系统提示词（Anthropic要求单独处理）
               - anthropic_messages: 转换后的消息列表

    格式差异处理：
    1. **系统消息分离**：
       - OpenAI: 系统消息混在消息列表中
       - Anthropic: 系统消息必须单独处理

    2. **工具结果合并**：
       - OpenAI: 每个工具调用结果单独一条消息
       - Anthropic: 连续的工具结果必须合并为一条用户消息

    3. **工具调用块清理**：
       - 修复某些代理服务器返回的空字符串输入问题
       - 确保工具调用参数为有效的JSON对象

    技术要点：
    - 状态机处理：跟踪待处理的工具结果
    - 动态合并：将连续的工具结果批量处理
    - 格式验证：确保工具调用块的结构正确性
    - 兼容性：处理不同代理服务器的响应差异
    """
    system_prompt = ""
    anthropic_messages = []
    pending_tool_results = []  # Collect consecutive tool results

    def flush_tool_results():
        """Flush pending tool results as a single user message."""
        nonlocal pending_tool_results
        if pending_tool_results:
            anthropic_messages.append({
                "role": "user",
                "content": pending_tool_results
            })
            pending_tool_results = []

    def clean_tool_use_blocks(blocks):
        """Clean tool_use blocks: fix input field format (some proxies return '' instead of {})."""
        if not isinstance(blocks, list):
            return blocks
        cleaned = []
        for block in blocks:
            if isinstance(block, dict):
                block_copy = block.copy()
                # Fix empty string input to empty object (Anthropic requires object, not string)
                if block_copy.get("type") == "tool_use" and block_copy.get("input") == "":
                    block_copy["input"] = {}
                cleaned.append(block_copy)
            else:
                cleaned.append(block)
        return cleaned

    for msg in openai_messages:
        role = msg.get("role")
        content = msg.get("content", "")

        if role == "system":
            system_prompt = content
        elif role == "user":
            flush_tool_results()  # Flush any pending tool results first
            anthropic_messages.append({"role": "user", "content": content})
        elif role == "assistant":
            flush_tool_results()  # Flush any pending tool results first
            # Check if this message has tool_use (from previous Anthropic response)
            if "tool_use_blocks" in msg:
                # Clean the blocks before sending back
                cleaned_blocks = clean_tool_use_blocks(msg["tool_use_blocks"])
                anthropic_messages.append({
                    "role": "assistant",
                    "content": cleaned_blocks
                })
            else:
                anthropic_messages.append({"role": "assistant", "content": content})
        elif role == "tool":
            # Collect tool results - they will be merged into one user message
            pending_tool_results.append({
                "type": "tool_result",
                "tool_use_id": msg.get("tool_call_id", ""),
                "content": content
            })

    # Flush any remaining tool results
    flush_tool_results()

    return system_prompt, anthropic_messages


def _call_anthropic_streaming(endpoint: str, payload: dict, headers: dict, timeout: int = 180) -> dict:
    """
    Call Anthropic API with streaming to avoid Cloudflare timeout.

    Streaming keeps the connection alive by sending data chunks continuously,
    preventing gateway timeouts (504) from Cloudflare or other proxies.

    Returns: dict with same structure as non-streaming response
        {"content": [...], "stop_reason": "..."}
    """
    """
    使用流式调用Anthropic API以避免Cloudflare超时

    流式传输通过持续发送数据块保持连接活跃，防止Cloudflare或其他
    代理服务器的网关超时（504错误），特别适用于长时间的AI代码生成任务。

    Args:
        endpoint: API端点URL
        payload: 请求负载数据（将被添加stream=True参数）
        headers: HTTP请求头
        timeout: 超时时间（秒），默认180秒

    Returns:
        dict: 与非流式响应相同结构的字典
              {"content": [...], "stop_reason": "..."}

    工作原理：
    1. 启用流式传输：在请求中添加stream=True参数
    2. SSE解析：解析Server-Sent Events格式的响应流
    3. 内容聚合：逐块接收并重组完整的响应内容
    4. 工具调用处理：正确处理Function Calling的流式响应

    流式传输优势：
    - 避免超时：长时间AI响应不会触发网关超时
    - 实时反馈：可以实时显示AI生成的代码（虽然当前未实现）
    - 网络稳定：减少大数据块传输失败的风险
    - 连接保活：通过持续数据流保持连接活跃

    异常处理：
    - HTTP错误：抛出包含状态码和错误信息的异常
    - JSON解析错误：忽略无效的数据行，继续处理
    - 编码问题：显式使用UTF-8解码避免编码错误
    """
    # Enable streaming
    payload = payload.copy()
    payload["stream"] = True

    content_blocks = []  # Accumulated content blocks
    current_block = None  # Current block being built
    current_block_index = -1
    stop_reason = None

    response = requests.post(endpoint, json=payload, headers=headers, timeout=timeout, stream=True)

    if response.status_code != 200:
        # Return error info for caller to handle
        raise Exception(f"HTTP {response.status_code}: {response.text[:500]}")

    # Parse SSE stream - use explicit UTF-8 decoding to avoid encoding issues
    for line_bytes in response.iter_lines():
        if not line_bytes:
            continue
        # Decode with UTF-8 explicitly
        line = line_bytes.decode('utf-8')
        if line.startswith("event:"):
            continue  # Skip event type lines, we parse data directly
        if not line.startswith("data:"):
            continue

        data_str = line[5:].strip()  # Remove "data:" prefix
        if data_str == "[DONE]":
            break

        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        event_type = data.get("type", "")

        if event_type == "content_block_start":
            # New content block starting
            current_block_index = data.get("index", 0)
            block_data = data.get("content_block", {})
            block_type = block_data.get("type", "")

            if block_type == "text":
                current_block = {"type": "text", "text": ""}
            elif block_type == "tool_use":
                current_block = {
                    "type": "tool_use",
                    "id": block_data.get("id", ""),
                    "name": block_data.get("name", ""),
                    "input": ""  # Will accumulate JSON string, parse at end
                }

        elif event_type == "content_block_delta":
            # Incremental content
            delta = data.get("delta", {})
            delta_type = delta.get("type", "")

            if delta_type == "text_delta" and current_block:
                current_block["text"] += delta.get("text", "")
            elif delta_type == "input_json_delta" and current_block:
                current_block["input"] += delta.get("partial_json", "")

        elif event_type == "content_block_stop":
            # Block complete, add to list
            if current_block:
                # Parse tool_use input from accumulated JSON string
                if current_block.get("type") == "tool_use":
                    input_str = current_block.get("input", "")
                    if input_str:
                        try:
                            current_block["input"] = json.loads(input_str)
                        except json.JSONDecodeError:
                            current_block["input"] = {}
                    else:
                        current_block["input"] = {}
                content_blocks.append(current_block)
                current_block = None

        elif event_type == "message_delta":
            # Message-level delta (contains stop_reason)
            delta = data.get("delta", {})
            stop_reason = delta.get("stop_reason")

    return {
        "content": content_blocks,
        "stop_reason": stop_reason
    }


# Anthropic format tools (pre-converted for efficiency)
PROGRAM_TOOLS_ANTHROPIC = _convert_tools_to_anthropic(PROGRAM_TOOLS)


# API Documentation content
MARKET_API_DOCS = """
## MarketData Object (passed to should_trade as 'data')

### Properties (Direct Access)
- data.available_balance: float - Available balance in USD (e.g., 10000.0)
- data.total_equity: float - Total account equity including unrealized PnL (e.g., 10250.5)
- data.used_margin: float - Currently used margin (e.g., 1500.0)
- data.margin_usage_percent: float - Margin usage percentage 0-100 (e.g., 15.0 means 15%)
- data.maintenance_margin: float - Maintenance margin requirement (e.g., 750.0)
- data.trigger_symbol: str - Symbol that triggered this evaluation (empty string "" for scheduled triggers)
- data.trigger_type: str - "signal" or "scheduled"
- data.positions: Dict[str, Position] - Current open positions (keyed by symbol)
- data.recent_trades: List[Trade] - Recent closed trades history (most recent first)
- data.open_orders: List[Order] - Current open orders (TP/SL, limit orders)

### Position Object (from data.positions)
- pos.symbol: str - Trading symbol
- pos.side: str - "long" or "short"
- pos.size: float - Position size
- pos.entry_price: float - Entry price
- pos.unrealized_pnl: float - Unrealized PnL
- pos.leverage: int - Leverage used
- pos.liquidation_price: float - Liquidation price

### Trade Object (from data.recent_trades)
- trade.symbol: str - Trading symbol (e.g., "BTC")
- trade.side: str - "Long" or "Short"
- trade.size: float - Trade size (e.g., 0.5)
- trade.price: float - Close price (e.g., 95000.0)
- trade.timestamp: int - Close timestamp in milliseconds (e.g., 1736690000000)
- trade.pnl: float - Realized profit/loss in USD (e.g., 125.50)
- trade.close_time: str - Close time in UTC string format (e.g., "2026-01-12 15:30:00 UTC")

### Order Object (from data.open_orders)
- order.order_id: int - Unique order ID (e.g., 12345678)
- order.symbol: str - Trading symbol (e.g., "BTC")
- order.side: str - "Buy" or "Sell"
- order.direction: str - "Open Long", "Open Short", "Close Long", "Close Short"
- order.order_type: str - "Limit", "Stop Limit", "Take Profit Limit"
- order.size: float - Order size (e.g., 0.1)
- order.price: float - Limit price (e.g., 95000.0)
- order.trigger_price: float - Trigger price for stop/TP orders (e.g., 94500.0)
- order.reduce_only: bool - Whether this is a reduce-only order
- order.timestamp: int - Order placement timestamp in milliseconds (e.g., 1736697952000)

### Methods

#### data.get_indicator(symbol: str, indicator: str, period: str) -> dict
Get technical indicator values.
- symbol: "BTC", "ETH", etc.
- indicator: "RSI14", "RSI7", "MA5", "MA10", "MA20", "EMA20", "EMA50", "EMA100", "MACD", "BOLL", "ATR14", "VWAP", "STOCH", "OBV"
- period: "1m", "5m", "15m", "1h", "4h"
- Returns:
  - RSI/MA/EMA/ATR/VWAP/OBV: {"value": 45.2} (float)
  - MACD: {"macd": 123.5, "signal": 98.2, "histogram": 25.3}
  - BOLL: {"upper": 96500.0, "middle": 95000.0, "lower": 93500.0}
  - STOCH: {"k": 65.3, "d": 58.7}

#### data.get_klines(symbol: str, period: str, count: int = 50) -> list
Get K-line (candlestick) data.
- symbol: "BTC", "ETH", etc.
- period: "1m", "5m", "15m", "1h", "4h"
- count: Number of candles to return (default 50)
- Returns: List of Kline objects with: timestamp (int seconds), open, high, low, close, volume (all float)

#### data.get_market_data(symbol: str) -> dict
Get complete market data (price, volume, open interest, funding rate).
**Reuses AI Trader's data layer** - same source as {BTC_market_data} variable.
- symbol: "BTC", "ETH", "SOL", etc.
- Returns: Dict with fields:
  - "symbol": "BTC"
  - "price": 95220.0 (mark price)
  - "oracle_price": 95172.0
  - "change24h": 159.0 (USD)
  - "percentage24h": 0.167 (%)
  - "volume24h": 1781547.32 (USD)
  - "open_interest": 10872198.65 (USD)
  - "funding_rate": 0.0000125
- Example: btc_data = data.get_market_data("BTC"); funding = btc_data.get("funding_rate", 0)

**IMPORTANT: Price Access**
- To get current price, use data.get_market_data(symbol) and extract the "price" field
- Example: market_data = data.get_market_data("BTC"); price = market_data.get("price", 0)
- This method returns complete market data (price, volume, OI, funding rate) in one API call
- Do NOT use data.prices (removed) - always use get_market_data() instead

#### data.get_flow(symbol: str, metric: str, period: str) -> dict
Get market flow metrics. All metrics include `last_5` for trend analysis.
- symbol: "BTC", "ETH", etc.
- metric: "CVD", "OI", "OI_DELTA", "TAKER", "FUNDING", "DEPTH", "IMBALANCE"
- period: "1m", "5m", "15m", "1h", "4h"
- Returns (with real data examples):
  - "CVD": {"current": 14877256.20, "last_5": [...], "cumulative": 17906808.24, "period": "1h"}
  - "OI": {"current": 16826201.53, "last_5": [...], "period": "1h"}
  - "OI_DELTA": {"current": 0.595, "last_5": [...], "period": "1h"} (% change)
  - "TAKER": {"buy": 18915411.13, "sell": 4038154.92, "ratio": 4.684, "ratio_last_5": [...], "volume_last_5": [...], "period": "1h"}
  - "FUNDING": {"current": 11.2, "current_pct": 0.00112, "change": 1.55, "change_pct": 0.000155, "last_5": [...], "annualized": 1.2264, "period": "1h"}
  - "DEPTH": {"bid": 28.34, "ask": 0.04, "ratio": 635.07, "ratio_last_5": [...], "spread": 1.0, "period": "1h"}
  - "IMBALANCE": {"current": 0.997, "last_5": [...], "period": "1h"} (-1 to +1)

#### data.get_regime(symbol: str, period: str) -> RegimeInfo
Get market regime classification.
- symbol: "BTC", "ETH", etc.
- period: "1m", "5m", "15m", "1h", "4h"
- Returns: RegimeInfo object
  - regime.regime: "breakout", "absorption", "stop_hunt", "exhaustion", "trap", "continuation", "noise"
  - regime.conf: 0.85 (confidence 0.0-1.0)
  - regime.direction: "bullish", "bearish", "neutral"
  - regime.reason: "Strong buying pressure with OI expansion"
  - regime.indicators: {"cvd_ratio": 0.997, "oi_delta": 0.595, "taker_ratio": 4.684, "price_atr": 0.5, "rsi": 55.2}

#### data.get_price_change(symbol: str, period: str) -> dict
Get price change over period.
- symbol: "BTC", "ETH", etc.
- period: "1m", "5m", "15m", "1h", "4h"
- Returns: {"change_percent": 2.5, "change_usd": 2350.0}

### Available in Sandbox
- time: For timestamp operations (time.time() returns Unix timestamp)
- math: sqrt, log, log10, exp, pow, floor, ceil, fabs
- log(message): Debug output function
"""

DECISION_API_DOCS = """
## Decision Object (return from should_trade)

Your should_trade method must return a Decision object:

```python
# For BUY (open long position):
return Decision(
    operation="buy",                    # Required: "buy", "sell", "close", "hold"
    symbol="BTC",                       # Required: Trading symbol
    target_portion_of_balance=0.5,      # Required: 0.1-1.0 (portion of balance to use)
    leverage=10,                        # Required: 1-50
    max_price=95000.0,                  # Required for buy: maximum entry price
    time_in_force="Ioc",                # Optional: "Ioc", "Gtc", "Alo" (default: "Ioc")
    take_profit_price=100000.0,         # Optional: TP trigger price
    stop_loss_price=90000.0,            # Optional: SL trigger price
    tp_execution="limit",               # Optional: "market" or "limit" (default: "limit")
    sl_execution="limit",               # Optional: "market" or "limit" (default: "limit")
    reason="RSI oversold",              # Optional: Reason for decision
    trading_strategy="Entry thesis..."  # Optional: Strategy description
)

# For SELL (open short position):
return Decision(
    operation="sell",
    symbol="BTC",
    target_portion_of_balance=0.5,
    leverage=10,
    min_price=95000.0,                  # Required for sell: minimum entry price
    ...
)

# For CLOSE (close existing position):
return Decision(
    operation="close",
    symbol="BTC",
    target_portion_of_balance=1.0,      # Portion of position to close
    leverage=10,
    min_price=95000.0,                  # Required for closing LONG position
    # OR max_price=95000.0,             # Required for closing SHORT position
    ...
)

# For HOLD (no action):
return Decision(operation="hold", symbol="BTC", reason="No trade condition")
```

### Operation Types
- "buy" - Open long position (requires max_price)
- "sell" - Open short position (requires min_price)
- "close" - Close existing position (requires min_price for long, max_price for short)
- "hold" - No action

### Decision Fields
| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| operation | str | Yes | - | "buy", "sell", "close", "hold" |
| symbol | str | Yes | - | Trading symbol (e.g., "BTC") |
| target_portion_of_balance | float | For buy/sell/close | 0.0 | 0.1-1.0 |
| leverage | int | For buy/sell/close | 10 | 1-50 |
| max_price | float | For buy/close short | None | Maximum entry price |
| min_price | float | For sell/close long | None | Minimum entry price |
| time_in_force | str | No | "Ioc" | "Ioc", "Gtc", "Alo" |
| take_profit_price | float | No | None | TP trigger price |
| stop_loss_price | float | No | None | SL trigger price |
| tp_execution | str | No | "limit" | "market" or "limit" |
| sl_execution | str | No | "limit" | "market" or "limit" |
| reason | str | No | "" | Reason for decision |
| trading_strategy | str | No | "" | Entry thesis, risk controls |

### Time In Force Options
- "Ioc" (Immediate or Cancel): Fill immediately or cancel unfilled portion
- "Gtc" (Good Till Cancel): Order stays in orderbook until filled or cancelled
- "Alo" (Add Liquidity Only): Maker-only order, rejected if would take liquidity
"""


def _query_market_data(db: Session, symbol: str, period: str) -> str:
    """Query current market data for AI to understand indicator value ranges."""
    try:
        from program_trader.data_provider import DataProvider
        from services.hyperliquid_market_data import get_last_price_from_hyperliquid

        data_provider = DataProvider(db=db, account_id=0, environment="mainnet")

        # Get current price
        price = get_last_price_from_hyperliquid(symbol, "mainnet")

        # Get all indicators
        indicators = {}
        for ind in ["RSI14", "RSI7", "MA5", "MA10", "MA20", "EMA20", "EMA50", "EMA100",
                    "MACD", "BOLL", "ATR14", "VWAP", "STOCH", "OBV"]:
            result = data_provider.get_indicator(symbol, ind, period)
            if result:
                indicators[ind] = result

        # Get all flow metrics
        flow_metrics = {}
        for metric in ["CVD", "OI", "OI_DELTA", "TAKER", "FUNDING", "DEPTH", "IMBALANCE"]:
            result = data_provider.get_flow(symbol, metric, period)
            if result:
                flow_metrics[metric] = result

        # Get regime
        regime = data_provider.get_regime(symbol, period)

        # Format response
        result = {
            "symbol": symbol,
            "period": period,
            "current_price": float(price) if price else None,
            "indicators": indicators,
            "flow_metrics": flow_metrics,
            "regime": {"regime": regime.regime, "confidence": regime.conf}
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)})


def _execute_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    db: Session,
    program_id: Optional[int],
    user_id: int
) -> str:
    """Execute a tool and return result as string."""
    """
    执行AI请求的工具函数并返回结果

    AI编程助手的核心执行引擎，处理AI在代码生成过程中调用的各种工具。
    通过Function Calling机制，AI可以主动查询市场数据、验证代码、测试运行等。

    Args:
        tool_name: 工具名称（如"query_market_data", "validate_code"等）
        arguments: 工具参数字典，由AI生成
        db: 数据库会话
        program_id: 编辑中的程序ID（新建程序时为None）
        user_id: 用户ID

    Returns:
        str: 工具执行结果的JSON字符串或纯文本

    支持的工具类型：
    1. **市场数据查询**：
       - query_market_data: 获取当前市场指标数据
       - 用途：AI在编写策略前了解指标数值范围

    2. **API文档查询**：
       - get_api_docs: 获取MarketData和Decision对象的详细文档
       - 用途：AI查询可用的属性和方法

    3. **代码管理**：
       - get_current_code: 获取正在编辑的程序代码
       - 用途：AI了解现有代码结构，进行针对性修改

    4. **代码验证**：
       - validate_code: 检查Python代码语法和结构
       - 用途：确保生成的代码语法正确

    5. **代码测试**：
       - test_run_code: 在安全环境中测试代码执行
       - 用途：验证代码逻辑的正确性

    6. **代码保存建议**：
       - suggest_save_code: 建议保存完成的代码
       - 用途：AI完成编程后提供保存建议

    7. **信号池工具**：
       - get_signal_pools: 查询可用的信号池
       - run_signal_backtest: 运行信号池回测
       - 用途：帮助AI了解触发条件和历史表现

    错误处理：
    - 工具不存在：返回错误信息
    - 参数错误：捕获异常并返回错误描述
    - 执行失败：记录日志并返回详细错误信息

    安全考虑：
    - 沙盒执行：代码测试在隔离环境中进行
    - 权限检查：验证用户对程序的编辑权限
    - 参数校验：防止恶意参数注入
    """
    try:
        if tool_name == "query_market_data":
            symbol = arguments.get("symbol", "BTC")
            period = arguments.get("period", "1h")
            return _query_market_data(db, symbol, period)

        elif tool_name == "get_api_docs":
            api_type = arguments.get("api_type", "all")
            if api_type == "market":
                return MARKET_API_DOCS
            elif api_type == "decision":
                return DECISION_API_DOCS
            else:
                return MARKET_API_DOCS + "\n" + DECISION_API_DOCS

        elif tool_name == "get_current_code":
            if program_id:
                program = db.query(TradingProgram).filter(
                    TradingProgram.id == program_id,
                    TradingProgram.user_id == user_id
                ).first()
                if program:
                    return f"Current program: {program.name}\n\n```python\n{program.code}\n```"
            return "No existing code. This is a new program."

        elif tool_name == "validate_code":
            code = arguments.get("code", "")
            return _validate_python_code(code)

        elif tool_name == "test_run_code":
            code = arguments.get("code", "")
            symbol = arguments.get("symbol", "BTC")
            return _test_run_code(db, code, symbol)

        elif tool_name == "suggest_save_code":
            code = arguments.get("code", "")
            name = arguments.get("name", "Untitled Program")
            description = arguments.get("description", "")
            # Return suggestion format - frontend will show confirmation dialog
            return json.dumps({
                "type": "save_suggestion",
                "code": code,
                "name": name,
                "description": description,
                "message": "Code ready to save. User confirmation required."
            })

        elif tool_name == "get_signal_pools":
            return execute_get_signal_pools(db)

        elif tool_name == "run_signal_backtest":
            pool_id = arguments.get("pool_id")
            if pool_id is None:
                return json.dumps({"error": "pool_id is required"})
            symbol = arguments.get("symbol", "BTC")
            hours = arguments.get("hours", 24)
            return execute_run_signal_backtest(db, pool_id, symbol, hours)

        else:
            return f"Unknown tool: {tool_name}"

    except Exception as e:
        logger.error(f"Tool execution error: {tool_name} - {e}")
        return f"Error executing {tool_name}: {str(e)}"


def _format_tool_calls_log(tool_calls_log: List[Dict], reasoning_snapshot: str) -> str:
    """Format tool calls log and reasoning as Markdown for storage and display.

    Interleaves reasoning and tool calls by round number for better readability.
    """
    """
    将工具调用日志和推理过程格式化为Markdown文档

    为了用户更好地理解AI的编程决策过程，此函数将工具调用历史和推理过程
    整合为可读性强的Markdown格式文档，展示AI的完整思考路径。

    Args:
        tool_calls_log: 工具调用历史列表
                       格式：[{"tool": "工具名", "args": {...}, "result": "结果"}, ...]
        reasoning_snapshot: AI推理过程快照
                          格式：包含多轮推理的长文本，以"[Round N]"分隔

    Returns:
        str: 格式化的Markdown文档字符串

    文档结构：
    1. **折叠面板**：使用<details>标签创建可折叠的分析过程面板
    2. **轮次交错**：按轮次交错显示推理和工具调用
    3. **内容摘要**：长内容自动截断并添加省略号
    4. **代码高亮**：使用```python代码块高亮显示代码

    格式化特点：
    - **推理内容**：每轮AI的思考过程（限制500字符）
    - **工具调用**：工具名称、参数、执行结果
    - **代码展示**：完整显示代码参数，其他参数摘要显示
    - **结果预览**：限制结果显示长度，避免文档过长

    应用场景：
    - **调试分析**：用户查看AI的决策过程
    - **学习参考**：理解AI如何分析和解决编程问题
    - **结果存储**：保存完整的分析历史供后续查看
    - **透明性**：提供AI编程过程的完整可见性

    技术实现：
    - 轮次解析：从推理快照中提取各轮次内容
    - 安全转义：处理Markdown特殊字符避免格式错误
    - 长度控制：自动截断过长内容保持文档可读性
    """
    if not tool_calls_log and not reasoning_snapshot:
        return ""

    lines = ["<details>", "<summary>Analysis Process</summary>", ""]

    # Parse reasoning by rounds into a dict
    reasoning_by_round = {}
    if reasoning_snapshot:
        rounds = reasoning_snapshot.split("\n[Round ")
        for round_text in rounds:
            if not round_text.strip():
                continue
            if round_text.startswith("[Round "):
                round_text = round_text[7:]
            parts = round_text.split("]\n", 1)
            if len(parts) == 2:
                try:
                    round_num = int(parts[0])
                    content = parts[1].strip()
                    if len(content) > 500:
                        content = content[:500] + "..."
                    content = content.replace("```", "'''")
                    reasoning_by_round[round_num] = content
                except ValueError:
                    pass

    # Determine max round from both sources
    max_round = 0
    if reasoning_by_round:
        max_round = max(max_round, max(reasoning_by_round.keys()))
    if tool_calls_log:
        max_round = max(max_round, len(tool_calls_log))

    # Interleave by round
    tool_idx = 0
    for round_num in range(1, max_round + 1):
        # Add reasoning for this round if exists
        if round_num in reasoning_by_round:
            lines.append(f"**Round {round_num} - Reasoning:**")
            lines.append(f"> {reasoning_by_round[round_num]}")
            lines.append("")

        # Add tool call for this round if exists
        if tool_idx < len(tool_calls_log):
            entry = tool_calls_log[tool_idx]
            tool_name = entry.get("tool", "unknown")
            args = entry.get("args", {})
            result = entry.get("result", "")

            lines.append(f"**Round {round_num} - Tool: `{tool_name}`**")
            # Include all arguments except code in one line
            args_str = ", ".join(f"{k}={v}" for k, v in args.items() if k != "code")
            if args_str:
                lines.append(f"- Arguments: {args_str}")
            # Include code separately in a code block for full context
            if "code" in args:
                code_content = args["code"]
                lines.append("- Code:")
                lines.append("```python")
                lines.append(code_content)
                lines.append("```")
            result_preview = result[:200] + "..." if len(result) > 200 else result
            result_preview = result_preview.replace("```", "'''").replace("\n", " ")
            lines.append(f"- Result: {result_preview}")
            lines.append("")
            tool_idx += 1

    lines.append("</details>")
    lines.append("")
    return "\n".join(lines)


def _validate_python_code(code: str) -> str:
    """Validate Python code using system validator."""
    """
    使用系统验证器验证Python代码

    在AI生成的代码被测试或保存之前，先进行语法和结构验证
    确保代码符合系统要求，避免运行时错误。

    Args:
        code: 待验证的Python代码字符串

    Returns:
        str: 验证结果说明
             - 成功：返回"Syntax OK"相关信息
             - 失败：返回具体的错误信息

    验证内容：
    1. **语法检查**：Python语法是否正确
    2. **结构验证**：是否包含必需的类和方法
    3. **接口规范**：should_trade方法签名是否正确
    4. **导入检查**：是否使用了未授权的模块

    应用价值：
    - **快速反馈**：在代码执行前发现基础错误
    - **安全保障**：防止恶意代码进入执行环境
    - **用户友好**：提供清晰的错误信息便于修改
    """
    from program_trader import validate_strategy_code

    result = validate_strategy_code(code)
    if result.is_valid:
        if result.warnings:
            return f"Syntax OK. Warnings: {'; '.join(result.warnings)}"
        return "Syntax OK. Code structure is valid."
    else:
        return f"Validation failed: {'; '.join(result.errors)}"


def _test_run_code(db: Session, code: str, symbol: str) -> str:
    """Test run code with real market data."""
    """
    使用真实市场数据测试运行代码

    在安全的沙盒环境中执行AI生成的交易策略代码，使用真实的市场数据
    验证代码的逻辑正确性和运行稳定性，确保策略能够正常工作。

    Args:
        db: 数据库会话
        code: 待测试的Python代码
        symbol: 测试用的交易标的（如"BTC"）

    Returns:
        str: JSON格式的测试结果
             成功：{"success": true, "decision": {...}, "message": "..."}
             失败：{"success": false, "error": "...", "traceback": "..."}

    测试环境配置：
    1. **模拟账户**：
       - 账户余额：10000 USD（模拟资金）
       - 无持仓：干净的测试环境
       - 无保证金：避免保证金计算复杂性

    2. **真实数据**：
       - 市场价格：从Hyperliquid获取真实价格
       - 技术指标：基于真实K线数据计算
       - 市场数据：包含成交量、持仓量、资金费率等

    3. **沙盒隔离**：
       - 执行超时：10秒限制防止死循环
       - 资源限制：防止恶意代码消耗系统资源
       - 网络隔离：代码无法访问外部网络

    测试流程：
    1. 创建模拟市场数据对象
    2. 在沙盒执行器中运行策略代码
    3. 捕获并解析决策结果
    4. 处理新旧Decision格式的兼容性
    5. 返回详细的测试结果

    错误处理：
    - 语法错误：Python编译失败
    - 运行时错误：代码执行异常
    - 逻辑错误：Decision对象构造错误
    - 超时错误：代码执行时间过长

    应用价值：
    - **快速验证**：在部署前验证策略逻辑
    - **真实环境**：使用真实数据避免回测偏差
    - **安全测试**：隔离环境防止影响生产系统
    - **调试支持**：提供详细的错误信息和堆栈跟踪
    """
    try:
        from program_trader.executor import SandboxExecutor
        from program_trader.models import MarketData
        from program_trader.data_provider import DataProvider

        # Create data provider with test account
        # Note: account_id=0 has no real wallet, so we use simulated account data
        # Strategy code can still call data_provider methods to get market data
        data_provider = DataProvider(db=db, account_id=0, environment="mainnet")

        # Create MarketData object with simulated account data
        market_data = MarketData(
            available_balance=10000.0,  # Simulated balance for testing
            total_equity=10000.0,
            used_margin=0.0,
            margin_usage_percent=0.0,
            maintenance_margin=0.0,
            positions={},  # No positions in test mode
            trigger_symbol=symbol,
            trigger_type="signal",
            _data_provider=data_provider,
        )

        # Create executor and run
        executor = SandboxExecutor(timeout_seconds=10)
        result = executor.execute(code, market_data, {})

        if result.success:
            decision = result.decision
            # Handle both old (action) and new (operation) Decision formats
            action_str = "none"
            if decision:
                if hasattr(decision, 'operation'):
                    action_str = decision.operation
                elif hasattr(decision, 'action'):
                    action_str = decision.action.value if hasattr(decision.action, 'value') else str(decision.action)
            return json.dumps({
                "success": True,
                "decision": decision.to_dict() if decision else None,
                "message": f"Test passed! Decision: {action_str}"
            }, indent=2)
        else:
            return json.dumps({
                "success": False,
                "error_type": "ExecutionError",
                "error": result.error,
            }, indent=2)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error_type": type(e).__name__,
            "error": str(e),
            "traceback": traceback.format_exc()[:500]
        }, indent=2)


def _extract_reasoning(message: Dict[str, Any], model: str) -> Optional[str]:
    """Extract reasoning/thinking content from AI response."""
    """
    从AI响应中提取推理/思考内容

    不同的AI模型使用不同的字段名来存储推理过程内容，
    此函数统一处理各种格式，提取AI的思考过程供分析和调试使用。

    Args:
        message: AI响应消息字典
        model: AI模型标识（用于确定提取策略）

    Returns:
        Optional[str]: 提取的推理内容，如果没有找到则返回None

    支持的推理格式：
    1. **DeepSeek格式**：
       - 字段：message.reasoning_content
       - 特点：直接包含推理文本内容

    2. **Claude格式**：
       - 字段：message.content[].thinking（thinking块）
       - 特点：结构化的thinking块数组

    3. **Qwen格式**：
       - 字段：message.thinking
       - 特点：简单的thinking字段

    应用场景：
    - **透明性**：向用户展示AI的思考过程
    - **调试分析**：理解AI决策的逻辑链条
    - **学习参考**：研究AI如何分析编程问题
    - **质量评估**：评估AI推理的质量和深度

    技术实现：
    - **格式兼容**：支持多种AI模型的推理格式
    - **安全提取**：防止字段不存在导致的异常
    - **内容验证**：确保提取的内容不为空
    """
    # DeepSeek format
    if message.get("reasoning_content"):
        return message["reasoning_content"]

    # Claude format (thinking blocks)
    content = message.get("content", [])
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "thinking":
                return block.get("thinking", "")

    # Qwen format
    if message.get("thinking"):
        return message["thinking"]

    return None


def generate_program_with_ai_stream(
    db: Session,
    account_id: int,
    user_message: str,
    conversation_id: Optional[int] = None,
    program_id: Optional[int] = None,
    user_id: int = 1
) -> Generator[str, None, None]:
    """
    Generate program code using AI with SSE streaming.
    Yields SSE events for real-time updates.
    """
    """
    使用AI生成程序代码的流式处理主函数

    这是AI编程服务的核心函数，通过Server-Sent Events (SSE)流式协议
    实现AI辅助编程的完整工作流，为用户提供实时的编程进度反馈。

    Args:
        db: 数据库会话
        account_id: AI账户ID（包含API配置信息）
        user_message: 用户的编程需求描述
        conversation_id: 可选的会话ID（继续已有会话）
        program_id: 可选的程序ID（编辑现有程序）
        user_id: 用户ID

    Yields:
        str: SSE格式的事件数据
             格式：data: {"type": "event_type", "content": "..."}\n\n

    核心工作流程：
    1. **会话管理**：
       - 获取或创建对话会话
       - 构建消息历史上下文
       - 保存用户消息到数据库

    2. **系统提示词构建**：
       - 基础编程专家系统提示词
       - 根据编辑/新建模式添加上下文
       - 动态调整AI的行为模式

    3. **API配置检测**：
       - 自动识别API格式（OpenAI/Anthropic）
       - 构建适配的请求端点
       - 设置正确的请求头和参数

    4. **多轮工具调用循环**：
       - 最多15轮的Function Calling交互
       - AI主动调用工具查询数据、验证代码
       - 实时返回工具调用进度和结果

    5. **流式响应处理**：
       - 解析AI的推理过程和工具调用
       - 处理代码保存建议
       - 格式化分析过程为Markdown文档

    6. **结果存储**：
       - 保存完整的对话历史
       - 存储工具调用日志和推理快照
       - 标记消息完成状态用于重试支持

    SSE事件类型：
    - conversation_created: 新会话创建
    - tool_round: 工具调用轮次开始
    - tool_call: 工具调用详情
    - tool_result: 工具执行结果
    - reasoning: AI推理过程（部分模型）
    - content: AI生成的文本内容
    - save_suggestion: 代码保存建议
    - retry: API重试通知
    - interrupted: 执行中断（支持重试）
    - error: 执行错误
    - done: 执行完成

    重试机制：
    - 自动重试：网络错误和临时故障
    - 指数退避：避免对API服务器造成冲击
    - 状态保存：支持从中断点恢复执行
    - 错误分类：区分可重试和不可重试的错误

    技术特点：
    - **实时反馈**：通过SSE提供即时的进度更新
    - **跨API兼容**：同时支持OpenAI和Anthropic格式API
    - **容错处理**：完善的异常处理和重试机制
    - **状态持久化**：完整保存执行过程供后续分析
    - **安全隔离**：代码在沙盒环境中执行和测试

    应用价值：
    - **用户体验**：实时反馈提升交互体验
    - **透明性**：完整展示AI的分析和编程过程
    - **可靠性**：多重容错确保服务稳定性
    - **可扩展性**：支持多种AI模型和API提供商
    """
    import requests

    start_time = time.time()
    request_id = f"program_gen_{int(start_time)}"

    logger.info(f"[AI Program {request_id}] Starting: account_id={account_id}, "
                f"conversation_id={conversation_id}, program_id={program_id}")

    try:
        # Get AI account
        account = db.query(Account).filter(
            Account.id == account_id,
            Account.account_type == "AI"
        ).first()

        if not account:
            yield f"data: {json.dumps({'type': 'error', 'content': 'AI account not found'})}\n\n"
            return

        # Get or create conversation
        conversation = None
        if conversation_id:
            conversation = db.query(AiProgramConversation).filter(
                AiProgramConversation.id == conversation_id,
                AiProgramConversation.user_id == user_id
            ).first()

        if not conversation:
            title = user_message[:50] + "..." if len(user_message) > 50 else user_message
            conversation = AiProgramConversation(
                user_id=user_id,
                program_id=program_id,
                title=title
            )
            db.add(conversation)
            db.flush()
            yield f"data: {json.dumps({'type': 'conversation_created', 'conversation_id': conversation.id})}\n\n"

        # Save user message
        user_msg = AiProgramMessage(
            conversation_id=conversation.id,
            role="user",
            content=user_message
        )
        db.add(user_msg)
        db.flush()

        # Build dynamic system prompt based on edit/new mode
        system_prompt = PROGRAM_SYSTEM_PROMPT
        if program_id:
            # Edit mode - add context about the program being edited
            program = db.query(TradingProgram).filter(
                TradingProgram.id == program_id,
                TradingProgram.user_id == user_id
            ).first()
            if program:
                system_prompt += f"""

## CURRENT CONTEXT
You are editing an existing program:
- **Program ID**: {program.id}
- **Program Name**: {program.name}
- **Description**: {program.description or 'No description'}

**IMPORTANT**: Before making any changes, you MUST first call `get_current_code` to understand the existing implementation. Then modify the code based on user's requirements while preserving the overall structure unless explicitly asked to rewrite.
"""
            else:
                system_prompt += """

## CURRENT CONTEXT
You are creating a new program. Start fresh and design the strategy based on user's requirements.
"""
        else:
            system_prompt += """

## CURRENT CONTEXT
You are creating a new program. Start fresh and design the strategy based on user's requirements.
"""

        # Build message history
        messages = [{"role": "system", "content": system_prompt}]

        history = db.query(AiProgramMessage).filter(
            AiProgramMessage.conversation_id == conversation.id,
            AiProgramMessage.id != user_msg.id
        ).order_by(AiProgramMessage.created_at).limit(10).all()

        for msg in history:
            messages.append({"role": msg.role, "content": msg.content})

        messages.append({"role": "user", "content": user_message})

        # Detect API format and build endpoints
        endpoint, api_format = detect_api_format(account.base_url)
        if not endpoint:
            yield f"data: {json.dumps({'type': 'error', 'content': 'Invalid API configuration'})}\n\n"
            return

        # For OpenAI format, use fallback endpoints; for Anthropic, use single endpoint
        if api_format == 'anthropic':
            endpoints = [endpoint]
            headers = {
                "Content-Type": "application/json",
                "x-api-key": account.api_key,
                "anthropic-version": "2023-06-01"
            }
        else:
            endpoints = build_chat_completion_endpoints(account.base_url, account.model)
            if not endpoints:
                yield f"data: {json.dumps({'type': 'error', 'content': 'Invalid API configuration'})}\n\n"
                return
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {account.api_key}"
            }

        # Tool calling loop
        max_rounds = 15
        tool_round = 0
        tool_calls_log = []
        final_content = ""
        reasoning_snapshot = ""
        code_suggestion = None

        # For Anthropic, we need to track tool_use blocks separately
        anthropic_tool_use_blocks = []

        # Create assistant message upfront with is_complete=False for retry support
        assistant_msg = AiProgramMessage(
            conversation_id=conversation.id,
            role="assistant",
            content="",  # Will be updated each round
            is_complete=False  # Mark as incomplete until done
        )
        db.add(assistant_msg)
        db.flush()

        while tool_round < max_rounds:
            tool_round += 1
            is_last = tool_round == max_rounds

            yield f"data: {json.dumps({'type': 'tool_round', 'round': tool_round, 'max': max_rounds})}\n\n"

            if api_format == 'anthropic':
                # Build Anthropic format payload
                system_prompt, anthropic_messages = _convert_messages_to_anthropic(messages)
                payload = {
                    "model": account.model,
                    "max_tokens": get_max_tokens(account.model),
                    "system": system_prompt,
                    "messages": anthropic_messages,
                }
                if not is_last:
                    payload["tools"] = PROGRAM_TOOLS_ANTHROPIC
            else:
                # OpenAI format payload
                payload = {
                    "model": account.model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": get_max_tokens(account.model),
                }
                if not is_last:
                    payload["tools"] = PROGRAM_TOOLS
                    payload["tool_choice"] = "auto"

            # Call API
            logger.info(f"[AI Program {request_id}] Round {tool_round}: Calling API with {len(endpoints)} endpoints, format={api_format}")
            if api_format == 'anthropic' and tool_round > 1:
                # Debug: log the converted messages for troubleshooting (warning level to ensure visibility)
                logger.warning(f"[AI Program {request_id}] Anthropic round {tool_round} payload messages count: {len(payload.get('messages', []))}")
                for i, m in enumerate(payload.get('messages', [])):
                    role = m.get('role', 'unknown')
                    content = m.get('content', '')
                    if isinstance(content, list):
                        content_summary = f"[{len(content)} blocks: {[b.get('type', '?') for b in content]}]"
                    else:
                        content_summary = f"str({len(str(content))} chars)"
                    logger.warning(f"[AI Program {request_id}]   msg[{i}]: role={role}, content={content_summary}")

            # API call with retry logic
            response = None
            resp_json = None  # For Anthropic streaming, we get parsed result directly
            last_error = None
            last_status_code = None

            for retry_attempt in range(API_MAX_RETRIES):
                response = None
                resp_json = None
                last_error = None

                for endpoint in endpoints:
                    try:
                        logger.info(f"[AI Program {request_id}] Trying endpoint: {endpoint}" +
                                   (f" (retry {retry_attempt + 1}/{API_MAX_RETRIES})" if retry_attempt > 0 else ""))

                        if api_format == 'anthropic':
                            # Use streaming for Anthropic to avoid Cloudflare timeout
                            resp_json = _call_anthropic_streaming(endpoint, payload, headers, timeout=180)
                            logger.info(f"[AI Program {request_id}] Anthropic streaming response received")
                            break  # Success
                        else:
                            # OpenAI format - use regular request
                            response = requests.post(endpoint, json=payload, headers=headers, timeout=120)
                            logger.info(f"[AI Program {request_id}] Response status: {response.status_code}")
                            if response.status_code != 200:
                                logger.warning(f"[AI Program {request_id}] Non-200 response from {endpoint}: {response.status_code} - {response.text[:500]}")
                                last_status_code = response.status_code
                            if response.status_code == 200:
                                break
                    except Exception as e:
                        last_error = str(e)
                        logger.warning(f"[AI Program {request_id}] Endpoint {endpoint} error: {e}")

                # Check if successful
                if api_format == 'anthropic' and resp_json:
                    break  # Anthropic streaming succeeded
                if api_format != 'anthropic' and response and response.status_code == 200:
                    break

                # Check if should retry
                if not _should_retry_api(last_status_code, last_error):
                    logger.info(f"[AI Program {request_id}] Error not retryable, giving up")
                    break

                # Check if more retries available
                if retry_attempt < API_MAX_RETRIES - 1:
                    delay = _get_retry_delay(retry_attempt)
                    logger.warning(f"[AI Program {request_id}] Retrying in {delay:.1f}s (attempt {retry_attempt + 2}/{API_MAX_RETRIES})")
                    yield f"data: {json.dumps({'type': 'retry', 'attempt': retry_attempt + 2, 'max_retries': API_MAX_RETRIES})}\n\n"
                    time.sleep(delay)

            # Check for failure
            if api_format == 'anthropic':
                if not resp_json:
                    error_detail = f"No response (last_error: {last_error})" if last_error else "No response"
                    logger.error(f"[AI Program {request_id}] API failed at round {tool_round}: {error_detail}")

                    if tool_calls_log:
                        analysis_markdown = _format_tool_calls_log(tool_calls_log, reasoning_snapshot)
                        assistant_msg.content = analysis_markdown + f"\n\n**[Interrupted at round {tool_round}]** {error_detail}"
                        assistant_msg.tool_calls_log = json.dumps(tool_calls_log)
                        assistant_msg.reasoning_snapshot = reasoning_snapshot if reasoning_snapshot else None
                        db.commit()
                        yield f"data: {json.dumps({'type': 'interrupted', 'message_id': assistant_msg.id, 'round': tool_round, 'error': error_detail})}\n\n"
                    else:
                        db.delete(assistant_msg)
                        db.commit()
                        yield f"data: {json.dumps({'type': 'error', 'content': f'API request failed: {error_detail}'})}\n\n"
                    return
            else:
                if not response or response.status_code != 200:
                    error_detail = f"No response (last_error: {last_error})" if last_error else "No response"
                    if response:
                        error_detail = f"HTTP {response.status_code}: {response.text[:500]}"
                    logger.error(f"[AI Program {request_id}] API failed at round {tool_round}: {error_detail}")

                    if tool_calls_log:
                        analysis_markdown = _format_tool_calls_log(tool_calls_log, reasoning_snapshot)
                        assistant_msg.content = analysis_markdown + f"\n\n**[Interrupted at round {tool_round}]** {error_detail}"
                        assistant_msg.tool_calls_log = json.dumps(tool_calls_log)
                        assistant_msg.reasoning_snapshot = reasoning_snapshot if reasoning_snapshot else None
                        db.commit()
                        yield f"data: {json.dumps({'type': 'interrupted', 'message_id': assistant_msg.id, 'round': tool_round, 'error': error_detail})}\n\n"
                    else:
                        db.delete(assistant_msg)
                        db.commit()
                        yield f"data: {json.dumps({'type': 'error', 'content': f'API request failed: {error_detail}'})}\n\n"
                    return
                resp_json = response.json()

            # Parse response based on API format
            if api_format == 'anthropic':
                # Anthropic response format
                content_blocks = resp_json.get("content", [])
                tool_uses = []
                content = ""

                for block in content_blocks:
                    if block.get("type") == "text":
                        content += block.get("text", "")
                    elif block.get("type") == "tool_use":
                        tool_uses.append(block)

                # No reasoning_content in Anthropic format
                reasoning_content = ""

                if tool_uses:
                    # Store the raw content blocks for message history
                    assistant_msg_dict = {
                        "role": "assistant",
                        "content": content,
                        "tool_use_blocks": content_blocks  # Store for conversion
                    }
                    messages.append(assistant_msg_dict)

                    for tu in tool_uses:
                        fn_name = tu.get("name", "")
                        fn_args = tu.get("input", {})
                        tool_use_id = tu.get("id", "")

                        # Handle empty string input (some proxies return "" instead of {})
                        if fn_args == "":
                            fn_args = {}

                        yield f"data: {json.dumps({'type': 'tool_call', 'name': fn_name, 'args': fn_args})}\n\n"

                        result = _execute_tool(fn_name, fn_args, db, program_id, user_id)
                        tool_calls_log.append({"tool": fn_name, "args": fn_args, "result": result[:1000]})

                        # Check for save suggestion
                        if fn_name == "suggest_save_code":
                            try:
                                suggestion = json.loads(result)
                                if suggestion.get("type") == "save_suggestion":
                                    code_suggestion = json.dumps({
                                        "code": suggestion.get("code", ""),
                                        "name": suggestion.get("name", ""),
                                        "description": suggestion.get("description", "")
                                    })
                                    yield f"data: {json.dumps({'type': 'save_suggestion', 'data': suggestion})}\n\n"
                            except:
                                pass

                        yield f"data: {json.dumps({'type': 'tool_result', 'name': fn_name, 'result': result[:500]})}\n\n"

                        # Add tool result in OpenAI format (will be converted for Anthropic)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_use_id,
                            "content": result
                        })
                else:
                    # No tool calls - final response
                    final_content = content or ""
                    yield f"data: {json.dumps({'type': 'content', 'content': final_content})}\n\n"
                    break
            else:
                # OpenAI format response
                message = resp_json["choices"][0]["message"]
                tool_calls = message.get("tool_calls", [])
                reasoning_content = message.get("reasoning_content", "")
                content = message.get("content", "")

                # Extract reasoning (for DeepSeek Reasoner, use reasoning_content directly)
                if reasoning_content:
                    reasoning_snapshot += f"\n[Round {tool_round}]\n{reasoning_content}"
                    yield f"data: {json.dumps({'type': 'reasoning', 'content': reasoning_content[:500]})}\n\n"
                else:
                    # Fallback for other models
                    reasoning = _extract_reasoning(message, account.model)
                    if reasoning:
                        reasoning_snapshot += f"\n[Round {tool_round}]\n{reasoning}"
                        yield f"data: {json.dumps({'type': 'reasoning', 'content': reasoning[:500]})}\n\n"

                if tool_calls:
                    # Process tool calls - MUST include reasoning_content for DeepSeek Reasoner
                    assistant_msg_dict = {
                        "role": "assistant",
                        "content": content or "",
                        "tool_calls": tool_calls
                    }
                    if reasoning_content:
                        assistant_msg_dict["reasoning_content"] = reasoning_content
                    messages.append(assistant_msg_dict)

                    for tc in tool_calls:
                        fn_name = tc["function"]["name"]
                        try:
                            fn_args = json.loads(tc["function"]["arguments"])
                        except:
                            fn_args = {}

                        yield f"data: {json.dumps({'type': 'tool_call', 'name': fn_name, 'args': fn_args})}\n\n"

                        result = _execute_tool(fn_name, fn_args, db, program_id, user_id)
                        tool_calls_log.append({"tool": fn_name, "args": fn_args, "result": result[:1000]})

                        # Check for save suggestion
                        if fn_name == "suggest_save_code":
                            try:
                                suggestion = json.loads(result)
                                if suggestion.get("type") == "save_suggestion":
                                    code_suggestion = json.dumps({
                                        "code": suggestion.get("code", ""),
                                        "name": suggestion.get("name", ""),
                                        "description": suggestion.get("description", "")
                                    })
                                    yield f"data: {json.dumps({'type': 'save_suggestion', 'data': suggestion})}\n\n"
                            except:
                                pass

                        yield f"data: {json.dumps({'type': 'tool_result', 'name': fn_name, 'result': result[:500]})}\n\n"

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result
                        })
                else:
                    # No tool calls - final response
                    final_content = content or ""
                    yield f"data: {json.dumps({'type': 'content', 'content': final_content})}\n\n"
                    break

            # Save progress after each round (for retry support)
            if tool_calls_log:
                analysis_markdown = _format_tool_calls_log(tool_calls_log, reasoning_snapshot)
                assistant_msg.content = analysis_markdown
                assistant_msg.tool_calls_log = json.dumps(tool_calls_log)
                assistant_msg.reasoning_snapshot = reasoning_snapshot if reasoning_snapshot else None
                db.commit()

        # Handle case where final_content is empty (AI ended with tool calls)
        # Same pattern as ai_signal_generation_service
        if not final_content:
            if 'message' in dir() and message:
                last_content = message.get("content", "")
                if last_content:
                    final_content = last_content
            if not final_content:
                final_content = "Processing completed."

        # Format tool calls log as Markdown for storage (same as AI Signal)
        analysis_markdown = _format_tool_calls_log(tool_calls_log, reasoning_snapshot)
        full_content_for_storage = analysis_markdown + final_content if analysis_markdown else final_content

        # Update assistant message (created at loop start) and mark as complete
        assistant_msg.content = full_content_for_storage
        assistant_msg.code_suggestion = code_suggestion
        assistant_msg.reasoning_snapshot = reasoning_snapshot if reasoning_snapshot else None
        assistant_msg.tool_calls_log = json.dumps(tool_calls_log) if tool_calls_log else None
        assistant_msg.is_complete = True
        db.commit()

        yield f"data: {json.dumps({'type': 'done', 'message_id': assistant_msg.id, 'content': full_content_for_storage, 'conversation_id': conversation.id})}\n\n"

    except Exception as e:
        logger.error(f"[AI Program {request_id}] Error: {e}")
        db.rollback()
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
