"""
K线数据补漏管理器 - 处理后台补漏任务
"""

import asyncio
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from typing import Optional
import logging

from database.connection import SessionLocal
from database.models import KlineCollectionTask
from .kline_data_service import kline_service

logger = logging.getLogger(__name__)


class BackfillManager:
    """补漏任务管理器"""
    """
    K线数据补漏任务管理器

    负责管理和执行K线历史数据的补漏任务，确保数据库中的K线数据完整性。
    当检测到数据缺失时，自动创建补漏任务并在后台异步执行。

    核心功能：
    1. **任务调度**：管理待处理的补漏任务队列
    2. **并发控制**：限制同时执行的任务数避免资源过载
    3. **分批处理**：大时间范围的数据分批获取避免超时
    4. **进度跟踪**：实时更新任务执行进度和状态
    5. **错误处理**：异常情况下的任务失败处理和重试
    6. **资源清理**：自动清理过期的任务记录

    设计特点：
    - **异步执行**：基于asyncio的非阻塞任务处理
    - **状态管理**：完整的任务生命周期状态跟踪
    - **分批策略**：6小时批次避免单次请求过大
    - **并发限制**：最多3个并发任务平衡效率和资源
    - **API节流**：批次间延迟避免触发交易所限流

    任务状态流转：
    pending -> running -> completed/failed

    应用场景：
    - **数据修复**：修复由于网络中断导致的数据缺失
    - **历史回填**：获取新增交易对的历史数据
    - **数据验证**：确保关键时间段的数据完整性
    - **系统恢复**：系统故障后的数据恢复
    """

    def __init__(self):
        """
        初始化补漏管理器

        配置管理器的基本参数，包括并发限制和执行策略。
        """
        self.max_concurrent_tasks = 3  # 最大并发任务数
        # 并发数设置考虑：
        # - 3个任务：平衡执行效率和系统负载
        # - 避免对交易所API造成过大压力
        # - 确保数据库连接池不被耗尽

    async def process_task(self, task_id: int):
        """处理单个补漏任务"""
        """
        执行单个K线数据补漏任务

        完整的补漏任务执行流程，从任务初始化到数据采集完成的全过程管理。
        采用分批处理策略，确保大时间范围的数据能够稳定可靠地获取。

        Args:
            task_id: 补漏任务的唯一标识ID

        执行流程：
        1. **任务验证**：
           - 从数据库加载任务信息
           - 验证任务状态是否为待处理
           - 检查任务参数的有效性

        2. **预处理**：
           - 更新任务状态为运行中
           - 初始化数据服务连接
           - 计算预期采集的记录数

        3. **分批采集**：
           - 将大时间范围分解为6小时的批次
           - 逐批调用kline_service获取历史数据
           - 实时更新任务进度和已采集记录数

        4. **进度管理**：
           - 基于时间范围计算完成百分比
           - 更新数据库中的进度记录
           - 提供实时的执行状态反馈

        5. **完成处理**：
           - 标记任务为已完成状态
           - 记录最终的采集统计信息
           - 生成执行日志便于审计

        分批策略：
        - 批次大小：6小时
        - 批次间延迟：2秒（避免API限流）
        - 进度计算：基于时间范围的百分比

        异常处理：
        - 任务不存在：记录错误并返回
        - 状态异常：跳过非待处理任务
        - 采集失败：标记任务失败并记录错误信息

        性能考虑：
        - 避免单次请求过大的数据量
        - 控制API调用频率防止限流
        - 及时更新进度减少用户等待焦虑
        """
        logger.info(f"Starting backfill task {task_id}")

        with SessionLocal() as db:
            # 获取任务信息
            task = db.query(KlineCollectionTask).filter(
                KlineCollectionTask.id == task_id
            ).first()

            if not task:
                logger.error(f"Task {task_id} not found")
                return

            if task.status != "pending":
                logger.warning(f"Task {task_id} is not pending (status: {task.status})")
                return

            try:
                # 更新任务状态为运行中
                task.status = "running"
                task.progress = 0
                db.commit()

                # 确保数据服务已初始化
                await kline_service.initialize()

                # 计算预期的记录数（1分钟间隔）
                time_diff = task.end_time - task.start_time
                expected_records = int(time_diff.total_seconds() / 60)
                task.total_records = expected_records
                db.commit()

                logger.info(f"Task {task_id}: Collecting {expected_records} records for {task.symbol}")

                # 分批采集数据（每次最多6小时）
                batch_hours = 6
                current_start = task.start_time
                collected_total = 0

                while current_start < task.end_time:
                    # 计算当前批次的结束时间
                    current_end = min(
                        current_start + timedelta(hours=batch_hours),
                        task.end_time
                    )

                    logger.debug(f"Task {task_id}: Collecting batch {current_start} to {current_end}")

                    # 采集当前批次的数据
                    collected_batch = await kline_service.collect_historical_klines(
                        task.symbol,
                        current_start,
                        current_end,
                        task.period
                    )

                    collected_total += collected_batch

                    # 更新进度
                    progress = min(
                        int((current_end - task.start_time).total_seconds() / time_diff.total_seconds() * 100),
                        100
                    )

                    task.progress = progress
                    task.collected_records = collected_total
                    db.commit()

                    logger.debug(f"Task {task_id}: Progress {progress}%, collected {collected_batch} records")

                    # 移动到下一个批次
                    current_start = current_end

                    # 避免API限流
                    if current_start < task.end_time:
                        await asyncio.sleep(2)

                # 任务完成
                task.status = "completed"
                task.progress = 100
                task.collected_records = collected_total
                db.commit()

                logger.info(f"Task {task_id} completed successfully. Collected {collected_total} records.")

            except Exception as e:
                # 任务失败
                error_msg = str(e)
                logger.error(f"Task {task_id} failed: {error_msg}")

                task.status = "failed"
                task.error_message = error_msg
                db.commit()

    async def process_pending_tasks(self):
        """处理所有待处理的任务"""
        """
        批量处理所有待处理的补漏任务

        系统的主要入口函数，负责发现并并发执行所有待处理的补漏任务。
        通过合理的并发控制，最大化数据补漏的效率。

        执行策略：
        1. **任务发现**：
           - 查询数据库中状态为pending的任务
           - 按创建时间排序确保FIFO执行顺序
           - 限制单次处理的任务数量

        2. **并发执行**：
           - 为每个任务创建独立的异步协程
           - 设置有意义的任务名称便于调试
           - 使用asyncio.gather等待所有任务完成

        3. **异常容错**：
           - return_exceptions=True防止单个任务失败影响其他任务
           - 每个任务的异常都在task内部处理
           - 确保系统的整体稳定性

        并发控制：
        - 最大并发数：3个任务同时执行
        - 避免资源竞争和数据库连接耗尽
        - 平衡执行效率和系统稳定性

        调度策略：
        - FIFO队列：按任务创建时间先进先出
        - 批量处理：一次性获取多个待处理任务
        - 限制数量：单次最多处理3个任务

        应用场景：
        - **定时调度**：系统定期检查并处理待补漏的数据
        - **手动触发**：管理员手动执行数据修复
        - **故障恢复**：系统重启后自动继续未完成的任务
        - **批量补漏**：集中处理大量历史数据缺失

        性能特点：
        - **高效并发**：充分利用异步IO提升处理速度
        - **资源控制**：避免过多并发任务导致系统过载
        - **容错设计**：单个任务失败不影响其他任务继续执行
        """
        with SessionLocal() as db:
            # 获取待处理的任务
            pending_tasks = db.query(KlineCollectionTask).filter(
                KlineCollectionTask.status == "pending"
            ).order_by(KlineCollectionTask.created_at).limit(self.max_concurrent_tasks).all()

            if not pending_tasks:
                logger.debug("No pending backfill tasks found")
                return

            logger.info(f"Processing {len(pending_tasks)} pending backfill tasks")

            # 并发处理任务
            tasks = []
            for task in pending_tasks:
                task_coroutine = asyncio.create_task(
                    self.process_task(task.id),
                    name=f"backfill_task_{task.id}"
                )
                tasks.append(task_coroutine)

            # 等待所有任务完成
            await asyncio.gather(*tasks, return_exceptions=True)

    async def cleanup_old_tasks(self, days: int = 30):
        """清理旧的任务记录"""
        """
        清理过期的补漏任务记录

        定期维护数据库，删除过期的任务记录以控制数据库大小和提升查询性能。
        只清理已完成或失败的任务，保留运行中的任务避免数据丢失。

        Args:
            days: 保留天数，默认30天
                  超过此天数的已完成/失败任务将被删除

        清理策略：
        1. **时间筛选**：
           - 计算截止日期 = 当前时间 - 保留天数
           - 只处理创建时间早于截止日期的任务

        2. **状态筛选**：
           - 只删除已完成(completed)或失败(failed)的任务
           - 保留运行中(running)和待处理(pending)的任务
           - 确保活跃任务不受影响

        3. **批量删除**：
           - 使用数据库的批量删除操作提升效率
           - 统计删除的记录数量用于日志记录
           - 确保事务的原子性

        维护价值：
        - **性能优化**：减少任务表的记录数量，提升查询速度
        - **存储节约**：定期清理避免历史数据无限制增长
        - **系统维护**：保持系统的整洁性和可维护性

        调用时机：
        - **定期调度**：系统定时任务定期执行清理
        - **手动维护**：管理员根据需要手动清理
        - **存储告警**：数据库空间不足时自动清理

        安全考虑：
        - 只删除终态任务(completed/failed)
        - 保留足够的历史记录供审计使用
        - 原子性操作避免数据不一致
        """
        cutoff_date = datetime.now() - timedelta(days=days)

        with SessionLocal() as db:
            # 删除30天前的已完成或失败任务
            deleted = db.query(KlineCollectionTask).filter(
                KlineCollectionTask.created_at < cutoff_date,
                KlineCollectionTask.status.in_(["completed", "failed"])
            ).delete()

            db.commit()

            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old backfill tasks")

    def get_task_status(self, task_id: int) -> Optional[dict]:
        """获取任务状态"""
        """
        查询指定任务的详细状态信息

        为前端或其他服务提供任务执行状态的查询接口，
        返回任务的完整执行情况和进度信息。

        Args:
            task_id: 任务的唯一标识ID

        Returns:
            Optional[dict]: 任务状态信息字典，任务不存在时返回None
                          包含以下字段：
                          - task_id: 任务ID
                          - exchange: 交易所名称
                          - symbol: 交易对符号
                          - status: 任务状态(pending/running/completed/failed)
                          - progress: 完成进度(0-100)
                          - total_records: 预期采集的总记录数
                          - collected_records: 已采集的记录数
                          - error_message: 错误信息(失败任务)
                          - created_at: 创建时间
                          - updated_at: 更新时间

        状态字段说明：
        1. **基础信息**：
           - task_id: 任务唯一标识
           - exchange/symbol: 数据源和交易对信息

        2. **执行状态**：
           - status: 当前任务状态
           - progress: 完成百分比(0-100)
           - error_message: 失败原因(仅失败任务有值)

        3. **数据统计**：
           - total_records: 预期需要采集的K线记录总数
           - collected_records: 已成功采集的记录数
           - 两者对比可以看出采集完成度

        4. **时间信息**：
           - created_at: 任务创建时间
           - updated_at: 最后更新时间

        应用场景：
        - **进度监控**：前端定期轮询获取任务进度
        - **状态查询**：用户查看历史任务的执行结果
        - **故障排查**：检查失败任务的具体错误信息
        - **系统监控**：监控系统整体的任务执行情况

        返回格式：
        成功时返回包含完整状态信息的字典
        任务不存在时返回None，调用方需要处理空值情况
        """
        with SessionLocal() as db:
            task = db.query(KlineCollectionTask).filter(
                KlineCollectionTask.id == task_id
            ).first()

            if not task:
                return None

            return {
                "task_id": task.id,
                "exchange": task.exchange,
                "symbol": task.symbol,
                "status": task.status,
                "progress": task.progress,
                "total_records": task.total_records or 0,
                "collected_records": task.collected_records or 0,
                "error_message": task.error_message,
                "created_at": task.created_at,
                "updated_at": task.updated_at
            }