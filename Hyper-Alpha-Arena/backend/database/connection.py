from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# Prefer explicit env override; default to service name for containerized deployment
# Default to docker-compose service name; override via env when needed
# 优先使用显式环境变量覆盖；容器化部署时默认使用服务名
# 默认使用docker-compose服务名；需要时通过环境变量覆盖
DATABASE_URL = os.environ.get('DATABASE_URL', "postgresql://alpha_user:alpha_pass@postgres:5432/alpha_arena")
# 数据库连接URL配置
# - 用户名: alpha_user（交易系统专用数据库用户）
# - 密码: alpha_pass（生产环境中应使用强密码）
# - 主机: postgres（Docker容器服务名，本地开发时可改为localhost）
# - 端口: 5432（PostgreSQL默认端口）
# - 数据库: alpha_arena（主数据库，存储所有交易相关数据）

# Allow tuning via environment variables but provide sensible defaults for our workload
# 允许通过环境变量调优，但为我们的工作负载提供合理的默认值
POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "20"))                    # 连接池基础大小
POOL_MAX_OVERFLOW = int(os.environ.get("DB_POOL_MAX_OVERFLOW", "20"))    # 连接池最大溢出数量
POOL_RECYCLE = int(os.environ.get("DB_POOL_RECYCLE", "1800"))            # 连接回收时间（秒）
POOL_TIMEOUT = int(os.environ.get("DB_POOL_TIMEOUT", "30"))              # 获取连接超时时间（秒）

# 数据库连接池配置详解：
# - POOL_SIZE (20): 连接池中保持的持久连接数量，适合中等并发量
# - POOL_MAX_OVERFLOW (20): 高并发时可额外创建的连接数，总连接数=POOL_SIZE+MAX_OVERFLOW
# - POOL_RECYCLE (1800秒=30分钟): 连接在池中的最长存活时间，避免长时间闲置连接
# - POOL_TIMEOUT (30秒): 从池中获取连接的最大等待时间，超时将抛出异常

engine = create_engine(
    DATABASE_URL,                    # 数据库连接URL
    pool_size=POOL_SIZE,            # 连接池大小
    max_overflow=POOL_MAX_OVERFLOW,  # 最大溢出连接数
    pool_recycle=POOL_RECYCLE,      # 连接回收时间
    pool_timeout=POOL_TIMEOUT,      # 连接获取超时
)
# SQLAlchemy数据库引擎
# 负责管理数据库连接，处理SQL执行，维护连接池
# 这是整个应用与PostgreSQL数据库交互的核心组件

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# 数据库会话工厂
# - autocommit=False: 禁用自动提交，需要显式调用commit()
# - autoflush=False: 禁用自动刷新，提高性能并便于事务管理
# - bind=engine: 绑定到上面创建的数据库引擎

Base = declarative_base()
# SQLAlchemy声明式基类
# 所有数据库模型类都继承自此基类，用于：
# - 定义表结构和字段映射
# - 建立关系映射
# - 生成数据库表结构


def get_db():
    """
    数据库会话依赖注入函数

    FastAPI依赖注入系统使用的标准数据库会话提供器。
    每个API请求都会获得一个独立的数据库会话，确保事务隔离。

    工作原理：
    1. 创建新的数据库会话
    2. 通过yield将会话提供给请求处理函数
    3. 请求完成后自动关闭会话，释放连接回池中

    使用方式：
    @app.get("/api/example")
    def example_endpoint(db: Session = Depends(get_db)):
        # 使用db进行数据库操作
        pass

    优势：
    - 自动会话管理，无需手动关闭
    - 连接池复用，提高性能
    - 异常安全，即使出错也能正确释放资源
    - 支持事务回滚
    """
    db = SessionLocal()  # 创建新的数据库会话实例
    try:
        yield db        # 提供给API路由使用
    finally:
        db.close()      # 确保会话关闭，连接返回池中
