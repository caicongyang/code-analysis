"""
Program Trader execution service.
Handles signal-triggered and scheduled execution of bound programs.

Architecture:
- Programs are bound to AI Traders via AccountProgramBinding
- Each binding has its own trigger configuration (signal pools, interval)
- Execution uses the AI Trader's wallet for trading
"""
"""
程序交易者执行服务

处理程序交易者的信号触发和定时执行的核心服务。负责管理程序与
AI交易者账户的绑定关系，并在合适的时机执行交易策略代码。

系统架构：
1. 绑定模型：程序通过AccountProgramBinding绑定到AI交易者账户
2. 触发配置：每个绑定有独立的触发配置（信号池、定时间隔）
3. 钱包共享：程序执行使用AI交易者的钱包进行实际交易
4. 状态管理：维护程序执行状态和历史记录

核心功能：
- 信号触发执行：监听市场信号，触发相应的程序交易策略
- 定时执行：按设定间隔定期检查和执行交易逻辑
- 多程序管理：支持一个账户绑定多个交易程序
- 并发控制：防止同一程序的重复执行和资源竞争
- 执行日志：记录详细的执行过程和结果

设计特点：
- 单例模式：全局唯一的执行服务实例，确保资源统一管理
- 线程安全：支持多线程环境下的并发执行
- 状态缓存：缓存绑定状态，减少数据库查询开销
- 错误隔离：单个程序的错误不会影响其他程序执行
- 资源管理：合理分配执行资源，避免系统过载

与AI交易者的关系：
- 共享钱包：程序交易者使用AI交易者的Hyperliquid钱包
- 独立策略：程序交易者有自己的Python代码逻辑
- 统一管理：通过同一个账户管理界面配置
- 风险控制：继承AI交易者的风险控制参数
"""

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from database.connection import SessionLocal
from database.models import (
    TradingProgram, AccountProgramBinding, ProgramExecutionLog,
    Account, HyperliquidWallet
)
from program_trader.executor import execute_strategy
from program_trader.models import MarketData, ActionType
from program_trader.data_provider import DataProvider

logger = logging.getLogger(__name__)


class ProgramExecutionService:
    """Manages execution of bound programs when signals trigger."""
    """
    程序执行服务管理类

    采用单例模式的服务类，负责管理所有程序交易者的执行调度。
    提供线程安全的并发执行环境和状态管理功能。

    类设计：
    - 单例模式：确保全局唯一的服务实例
    - 线程安全：使用锁机制保护关键状态
    - 状态管理：维护程序执行状态和绑定关系
    - 资源控制：防止同一程序的并发执行冲突

    核心属性：
    - _running_bindings: 记录正在运行的绑定ID，防重复执行
    - _binding_locks: 为每个绑定提供独立的执行锁
    - _binding_states: 缓存绑定状态，优化定时触发性能

    并发控制：
    - 全局锁：保护服务实例的创建过程
    - 绑定锁：防止同一绑定的并发执行
    - 状态缓存：减少数据库访问，提高响应速度
    """

    _instance = None          # 单例实例
    _lock = threading.Lock()  # 类级别的线程锁

    def __new__(cls):
        """
        单例模式实现

        线程安全的单例创建，确保整个应用只有一个执行服务实例。
        使用双重检查锁定模式避免不必要的锁竞争。
        """
        if cls._instance is None:
            with cls._lock:  # 获取类级别锁
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False  # 标记为未初始化
        return cls._instance

    def __init__(self):
        """
        服务初始化

        初始化执行服务的核心数据结构和状态管理器。
        采用懒初始化模式，只在第一次创建时执行初始化逻辑。
        """
        if self._initialized:
            return  # 避免重复初始化

        self._initialized = True

        # 执行状态管理
        self._running_bindings: Dict[int, bool] = {}         # 正在运行的绑定ID集合
        self._binding_locks: Dict[int, threading.Lock] = {}  # 每个绑定的执行锁

        # Binding state cache for scheduled triggers (similar to AI Trader's strategies)
        # 绑定状态缓存，用于定时触发（类似于AI交易者的策略缓存）
        self._binding_states: Dict[int, dict] = {}  # binding_id -> 状态字典映射
        self._last_cache_refresh: Optional[datetime] = None
        self._cache_refresh_interval = 60  # Refresh cache every 60 seconds
        logger.info("[ProgramExecution] Service initialized")

    def on_signal_triggered(
        self,
        symbol: str,
        pool: dict,
        market_data_snapshot: dict,
        triggered_signals: list,
    ):
        """Called when a signal pool triggers - execute bound programs."""
        pool_id = pool.get("pool_id")
        pool_name = pool.get("pool_name", "Unknown")

        logger.info(f"[ProgramExecution] Signal triggered: {pool_name} (pool_id={pool_id}) on {symbol}")

        db = SessionLocal()
        try:
            # Find active bindings that include this pool_id
            all_bindings = db.query(AccountProgramBinding).filter(
                AccountProgramBinding.is_active == True
            ).all()

            # Filter bindings that have this pool_id in their signal_pool_ids
            bindings = []
            for binding in all_bindings:
                if binding.signal_pool_ids:
                    try:
                        pool_ids = json.loads(binding.signal_pool_ids)
                        if pool_id in pool_ids:
                            bindings.append(binding)
                    except:
                        pass

            if not bindings:
                logger.debug(f"[ProgramExecution] No bindings for pool_id={pool_id}")
                return

            logger.info(f"[ProgramExecution] Found {len(bindings)} bindings for pool_id={pool_id}")

            for binding in bindings:
                self._execute_binding(db, binding, symbol, pool, market_data_snapshot, triggered_signals)

        except Exception as e:
            logger.error(f"[ProgramExecution] Error processing signal: {e}")
        finally:
            db.close()

    def on_price_update(self, symbol: str, price: float, event_time: datetime):
        """Called on price updates - check for scheduled triggers (like AI Trader)."""
        try:
            # Refresh binding cache periodically
            self._maybe_refresh_cache()

            # Check each binding for scheduled trigger
            for binding_id, state in list(self._binding_states.items()):
                if self._should_trigger_scheduled(binding_id, state, event_time):
                    # Scheduled triggers have no specific symbol (empty string)
                    self._execute_scheduled_trigger(binding_id, "", event_time)

        except Exception as e:
            logger.error(f"[ProgramExecution] Error in on_price_update: {e}")

    def _maybe_refresh_cache(self):
        """Refresh binding state cache if needed."""
        now = datetime.now(timezone.utc)
        if (self._last_cache_refresh is None or
            (now - self._last_cache_refresh).total_seconds() >= self._cache_refresh_interval):
            self._refresh_binding_cache()
            self._last_cache_refresh = now

    def _refresh_binding_cache(self):
        """Load active bindings with scheduled trigger enabled into cache."""
        db = SessionLocal()
        try:
            bindings = db.query(AccountProgramBinding).filter(
                AccountProgramBinding.is_active == True,
                AccountProgramBinding.scheduled_trigger_enabled == True
            ).all()

            for binding in bindings:
                self._binding_states[binding.id] = {
                    "binding_id": binding.id,
                    "account_id": binding.account_id,
                    "program_id": binding.program_id,
                    "trigger_interval": binding.trigger_interval,
                    "last_trigger_at": binding.last_trigger_at,
                    "signal_pool_ids": json.loads(binding.signal_pool_ids) if binding.signal_pool_ids else [],
                }

            # Remove bindings that are no longer active/enabled
            active_ids = {b.id for b in bindings}
            for bid in list(self._binding_states.keys()):
                if bid not in active_ids:
                    del self._binding_states[bid]

            logger.debug(f"[ProgramExecution] Refreshed cache: {len(self._binding_states)} scheduled bindings")
        except Exception as e:
            logger.error(f"[ProgramExecution] Error refreshing cache: {e}")
        finally:
            db.close()

    def _should_trigger_scheduled(self, binding_id: int, state: dict, event_time: datetime) -> bool:
        """Check if binding should trigger based on scheduled interval."""
        # Check if already running
        if self._running_bindings.get(binding_id, False):
            return False

        trigger_interval = state.get("trigger_interval", 300)
        last_trigger_at = state.get("last_trigger_at")

        now_ts = event_time.timestamp()
        last_ts = last_trigger_at.timestamp() if last_trigger_at else 0
        time_diff = now_ts - last_ts

        if time_diff >= trigger_interval:
            logger.info(
                f"[ProgramExecution] Scheduled trigger for binding {binding_id}: "
                f"interval={trigger_interval}s, elapsed={time_diff:.1f}s"
            )
            return True

        return False

    def _execute_scheduled_trigger(self, binding_id: int, symbol: str, event_time: datetime):
        """Execute a scheduled trigger for a binding."""
        db = SessionLocal()
        try:
            binding = db.query(AccountProgramBinding).filter(
                AccountProgramBinding.id == binding_id,
                AccountProgramBinding.is_active == True
            ).first()

            if not binding:
                logger.warning(f"[ProgramExecution] Binding {binding_id} not found or inactive")
                return

            # Build minimal pool/trigger context for scheduled execution
            pool = {
                "pool_id": None,
                "pool_name": None,
            }
            market_data_snapshot = {}
            triggered_signals = []

            # Execute with trigger_type="scheduled"
            self._execute_binding(
                db, binding, symbol, pool, market_data_snapshot, triggered_signals,
                trigger_type="scheduled", event_time=event_time
            )

        except Exception as e:
            logger.error(f"[ProgramExecution] Error executing scheduled trigger: {e}")
        finally:
            db.close()

    def _execute_binding(
        self,
        db,
        binding: AccountProgramBinding,
        symbol: str,
        pool: dict,
        market_data_snapshot: dict,
        triggered_signals: list,
        trigger_type: str = "signal",
        event_time: Optional[datetime] = None,
    ):
        """Execute a single binding (program + account combination)."""
        binding_id = binding.id
        if event_time is None:
            event_time = datetime.now(timezone.utc)

        # Get or create lock for this binding
        if binding_id not in self._binding_locks:
            self._binding_locks[binding_id] = threading.Lock()

        lock = self._binding_locks[binding_id]

        # Check if already running
        if not lock.acquire(blocking=False):
            logger.warning(f"[ProgramExecution] Binding {binding_id} already running, skipping")
            return

        try:
            self._running_bindings[binding_id] = True

            # Update last_trigger_at immediately (like AI Trader does)
            # This resets the scheduled trigger timer for both signal and scheduled triggers
            binding.last_trigger_at = event_time
            db.commit()

            # Also update cache
            if binding_id in self._binding_states:
                self._binding_states[binding_id]["last_trigger_at"] = event_time

            # Load related objects
            program = binding.program
            account = binding.account

            if not program or not account:
                logger.error(f"[ProgramExecution] Binding {binding_id} missing program or account")
                return

            logger.info(f"[ProgramExecution] Executing: {program.name} via {account.name} (trigger: {trigger_type})")

            # Get wallet address for this account
            wallet_address = self._get_wallet_address(db, account)

            # Get trading environment and create trading client
            from services.hyperliquid_environment import get_global_trading_mode, get_hyperliquid_client, get_leverage_settings

            environment = get_global_trading_mode(db)
            trading_client = None
            if environment and wallet_address:
                try:
                    trading_client = get_hyperliquid_client(db, account.id, override_environment=environment)
                except Exception as e:
                    logger.warning(f"[ProgramExecution] Failed to create trading client: {e}")

            # Get leverage settings (same as AI Trader)
            leverage_settings = get_leverage_settings(db, account.id, environment or "mainnet")
            max_leverage = leverage_settings["max_leverage"]
            default_leverage = leverage_settings["default_leverage"]

            # Build MarketData with trading client (enable query recording for analysis)
            data_provider = DataProvider(
                db, account.id, environment or "mainnet", trading_client, record_queries=True
            )
            market_data = self._build_market_data(
                data_provider=data_provider,
                symbol=symbol,
                pool=pool,
                market_data_snapshot=market_data_snapshot,
                triggered_signals=triggered_signals,
                trigger_type=trigger_type,
                environment=environment or "mainnet",
                max_leverage=max_leverage,
                default_leverage=default_leverage,
            )

            # Get params (binding override > program default)
            params = {}
            if program.params:
                try:
                    params = json.loads(program.params)
                except:
                    pass
            if binding.params_override:
                try:
                    override = json.loads(binding.params_override)
                    params.update(override)
                except:
                    pass

            # Execute strategy
            result = execute_strategy(program.code, market_data, params)

            # Log execution with full context for analysis
            log_id = self._log_execution(
                db, binding, symbol, pool, wallet_address, result, params,
                data_provider, market_data, environment or "mainnet", trigger_type
            )

            # Handle decision if successful
            if result.success and result.decision:
                order_result = self._handle_decision(db, binding, result.decision, symbol, wallet_address)
                # Update log with order result and create HyperliquidTrade if filled
                # Skip for HOLD decisions - they don't execute orders
                op = result.decision.operation.lower() if hasattr(result.decision, 'operation') else result.decision.action.value
                if log_id and op != "hold":
                    self._update_log_with_order(
                        db, log_id, order_result, binding, result.decision,
                        wallet_address, environment or "mainnet"
                    )

        except Exception as e:
            logger.error(f"[ProgramExecution] Error executing binding {binding_id}: {e}")
        finally:
            self._running_bindings[binding_id] = False
            lock.release()

    def _get_wallet_address(self, db, account: Account) -> Optional[str]:
        """Get the active wallet address for an account."""
        from services.hyperliquid_environment import get_global_trading_mode

        environment = get_global_trading_mode(db)
        if not environment:
            return None

        wallet = db.query(HyperliquidWallet).filter(
            HyperliquidWallet.account_id == account.id,
            HyperliquidWallet.environment == environment,
            HyperliquidWallet.is_active == "true"
        ).first()

        return wallet.wallet_address if wallet else None

    def _build_market_data(
        self,
        data_provider: DataProvider,
        symbol: str,
        pool: dict,
        market_data_snapshot: dict,
        triggered_signals: list,
        trigger_type: str = "signal",
        environment: str = "mainnet",
        max_leverage: int = 10,
        default_leverage: int = 3,
    ) -> MarketData:
        """Build MarketData object for strategy execution.

        Populates all fields to match AI Trader's prompt context variables,
        ensuring Programs have access to the same information.
        """
        from program_trader.models import RegimeInfo

        account_info = data_provider.get_account_info()

        # Extract trigger context from pool (matches AI Trader's {trigger_context})
        signal_pool_name = pool.get("pool_name", "") or ""
        pool_logic = pool.get("logic", "OR") or "OR"

        # Build trigger market regime snapshot if this is a signal trigger
        trigger_market_regime = None
        if trigger_type == "signal" and symbol:
            # Get market regime at trigger time (same timeframe as first signal if available)
            timeframe = "5m"  # Default
            if triggered_signals:
                timeframe = triggered_signals[0].get("time_window", "5m")
            regime_info = data_provider.get_regime(symbol, timeframe)
            trigger_market_regime = regime_info

        return MarketData(
            # Account info
            available_balance=account_info.get("available_balance", 0.0),
            total_equity=account_info.get("total_equity", 0.0),
            used_margin=account_info.get("used_margin", 0.0),
            margin_usage_percent=account_info.get("margin_usage_percent", 0.0),
            maintenance_margin=account_info.get("maintenance_margin", 0.0),
            # Positions and trades
            positions=data_provider.get_positions(),
            recent_trades=data_provider.get_recent_trades(),
            open_orders=data_provider.get_open_orders(),
            # Trigger info (basic)
            trigger_symbol=symbol,
            trigger_type=trigger_type,
            # Trigger context (detailed)
            signal_pool_name=signal_pool_name,
            pool_logic=pool_logic,
            triggered_signals=triggered_signals or [],
            # Trigger market regime snapshot
            trigger_market_regime=trigger_market_regime,
            # Environment info
            environment=environment,
            max_leverage=max_leverage,
            default_leverage=default_leverage,
            # Data provider
            _data_provider=data_provider,
        )

    def _log_execution(
        self,
        db,
        binding: AccountProgramBinding,
        symbol: str,
        pool: dict,
        wallet_address: Optional[str],
        result,
        params: dict,
        data_provider: Optional[DataProvider],
        market_data,
        environment: str,
        trigger_type: str = "signal"
    ):
        """Log program execution to database with full context for analysis."""
        try:
            decision = result.decision
            # Handle both old (action) and new (operation) Decision formats
            action_value = None
            size_value = None
            if decision:
                if hasattr(decision, 'operation'):
                    action_value = decision.operation
                    size_value = decision.target_portion_of_balance
                elif hasattr(decision, 'action'):
                    action_value = decision.action.value if hasattr(decision.action, 'value') else decision.action
                    size_value = getattr(decision, 'size_usd', None)

            # Build comprehensive market_context for analysis/backtest
            positions_snapshot = {}
            if market_data and market_data.positions:
                for sym, pos in market_data.positions.items():
                    positions_snapshot[sym] = {
                        "side": pos.side,
                        "size": pos.size,
                        "entry_price": pos.entry_price,
                        "unrealized_pnl": getattr(pos, 'unrealized_pnl', 0),
                        "leverage": getattr(pos, 'leverage', None),
                    }

            market_context = {
                "input_data": {
                    "environment": environment,
                    "trigger_symbol": symbol,
                    "trigger_type": trigger_type,
                    "signal_pool_id": pool.get("pool_id"),
                    "signal_pool_name": pool.get("pool_name"),
                    "pool_logic": market_data.pool_logic if market_data else "OR",
                    "triggered_signals": market_data.triggered_signals if market_data else [],
                    "trigger_market_regime": {
                        "regime": market_data.trigger_market_regime.regime,
                        "conf": market_data.trigger_market_regime.conf,
                        "direction": market_data.trigger_market_regime.direction,
                        "indicators": market_data.trigger_market_regime.indicators,
                    } if market_data and market_data.trigger_market_regime else None,
                    "max_leverage": market_data.max_leverage if market_data else 10,
                    "default_leverage": market_data.default_leverage if market_data else 3,
                    "available_balance": market_data.available_balance if market_data else 0,
                    "total_equity": market_data.total_equity if market_data else 0,
                    "margin_usage_percent": market_data.margin_usage_percent if market_data else 0,
                    "positions": positions_snapshot,
                    "positions_count": len(positions_snapshot),
                    "open_orders": [
                        {
                            "order_id": o.order_id,
                            "symbol": o.symbol,
                            "side": o.side,
                            "direction": o.direction,
                            "order_type": o.order_type,
                            "size": o.size,
                            "price": o.price,
                            "trigger_price": o.trigger_price,
                            "reduce_only": o.reduce_only,
                            "timestamp": o.timestamp,
                        }
                        for o in (market_data.open_orders if market_data else [])
                    ],
                    "open_orders_count": len(market_data.open_orders) if market_data else 0,
                },
                "data_queries": data_provider.get_query_log() if data_provider else [],
                "execution_logs": getattr(result, 'logs', []) or [],
            }

            log = ProgramExecutionLog(
                binding_id=binding.id,
                account_id=binding.account_id,
                program_id=binding.program_id,
                program_name=binding.program.name if binding.program else None,
                trigger_type=trigger_type,
                trigger_symbol=symbol,
                signal_pool_id=pool.get("pool_id"),
                wallet_address=wallet_address,
                environment=environment,  # Track execution environment for attribution
                success=result.success,
                error_message=result.error,
                execution_time_ms=result.execution_time_ms,
                decision_action=action_value,
                decision_symbol=decision.symbol if decision else None,
                decision_size_usd=size_value,
                decision_leverage=decision.leverage if decision else None,
                decision_reason=decision.reason if decision else None,
                decision_json=json.dumps(decision.to_dict()) if decision else None,
                params_snapshot=json.dumps(params) if params else None,
                market_context=json.dumps(market_context),
            )
            db.add(log)
            db.commit()
            db.refresh(log)
            return log.id
        except Exception as e:
            logger.error(f"[ProgramExecution] Failed to log execution: {e}")
            return None

    def _update_log_with_order(
        self,
        db,
        log_id: int,
        order_result: Optional[dict],
        binding: AccountProgramBinding,
        decision,
        wallet_address: str,
        environment: str
    ):
        """Update execution log with order IDs and create HyperliquidTrade if filled."""
        try:
            log = db.query(ProgramExecutionLog).filter(ProgramExecutionLog.id == log_id).first()
            if not log:
                return

            # If order failed (order_result is None), mark the log as failed
            if order_result is None:
                log.success = False
                log.error_message = (log.error_message or "") + " [Order execution failed]"
                db.commit()
                logger.info(f"[ProgramExecution] Updated log {log_id} with order failure status")
                return

            # Extract order IDs from result
            order_id = order_result.get('order_id')
            tp_order_id = order_result.get('tp_order_id')
            sl_order_id = order_result.get('sl_order_id')

            # Update log with order IDs
            if order_id:
                log.hyperliquid_order_id = str(order_id)
            if tp_order_id:
                log.tp_order_id = str(tp_order_id)
            if sl_order_id:
                log.sl_order_id = str(sl_order_id)
            db.commit()
            logger.info(f"[ProgramExecution] Updated log {log_id} with order IDs")

            # Create HyperliquidTrade record only if order is filled
            order_status = order_result.get('status')
            if order_status == 'filled':
                self._create_hyperliquid_trade(
                    binding, decision, order_result, wallet_address, environment
                )

        except Exception as e:
            logger.error(f"[ProgramExecution] Failed to update log with order: {e}")

    def _create_hyperliquid_trade(
        self,
        binding: AccountProgramBinding,
        decision,
        order_result: dict,
        wallet_address: str,
        environment: str
    ):
        """Create HyperliquidTrade record for filled orders (same as trading_commands.py)."""
        try:
            from database.snapshot_connection import SnapshotSessionLocal
            from database.snapshot_models import HyperliquidTrade
            from decimal import Decimal

            op = decision.operation.lower() if hasattr(decision, 'operation') else decision.action.value
            order_id = order_result.get('order_id')
            order_status = order_result.get('status')
            leverage = decision.leverage if hasattr(decision, 'leverage') else 1

            snapshot_db = SnapshotSessionLocal()
            try:
                trade_record = HyperliquidTrade(
                    account_id=binding.account_id,
                    environment=environment,
                    wallet_address=wallet_address,
                    symbol=decision.symbol,
                    side=op,
                    quantity=Decimal(str(order_result.get('filled_amount', 0))),
                    price=Decimal(str(order_result.get('average_price', 0))),
                    leverage=leverage,
                    order_id=order_id,
                    order_status=order_status,
                    trade_value=Decimal(str(order_result.get('filled_amount', 0))) * Decimal(str(order_result.get('average_price', 0))),
                    fee=Decimal(str(order_result.get('fee', 0)))
                )
                snapshot_db.add(trade_record)
                snapshot_db.commit()
                logger.info(f"[ProgramExecution] HyperliquidTrade record saved for binding {binding.id}")
            finally:
                snapshot_db.close()
        except Exception as e:
            logger.warning(f"[ProgramExecution] Failed to save HyperliquidTrade record: {e}")

    def _handle_decision(
        self,
        db,
        binding: AccountProgramBinding,
        decision,
        symbol: str,
        wallet_address: Optional[str]
    ):
        """Handle the decision from program execution - execute actual trade."""
        from program_trader.executor import validate_decision
        from services.hyperliquid_environment import get_global_trading_mode, get_hyperliquid_client

        op = decision.operation.lower() if hasattr(decision, 'operation') else decision.action.value

        if op == "hold":
            logger.info(f"[ProgramExecution] Binding {binding.id} decision: HOLD - {decision.reason}")
            return None  # HOLD is not an order, no success/failure

        # Validate decision
        positions_dict = {}
        environment = get_global_trading_mode(db)
        if hasattr(decision, 'operation'):
            # New Decision format - get positions for validation
            if environment and wallet_address:
                try:
                    client = get_hyperliquid_client(db, binding.account_id, override_environment=environment)
                    data_provider = DataProvider(db, binding.account_id, environment, client)
                    for sym, pos in data_provider.get_positions().items():
                        positions_dict[sym] = {"side": pos.side, "size": pos.size}
                except Exception as e:
                    logger.warning(f"[ProgramExecution] Failed to get positions for validation: {e}")

            is_valid, errors = validate_decision(decision, positions_dict)
            if not is_valid:
                logger.error(f"[ProgramExecution] Invalid decision: {errors}")
                return False

        logger.info(
            f"[ProgramExecution] Binding {binding.id} decision: {op} "
            f"{decision.symbol} portion={getattr(decision, 'target_portion_of_balance', 0)} "
            f"leverage={decision.leverage}x - {decision.reason}"
        )

        # Check wallet
        if not wallet_address:
            logger.error(f"[ProgramExecution] No wallet address for binding {binding.id}")
            return False

        if not environment:
            logger.error(f"[ProgramExecution] No trading environment configured")
            return False

        try:
            # Initialize trading client using correct factory function
            client = get_hyperliquid_client(db, binding.account_id, override_environment=environment)

            # Get account info and current market price
            account_info = client.get_account_state(db)
            available_balance = account_info.get("available_balance", 0)

            # Get real-time market price for price bounds enforcement
            from services.hyperliquid_market_data import get_last_price_from_hyperliquid
            market_price = get_last_price_from_hyperliquid(decision.symbol, environment)
            if not market_price or market_price <= 0:
                market_price = getattr(decision, 'max_price', None) or getattr(decision, 'min_price', None)
            if not market_price:
                logger.error(f"[ProgramExecution] No price available for {decision.symbol}")
                return False

            # Execute based on operation type
            order_result = None
            if op == "buy":
                order_result = self._execute_buy(
                    db, client, decision, available_balance, market_price, environment
                )
            elif op == "sell":
                order_result = self._execute_sell(
                    db, client, decision, available_balance, market_price, environment
                )
            elif op == "close":
                order_result = self._execute_close(
                    db, client, decision, positions_dict, market_price, environment
                )

            # Log result
            if order_result and order_result.get("status") in ["filled", "resting"]:
                logger.info(f"[ProgramExecution] Order succeeded: {order_result}")
                return order_result  # Return full order_result for HyperliquidTrade creation
            else:
                error_msg = order_result.get('error', 'Unknown error') if order_result else 'No result'
                logger.error(f"[ProgramExecution] Order failed: {error_msg}")
                return None

        except Exception as e:
            logger.error(f"[ProgramExecution] Error executing trade: {e}")
            return None

    def _execute_buy(self, db, client, decision, available_balance, market_price, environment):
        """Execute BUY order with price bounds and IOC->GTC retry."""
        symbol = decision.symbol
        leverage = decision.leverage
        portion = getattr(decision, 'target_portion_of_balance', 0)
        time_in_force = getattr(decision, 'time_in_force', 'Ioc')

        # Calculate position size
        margin = available_balance * portion
        order_value = margin * leverage
        quantity = round(order_value / market_price, 6)

        # Use max_price from decision directly (no bounds adjustment)
        max_price = getattr(decision, 'max_price', None)
        if max_price:
            price_to_use = max_price
        else:
            price_to_use = market_price * 1.005  # Default: slightly above market
            logger.warning(f"[ProgramExecution] BUY {symbol}: No max_price, using {price_to_use:.2f}")

        logger.info(
            f"[ProgramExecution] BUY {symbol}: size={quantity}, price={price_to_use:.2f}, "
            f"leverage={leverage}x, TIF={time_in_force}"
        )

        # Place order
        order_result = client.place_order_with_tpsl(
            db=db, symbol=symbol, is_buy=True, size=quantity, price=price_to_use,
            leverage=leverage, time_in_force=time_in_force, reduce_only=False,
            take_profit_price=getattr(decision, 'take_profit_price', None),
            stop_loss_price=getattr(decision, 'stop_loss_price', None),
            tp_execution=getattr(decision, 'tp_execution', 'limit'),
            sl_execution=getattr(decision, 'sl_execution', 'limit'),
        )

        # IOC->GTC retry if no liquidity
        if order_result and order_result.get('status') == 'error':
            error_msg = order_result.get('error', '').lower()
            if 'could not immediately match' in error_msg or 'no resting orders' in error_msg:
                logger.warning(f"[ProgramExecution] BUY {symbol} IOC failed, retrying with GTC...")
                order_result = client.place_order_with_tpsl(
                    db=db, symbol=symbol, is_buy=True, size=quantity, price=price_to_use,
                    leverage=leverage, time_in_force="Gtc", reduce_only=False,
                    take_profit_price=getattr(decision, 'take_profit_price', None),
                    stop_loss_price=getattr(decision, 'stop_loss_price', None),
                    tp_execution=getattr(decision, 'tp_execution', 'limit'),
                    sl_execution=getattr(decision, 'sl_execution', 'limit'),
                )
                if order_result and order_result.get('status') in ['filled', 'resting']:
                    logger.info(f"[ProgramExecution] BUY {symbol} GTC fallback succeeded")

        return order_result

    def _execute_sell(self, db, client, decision, available_balance, market_price, environment):
        """Execute SELL order with price bounds and IOC->GTC retry."""
        symbol = decision.symbol
        leverage = decision.leverage
        portion = getattr(decision, 'target_portion_of_balance', 0)
        time_in_force = getattr(decision, 'time_in_force', 'Ioc')

        # Calculate position size
        margin = available_balance * portion
        order_value = margin * leverage
        quantity = round(order_value / market_price, 6)

        # Use min_price from decision directly (no bounds adjustment)
        min_price = getattr(decision, 'min_price', None)
        if min_price:
            price_to_use = min_price
        else:
            price_to_use = market_price * 0.995  # Default: slightly below market
            logger.warning(f"[ProgramExecution] SELL {symbol}: No min_price, using {price_to_use:.2f}")

        logger.info(
            f"[ProgramExecution] SELL {symbol}: size={quantity}, price={price_to_use:.2f}, "
            f"leverage={leverage}x, TIF={time_in_force}"
        )

        # Place order
        order_result = client.place_order_with_tpsl(
            db=db, symbol=symbol, is_buy=False, size=quantity, price=price_to_use,
            leverage=leverage, time_in_force=time_in_force, reduce_only=False,
            take_profit_price=getattr(decision, 'take_profit_price', None),
            stop_loss_price=getattr(decision, 'stop_loss_price', None),
            tp_execution=getattr(decision, 'tp_execution', 'limit'),
            sl_execution=getattr(decision, 'sl_execution', 'limit'),
        )

        # IOC->GTC retry if no liquidity
        if order_result and order_result.get('status') == 'error':
            error_msg = order_result.get('error', '').lower()
            if 'could not immediately match' in error_msg or 'no resting orders' in error_msg:
                logger.warning(f"[ProgramExecution] SELL {symbol} IOC failed, retrying with GTC...")
                order_result = client.place_order_with_tpsl(
                    db=db, symbol=symbol, is_buy=False, size=quantity, price=price_to_use,
                    leverage=leverage, time_in_force="Gtc", reduce_only=False,
                    take_profit_price=getattr(decision, 'take_profit_price', None),
                    stop_loss_price=getattr(decision, 'stop_loss_price', None),
                    tp_execution=getattr(decision, 'tp_execution', 'limit'),
                    sl_execution=getattr(decision, 'sl_execution', 'limit'),
                )
                if order_result and order_result.get('status') in ['filled', 'resting']:
                    logger.info(f"[ProgramExecution] SELL {symbol} GTC fallback succeeded")

        return order_result

    def _execute_close(self, db, client, decision, positions_dict, market_price, environment):
        """Execute CLOSE order with multi-retry and GTC fallback."""
        symbol = decision.symbol
        portion = getattr(decision, 'target_portion_of_balance', 1.0)

        # Get position info
        pos_info = positions_dict.get(symbol, {})
        is_long = pos_info.get("side") == "long"
        position_size = pos_info.get("size", 0)

        if not position_size or position_size <= 0:
            logger.warning(f"[ProgramExecution] CLOSE {symbol}: No position found")
            return {"status": "error", "error": "No position to close"}

        close_size = position_size * portion

        # Use price from decision directly (no bounds adjustment)
        if is_long:
            # Close long = sell, use min_price
            ai_price = getattr(decision, 'min_price', None)
            fallback_mult = 0.995
        else:
            # Close short = buy, use max_price
            ai_price = getattr(decision, 'max_price', None)
            fallback_mult = 1.005

        if ai_price:
            close_price = ai_price
        else:
            close_price = market_price * fallback_mult

        # Validate price direction (only when AI didn't provide price)
        if not ai_price:
            if not is_long and close_price < market_price:
                close_price = market_price * 1.005
            elif is_long and close_price > market_price:
                close_price = market_price * 0.995

        logger.info(
            f"[ProgramExecution] CLOSE {symbol}: size={close_size}, price={close_price:.2f}, "
            f"direction={'long->sell' if is_long else 'short->buy'}"
        )

        # Multi-retry with progressive price adjustment
        max_retries = 4
        price_mults = [0.996, 0.994, 0.992, 0.99] if is_long else [1.004, 1.006, 1.008, 1.01]
        order_result = None

        for retry in range(max_retries):
            attempt_price = close_price if retry == 0 else market_price * price_mults[retry]
            if retry > 0:
                logger.info(f"[ProgramExecution] CLOSE {symbol} retry {retry}: price={attempt_price:.2f}")

            attempt_result = client.place_order_with_tpsl(
                db=db, symbol=symbol, is_buy=(not is_long), size=close_size,
                price=attempt_price, leverage=1, time_in_force="Ioc", reduce_only=True,
                take_profit_price=None, stop_loss_price=None,
            )

            if attempt_result and attempt_result.get('status') == 'filled':
                order_result = attempt_result
                if retry > 0:
                    logger.info(f"[ProgramExecution] CLOSE {symbol} succeeded on retry {retry}")
                break

            error_msg = attempt_result.get('error', '').lower() if attempt_result else ''
            should_retry = 'could not immediately match' in error_msg or 'no resting orders' in error_msg
            if not should_retry or retry >= max_retries - 1:
                order_result = attempt_result
                break

        # GTC fallback if IOC retries failed
        if not order_result or order_result.get('status') != 'filled':
            boundary_mult = 0.99 if is_long else 1.01
            fallback_price = market_price * boundary_mult
            logger.warning(f"[ProgramExecution] CLOSE {symbol} fallback: GTC at {fallback_price:.2f}")

            order_result = client.place_order_with_tpsl(
                db=db, symbol=symbol, is_buy=(not is_long), size=close_size,
                price=fallback_price, leverage=1, time_in_force="Gtc", reduce_only=True,
                take_profit_price=None, stop_loss_price=None,
            )

        return order_result


# Singleton instance
program_execution_service = ProgramExecutionService()
