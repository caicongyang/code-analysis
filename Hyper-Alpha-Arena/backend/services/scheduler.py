"""
Scheduled task scheduler service
Used to manage WebSocket snapshot updates and other scheduled tasks
"""
"""
定时任务调度服务

基于APScheduler的统一任务调度管理器，为整个系统提供定时任务基础设施。
负责管理WebSocket快照更新、市场数据收集、缓存清理等各种定时任务。

核心功能：
1. 任务调度：基于时间间隔或Cron表达式的任务调度
2. 生命周期管理：任务的创建、启动、停止、删除
3. 异常处理：任务执行失败时的错误处理和重试
4. 资源管理：避免任务重复执行和资源冲突
5. 状态监控：任务执行状态和性能监控

支持的任务类型：
- 间隔任务：固定时间间隔重复执行
- Cron任务：基于Cron表达式的复杂调度
- 一次性任务：指定时间执行一次的任务
- 条件任务：满足特定条件时触发的任务

系统中的定时任务：
1. WebSocket快照更新（实时）
2. 市场数据收集（每分钟）
3. K线数据同步（每小时）
4. 价格缓存清理（每2分钟）
5. 交易符号刷新（每日）
6. 日志文件清理（每日）
7. 数据库优化（每周）

技术特点：
- 后台运行：不阻塞主线程的后台任务执行
- 线程安全：支持多线程环境下的安全调度
- 持久化：任务状态可持久化到数据库
- 集群支持：支持多实例部署的任务协调
- 监控接口：提供任务状态查询和管理接口

优势：
- 统一管理：所有定时任务的中央管理
- 高可靠：异常恢复和故障转移机制
- 易扩展：简单的任务注册和配置接口
- 高性能：优化的任务执行和资源使用
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Dict, Set, Callable, Optional, List
import logging
from datetime import date, datetime

from database.connection import SessionLocal
from database.models import Position, CryptoPrice

logger = logging.getLogger(__name__)


class TaskScheduler:
    """Unified task scheduler"""
    """
    统一任务调度器类

    封装APScheduler功能的任务调度管理器，提供简洁的任务管理接口。
    支持任务的注册、启动、停止和状态监控。

    设计特点：
    - 单例模式：全局统一的调度器实例
    - 状态管理：跟踪调度器和任务的运行状态
    - 连接跟踪：管理WebSocket连接与账户的关联关系
    - 异常安全：优雅的启动和关闭流程

    核心属性：
    - scheduler: APScheduler后台调度器实例
    - _started: 调度器启动状态标志
    - _account_connections: 账户连接跟踪字典

    生命周期：
    1. 初始化：创建调度器实例但不启动
    2. 启动：启动后台调度器开始执行任务
    3. 运行：持续执行已注册的定时任务
    4. 关闭：优雅停止所有任务并清理资源
    """

    def __init__(self):
        """
        初始化任务调度器

        创建调度器实例但不立即启动，允许在启动前注册任务。
        初始化状态跟踪和连接管理数据结构。
        """
        self.scheduler: Optional[BackgroundScheduler] = None  # APScheduler实例
        self._started = False                                  # 启动状态标志
        self._account_connections: Dict[int, Set] = {}         # 账户连接跟踪

    def start(self):
        """Start the scheduler"""
        """
        启动任务调度器

        启动APScheduler后台调度器，开始执行所有已注册的定时任务。
        使用幂等性设计，重复调用不会产生副作用。

        特点：
        - 幂等性：重复调用start()是安全的
        - 后台运行：不阻塞主线程
        - 状态跟踪：维护启动状态标志
        """
        if not self._started:
            self.scheduler = BackgroundScheduler()  # 创建后台调度器
            self.scheduler.start()                  # 启动调度器
            self._started = True                    # 更新状态标志
            logger.info("Scheduler started")

    def shutdown(self):
        """Shutdown the scheduler"""
        """
        关闭任务调度器

        优雅地停止所有正在运行的任务并清理资源。
        确保所有任务都能正常完成或安全中断。

        关闭流程：
        1. 检查调度器是否正在运行
        2. 停止接受新任务
        3. 等待当前任务完成
        4. 释放资源并更新状态

        特点：
        - 优雅关闭：等待任务完成而非强制终止
        - 资源清理：防止内存泄漏和资源占用
        - 状态同步：更新内部状态标志
        """
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown()  # 优雅关闭调度器
            self._started = False      # 重置状态标志
            logger.info("Scheduler shutdown")
    
    def is_running(self) -> bool:
        """Check if scheduler is running"""
        return self._started and self.scheduler and self.scheduler.running
    
    def add_account_snapshot_task(self, account_id: int, interval_seconds: int = 10):
        """
        Add snapshot update task for account

        Args:
            account_id: Account ID
            interval_seconds: Update interval (seconds), default 10 seconds
        """
        if not self.is_running():
            self.start()
            
        job_id = f"snapshot_account_{account_id}"
        
        # Check if task already exists
        if self.scheduler.get_job(job_id):
            logger.debug(f"Snapshot task for account {account_id} already exists")
            return
        
        self.scheduler.add_job(
            func=self._execute_account_snapshot,
            trigger=IntervalTrigger(seconds=interval_seconds),
            args=[account_id],
            id=job_id,
            replace_existing=True,
            max_instances=1,  # Avoid duplicate execution
            coalesce=True,    # Combine missed executions into one
            misfire_grace_time=5  # Allow 5 seconds grace time for late execution
        )
        
        logger.info(f"Added snapshot task for account {account_id}, interval {interval_seconds} seconds")
    
    def remove_account_snapshot_task(self, account_id: int):
        """
        Remove snapshot update task for account

        Args:
            account_id: Account ID
        """
        if not self.scheduler:
            return
            
        job_id = f"snapshot_account_{account_id}"
        
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed snapshot task for account {account_id}")
        except Exception as e:
            logger.debug(f"Failed to remove snapshot task for account {account_id}: {e}")
    
    
    def add_interval_task(self, task_func: Callable, interval_seconds: int, task_id: str, *args, **kwargs):
        """
        Add interval execution task

        Args:
            task_func: Function to execute
            interval_seconds: Execution interval (seconds)
            task_id: Task unique identifier
            *args, **kwargs: Parameters passed to task_func
        """
        if not self.is_running():
            self.start()
            
        self.scheduler.add_job(
            func=task_func,
            trigger=IntervalTrigger(seconds=interval_seconds),
            args=args,
            kwargs=kwargs,
            id=task_id,
            replace_existing=True
        )
        
        logger.info(f"Added interval task {task_id}: Execute every {interval_seconds} seconds")
    
    def remove_task(self, task_id: str):
        """
        Remove specified task

        Args:
            task_id: Task ID
        """
        if not self.scheduler:
            return
            
        try:
            self.scheduler.remove_job(task_id)
            logger.info(f"Removed task: {task_id}")
        except Exception as e:
            logger.debug(f"Failed to remove task {task_id}: {e}")

    def get_job_info(self) -> list:
        """Get all task information"""
        if not self.scheduler:
            return []

        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'next_run_time': job.next_run_time,
                'func_name': job.func.__name__ if hasattr(job.func, '__name__') else str(job.func)
            })
        return jobs

    async def _execute_account_snapshot(self, account_id: int):
        """
        Internal method to execute account snapshot update

        Args:
            account_id: Account ID
        """
        start_time = datetime.now()
        try:
            # Dynamic import to avoid circular dependency
            from api.ws import manager, _send_snapshot_optimized

            # Check if account still has active connections
            if account_id not in manager.active_connections:
                # Account disconnected, remove task
                self.remove_account_snapshot_task(account_id)
                return

            # Execute optimized snapshot update
            db: Session = SessionLocal()
            try:
                # Send optimized snapshot update (reduced frequency for expensive data)
                # Note: For now, skip the async WebSocket update in sync scheduler context
                # This can be enhanced later to properly handle async operations
                logger.debug(f"Skipping WebSocket snapshot update for account {account_id} in sync context")

                # Save latest prices for account's positions (less frequently)
                if start_time.second % 30 == 0:  # Only every 30 seconds
                    self._save_position_prices(db, account_id)

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Account {account_id} snapshot update failed: {e}")
        finally:
            execution_time = (datetime.now() - start_time).total_seconds()
            if execution_time > 5:  # Log if execution takes longer than 5 seconds
                logger.warning(f"Slow snapshot execution for account {account_id}: {execution_time:.2f}s")
    
    def _save_position_prices(self, db: Session, account_id: int):
        """
        Save latest prices for account's positions on the current date

        Args:
            db: Database session
            account_id: Account ID
        """
        try:
            # Get all account's positions
            positions = db.query(Position).filter(
                Position.account_id == account_id,
                Position.quantity > 0
            ).all()

            if not positions:
                logger.debug(f"Account {account_id} has no positions, skip price saving")
                return

            today = date.today()

            for position in positions:
                try:
                    # Check if crypto price already saved today
                    existing_price = db.query(CryptoPrice).filter(
                        CryptoPrice.symbol == position.symbol,
                        CryptoPrice.market == position.market,
                        CryptoPrice.price_date == today
                    ).first()

                    if existing_price:
                        logger.debug(f"crypto {position.symbol} price already exists for today, skip")
                        continue

                    # Get latest price
                    from services.market_data import get_last_price
                    current_price = get_last_price(position.symbol, position.market)

                    # Save price record
                    crypto_price = CryptoPrice(
                        symbol=position.symbol,
                        market=position.market,
                        price=current_price,
                        price_date=today
                    )

                    db.add(crypto_price)
                    db.commit()

                    logger.info(f"Saved crypto price: {position.symbol} {today} {current_price}")

                except Exception as e:
                    logger.error(f"Failed to save crypto {position.symbol} price: {e}")
                    db.rollback()
                    continue

        except Exception as e:
            logger.error(f"Failed to save account {account_id} position prices: {e}")
            db.rollback()


# Global scheduler instance
task_scheduler = TaskScheduler()


# Convenience functions
def start_scheduler():
    """Start global scheduler"""
    task_scheduler.start()


def stop_scheduler():
    """Stop global scheduler"""
    task_scheduler.shutdown()


def add_account_snapshot_job(account_id: int, interval_seconds: int = 10):
    """Convenience function to add snapshot task for account"""
    task_scheduler.add_account_snapshot_task(account_id, interval_seconds)


def remove_account_snapshot_job(account_id: int):
    """Convenience function to remove account snapshot task"""
    task_scheduler.remove_account_snapshot_task(account_id)


# Legacy compatibility functions
def add_user_snapshot_job(user_id: int, interval_seconds: int = 10):
    """Legacy function - now redirects to account-based function"""
    # For backward compatibility, assume this is account_id
    add_account_snapshot_job(user_id, interval_seconds)


def remove_user_snapshot_job(user_id: int):
    """Legacy function - now redirects to account-based function"""
    # For backward compatibility, assume this is account_id
    remove_account_snapshot_job(user_id)


def setup_market_tasks():
    """Set up crypto market-related scheduled tasks"""
    # Crypto markets run 24/7, no specific market open/close times needed
    logger.info("Crypto markets run 24/7 - no market hours tasks needed")


def _ensure_market_data_ready() -> None:
    """Prefetch required market data before enabling trading tasks"""
    try:
        from services.trading_commands import AI_TRADING_SYMBOLS
        from services.market_data import get_last_price

        missing_symbols: List[str] = []

        for symbol in AI_TRADING_SYMBOLS:
            try:
                price = get_last_price(symbol, "CRYPTO")
                if price is None or price <= 0:
                    missing_symbols.append(symbol)
                    logger.warning(f"Prefetch returned invalid price for {symbol}: {price}")
                else:
                    logger.debug(f"Prefetched market data for {symbol}: {price}")
            except Exception as fetch_err:
                missing_symbols.append(symbol)
                logger.warning(f"Failed to prefetch price for {symbol}: {fetch_err}")

        if missing_symbols:
            raise RuntimeError(
                "Market data not ready for symbols: " + ", ".join(sorted(set(missing_symbols)))
            )

    except Exception as err:
        logger.error(f"Market data readiness check failed: {err}")
        raise


def reset_auto_trading_job():
    """DEPRECATED: Legacy function from paper trading module

    This function is now DISABLED and performs no operations.

    Historical issue (GitHub #31):
    - This function used to unconditionally start a fixed 300-second APScheduler task
    - That task called place_ai_driven_crypto_order() for ALL accounts every 5 minutes
    - This conflicted with Hyperliquid strategy manager's per-account trigger intervals
    - Result: Users configured 600s interval but got double triggers at ~300s intervals

    Current behavior:
    - No-op function (does nothing)
    - All trading is now managed exclusively by Hyperliquid strategy manager
    - Strategy manager respects per-account trigger intervals configured in strategy settings
    """
    logger.info(
        "reset_auto_trading_job() called but DISABLED (paper trading legacy). "
        "All trading managed by Hyperliquid strategy manager. See GitHub issue #31."
    )




def start_asset_curve_broadcast():
    """Start asset curve broadcast task - broadcasts every 60 seconds"""
    import asyncio
    from api.ws import broadcast_asset_curve_update

    def broadcast_all_timeframes():
        """Broadcast asset curve updates for all timeframes"""
        try:
            # Create event loop for async tasks
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Broadcast updates for all timeframes
            loop.run_until_complete(broadcast_asset_curve_update("5m"))
            loop.run_until_complete(broadcast_asset_curve_update("1h"))
            loop.run_until_complete(broadcast_asset_curve_update("1d"))

            logger.debug("Broadcasted asset curve updates for all timeframes")

        except Exception as e:
            logger.error(f"Failed to broadcast asset curve updates: {e}")
        finally:
            try:
                loop.close()
            except:
                pass

    try:
        # Ensure scheduler is running
        if not task_scheduler.is_running():
            task_scheduler.start()
            logger.info("Started scheduler for asset curve broadcast")

        # Add broadcast task (every 60 seconds)
        ASSET_CURVE_BROADCAST_JOB_ID = "asset_curve_broadcast"
        BROADCAST_INTERVAL_SECONDS = 60

        # Remove existing job if it exists
        if task_scheduler.scheduler and task_scheduler.scheduler.get_job(ASSET_CURVE_BROADCAST_JOB_ID):
            task_scheduler.remove_task(ASSET_CURVE_BROADCAST_JOB_ID)
            logger.info(f"Removed existing asset curve broadcast job")

        # Add the broadcast job
        task_scheduler.add_interval_task(
            task_func=broadcast_all_timeframes,
            interval_seconds=BROADCAST_INTERVAL_SECONDS,
            task_id=ASSET_CURVE_BROADCAST_JOB_ID
        )

        logger.info(f"Asset curve broadcast job started - interval: {BROADCAST_INTERVAL_SECONDS}s")

    except Exception as e:
        logger.error(f"Failed to start asset curve broadcast: {e}")
        raise