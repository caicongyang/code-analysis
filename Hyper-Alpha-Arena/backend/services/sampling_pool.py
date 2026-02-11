"""
Unified sampling pool for AI decision making
"""
"""
统一的采样池 - 为AI决策提供价格样本数据

为AI交易决策系统提供价格采样和历史数据管理服务。
通过滑动窗口机制维护每个交易标的的近期价格样本，
支持价格变化分析、趋势检测和决策上下文构建。

核心功能：
1. 价格采样管理：为每个交易标的维护价格样本队列
2. 滑动窗口：使用固定大小的队列自动淘汰旧样本
3. 采样频率控制：基于时间间隔控制采样频率
4. 价格变化分析：计算价格变化百分比和趋势
5. 多标的支持：同时管理多个交易对的价格数据

设计特点：
- **内存高效**：使用deque实现固定大小的滑动窗口
- **时间感知**：每个样本包含时间戳和UTC时间
- **配置灵活**：支持每个标的独立配置样本数量
- **性能优化**：O(1)的插入和获取操作
- **监控友好**：提供完整的池状态监控接口

技术实现：
- 基于collections.deque的高效队列操作
- 时间戳和datetime对象的双重时间记录
- 字典结构支持多标的并行管理
- 配置参数的动态更新和生效

应用场景：
- **AI决策上下文**：为AI提供近期价格变化情况
- **趋势分析**：计算短期价格趋势和波动性
- **采样控制**：按固定间隔采集价格避免过度采样
- **监控统计**：实时监控各标的的价格变化状况
"""
import time
from collections import deque
from typing import Dict, Optional, List
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

class SamplingPool:
    """
    价格采样池管理器

    为多个交易标的维护价格样本的统一管理器。每个标的拥有独立的
    滑动窗口队列，支持灵活的样本数量配置和高效的数据操作。

    核心组件：
    1. **样本池字典** (pools)：存储每个标的的价格样本队列
    2. **配置管理** (max_samples_per_symbol)：每个标的的样本数量限制
    3. **时间跟踪** (last_sample_time)：每个标的的最后采样时间
    4. **默认配置** (default_max_samples)：新标的的默认样本数量

    数据结构：
    - pools: {symbol: deque([sample1, sample2, ...])}
    - sample: {"price": float, "timestamp": float, "datetime": datetime}

    生命周期管理：
    - 自动创建：首次添加样本时自动创建标的池
    - 自动淘汰：队列满时自动删除最旧的样本
    - 配置更新：支持运行时动态调整样本数量
    """

    def __init__(self, default_max_samples: int = 10):
        """
        初始化采样池管理器

        Args:
            default_max_samples: 默认每个标的保存的样本数量
                               影响滑动窗口的大小和内存使用

        初始化的数据结构：
        - pools: 空字典，标的池将在首次使用时创建
        - max_samples_per_symbol: 空字典，支持每个标的独立配置
        - last_sample_time: 空字典，用于采样频率控制

        默认样本数选择：
        - 10个样本：平衡内存使用和数据充分性
        - 可以覆盖约3-5分钟的价格变化（18秒间隔）
        - 足够进行短期趋势分析和价格变化计算
        """
        self.pools: Dict[str, deque] = {}                 # 各标的的样本池
        self.max_samples_per_symbol: Dict[str, int] = {}  # 每个标的的样本数限制
        self.default_max_samples = default_max_samples    # 默认样本数量
        self.last_sample_time: Dict[str, float] = {}      # 最后采样时间记录

    def set_max_samples(self, symbol: str, max_samples: int):
        """Set maximum samples for a specific symbol"""
        """
        设置指定标的的最大样本数量

        为特定交易标的配置独立的样本数量限制，支持运行时动态调整。
        不同的交易标的可能需要不同的样本深度来进行有效的分析。

        Args:
            symbol: 交易标的符号（如"BTC", "ETH"）
            max_samples: 最大样本数量，必须>=1

        Raises:
            ValueError: 当max_samples小于1时抛出

        配置更新策略：
        1. **参数验证**：确保样本数量合法（>=1）
        2. **配置存储**：更新标的的个性化配置
        3. **队列重建**：如果标的池已存在，使用新配置重建队列
        4. **数据保留**：重建时保留现有样本（在新限制范围内）

        使用场景：
        - **高频标的**：活跃交易标的可能需要更多样本
        - **低频标的**：不活跃标的可以使用较少样本
        - **策略调整**：根据策略需求动态调整分析窗口
        - **内存优化**：为不重要的标的减少内存使用

        注意事项：
        - 减少样本数时会丢弃最旧的样本
        - 增加样本数时保留所有现有样本
        - 配置立即生效，影响后续的样本管理
        """
        if max_samples < 1:
            raise ValueError(f"max_samples must be >= 1, got {max_samples}")

        self.max_samples_per_symbol[symbol] = max_samples

        # If pool already exists, recreate it with new maxlen
        if symbol in self.pools:
            old_samples = list(self.pools[symbol])
            self.pools[symbol] = deque(old_samples, maxlen=max_samples)
            logger.info(f"Updated sampling depth for {symbol}: {max_samples} samples")

    def get_max_samples(self, symbol: str) -> int:
        """Get maximum samples configured for a symbol"""
        """
        获取指定标的的最大样本数量配置

        查询特定标的的样本数量限制，如果未单独配置则返回默认值。
        用于确定滑动窗口的大小和内存分配。

        Args:
            symbol: 交易标的符号

        Returns:
            int: 该标的的最大样本数量
                 - 如果有个性化配置，返回配置值
                 - 否则返回默认样本数量

        应用场景：
        - **池创建**：创建新标的池时确定队列大小
        - **状态查询**：检查标的的配置信息
        - **容量计算**：计算内存使用和数据容量
        - **配置验证**：验证当前的配置状态

        设计理念：
        - 优先级：个性化配置 > 默认配置
        - 一致性：确保所有标的都有明确的样本限制
        - 简化调用：调用方无需关心配置的存在性
        """
        return self.max_samples_per_symbol.get(symbol, self.default_max_samples)

    def add_sample(self, symbol: str, price: float, timestamp: Optional[float] = None):
        """Add price sample to symbol pool"""
        """
        向指定标的的采样池添加价格样本

        核心的数据输入接口，将新的价格样本添加到对应标的的滑动窗口中。
        自动处理池的创建、时间戳生成和样本格式化。

        Args:
            symbol: 交易标的符号（如"BTC", "ETH"）
            price: 价格数据（浮点数）
            timestamp: 可选的时间戳，默认使用当前时间

        样本数据结构：
        {
            'price': float,              # 价格数据
            'timestamp': float,          # Unix时间戳（秒）
            'datetime': datetime         # UTC datetime对象
        }

        处理流程：
        1. **时间戳处理**：
           - 如果未提供时间戳，使用当前系统时间
           - 确保所有样本都有准确的时间信息

        2. **池管理**：
           - 如果标的池不存在，自动创建新池
           - 使用该标的配置的最大样本数量
           - 新池使用deque的maxlen特性自动限制大小

        3. **样本构造**：
           - 创建包含价格和时间信息的样本字典
           - 同时存储timestamp（计算用）和datetime（显示用）
           - 使用UTC时区确保时间的一致性

        4. **数据更新**：
           - 将样本添加到池的末尾（最新位置）
           - 更新该标的的最后采样时间记录
           - 如果池已满，最旧的样本会被自动淘汰

        自动化特性：
        - **惰性创建**：首次使用时才创建标的池
        - **自动淘汰**：超过限制时自动删除最旧样本
        - **时间管理**：自动处理时间戳的生成和格式转换

        应用场景：
        - **价格采集**：实时价格数据的持续采集
        - **批量导入**：历史数据的批量导入（提供timestamp）
        - **监控更新**：定期的价格监控和记录
        """
        if timestamp is None:
            timestamp = time.time()

        # Get max samples for this symbol
        max_samples = self.get_max_samples(symbol)

        # Create pool if not exists
        if symbol not in self.pools:
            self.pools[symbol] = deque(maxlen=max_samples)

        # Add sample
        sample = {
            'price': price,
            'timestamp': timestamp,
            'datetime': datetime.fromtimestamp(timestamp, tz=timezone.utc)
        }

        self.pools[symbol].append(sample)
        self.last_sample_time[symbol] = timestamp

    def get_samples(self, symbol: str) -> List[Dict]:
        """Get all samples for symbol"""
        """
        获取指定标的的所有样本数据

        返回标的池中的完整样本列表，用于分析和计算。
        返回的是副本，对返回数据的修改不会影响原始池。

        Args:
            symbol: 交易标的符号

        Returns:
            List[Dict]: 样本数据列表，按时间顺序排序（最旧到最新）
                       如果标的不存在，返回空列表

        样本格式：
        [
            {
                'price': 95000.0,
                'timestamp': 1640995200.0,
                'datetime': datetime(2022, 1, 1, 0, 0, tzinfo=timezone.utc)
            },
            ...
        ]

        应用场景：
        - **趋势分析**：分析价格的变化趋势和模式
        - **统计计算**：计算均值、方差、波动率等统计指标
        - **数据导出**：将样本数据提供给外部分析系统
        - **调试诊断**：检查采样数据的完整性和正确性

        性能考虑：
        - 返回副本保护原始数据不被意外修改
        - 对于大量样本，考虑内存占用
        - 安全处理不存在的标的，返回空列表而非异常
        """
        return list(self.pools.get(symbol, []))

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """Get latest price for symbol"""
        """
        获取指定标的的最新价格

        快速获取标的池中最近添加的价格样本，常用于当前价格查询。
        这是最频繁使用的查询接口之一。

        Args:
            symbol: 交易标的符号

        Returns:
            Optional[float]: 最新价格，如果标的不存在或池为空则返回None

        实现逻辑：
        1. 检查标的池是否存在
        2. 检查池是否包含样本数据
        3. 返回队列末尾（最新）样本的价格

        应用场景：
        - **当前价格**：获取最新的市场价格
        - **价格监控**：实时监控价格变化
        - **决策输入**：为交易决策提供当前价格基准
        - **状态检查**：验证价格数据的可用性

        性能特点：
        - O(1)时间复杂度：直接访问队列末尾
        - 空安全：妥善处理不存在或空池的情况
        - 轻量级：只返回价格数值，不包含时间信息
        """
        if symbol in self.pools and self.pools[symbol]:
            return self.pools[symbol][-1]['price']
        return None

    def should_sample(self, symbol: str, interval_seconds: int = 18) -> bool:
        """Check if should add new sample based on interval"""
        """
        检查是否应该为指定标的添加新样本

        基于时间间隔的采样频率控制，避免过度采样造成数据冗余和资源浪费。
        实现智能的采样节流机制。

        Args:
            symbol: 交易标的符号
            interval_seconds: 采样间隔（秒），默认18秒

        Returns:
            bool: True表示应该采样，False表示应该跳过

        判断逻辑：
        1. **首次采样**：如果从未采样过，返回True
        2. **间隔检查**：计算距离上次采样的时间间隔
        3. **阈值比较**：间隔超过设定值时允许新采样

        间隔选择（18秒默认值）：
        - 平衡数据时效性和存储效率
        - 10个样本可覆盖约3分钟的价格变化
        - 适合短期趋势分析和价格波动监控
        - 避免过于频繁的采样增加存储负担

        应用场景：
        - **采样控制**：在数据收集循环中控制采样频率
        - **资源节约**：避免不必要的数据存储和处理
        - **数据质量**：保持合适的时间粒度用于分析
        - **系统性能**：减少频繁的数据操作

        使用示例：
        ```python
        if sampling_pool.should_sample("BTC", 18):
            sampling_pool.add_sample("BTC", current_price)
        ```
        """
        if symbol not in self.last_sample_time:
            return True
        return time.time() - self.last_sample_time[symbol] >= interval_seconds

    def get_price_change_percent(self, symbol: str) -> Optional[float]:
        """Calculate price change percentage from oldest to latest sample"""
        """
        计算指定标的从最旧样本到最新样本的价格变化百分比

        这是核心的价格分析功能，计算采样窗口内的总体价格变化。
        用于趋势判断和价格波动分析。

        Args:
            symbol: 交易标的符号

        Returns:
            Optional[float]: 价格变化百分比
                           - 正值表示价格上涨
                           - 负值表示价格下跌
                           - None表示数据不足或计算无效

        计算公式：
        price_change% = (latest_price - oldest_price) / oldest_price * 100

        数据有效性检查：
        1. **池存在性**：检查标的池是否存在
        2. **样本充足性**：至少需要2个样本才能计算变化
        3. **除零保护**：oldest_price为0时返回None避免除零错误

        应用场景：
        - **趋势分析**：判断短期价格趋势方向
        - **波动监控**：监控价格波动的幅度
        - **交易信号**：价格变化可作为交易信号的一部分
        - **风险评估**：评估价格变化的风险水平

        结果解读：
        - > 5%：显著上涨
        - 1% ~ 5%：温和上涨
        - -1% ~ 1%：横盘整理
        - -5% ~ -1%：温和下跌
        - < -5%：显著下跌

        时间窗口：
        取决于采样池的大小和采样间隔
        默认配置(10样本×18秒)覆盖约3分钟的价格变化
        """
        if symbol not in self.pools or len(self.pools[symbol]) < 2:
            return None

        oldest_price = self.pools[symbol][0]['price']
        latest_price = self.pools[symbol][-1]['price']

        if oldest_price == 0:
            return None

        return ((latest_price - oldest_price) / oldest_price) * 100

    def get_pool_status(self) -> Dict:
        """Get status of all pools for monitoring"""
        """
        获取所有采样池的状态信息用于监控

        全面的系统状态查询接口，提供所有标的池的详细状态信息。
        用于系统监控、调试和运营管理。

        Returns:
            Dict: 标的状态字典，键为标的符号，值为状态信息
                 状态信息包含以下字段：
                 - sample_count: 当前样本数量
                 - latest_price: 最新价格
                 - latest_time: 最新采样时间(ISO格式)
                 - oldest_time: 最旧采样时间(ISO格式)
                 - price_change_percent: 价格变化百分比(保留2位小数)

        返回数据结构：
        {
            "BTC": {
                "sample_count": 10,
                "latest_price": 95000.0,
                "latest_time": "2022-01-01T12:00:00+00:00",
                "oldest_time": "2022-01-01T11:57:00+00:00",
                "price_change_percent": 1.25
            },
            "ETH": {
                "sample_count": 0,  # 空池情况
                "latest_price": None,
                "latest_time": None,
                "oldest_time": None,
                "price_change_percent": None
            }
        }

        状态字段说明：
        1. **样本统计**：
           - sample_count: 池中当前的样本数量
           - 反映数据的完整程度

        2. **价格信息**：
           - latest_price: 最新价格数据
           - 用于实时价格显示

        3. **时间范围**：
           - latest_time/oldest_time: 采样的时间范围
           - ISO格式便于前端解析和显示

        4. **变化分析**：
           - price_change_percent: 窗口内的价格变化
           - 保留2位小数提高可读性

        应用场景：
        - **系统监控**：实时监控各标的的数据状态
        - **调试分析**：诊断数据收集和处理问题
        - **运营管理**：了解系统的整体运行状况
        - **前端展示**：为管理界面提供状态数据

        特殊处理：
        - 空池安全：妥善处理没有样本的标的
        - 时间格式：使用ISO标准格式便于解析
        - 数值精度：价格变化保留合适的精度
        """
        status = {}
        for symbol, pool in self.pools.items():
            if pool:
                price_change = self.get_price_change_percent(symbol)
                status[symbol] = {
                    'sample_count': len(pool),
                    'latest_price': pool[-1]['price'],
                    'latest_time': pool[-1]['datetime'].isoformat(),
                    'oldest_time': pool[0]['datetime'].isoformat(),
                    'price_change_percent': round(price_change, 2) if price_change else None
                }
            else:
                status[symbol] = {
                    'sample_count': 0,
                    'latest_price': None,
                    'latest_time': None,
                    'oldest_time': None,
                    'price_change_percent': None
                }
        return status

# Global sampling pool instance
# 全局采样池实例
sampling_pool = SamplingPool()

# 全局采样池说明：
# - 单例模式：整个应用共享同一个采样池实例
# - 统一管理：所有标的的价格样本都在这个实例中管理
# - 内存高效：避免创建多个采样池实例
# - 便于访问：各个服务模块可以直接导入使用
#
# 使用方式：
# from services.sampling_pool import sampling_pool
# sampling_pool.add_sample("BTC", 95000.0)
# price_change = sampling_pool.get_price_change_percent("BTC")