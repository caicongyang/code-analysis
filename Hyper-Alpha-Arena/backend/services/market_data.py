"""
市场数据统一接口服务

提供统一的市场数据获取接口，屏蔽底层交易所API的复杂性。
支持多交易所、多环境（测试网/主网）的数据获取和缓存管理。

核心功能：
1. 价格数据获取：实时价格、历史价格、价格缓存
2. K线数据管理：多周期K线数据获取和本地持久化
3. 市场状态监控：交易状态、流动性、成交量等
4. 多环境支持：测试网和主网数据隔离
5. 缓存策略：提高数据访问性能，减少API调用

设计特点：
- 统一接口：为上层服务提供一致的数据访问方式
- 多交易所支持：当前支持Hyperliquid，可扩展其他交易所
- 环境隔离：测试网和主网数据完全隔离
- 智能缓存：根据数据特性采用不同的缓存策略
- 容错机制：API失败时的降级和重试策略

技术架构：
- 适配器模式：封装具体交易所的API差异
- 缓存层：多级缓存提高性能
- 持久化：重要数据本地存储
- 监控：API调用性能和成功率统计
"""

from typing import Dict, List, Any
import logging
from .hyperliquid_market_data import (
    get_last_price_from_hyperliquid,      # Hyperliquid实时价格获取
    get_kline_data_from_hyperliquid,      # Hyperliquid K线数据获取
    get_market_status_from_hyperliquid,   # Hyperliquid市场状态获取
    get_all_symbols_from_hyperliquid,     # Hyperliquid所有交易对获取
    get_ticker_data_from_hyperliquid,     # Hyperliquid行情数据获取
    get_default_hyperliquid_client,       # Hyperliquid默认客户端
)

logger = logging.getLogger(__name__)


def get_last_price(symbol: str, market: str = "CRYPTO", environment: str = "mainnet") -> float:
    """
    获取最新价格（带缓存优化）

    获取指定交易对的最新价格，优先使用缓存数据以提高性能，
    缓存失效时从交易所API获取实时数据。

    Args:
        symbol: 交易标的符号（如"BTC"、"ETH"）
        market: 市场类型，默认"CRYPTO"（加密货币市场）
        environment: 交易环境，"mainnet"主网或"testnet"测试网

    Returns:
        float: 最新价格（USD计价）

    缓存策略：
    1. 首先检查内存缓存，如有有效数据直接返回
    2. 缓存失效时调用交易所API获取最新价格
    3. 将新价格存入缓存供后续使用
    4. 环境隔离：不同环境使用独立的缓存空间

    异常处理：
    - API调用失败：记录错误日志并抛出异常
    - 价格数据无效：检查价格是否大于0
    - 网络超时：依赖底层HTTP客户端的重试机制

    性能优化：
    - 缓存命中时避免API调用，响应时间从秒级降至毫秒级
    - 环境特定缓存，避免测试网和主网数据混淆
    - 调试日志记录，便于性能分析和问题排查
    """
    key = f"{symbol}.{market}.{environment}"  # 构建唯一标识符

    # Check cache first (environment-specific)
    # 优先检查缓存（环境特定）
    from .price_cache import get_cached_price, cache_price
    cached_price = get_cached_price(symbol, market, environment)
    if cached_price is not None:
        logger.debug(f"Using cached price for {key}: {cached_price}")
        return cached_price

    logger.info(f"Getting real-time price for {key} from API ({environment})...")

    try:
        # 从Hyperliquid获取实时价格
        price = get_last_price_from_hyperliquid(symbol, environment)
        if price and price > 0:
            logger.info(f"Got real-time price for {key} from Hyperliquid ({environment}): {price}")
            # Cache the price (environment-specific)
            # 缓存价格（环境特定）
            cache_price(symbol, market, price, environment)
            return price
        raise Exception(f"Hyperliquid returned invalid price: {price}")
    except Exception as hl_err:
        logger.error(f"Failed to get price from Hyperliquid ({environment}): {hl_err}")
        raise Exception(f"Unable to get real-time price for {key}: {hl_err}")


def get_kline_data(symbol: str, market: str = "CRYPTO", period: str = "1d", count: int = 100, environment: str = "mainnet", persist: bool = True) -> List[Dict[str, Any]]:
    """
    获取K线数据（支持多周期和持久化）

    获取指定交易对的历史K线数据，支持多种时间周期，
    可选择性地将数据持久化到本地数据库。

    Args:
        symbol: 交易标的符号（如"BTC"、"ETH"）
        market: 市场类型，默认"CRYPTO"
        period: K线周期（"1m"、"5m"、"15m"、"1h"、"1d"等）
        count: 获取的K线根数，默认100根
        environment: 交易环境（"mainnet"或"testnet"）
        persist: 是否持久化到数据库，默认True

    Returns:
        List[Dict]: K线数据列表，每个元素包含：
                   - timestamp: 时间戳
                   - open: 开盘价
                   - high: 最高价
                   - low: 最低价
                   - close: 收盘价
                   - volume: 成交量

    功能特点：
    1. 多周期支持：从分钟级到日级的全覆盖
    2. 环境隔离：测试网和主网数据分离存储
    3. 自动持久化：可选择性保存到本地数据库
    4. 数据验证：确保返回数据的完整性和有效性

    使用场景：
    - 技术指标计算：为RSI、MACD等指标提供数据源
    - 策略回测：历史数据分析和策略验证
    - 价格走势分析：图表展示和趋势识别
    - 机器学习训练：价格预测模型的特征工程

    性能考虑：
    - 大量数据请求可能较慢，建议合理设置count参数
    - 持久化可能增加响应时间，但提供数据一致性保证
    - 频繁调用建议配合缓存机制使用
    """
    key = f"{symbol}.{market}.{environment}"  # 构建数据标识符

    try:
        # 从Hyperliquid获取K线数据
        data = get_kline_data_from_hyperliquid(symbol, period, count, persist=persist, environment=environment)
        if data:
            logger.info(f"Got K-line data for {key} from Hyperliquid ({environment}), total {len(data)} items")
            return data
        raise Exception("Hyperliquid returned empty K-line data")
    except Exception as hl_err:
        logger.error(f"Failed to get K-line data from Hyperliquid ({environment}): {hl_err}")
        raise Exception(f"Unable to get K-line data for {key}: {hl_err}")


def get_market_status(symbol: str, market: str = "CRYPTO") -> Dict[str, Any]:
    key = f"{symbol}.{market}"

    try:
        status = get_market_status_from_hyperliquid(symbol)
        logger.info(f"Retrieved market status for {key} from Hyperliquid: {status.get('market_status')}")
        return status
    except Exception as hl_err:
        logger.error(f"Failed to get market status: {hl_err}")
        raise Exception(f"Unable to get market status for {key}: {hl_err}")


def get_all_symbols() -> List[str]:
    """Get all available trading pairs"""
    try:
        symbols = get_all_symbols_from_hyperliquid()
        logger.info(f"Got {len(symbols)} trading pairs from Hyperliquid")
        return symbols
    except Exception as hl_err:
        logger.error(f"Failed to get trading pairs list: {hl_err}")
        return ['BTC/USD', 'ETH/USD', 'SOL/USD']  # default trading pairs


def get_ticker_data(symbol: str, market: str = "CRYPTO", environment: str = "mainnet") -> Dict[str, Any]:
    """Get complete ticker data including 24h change and volume"""
    key = f"{symbol}.{market}.{environment}"
    logger.info(f"[DEBUG] get_ticker_data called for {key} in {environment}")

    try:
        logger.info(f"[DEBUG] Calling get_ticker_data_from_hyperliquid for {symbol} in {environment}")
        ticker_data = get_ticker_data_from_hyperliquid(symbol, environment)
        logger.info(f"[DEBUG] get_ticker_data_from_hyperliquid returned: {ticker_data}")
        if ticker_data:
            logger.info(f"Got ticker data for {key}: price={ticker_data['price']}, change24h={ticker_data['change24h']}")
            return ticker_data
        raise Exception("Hyperliquid returned empty ticker data")
    except Exception as hl_err:
        logger.error(f"Failed to get ticker data from Hyperliquid ({environment}): {hl_err}")
        # Fallback to price-only data
        logger.info(f"[DEBUG] Falling back to price-only data for {key}")
        try:
            price = get_last_price(symbol, market, environment)
            fallback_data = {
                'symbol': symbol,
                'price': price,
                'change24h': 0,
                'volume24h': 0,
                'percentage24h': 0,
            }
            logger.info(f"[DEBUG] Returning fallback data for {key}: {fallback_data}")
            return fallback_data
        except Exception:
            raise Exception(f"Unable to get ticker data for {key}: {hl_err}")
