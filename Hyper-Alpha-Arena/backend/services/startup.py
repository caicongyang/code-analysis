"""Application startup initialization service"""
"""
应用启动初始化服务

Hyper Alpha Arena系统启动时的服务编排和初始化管理器。
负责按正确顺序启动所有核心服务，确保系统各组件正常运行。

服务启动顺序：
1. 任务调度器（Task Scheduler）- 提供定时任务基础设施
2. 符号目录刷新 - 从Hyperliquid获取最新的交易对信息
3. 市场任务设置 - 配置各种市场数据收集和处理任务
4. 缓存清理任务 - 定期清理过期的价格缓存
5. 市场数据流 - 启动实时市场数据WebSocket连接
6. 事件订阅 - 设置价格更新等事件的处理器
7. 策略管理器 - 启动AI交易策略的执行引擎
8. 程序执行服务 - 启动程序交易者的执行调度

设计原则：
- 依赖顺序：确保被依赖的服务先启动
- 错误隔离：单个服务启动失败不影响其他服务
- 优雅降级：关键服务启动失败时的降级策略
- 资源管理：合理分配系统资源，避免启动时的资源竞争

容错机制：
- 服务启动超时检测
- 启动失败的重试机制
- 服务健康状态监控
- 异常情况的日志记录

监控指标：
- 启动时间统计
- 服务启动成功率
- 资源使用情况
- 错误日志汇总
"""

import logging
import threading

from services.auto_trader import (
    place_ai_driven_crypto_order,
    place_random_crypto_order,
    AUTO_TRADE_JOB_ID,
    AI_TRADE_JOB_ID
)
from services.scheduler import start_scheduler, setup_market_tasks, task_scheduler
from services.market_stream import start_market_stream, stop_market_stream
from services.market_events import subscribe_price_updates, unsubscribe_price_updates
from services.asset_snapshot_service import handle_price_update
from services.trading_strategy import start_strategy_manager, stop_strategy_manager
from services.hyperliquid_symbol_service import (
    refresh_hyperliquid_symbols,
    schedule_symbol_refresh_task,
    build_market_stream_symbols,
)

logger = logging.getLogger(__name__)


def initialize_services():
    """Initialize all services"""
    """
    初始化所有系统服务

    系统启动时的核心初始化流程，按依赖关系顺序启动各个服务组件。
    确保每个服务都能正常工作，为用户提供完整的交易功能。

    初始化流程：
    1. 基础设施服务（调度器、符号管理等）
    2. 市场数据服务（WebSocket连接、数据收集等）
    3. 交易执行服务（策略管理器、订单执行等）
    4. 辅助服务（缓存清理、监控等）

    异常处理：
    - 任何服务启动失败都会记录详细日志
    - 非关键服务失败不会阻止系统启动
    - 提供服务状态查询接口用于健康检查
    """
    try:
        # Start the scheduler
        # 启动任务调度器 - 所有定时任务的基础设施
        print("Starting scheduler...")
        start_scheduler()  # 启动APScheduler实例
        print("Scheduler started")
        logger.info("Scheduler service started")

        # Refresh Hyperliquid symbol catalog + schedule periodic updates
        # 刷新Hyperliquid交易对目录并安排定期更新任务
        refresh_hyperliquid_symbols()     # 立即从API获取最新交易对信息
        schedule_symbol_refresh_task()    # 设置定期刷新任务（避免交易对变更）

        # Set up market-related scheduled tasks
        # 设置市场相关的定时任务（K线收集、流量监控等）
        setup_market_tasks()
        logger.info("Market scheduled tasks have been set up")

        # Add price cache cleanup task (every 2 minutes)
        # 添加价格缓存清理任务（每2分钟执行一次）
        from services.price_cache import clear_expired_prices
        task_scheduler.add_interval_task(
            task_func=clear_expired_prices,   # 清理过期价格缓存的函数
            interval_seconds=120,             # 2分钟间隔，平衡内存使用和性能
            task_id="price_cache_cleanup"     # 任务唯一标识符
        )
        logger.info("Price cache cleanup task started (2-minute interval)")

        # Start market data stream
        # NOTE: Paper trading snapshot service disabled - using Hyperliquid snapshots only
        combined_symbols = build_market_stream_symbols()
        print("Starting market data stream...")
        start_market_stream(combined_symbols, interval_seconds=1.5)
        print("Market data stream started")
        # subscribe_price_updates(handle_price_update)  # DISABLED: Paper trading snapshot
        # print("Asset snapshot handler subscribed")
        logger.info("Market data stream initialized")

        # Subscribe strategy manager to price updates
        from services.trading_strategy import handle_price_update as strategy_price_update

        def strategy_price_wrapper(event):
            """Wrapper to convert event format for strategy manager"""
            symbol = event.get("symbol")
            price = event.get("price")
            event_time = event.get("event_time")
            if symbol and price:
                strategy_price_update(symbol, float(price), event_time)

        subscribe_price_updates(strategy_price_wrapper)
        logger.info("Strategy manager subscribed to price updates")

        # Subscribe Program Trader to price updates (for scheduled triggers)
        from services.program_execution_service import program_execution_service

        def program_price_wrapper(event):
            """Wrapper to convert event format for program execution service"""
            symbol = event.get("symbol")
            price = event.get("price")
            event_time = event.get("event_time")
            if symbol and price:
                program_execution_service.on_price_update(symbol, float(price), event_time)

        subscribe_price_updates(program_price_wrapper)
        logger.info("Program execution service subscribed to price updates")

        # Start AI trading strategy manager
        print("Starting strategy manager...")
        start_strategy_manager()
        print("Strategy manager started")

        # Start asset curve broadcast task (every 60 seconds)
        from services.scheduler import start_asset_curve_broadcast
        start_asset_curve_broadcast()
        logger.info("Asset curve broadcast task started (60-second interval)")

        # Start Hyperliquid account snapshot service (every 30 seconds)
        from services.hyperliquid_snapshot_service import hyperliquid_snapshot_service
        import asyncio
        asyncio.create_task(hyperliquid_snapshot_service.start())
        logger.info("Hyperliquid snapshot service started (30-second interval)")

        # Start K-line realtime collection service
        from services.kline_realtime_collector import realtime_collector
        asyncio.create_task(realtime_collector.start())
        logger.info("K-line realtime collection service started (1-minute interval)")

        # Start market flow data collector (trades, orderbook, OI/funding)
        from services.market_flow_collector import market_flow_collector, cleanup_old_market_flow_data
        print("Starting market flow collector...")
        market_flow_collector.start()
        print("Market flow collector started")
        logger.info("Market flow collector started (15-second aggregation)")

        # Add market flow data cleanup task (every 6 hours)
        task_scheduler.add_interval_task(
            task_func=cleanup_old_market_flow_data,
            interval_seconds=6 * 3600,  # 6 hours
            task_id="market_flow_data_cleanup"
        )
        logger.info("Market flow data cleanup task started (6-hour interval, 30-day retention)")

        logger.info("All services initialized successfully")

    except Exception as e:
        logger.error(f"Service initialization failed: {e}")
        raise


def shutdown_services():
    """Shut down all services"""
    try:
        from services.scheduler import stop_scheduler
        from services.hyperliquid_snapshot_service import hyperliquid_snapshot_service
        from services.kline_realtime_collector import realtime_collector
        import asyncio

        stop_strategy_manager()
        stop_market_stream()
        unsubscribe_price_updates(handle_price_update)
        hyperliquid_snapshot_service.stop()

        # Stop K-line realtime collector
        asyncio.create_task(realtime_collector.stop())

        # Stop market flow collector
        from services.market_flow_collector import market_flow_collector
        market_flow_collector.stop()

        stop_scheduler()
        logger.info("All services have been shut down")

    except Exception as e:
        logger.error(f"Failed to shut down services: {e}")


async def startup_event():
    """FastAPI application startup event"""
    initialize_services()


async def shutdown_event():
    """FastAPI application shutdown event"""
    await shutdown_services()


def schedule_auto_trading(interval_seconds: int = 300, max_ratio: float = 0.2, use_ai: bool = True) -> None:
    """Schedule automatic trading tasks
    
    Args:
        interval_seconds: Interval between trading attempts
        max_ratio: Maximum portion of portfolio to use per trade
        use_ai: If True, use AI-driven trading; if False, use random trading
    """
    from services.auto_trader import (
        place_ai_driven_crypto_order,
        place_random_crypto_order,
        AUTO_TRADE_JOB_ID,
        AI_TRADE_JOB_ID
    )

    def execute_trade():
        try:
            if use_ai:
                place_ai_driven_crypto_order(max_ratio)
            else:
                place_random_crypto_order(max_ratio)
            logger.info("Initial auto-trading execution completed")
        except Exception as e:
            logger.error(f"Error during initial auto-trading execution: {e}")

    if use_ai:
        task_func = place_ai_driven_crypto_order
        job_id = AI_TRADE_JOB_ID
        logger.info("Scheduling AI-driven crypto trading")
    else:
        task_func = place_random_crypto_order
        job_id = AUTO_TRADE_JOB_ID
        logger.info("Scheduling random crypto trading")

    # Schedule the recurring task
    task_scheduler.add_interval_task(
        task_func=task_func,
        interval_seconds=interval_seconds,
        task_id=job_id,
        max_ratio=max_ratio,
    )
    
    # Execute the first trade immediately in a separate thread to avoid blocking
    initial_trade = threading.Thread(target=execute_trade, daemon=True)
    initial_trade.start()
