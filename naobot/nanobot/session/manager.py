# -*- coding: utf-8 -*-
"""
================================================================================
Session Manager - 会话管理器模块
================================================================================

功能描述:
    管理对话会话的存储和读取。对话历史以 JSONL 格式持久化存储，
    支持获取历史消息、创建会话、删除会话等功能。

核心概念:
    1. Session: 单个对话会话，包含消息列表和元数据
    2. SessionManager: 会话管理器，负责会话的加载和保存
    3. Session Key: 会话唯一标识（格式: channel:chat_id）

存储格式:
    - 目录: ~/.nanobot/sessions/
    - 文件: {safe_key}.jsonl
    - 格式: JSONL（每行一条 JSON）
        - 第一行：元数据（创建时间、更新时间等）
        - 后续行：消息记录

主要组件:
    - Session: 对话会话类
    - SessionManager: 会话管理器类

================================================================================
"""

import json
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger

from nanobot.utils.helpers import ensure_dir, safe_filename


@dataclass
class Session:
    """
    ========================================================================
    Session - 对话会话类
    ========================================================================
    
    表示一个对话会话，存储用户和助手之间的消息历史。
    
    属性说明:
        - key: 会话唯一标识（格式: channel:chat_id）
        - messages: 消息列表
        - created_at: 会话创建时间
        - updated_at: 最后更新时间
        - metadata: 元数据（如系统提示词版本等）
    
    消息格式:
        {
            "role": "user" | "assistant" | "tool",
            "content": "消息内容",
            "timestamp": "ISO 时间戳"
        }
    
    ========================================================================
    """
    
    key: str
    """会话唯一标识（channel:chat_id）"""
    
    messages: list[dict[str, Any]] = field(default_factory=list)
    """消息列表"""
    
    created_at: datetime = field(default_factory=datetime.now)
    """会话创建时间"""
    
    updated_at: datetime = field(default_factory=datetime.now)
    """最后更新时间"""
    
    metadata: dict[str, Any] = field(default_factory=dict)
    """元数据"""
    
    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        """
        添加消息到会话
        
        功能描述:
            向消息列表中添加一条新消息。
        
        参数说明:
            role: str，角色（user/assistant/tool）
            content: str，消息内容
            **kwargs: 其他附加字段
        """
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }
        self.messages.append(msg)
        self.updated_at = datetime.now()
    
    def get_history(self, max_messages: int = 50) -> list[dict[str, Any]]:
        """
        获取消息历史
        
        功能描述:
            获取最近 N 条消息用于 LLM 上下文。
        
        参数说明:
            max_messages: int，最大返回消息数
        
        返回值:
            list[dict]，格式化的消息列表（只包含 role 和 content）
        """
        # 获取最近的消息
        recent = self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages
        
        # 转换为 LLM 格式
        return [{"role": m["role"], "content": m["content"]} for m in recent]
    
    def clear(self) -> None:
        """
        清空会话
        
        功能描述:
            删除所有消息并更新时间戳。
        """
        self.messages = []
        self.updated_at = datetime.now()


class SessionManager:
    """
    ========================================================================
    SessionManager - 会话管理器类
    ========================================================================
    
    负责会话的加载、保存和列表操作。
    
    功能特点:
        1. 内存缓存：加速会话访问
        2. 持久化存储：JSONL 格式
        3. 自动保存：每次修改后自动保存
        
    使用流程:
        1. 创建 SessionManager
        2. 调用 get_or_create() 获取会话
        3. 调用 add_message() 添加消息
        4. 调用 save() 保存（add_message 会自动更新缓存）
    
    ========================================================================
    """
    
    def __init__(self, workspace: Path):
        """
        初始化会话管理器
        
        参数说明:
            workspace: Path，工作空间路径（用于构建 sessions 目录）
        """
        self.workspace = workspace
        self.sessions_dir = ensure_dir(Path.home() / ".nanobot" / "sessions")
        self._cache: dict[str, Session] = {}
    
    def _get_session_path(self, key: str) -> Path:
        """
        获取会话文件路径
        
        功能描述:
            根据会话 key 生成安全的文件名和路径。
        
        参数说明:
            key: str，会话 key
        
        返回值:
            Path，会话文件的完整路径
        """
        safe_key = safe_filename(key.replace(":", "_"))
        return self.sessions_dir / f"{safe_key}.jsonl"
    
    def get_or_create(self, key: str) -> Session:
        """
        获取或创建会话
        
        功能描述:
            根据 key 获取会话，如果不存在则创建新会话。
        
        参数说明:
            key: str，会话 key（通常为 channel:chat_id）
        
        返回值:
            Session，对话会话对象
        
        处理流程:
            1. 检查缓存
            2. 如果缓存命中，直接返回
            3. 尝试从磁盘加载
            4. 如果加载失败，创建新会话
            5. 加入缓存并返回
        """
        # 检查缓存
        if key in self._cache:
            return self._cache[key]
        
        # 尝试从磁盘加载
        session = self._load(key)
        if session is None:
            session = Session(key=key)
        
        self._cache[key] = session
        return session
    
    def _load(self, key: str) -> Session | None:
        """
        从磁盘加载会话
        
        参数说明:
            key: str，会话 key
        
        返回值:
            Session | None，加载的会话或 None（如果不存在）
        """
        path = self._get_session_path(key)
        
        if not path.exists():
            return None
        
        try:
            messages = []
            metadata = {}
            created_at = None
            
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    data = json.loads(line)
                    
                    if data.get("_type") == "metadata":
                        # 元数据行
                        metadata = data.get("metadata", {})
                        created_at_str = data.get("created_at")
                        created_at = datetime.fromisoformat(created_at_str) if created_at_str else None
                    else:
                        # 消息行
                        messages.append(data)
            
            return Session(
                key=key,
                messages=messages,
                created_at=created_at or datetime.now(),
                metadata=metadata
            )
        except Exception as e:
            logger.warning(f"Failed to load session {key}: {e}")
            return None
    
    def save(self, session: Session) -> None:
        """
        保存会话到磁盘
        
        功能描述:
            将会话写入 JSONL 文件。
        
        参数说明:
            session: Session，要保存的会话
        """
        path = self._get_session_path(session.key)
        
        with open(path, "w") as f:
            # 写入元数据
            metadata_line = {
                "_type": "metadata",
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "metadata": session.metadata
            }
            f.write(json.dumps(metadata_line) + "\n")
            
            # 写入消息
            for msg in session.messages:
                f.write(json.dumps(msg) + "\n")
        
        # 更新缓存
        self._cache[session.key] = session
    
    def delete(self, key: str) -> bool:
        """
        删除会话
        
        功能描述:
            从缓存和磁盘中删除会话。
        
        参数说明:
            key: str，会话 key
        
        返回值:
            bool，是否成功删除
        """
        # 从缓存移除
        self._cache.pop(key, None)
        
        # 删除文件
        path = self._get_session_path(key)
        if path.exists():
            path.unlink()
            return True
        return False
    
    def list_sessions(self) -> list[dict[str, Any]]:
        """
        列出所有会话
        
        功能描述:
            扫描 sessions 目录，返回所有会话的摘要信息。
        
        返回值:
            list[dict，会话信息列表，按更新时间降序排列
        """
        sessions = []
        
        for path in self.sessions_dir.glob("*.jsonl"):
            try:
                # 只读取第一行（元数据）
                with open(path) as f:
                    first_line = f.readline().strip()
                    if first_line:
                        data = json.loads(first_line)
                        if data.get("_type") == "metadata":
                            sessions.append({
                                "key": path.stem.replace("_", ":"),
                                "created_at": data.get("created_at"),
                                "updated_at": data.get("updated_at"),
                                "path": str(path)
                            })
            except Exception:
                continue
        
        # 按更新时间降序排列
        return sorted(sessions, key=lambda x: x.get("updated_at", ""), reverse=True)
