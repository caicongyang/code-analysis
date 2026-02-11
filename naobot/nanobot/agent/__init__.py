# -*- coding: utf-8 -*-
"""
================================================================================
NanoBot Agent Core - Agent 核心模块
================================================================================

功能描述:
    这是 NanoBot Agent 的核心模块，聚合了所有 Agent 运行所需的组件。
    包含主循环、上下文构建、记忆管理、技能加载等核心功能。

主要组件:
    - AgentLoop: 核心处理引擎，负责消息处理流程
    - ContextBuilder: 上下文构建器，为 LLM 组装所需信息
    - MemoryStore: 记忆存储，管理长期和短期记忆
    - SkillsLoader: 技能加载器，管理 Agent 可用的技能

模块关系:
    AgentLoop 依赖:
        - ContextBuilder: 构建 LLM 上下文
        - MemoryStore: 管理对话历史和记忆
        - SkillsLoader: 加载技能说明
        - ToolRegistry: 管理可用工具
        - SessionManager: 管理会话状态

使用示例:
    from nanobot.agent import AgentLoop, ContextBuilder, MemoryStore, SkillsLoader
    
    # 创建各组件
    context_builder = ContextBuilder(workspace)
    memory_store = MemoryStore(workspace)
    skills_loader = SkillsLoader(workspace)
    
    # 创建 Agent 循环
    agent = AgentLoop(
        bus=message_bus,
        provider=llm_provider,
        workspace=workspace,
    )

================================================================================
"""

from nanobot.agent.loop import AgentLoop
from nanobot.agent.context import ContextBuilder
from nanobot.agent.memory import MemoryStore
from nanobot.agent.skills import SkillsLoader

__all__ = ["AgentLoop", "ContextBuilder", "MemoryStore", "SkillsLoader"]
