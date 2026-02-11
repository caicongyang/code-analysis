"""
================================================================================
NanoBot Memory Store - 记忆存储模块
================================================================================

功能描述:
    负责 Agent 的持久化记忆管理，包括短期记忆（每日笔记）和长期记忆。
    Agent 可以通过写入记忆来保存重要的信息和决策。

记忆类型:
    1. 每日笔记 (Daily Notes):
       - 文件路径: memory/YYYY-MM-DD.md
       - 用途: 记录每天的工作、对话和发现
       - 特点: 按日期自动命名，便于查找

    2. 长期记忆 (Long-term Memory):
       - 文件路径: memory/MEMORY.md
       - 用途: 存储重要的、持久的信息
       - 特点: 不会被定期清理

记忆读取时机:
    - 系统启动时: 读取长期记忆和今天的笔记
    - 消息处理时: 构建上下文时会包含记忆内容

与 Agent 的交互:
    - Agent 可以调用 append_today() 追加今天的笔记
    - Agent 可以调用 write_long_term() 更新长期记忆
    - Agent 可以调用 get_memory_context() 获取所有记忆

================================================================================
"""

from pathlib import Path
from datetime import datetime

from nanobot.utils.helpers import ensure_dir, today_date


class MemoryStore:
    """
    ========================================================================
    MemoryStore - 记忆存储类
    ========================================================================
    
    负责管理 Agent 的所有持久化记忆。
    
    文件结构:
        workspace/
        └── memory/
            ├── MEMORY.md          # 长期记忆
            ├── 2026-02-11.md      # 今天的笔记
            ├── 2026-02-10.md      # 昨天的笔记
            └── ...
    
    核心方法:
        - read_today(): 读取今天的笔记
        - append_today(): 追加今天的笔记
        - read_long_term(): 读取长期记忆
        - write_long_term(): 写入长期记忆
        - get_memory_context(): 获取所有记忆（用于上下文构建）
        - get_recent_memories(): 获取最近 N 天的记忆
        - list_memory_files(): 列出所有记忆文件
    
    ========================================================================
    """
    
    def __init__(self, workspace: Path):
        """
        初始化记忆存储
        
        参数:
            workspace: Path，工作空间根目录
        
        初始化过程:
            1. 保存工作空间路径
            2. 创建 memory 目录（如果不存在）
            3. 确定长期记忆文件的路径
        """
        self.workspace = workspace
        self.memory_dir = ensure_dir(workspace / "memory")
        self.memory_file = self.memory_dir / "MEMORY.md"
    
    def get_today_file(self) -> Path:
        """
        获取今天记忆笔记的文件路径
        
        文件命名格式:
            YYYY-MM-DD.md
        
        返回:
            Path，今天记忆文件的完整路径
        
        使用示例:
            today_file = memory_store.get_today_file()
            print(f"今天的笔记: {today_file}")
        """
        return self.memory_dir / f"{today_date()}.md"
    
    def read_today(self) -> str:
        """
        读取今天的记忆笔记
        
        用途:
            - Agent 启动时加载今天的上下文
            - 构建系统提示词时包含今天的信息
        
        返回:
            str，今天的笔记内容
            如果文件不存在，返回空字符串
        
        使用示例:
            today_notes = memory_store.read_today()
            if today_notes:
                print(f"今天的笔记: {today_notes[:100]}...")
        """
        today_file = self.get_today_file()
        
        # 检查文件是否存在
        if today_file.exists():
            return today_file.read_text(encoding="utf-8")
        return ""
    
    def append_today(self, content: str) -> None:
        """
        向今天的记忆笔记追加内容
        
        用途:
            - Agent 记录新的发现或决策
            - 保存临时但重要的信息
        
        处理逻辑:
            1. 检查今天的文件是否存在
            2. 如果存在，读取现有内容
            3. 在末尾追加新内容
            4. 如果不存在，创建新文件（自动添加日期标题）
        
        参数:
            content: str，要追加的内容
        
        使用示例:
            # 记录一个发现
            memory_store.append_today("- 发现: SSH 连接需要配置超时")
        
        注意:
            - 如果是新文件，会自动添加 "# YYYY-MM-DD" 标题
            - 使用换行符分隔现有内容和新内容
        """
        today_file = self.get_today_file()
        
        if today_file.exists():
            # 文件存在，读取并追加
            existing = today_file.read_text(encoding="utf-8")
            content = existing + "\n" + content
        else:
            # 新文件，添加日期标题
            header = f"# {today_date()}\n\n"
            content = header + content
        
        # 写入文件
        today_file.write_text(content, encoding="utf-8")
    
    def read_long_term(self) -> str:
        """
        读取长期记忆（MEMORY.md）
        
        用途:
            - 存储 Agent 的核心配置和偏好
            - 记录重要的用户信息
            - 保存关键的决策和事实
        
        长期记忆示例内容:
            - 用户偏好（"喜欢用 Vim"）
            - 项目配置（"使用 PostgreSQL 数据库"）
            - 重要事实（"API 密钥保存在 .env 文件中"）
        
        返回:
            str，长期记忆的完整内容
            如果文件不存在，返回空字符串
        
        使用示例:
            long_term = memory_store.read_long_term()
        """
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""
    
    def write_long_term(self, content: str) -> None:
        """
        写入长期记忆（MEMORY.md）
        
        用途:
            - 更新 Agent 的核心配置
            - 记录重要的用户偏好
            - 保存关键的项目信息
        
        处理逻辑:
            - 直接覆盖整个 MEMORY.md 文件
            - 不追加，完全替换
        
        参数:
            content: str，要写入的完整内容
        
        使用示例:
            # 更新用户偏好
            memory_store.write_long_term(
                "用户偏好:\n- 使用 Vim 编辑器\n- 喜欢深色模式"
            )
        
        注意:
            - 这是覆盖操作，不是追加
            - 确保内容完整后再调用此方法
        """
        self.memory_file.write_text(content, encoding="utf-8")
    
    def get_recent_memories(self, days: int = 7) -> str:
        """
        获取最近 N 天的记忆笔记
        
        用途:
            - 为 Agent 提供近期的上下文
            - 回顾最近的工作进展
        
        参数:
            days: int，回溯的天数，默认为 7 天
        
        处理逻辑:
            1. 从今天开始，往回遍历 N 天
            2. 检查每天的文件是否存在
            3. 读取存在的文件内容
            4. 使用分隔符连接所有内容
        
        返回:
            str，所有近期记忆的合并内容
        
        使用示例:
            # 获取过去 3 天的记忆
            recent = memory_store.get_recent_memories(days=3)
        """
        from datetime import timedelta
        
        memories = []
        today = datetime.now().date()
        
        # 遍历最近 N 天
        for i in range(days):
            date = today - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            file_path = self.memory_dir / f"{date_str}.md"
            
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                memories.append(content)
        
        # 使用分隔符连接
        return "\n\n---\n\n".join(memories)
    
    def list_memory_files(self) -> list[Path]:
        """
        列出所有记忆文件
        
        用途:
            - 查看历史记忆
            - 清理旧文件
        
        返回:
            list[Path]，所有记忆文件的路径列表
            按日期降序排列（最新的在前）
        
        使用示例:
            files = memory_store.list_memory_files()
            for f in files:
                print(f.name)
        """
        if not self.memory_dir.exists():
            return []
        
        # 查找所有日期格式的文件
        files = list(self.memory_dir.glob("????-??-??.md"))
        
        # 按日期降序排列
        return sorted(files, reverse=True)
    
    def get_memory_context(self) -> str:
        """
        获取完整的记忆上下文（用于构建系统提示词）
        
        用途:
            - 在 build_system_prompt() 中调用
            - 为 Agent 提供所有相关记忆
        
        上下文组成:
            1. 长期记忆（MEMORY.md）
            2. 今天的笔记
        
        格式:
            ## Long-term Memory
            [长期记忆内容]
            
            ## Today's Notes
            [今天的内容]
        
        返回:
            str，格式化的记忆上下文
            如果没有任何记忆，返回空字符串
        
        使用示例:
            context = memory_store.get_memory_context()
            if context:
                prompt += f"\n\n# Memory\n\n{context}"
        """
        parts = []
        
        # 1. 长期记忆
        long_term = self.read_long_term()
        if long_term:
            parts.append("## Long-term Memory\n" + long_term)
        
        # 2. 今天的笔记
        today = self.read_today()
        if today:
            parts.append("## Today's Notes\n" + today)
        
        # 使用空行连接
        return "\n\n".join(parts) if parts else ""