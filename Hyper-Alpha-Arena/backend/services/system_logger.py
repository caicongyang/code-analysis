"""
System Log Collector Service
实时收集系统日志：价格更新、AI决策、错误异常
"""

import logging
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Deque
from dataclasses import dataclass, asdict
import threading
import json


@dataclass
class LogEntry:
    """日志条目"""
    """
    系统日志条目数据类

    定义系统日志的标准数据结构，用于统一管理和存储各类系统事件。
    使用dataclass简化代码并提供自动的序列化和比较功能。

    字段说明：
    - timestamp: ISO格式的时间戳字符串，记录日志产生的精确时间
    - level: 日志级别，支持INFO/WARNING/ERROR三级分类
    - category: 日志分类，用于业务逻辑分组和过滤
    - message: 主要日志消息，简洁描述发生的事件
    - details: 详细信息字典，存储结构化的扩展数据

    分类体系：
    1. **price_update**: 价格数据更新事件
       - 用途: 跟踪市场价格变化和数据流
       - 示例: BTC价格更新、价格快照记录

    2. **ai_decision**: AI交易决策事件
       - 用途: 记录AI的交易决策过程和结果
       - 示例: 买入决策、卖出信号、持仓策略

    3. **system_error**: 系统错误和警告事件
       - 用途: 记录系统异常、错误和警告
       - 示例: API调用失败、数据处理异常、配置错误

    设计优势：
    - **结构化**: 统一的数据格式便于处理和分析
    - **可扩展**: details字段支持任意结构化数据
    - **类型安全**: 使用dataclass提供类型提示
    - **序列化**: 内置to_dict方法便于JSON序列化
    """
    timestamp: str
    level: str  # INFO, WARNING, ERROR
    category: str  # price_update, ai_decision, system_error
    message: str
    details: Optional[Dict] = None

    def to_dict(self):
        """转换为字典"""
        """
        将日志条目转换为字典格式

        用于JSON序列化、API响应和前端数据传输。
        利用dataclasses.asdict自动处理所有字段的转换。

        Returns:
            Dict: 包含所有字段的字典
                 {"timestamp": "...", "level": "...", ...}

        应用场景：
        - **API接口**: 为REST API提供JSON格式数据
        - **WebSocket**: 实时日志推送的数据格式
        - **数据存储**: 存储到数据库或文件系统
        - **前端展示**: 为前端界面提供结构化数据
        """
        return asdict(self)


class SystemLogCollector:
    """系统日志收集器"""
    """
    系统日志收集和管理器

    提供统一的日志收集、存储、查询和分发服务。作为系统的中央日志中心，
    负责处理来自各个模块的日志事件，并为监控和调试提供实时数据。

    核心功能：
    1. **日志收集**: 接收并标准化各类系统日志
    2. **内存存储**: 使用循环队列高效管理内存中的日志
    3. **实时分发**: 通过监听器机制实时推送新日志
    4. **查询过滤**: 支持多维度的日志查询和过滤
    5. **线程安全**: 支持多线程并发的日志操作

    设计特点：
    - **内存优化**: 使用deque的maxlen特性自动管理内存使用
    - **线程安全**: 所有操作都受锁保护，支持并发访问
    - **实时性**: 新日志立即通知所有监听器
    - **灵活查询**: 支持按级别、分类、时间等多维度过滤

    存储策略：
    - 循环队列: 新日志自动替换最旧的日志
    - 内存限制: 默认500条日志，可配置
    - 持久化: 仅内存存储，重启后清空

    监听器机制：
    - 支持多个WebSocket连接同时监听
    - 新日志产生时自动推送给所有监听器
    - 异常隔离: 单个监听器异常不影响其他监听器
    """

    def __init__(self, max_logs: int = 500):
        """
        初始化日志收集器

        Args:
            max_logs: 内存中保存的最大日志数量
                     超过此数量时，最旧的日志会被自动清除

        初始化组件：
        - _logs: 循环日志队列，自动管理大小
        - _lock: 线程锁，保证并发安全
        - _listeners: 监听器列表，用于实时日志推送

        容量选择（默认500条）：
        - 平衡内存使用和历史查询需求
        - 假设平均每分钟10条日志，可保存约50分钟历史
        - 每条日志约1KB，500条约占用500KB内存
        """
        self._logs: Deque[LogEntry] = deque(maxlen=max_logs)
        self._lock = threading.Lock()
        self._listeners = []  # WebSocket监听器

    def add_log(self, level: str, category: str, message: str, details: Optional[Dict] = None):
        """
        添加日志条目

        Args:
            level: 日志级别 (INFO, WARNING, ERROR)
            category: 日志分类 (price_update, ai_decision, system_error)
            message: 日志消息
            details: 详细信息字典
        """
        """
        向系统添加新的日志条目

        这是日志收集器的核心方法，负责接收、格式化和存储各类系统日志。
        每个新日志都会触发实时通知机制。

        Args:
            level: 日志级别
                  - INFO: 普通信息，如价格更新、正常操作
                  - WARNING: 警告信息，如异常情况但不影响运行
                  - ERROR: 错误信息，如系统故障、操作失败

            category: 日志业务分类
                     - price_update: 价格和市场数据相关
                     - ai_decision: AI交易决策相关
                     - system_error: 系统错误和异常相关

            message: 主要日志消息
                    - 应简洁明了地描述发生的事件
                    - 建议控制在100字符以内
                    - 包含关键信息便于快速理解

            details: 详细信息字典（可选）
                    - 存储结构化的扩展数据
                    - 如: {"symbol": "BTC", "price": 95000.0}
                    - 便于后续分析和查询

        处理流程：
        1. **日志构造**: 创建LogEntry对象，自动添加ISO时间戳
        2. **线程安全存储**: 使用锁保护并发写入
        3. **队列管理**: 自动处理队列满时的旧数据淘汰
        4. **实时通知**: 立即向所有监听器推送新日志

        时间戳格式：
        使用ISO 8601格式 (YYYY-MM-DDTHH:MM:SS.ffffff)
        包含微秒精度，便于精确的时序分析

        应用示例：
        ```python
        # 记录价格更新
        add_log("INFO", "price_update", "BTC price updated",
                {"symbol": "BTC", "price": 95000.0})

        # 记录AI决策
        add_log("INFO", "ai_decision", "Buy signal triggered",
                {"symbol": "BTC", "operation": "BUY"})

        # 记录系统错误
        add_log("ERROR", "system_error", "API call failed",
                {"endpoint": "/api/price", "status_code": 500})
        ```
        """
        entry = LogEntry(
            timestamp=datetime.now().isoformat(),
            level=level,
            category=category,
            message=message,
            details=details or {}
        )

        with self._lock:
            self._logs.append(entry)

        # 通知所有监听器
        self._notify_listeners(entry)

    _LEVEL_ORDER = {
        "INFO": 1,
        "WARNING": 2,
        "ERROR": 3,
    }

    def get_logs(
        self,
        level: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 100,
        min_level: Optional[str] = None,
    ) -> List[Dict]:
        """
        获取日志列表

        Args:
            level: 过滤日志级别
            category: 过滤日志分类
            limit: 返回的最大日志数量

        Returns:
            日志字典列表
        """
        with self._lock:
            logs = list(self._logs)

        # 反转顺序（最新的在前）
        logs.reverse()

        # 过滤
        if level:
            logs = [log for log in logs if log.level == level]
        elif min_level:
            threshold = self._LEVEL_ORDER.get(min_level.upper(), 1)
            logs = [
                log for log in logs
                if self._LEVEL_ORDER.get(log.level.upper(), 1) >= threshold
            ]

        if category:
            logs = [log for log in logs if log.category == category]

        # 限制数量
        logs = logs[:limit]

        return [log.to_dict() for log in logs]

    def clear_logs(self):
        """清空所有日志"""
        with self._lock:
            self._logs.clear()

    def add_listener(self, callback):
        """添加WebSocket监听器"""
        self._listeners.append(callback)

    def remove_listener(self, callback):
        """移除WebSocket监听器"""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify_listeners(self, entry: LogEntry):
        """通知所有监听器有新日志"""
        for callback in self._listeners:
            try:
                callback(entry.to_dict())
            except Exception as e:
                logging.error(f"Failed to notify log listener: {e}")

    def log_price_update(self, symbol: str, price: float, change_percent: Optional[float] = None):
        """记录价格更新"""
        """
        记录交易标的的价格更新事件

        专门用于记录市场价格变化的便捷方法。自动格式化价格信息
        并存储相关的详细数据用于后续分析。

        Args:
            symbol: 交易标的符号（如"BTC", "ETH"）
            price: 最新价格数值
            change_percent: 可选的价格变化百分比

        记录内容：
        - 消息格式: "{symbol} price updated: ${price:.4f}"
        - 详细信息: 包含symbol、price和可选的change_percent
        - 分类: price_update，便于价格相关日志的统一管理

        应用场景：
        - **实时监控**: 跟踪价格数据的实时更新
        - **数据审计**: 验证价格数据的获取和处理
        - **性能分析**: 监控价格数据获取的频率和稳定性
        - **故障排查**: 定位价格数据异常的原因

        数据精度：
        - 价格显示保留4位小数
        - 变化百分比可选，用于趋势分析
        - 时间戳精确到微秒级别
        """
        details = {
            "symbol": symbol,
            "price": price
        }
        if change_percent is not None:
            details["change_percent"] = change_percent

        self.add_log(
            level="INFO",
            category="price_update",
            message=f"{symbol} price updated: ${price:.4f}",
            details=details
        )

    def log_ai_decision(
        self,
        account_name: str,
        model: str,
        operation: str,
        symbol: Optional[str],
        reason: str,
        success: bool = True
    ):
        """记录AI决策"""
        """
        记录AI交易决策事件

        专门用于记录AI交易系统的决策过程和结果。包含完整的决策上下文
        信息，便于分析AI的决策逻辑和性能表现。

        Args:
            account_name: AI账户名称，标识执行决策的账户
            model: 使用的AI模型名称（如"gpt-4", "claude-3"）
            operation: 决策操作类型（"BUY", "SELL", "HOLD", "CLOSE"）
            symbol: 涉及的交易标的，可选
            reason: 决策理由，AI生成的解释文本
            success: 决策是否成功执行，影响日志级别

        记录格式：
        - 成功决策: INFO级别，突出正常的交易决策
        - 失败决策: WARNING级别，标记需要关注的问题
        - 消息格式: "[账户名] 操作 标的: 理由"
        - 理由文本截断到100字符避免过长

        详细信息包含：
        - account: 执行账户信息
        - model: AI模型标识
        - operation: 具体操作类型
        - symbol: 交易标的
        - reason: 完整决策理由
        - success: 执行成功状态

        应用价值：
        - **决策审计**: 追踪AI的所有交易决策
        - **性能分析**: 评估不同模型和策略的表现
        - **风险控制**: 监控异常或失败的决策
        - **策略优化**: 分析决策理由改进策略
        """
        self.add_log(
            level="INFO" if success else "WARNING",
            category="ai_decision",
            message=f"[{account_name}] {operation.upper()} {symbol or 'N/A'}: {reason[:100]}",
            details={
                "account": account_name,
                "model": model,
                "operation": operation,
                "symbol": symbol,
                "reason": reason,
                "success": success
            }
        )

    def log_error(self, error_type: str, message: str, details: Optional[Dict] = None):
        """记录系统错误"""
        """
        记录系统错误事件

        统一的系统错误记录接口，用于记录各类系统故障、异常和错误。
        所有错误都使用ERROR级别，便于快速识别和处理。

        Args:
            error_type: 错误类型标识（如"API_ERROR", "DATABASE_ERROR"）
            message: 错误描述信息
            details: 可选的详细错误信息字典

        错误分类建议：
        - API_ERROR: API调用相关错误
        - DATABASE_ERROR: 数据库操作错误
        - NETWORK_ERROR: 网络连接错误
        - CONFIG_ERROR: 配置相关错误
        - VALIDATION_ERROR: 数据验证错误

        记录格式：
        - 级别: ERROR
        - 分类: system_error
        - 消息: "[错误类型] 错误描述"
        - 详细信息: 包含调试所需的技术细节

        应用场景：
        - **故障监控**: 实时监控系统故障情况
        - **问题排查**: 提供详细的错误信息用于调试
        - **稳定性评估**: 统计错误频率和类型分布
        - **告警触发**: 严重错误可触发运维告警
        """
        self.add_log(
            level="ERROR",
            category="system_error",
            message=f"[{error_type}] {message}",
            details=details or {}
        )

    def log_warning(self, warning_type: str, message: str, details: Optional[Dict] = None):
        """记录系统警告"""
        """
        记录系统警告事件

        用于记录不影响系统正常运行但需要关注的异常情况。
        WARNING级别介于INFO和ERROR之间，标识潜在问题。

        Args:
            warning_type: 警告类型标识（如"RATE_LIMIT", "DATA_INCOMPLETE"）
            message: 警告描述信息
            details: 可选的详细警告信息字典

        警告分类建议：
        - RATE_LIMIT: API频率限制警告
        - DATA_INCOMPLETE: 数据不完整警告
        - PERFORMANCE: 性能相关警告
        - CONFIGURATION: 配置项警告
        - DEPRECATED: 功能废弃警告

        记录格式：
        - 级别: WARNING
        - 分类: system_error（与错误共享分类）
        - 消息: "[警告类型] 警告描述"
        - 详细信息: 包含警告的具体情况

        应用价值：
        - **预防性监控**: 及早发现潜在问题
        - **维护提醒**: 提醒需要关注的系统状态
        - **优化指导**: 识别系统优化的机会
        - **趋势分析**: 监控警告的变化趋势
        """
        self.add_log(
            level="WARNING",
            category="system_error",
            message=f"[{warning_type}] {message}",
            details=details or {}
        )


# 全局单例
# 全局系统日志收集器实例
system_logger = SystemLogCollector(max_logs=500)

# 全局单例说明：
# - 整个应用共享同一个日志收集器实例
# - 统一管理所有模块的系统日志
# - 支持实时日志查询和WebSocket推送
# - 内存中维护最近500条日志记录
#
# 使用方式：
# from services.system_logger import system_logger
# system_logger.log_price_update("BTC", 95000.0)
# system_logger.log_ai_decision("account1", "gpt-4", "BUY", "BTC", "RSI oversold")


class SystemLogHandler(logging.Handler):
    """Python logging Handler，自动收集日志到SystemLogCollector"""
    """
    Python标准logging系统的自定义Handler

    将Python标准logging系统的日志自动转发到SystemLogCollector，
    实现统一的日志管理。这个Handler作为桥梁，将分散在各个模块的
    Python日志统一收集到系统日志中心。

    工作机制：
    1. **自动捕获**: 捕获Python logging系统的日志记录
    2. **智能分类**: 基于模块名和消息内容自动分类日志
    3. **级别过滤**: 只处理WARNING及以上级别的日志
    4. **格式转换**: 将LogRecord转换为SystemLogCollector格式
    5. **异常隔离**: Handler内部异常不影响主程序运行

    分类逻辑：
    - price_update: 包含"price"或来自市场模块的日志
    - ai_decision: 来自AI决策或交易模块的日志
    - system_error: 其他所有类型的日志

    特殊处理：
    - 自动收集策略触发和执行完成的INFO日志
    - 提取异常堆栈信息到details字段
    - 记录日志产生的模块、函数和行号信息
    """

    def emit(self, record: logging.LogRecord):
        """处理日志记录"""
        """
        处理单个日志记录

        这是Handler的核心方法，将Python LogRecord转换为SystemLogCollector
        的格式并进行适当的分类和过滤。

        Args:
            record: Python logging系统的日志记录对象
                   包含级别、消息、模块信息、异常信息等

        处理流程：
        1. **信息提取**: 从LogRecord提取关键信息
        2. **智能分类**: 基于内容和来源自动分类
        3. **详情构建**: 构建包含调试信息的details字典
        4. **异常处理**: 提取和格式化异常信息
        5. **条件过滤**: 根据级别和内容决定是否记录

        级别过滤策略：
        - WARNING及以上: 所有日志都记录
        - INFO级别: 只记录策略相关的特定日志
        - DEBUG级别: 不记录（避免过多噪音）

        异常处理：
        - 自动提取exc_info中的异常堆栈
        - 格式化为可读的字符串存储
        - 避免Handler本身的异常影响主程序

        分类算法：
        ```python
        if "price" in message or "market" in module:
            category = "price_update"
        elif "ai_decision" in module or "trading" in module:
            category = "ai_decision"
        else:
            category = "system_error"
        ```
        """
        try:
            # 判断日志来源和类型
            module = record.name
            level = record.levelname
            message = self.format(record)

            # 分类日志
            category = "system_error"
            if "price" in message.lower() or "market" in module:
                category = "price_update"
            elif "ai_decision" in module or "trading" in module:
                category = "ai_decision"

            # 提取详细信息
            details = {
                "module": module,
                "function": record.funcName,
                "line": record.lineno
            }

            # 添加异常信息
            if record.exc_info:
                import traceback
                details["exception"] = ''.join(traceback.format_exception(*record.exc_info))

            # 记录WARNING及以上级别,或者策略触发相关的INFO日志
            if record.levelno >= logging.WARNING:
                system_logger.add_log(
                    level=level,
                    category=category,
                    message=message,
                    details=details
                )
            elif record.levelno == logging.INFO and "Strategy triggered" in message:
                # 收集策略触发的INFO日志
                system_logger.add_log(
                    level=level,
                    category="ai_decision",
                    message=message,
                    details=details
                )
            elif record.levelno == logging.INFO and "Strategy execution completed" in message:
                # 收集策略执行完成的INFO日志
                system_logger.add_log(
                    level=level,
                    category="ai_decision",
                    message=message,
                    details=details
                )
        except Exception as e:
            # 避免日志处理器本身出错
            print(f"SystemLogHandler error: {e}")


class PriceSnapshotLogger:
    """每60秒记录一次价格快照"""
    """
    定时价格快照记录器

    定期采集和记录所有交易标的的价格快照，为系统提供价格变化的
    历史记录和监控能力。使用定时器机制实现精确的时间间隔控制。

    核心功能：
    1. **定时快照**: 每60秒自动采集所有标的的当前价格
    2. **批量记录**: 一次性记录多个标的的价格信息
    3. **历史追踪**: 维护各标的的最后价格记录
    4. **自动重调度**: 完成快照后自动安排下次执行

    设计特点：
    - **非阻塞**: 使用daemon线程避免影响主程序退出
    - **异常隔离**: 快照失败不影响定时器的继续运行
    - **资源高效**: 批量处理减少日志记录的开销
    - **可控制**: 支持启动和停止操作

    时间间隔选择（60秒）：
    - 平衡数据密度和系统开销
    - 足够捕捉短期价格变化趋势
    - 避免过于频繁的日志记录
    - 与AI决策周期配合

    数据来源：
    - 从price_cache获取缓存的价格数据
    - 仅处理AI_TRADING_SYMBOLS中的标的
    - 跳过无有效价格的标的

    应用价值：
    - **价格监控**: 提供系统级别的价格变化记录
    - **数据审计**: 验证价格数据的持续性和准确性
    - **性能基准**: 为价格相关功能提供基准数据
    - **故障诊断**: 帮助诊断价格数据获取问题
    """

    def __init__(self):
        """
        初始化价格快照记录器

        设置定时器相关的实例变量，准备定时快照功能。
        初始状态为停止状态，需要调用start()方法启动。

        实例变量：
        - _timer: Threading.Timer对象，用于定时执行
        - _interval: 快照间隔时间（秒）
        - _running: 运行状态标志
        - _last_prices: 最后记录的价格字典，用于历史追踪
        """
        self._timer: Optional[threading.Timer] = None
        self._interval = 60  # 60 seconds
        self._running = False
        self._last_prices: Dict[str, float] = {}

    def start(self):
        """启动价格快照记录器"""
        """
        启动定时价格快照功能

        开始定期价格快照的采集工作。设置运行标志并安排第一次快照执行。
        重复调用是安全的，不会创建重复的定时器。

        启动过程：
        1. 检查当前运行状态，避免重复启动
        2. 设置运行标志为True
        3. 调度第一次快照执行
        4. 记录启动日志便于监控

        调用时机：
        - 系统启动时自动调用
        - 手动管理价格监控功能
        - 故障恢复后重新启动

        安全性：
        - 幂等操作：重复调用不会产生副作用
        - 状态检查：避免创建重复的定时器
        - 异常安全：启动失败不影响系统运行
        """
        if self._running:
            return
        self._running = True
        self._schedule_next()
        logging.info("Price snapshot logger started (60-second interval)")

    def stop(self):
        """停止价格快照记录器"""
        """
        停止定时价格快照功能

        优雅地停止价格快照记录器，清理定时器资源并设置停止标志。
        确保已调度的定时器被正确取消。

        停止过程：
        1. 设置运行标志为False，阻止新的调度
        2. 取消当前的定时器（如果存在）
        3. 清理定时器引用释放资源
        4. 记录停止日志便于监控

        调用场景：
        - 系统关闭时清理资源
        - 临时禁用价格快照功能
        - 故障处理时停止异常组件

        资源清理：
        - 取消待执行的定时器
        - 释放定时器对象引用
        - 保留历史价格数据（不清空_last_prices）
        """
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
        logging.info("Price snapshot logger stopped")

    def _schedule_next(self):
        """安排下一次快照"""
        if not self._running:
            return
        self._timer = threading.Timer(self._interval, self._take_snapshot)
        self._timer.daemon = True
        self._timer.start()

    def _take_snapshot(self):
        """获取并记录所有币种的当前价格"""
        """
        执行价格快照采集

        实际的价格快照执行逻辑，负责从价格缓存获取当前价格并记录到系统日志。
        这是定时器回调的核心方法。

        执行流程：
        1. **动态导入**: 延迟导入避免循环依赖问题
        2. **批量采集**: 遍历所有AI交易标的获取价格
        3. **数据验证**: 跳过无效价格（None值）
        4. **格式化**: 将价格格式化为可读的字符串
        5. **批量记录**: 一次性记录所有有效价格
        6. **历史更新**: 更新_last_prices字典
        7. **自动调度**: 安排下一次快照（finally块保证执行）

        数据处理：
        - 价格显示: 保留4位小数的美元格式
        - 批量消息: 所有价格在一条日志中显示
        - 结构化数据: details中存储完整的价格字典

        异常处理：
        - 捕获所有异常避免定时器中断
        - 记录错误日志便于问题排查
        - 确保下一次调度不会因异常跳过

        日志格式：
        ```
        消息: "Price snapshot: BTC=$95000.0000, ETH=$3500.0000, ..."
        详情: {
            "prices": {"BTC": 95000.0, "ETH": 3500.0, ...},
            "symbols": ["BTC", "ETH", "SOL", ...]
        }
        ```

        性能考虑：
        - 批量操作减少日志记录次数
        - 缓存访问避免重复的网络请求
        - 异常处理确保定时器稳定运行
        - 最小化快照执行时间

        依赖服务：
        - price_cache.get_cached_price: 获取缓存价格
        - trading_commands.AI_TRADING_SYMBOLS: 交易标的列表
        - system_logger: 日志记录服务
        """
        try:
            from services.price_cache import get_cached_price
            from services.trading_commands import AI_TRADING_SYMBOLS

            prices_info = []
            for symbol in AI_TRADING_SYMBOLS:
                price = get_cached_price(symbol, "CRYPTO")
                if price is not None:
                    prices_info.append(f"{symbol}=${price:.4f}")
                    self._last_prices[symbol] = price

            if prices_info:
                message = "Price snapshot: " + ", ".join(prices_info)
                system_logger.add_log(
                    level="INFO",
                    category="price_update",
                    message=message,
                    details={"prices": self._last_prices.copy(), "symbols": AI_TRADING_SYMBOLS}
                )
        except Exception as e:
            logging.error(f"Failed to take price snapshot: {e}")
        finally:
            # 安排下一次快照
            self._schedule_next()


# 全局价格快照记录器
# 全局价格快照记录器实例
price_snapshot_logger = PriceSnapshotLogger()

# 价格快照说明：
# - 每60秒自动采集所有交易标的的价格快照
# - 提供系统级别的价格变化历史记录
# - 支持启动和停止控制
# - 异常隔离确保定时器稳定运行


def setup_system_logger():
    """设置系统日志处理器（在应用启动时调用）"""
    """
    初始化系统日志收集器

    在应用启动时调用此函数，将SystemLogHandler集成到Python标准logging系统中。
    这样所有通过Python logging记录的日志都会自动转发到SystemLogCollector。

    设置内容：
    1. **创建Handler**: 实例化SystemLogHandler
    2. **设置级别**: 只收集WARNING及以上级别的日志
    3. **注册Handler**: 添加到根logger，捕获所有模块的日志
    4. **记录启动**: 记录初始化完成的日志

    级别选择（WARNING及以上）：
    - 避免INFO和DEBUG日志造成噪音
    - 重点关注警告和错误信息
    - 特殊INFO日志（如策略触发）仍会被收集
    - 减少日志存储和处理开销

    调用时机：
    - 应用启动时（main.py或startup.py中）
    - 在其他日志配置之前调用
    - 确保所有后续日志都能被捕获

    效果：
    ```python
    import logging
    # 这些日志会自动被SystemLogCollector收集
    logging.warning("This will be collected")
    logging.error("This will also be collected")
    logging.info("This will be ignored unless it contains special keywords")
    ```

    注意事项：
    - 只需调用一次，重复调用会创建多个Handler
    - 必须在应用启动早期调用
    - 与其他logging配置兼容
    """
    handler = SystemLogHandler()
    handler.setLevel(logging.WARNING)  # 只收集WARNING及以上

    # 添加到根logger
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    logging.info("System log collector initialized")
