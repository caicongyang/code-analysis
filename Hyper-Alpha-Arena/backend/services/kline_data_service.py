"""
K线数据统一服务层 - 提供统一的数据操作接口
"""
"""
K线数据统一服务层（扩展版说明）

为整个交易系统提供统一的K线数据访问接口，屏蔽不同交易所API的差异。
这是技术指标计算、策略回测、市场分析等功能的数据基础设施。

核心功能：
1. 多交易所支持：统一接口访问不同交易所的K线数据
2. 数据缓存管理：本地数据库缓存，减少API调用频率
3. 实时数据获取：支持实时K线数据获取和更新
4. 批量数据处理：支持大批量历史数据的高效获取
5. 数据质量保证：自动验证和修复数据完整性

设计架构：
- **适配器模式**：为不同交易所提供统一的数据访问接口
- **策略模式**：根据配置动态选择数据源采集器
- **缓存策略**：多级缓存提高数据访问性能
- **异步处理**：支持异步数据获取，避免阻塞主线程

支持的交易所：
- Hyperliquid：去中心化永续合约交易所（默认）
- Binance：全球最大的加密货币交易所
- OKX：主流加密货币交易所
- 可扩展：支持添加新的交易所数据源

数据流处理：
1. 用户配置：读取用户选择的交易所偏好
2. 采集器初始化：创建对应交易所的数据采集器
3. 数据获取：从交易所API获取K线数据
4. 数据存储：将数据持久化到本地数据库
5. 数据查询：为上层服务提供高效的数据查询接口

性能优化：
- 启动时初始化：避免运行时的重复初始化开销
- 数据预取：预先获取常用的K线数据
- 增量更新：只获取新增的K线数据
- 并发处理：支持多标的并行数据获取

应用场景：
1. **技术指标计算**：为RSI、MACD等指标提供价格数据
2. **策略回测**：为历史策略回测提供完整的价格序列
3. **实时分析**：为实时策略执行提供最新的价格数据
4. **图表展示**：为前端图表组件提供K线数据
5. **市场研究**：为量化研究提供高质量的历史数据

数据质量保证：
- 数据完整性检查：检测缺失的时间段并自动补齐
- 异常值处理：识别和处理异常的价格数据
- 时间同步：确保不同来源数据的时间一致性
- 精度控制：保证价格数据的精度要求
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

from database.connection import SessionLocal
from database.models import CryptoKline, UserExchangeConfig, KlineCollectionTask
from .kline_collectors import ExchangeDataSourceFactory, BaseKlineCollector, KlineData

logger = logging.getLogger(__name__)


class KlineDataService:
    """K线数据统一服务 - 启动时确定交易所，后续不再判断"""
    """
    K线数据统一服务类

    采用单例模式的K线数据服务，在系统启动时确定数据源交易所，
    后续所有K线数据请求都使用同一个数据源，确保数据一致性。

    设计特点：
    - 启动初始化：系统启动时读取配置并初始化数据源
    - 配置驱动：根据用户配置动态选择交易所数据源
    - 状态缓存：避免重复初始化和配置查询开销
    - 异常安全：初始化失败时使用默认配置

    核心属性：
    - exchange_id: 当前使用的交易所标识符
    - collector: 对应交易所的K线数据采集器实例
    - _initialized: 初始化状态标志，防止重复初始化

    生命周期：
    1. 对象创建：创建服务实例但不进行初始化
    2. 配置读取：从数据库读取用户选择的交易所配置
    3. 采集器创建：基于配置创建对应的数据采集器
    4. 服务就绪：服务可以开始处理K线数据请求
    """

    def __init__(self):
        """
        初始化K线数据服务实例

        创建服务实例但不立即进行配置加载，支持延迟初始化。
        这种设计允许在系统完全启动后再进行数据源配置。
        """
        self.exchange_id: Optional[str] = None              # 交易所标识符
        self.collector: Optional[BaseKlineCollector] = None # 数据采集器实例
        self._initialized = False                           # 初始化状态标志

    async def initialize(self):
        """初始化服务 - 读取用户配置并确定交易所"""
        """
        异步初始化服务

        从数据库读取用户配置，确定要使用的交易所，并创建对应的
        数据采集器实例。支持幂等调用，重复调用不会产生副作用。

        初始化流程：
        1. 检查是否已初始化，避免重复执行
        2. 从数据库读取用户交易所配置
        3. 根据配置创建对应的数据采集器
        4. 标记为已初始化状态

        配置优先级：
        - 用户配置：优先使用用户在界面中选择的交易所
        - 系统默认：如无配置则使用Hyperliquid作为默认交易所

        异常处理：
        - 数据库连接失败：记录错误并使用默认配置
        - 采集器创建失败：抛出异常，需要修复配置
        """
        if self._initialized:
            return  # 避免重复初始化

        try:
            # 从数据库读取用户选择的交易所
            with SessionLocal() as db:
                config = db.query(UserExchangeConfig).filter(
                    UserExchangeConfig.user_id == 1  # 假设单用户系统
                ).first()

                if config:
                    self.exchange_id = config.selected_exchange  # 用户自定义配置
                else:
                    self.exchange_id = "hyperliquid"             # 默认使用Hyperliquid

            # 初始化对应的采集器
            self.collector = ExchangeDataSourceFactory.get_collector(self.exchange_id)
            self._initialized = True  # 标记为已初始化

            logger.info(f"KlineDataService initialized with exchange: {self.exchange_id}")

        except Exception as e:
            logger.error(f"Failed to initialize KlineDataService: {e}")
            # 使用默认配置
            self.exchange_id = "hyperliquid"
            self.collector = ExchangeDataSourceFactory.get_collector(self.exchange_id)
            self._initialized = True

    def _ensure_initialized(self):
        """确保服务已初始化"""
        if not self._initialized:
            raise RuntimeError("KlineDataService not initialized. Call initialize() first.")

    async def collect_current_kline(self, symbol: str, period: str = "1m") -> bool:
        """采集当前分钟的K线数据"""
        self._ensure_initialized()

        try:
            # 使用已确定的采集器获取数据
            kline_data = await self.collector.fetch_current_kline(symbol, period)
            if not kline_data:
                logger.warning(f"No kline data received for {symbol}")
                return False

            # 插入数据库（自动去重）
            return await self._insert_kline_data([kline_data])

        except Exception as e:
            logger.error(f"Failed to collect current kline for {symbol}: {e}")
            return False

    async def collect_historical_klines(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        period: str = "1m"
    ) -> int:
        """采集历史K线数据，返回成功插入的记录数"""
        self._ensure_initialized()

        try:
            # 使用已确定的采集器获取历史数据
            klines_data = await self.collector.fetch_historical_klines(
                symbol, start_time, end_time, period
            )

            if not klines_data:
                logger.warning(f"No historical klines received for {symbol}")
                return 0

            # 批量插入数据库
            success = await self._insert_kline_data(klines_data)
            return len(klines_data) if success else 0

        except Exception as e:
            logger.error(f"Failed to collect historical klines for {symbol}: {e}")
            return 0

    async def _insert_kline_data(self, klines_data: List[KlineData]) -> bool:
        """批量插入K线数据到数据库（自动去重）"""
        if not klines_data:
            return True

        try:
            with SessionLocal() as db:
                for kline in klines_data:
                    # Generate datetime_str from timestamp (UTC)
                    datetime_str = datetime.utcfromtimestamp(kline.timestamp).strftime('%Y-%m-%d %H:%M:%S')

                    # 使用原生SQL的ON CONFLICT DO NOTHING实现去重
                    # NOTE: K线数据库只存储 mainnet 数据，testnet 数据实时获取不存储
                    db.execute(text("""
                        INSERT INTO crypto_klines (
                            exchange, symbol, market, timestamp, period, datetime_str,
                            open_price, high_price, low_price, close_price, volume,
                            environment, created_at
                        ) VALUES (
                            :exchange, :symbol, :market, :timestamp, :period, :datetime_str,
                            :open_price, :high_price, :low_price, :close_price, :volume,
                            'mainnet', CURRENT_TIMESTAMP
                        ) ON CONFLICT (exchange, symbol, market, period, timestamp, environment) DO NOTHING
                    """), {
                        'exchange': kline.exchange,
                        'symbol': kline.symbol,
                        'market': 'CRYPTO',
                        'timestamp': kline.timestamp,
                        'period': kline.period,
                        'datetime_str': datetime_str,
                        'open_price': kline.open_price,
                        'high_price': kline.high_price,
                        'low_price': kline.low_price,
                        'close_price': kline.close_price,
                        'volume': kline.volume
                    })

                db.commit()
                logger.debug(f"Inserted {len(klines_data)} klines for {klines_data[0].symbol}")
                return True

        except Exception as e:
            logger.error(f"Failed to insert kline data: {e}")
            return False

    async def get_data_coverage(self, symbols: List[str] = None) -> List[Dict[str, Any]]:
        """获取数据覆盖情况"""
        self._ensure_initialized()

        try:
            with SessionLocal() as db:
                query = """
                    SELECT * FROM kline_coverage_stats
                    WHERE exchange = :exchange
                """
                params = {'exchange': self.exchange_id}

                if symbols:
                    query += " AND symbol = ANY(:symbols)"
                    params['symbols'] = symbols

                query += " ORDER BY symbol, period"

                result = db.execute(text(query), params)
                return [dict(row._mapping) for row in result]

        except Exception as e:
            logger.error(f"Failed to get data coverage: {e}")
            return []

    async def detect_missing_ranges(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        period: str = "1m"
    ) -> List[tuple]:
        """检测缺失的数据时间段"""
        self._ensure_initialized()

        try:
            with SessionLocal() as db:
                # 获取现有的时间戳
                result = db.execute(text("""
                    SELECT timestamp FROM crypto_klines
                    WHERE exchange = :exchange AND symbol = :symbol
                    AND period = :period AND timestamp BETWEEN :start_ts AND :end_ts
                    ORDER BY timestamp
                """), {
                    'exchange': self.exchange_id,
                    'symbol': symbol,
                    'period': period,
                    'start_ts': int(start_time.timestamp()),
                    'end_ts': int(end_time.timestamp())
                })

                existing_timestamps = {row[0] for row in result}

                # 生成期望的时间戳序列（1分钟间隔）
                expected_timestamps = []
                current = start_time
                while current <= end_time:
                    expected_timestamps.append(int(current.timestamp()))
                    current += timedelta(minutes=1)

                # 找出缺失的时间段
                missing_ranges = []
                range_start = None

                for ts in expected_timestamps:
                    if ts not in existing_timestamps:
                        if range_start is None:
                            range_start = ts
                    else:
                        if range_start is not None:
                            missing_ranges.append((
                                datetime.fromtimestamp(range_start),
                                datetime.fromtimestamp(ts - 60)  # 前一分钟
                            ))
                            range_start = None

                # 处理最后一个缺失段
                if range_start is not None:
                    missing_ranges.append((
                        datetime.fromtimestamp(range_start),
                        end_time
                    ))

                return missing_ranges

        except Exception as e:
            logger.error(f"Failed to detect missing ranges: {e}")
            return []

    def get_supported_symbols(self) -> List[str]:
        """获取当前交易所支持的交易对"""
        self._ensure_initialized()
        return self.collector.get_supported_symbols()

    async def refresh_exchange_config(self):
        """刷新交易所配置（当用户切换交易所时调用）"""
        self._initialized = False
        await self.initialize()


# 全局服务实例
kline_service = KlineDataService()