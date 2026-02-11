"""
Order scheduling service
Background task for periodically processing pending orders
"""
"""
订单调度服务

后台任务服务，定期处理待执行的订单。实现Paper Trading模式下
限价单的条件触发执行。

核心功能：
1. 定期检查：按固定间隔检查所有待处理订单
2. 条件匹配：根据市场价格判断限价单是否满足执行条件
3. 订单执行：触发满足条件的订单执行
4. 状态更新：更新订单状态和账户余额

工作机制：
- 独立后台线程运行，不阻塞主应用
- 默认每5秒检查一次待处理订单
- 支持平滑启动和停止

订单类型支持：
- 限价买入：当市场价格 <= 限价时执行
- 限价卖出：当市场价格 >= 限价时执行
- 市价单：立即执行，不经过调度器

应用场景：
- Paper Trading的订单撮合模拟
- 限价单的条件监控
- 测试环境的订单执行演示
"""

import asyncio
import threading
import time
import logging
from typing import Optional

from database.connection import SessionLocal
from .order_matching import process_all_pending_orders

logger = logging.getLogger(__name__)


class OrderScheduler:
    """Order scheduler"""
    """
    订单调度器类

    后台线程实现，定期检查和执行待处理订单。
    支持配置检查间隔和平滑停止。

    核心属性：
    - interval_seconds: 检查间隔（秒）
    - running: 运行状态标志
    - thread: 后台执行线程

    生命周期：
    - start(): 启动调度器线程
    - stop(): 优雅停止调度器
    - _run_scheduler(): 主循环逻辑
    """
    
    def __init__(self, interval_seconds: int = 5):
        """
        Initialize the order scheduler

        Args:
            interval_seconds: Check interval (seconds)
        """
        self.interval_seconds = interval_seconds
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
    
    def start(self):
        """Start the scheduler"""
        if self.running:
            logger.warning("Order scheduler is already running")
            return
        
        self.running = True
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.thread.start()
        logger.info(f"Order scheduler started, check interval: {self.interval_seconds} seconds")
    
    def stop(self):
        """Stop the scheduler"""
        if not self.running:
            return
        
        self.running = False
        self._stop_event.set()
        
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=10)
        
        logger.info("Order scheduler stopped")
    
    def _run_scheduler(self):
        """Scheduler main loop"""
        logger.info("Order scheduler started running")
        
        while self.running and not self._stop_event.is_set():
            try:
                # Process orders
                self._process_orders()
                
                # Wait for next execution
                if self._stop_event.wait(timeout=self.interval_seconds):
                    break
                    
            except Exception as e:
                logger.error(f"Order scheduler execution error: {e}")
                # Wait briefly after error to avoid rapid looping
                time.sleep(1)
        
        logger.info("Order scheduler main loop ended")
    
    def _process_orders(self):
        """Process pending orders"""
        db = SessionLocal()
        try:
            executed_count, total_checked = process_all_pending_orders(db)
            
            if total_checked > 0:
                logger.debug(f"Order processing: checked {total_checked}, executed {executed_count}")
            
        except Exception as e:
            logger.error(f"Error processing orders: {e}")
        finally:
            db.close()
    
    def process_orders_once(self):
        """Manually execute order processing once"""
        if not self.running:
            logger.warning("Order scheduler not running, cannot process orders")
            return
        
        try:
            self._process_orders()
            logger.info("Manual order processing completed")
        except Exception as e:
            logger.error(f"Manual order processing failed: {e}")


# Global scheduler instance
order_scheduler = OrderScheduler(interval_seconds=5)


def start_order_scheduler():
    """Start global order scheduler"""
    order_scheduler.start()


def stop_order_scheduler():
    """Stop global order scheduler"""
    order_scheduler.stop()


def get_scheduler_status():
    """Get scheduler status"""
    return {
        "running": order_scheduler.running,
        "interval_seconds": order_scheduler.interval_seconds,
        "thread_alive": order_scheduler.thread.is_alive() if order_scheduler.thread else False
    }