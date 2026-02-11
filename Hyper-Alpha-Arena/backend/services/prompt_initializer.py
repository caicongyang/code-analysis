"""
Prompt Template Initializer Service

Seeds default prompt templates into the database on system startup.
"""
"""
提示词模板初始化服务

在系统启动时将默认提示词模板写入数据库，确保AI交易系统
有可用的基础提示词配置。

核心功能：
1. 模板播种：创建默认、专业版和Hyperliquid专用提示词模板
2. 版本管理：自动检测并更新系统模板的变更
3. 清理遗留：删除旧版本的遗留数据表
4. 冲突处理：保护用户自定义修改，仅更新系统版本

提供的模板：
- default: 基础提示词模板，适用于一般AI交易决策
- pro: 专业版模板，包含更丰富的市场上下文信息
- hyperliquid: Hyperliquid专用模板，包含保证金和杠杆详情

更新策略：
- 仅更新system_template_text（系统版本）
- 保留用户在template_text中的自定义修改
- 更新模板名称和描述以反映最新功能

应用时机：
- 系统首次启动时创建默认模板
- 版本升级时更新系统模板内容
- 确保新功能的提示词支持
"""

from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy import text

from config.prompt_templates import DEFAULT_PROMPT_TEMPLATE, PRO_PROMPT_TEMPLATE, HYPERLIQUID_PROMPT_TEMPLATE
from repositories import prompt_repo

SYSTEM_USER = "system"
# 系统用户标识，用于标记由系统自动更新的模板


def seed_prompt_templates(db: Session) -> None:
    """Ensure default prompt templates exist in the database."""
    """
    确保默认提示词模板存在于数据库中

    系统启动时调用，检查并创建/更新默认提示词模板。
    保护用户的自定义修改，仅更新系统维护的模板版本。

    Args:
        db: 数据库会话对象

    执行步骤：
    1. 清理旧版本遗留表（model_prompt_overrides）
    2. 遍历预定义的模板列表
    3. 检查每个模板是否存在
    4. 不存在则创建，存在则检查系统版本是否需要更新
    5. 提交所有变更到数据库
    """
    # Clean up legacy table if it still exists
    try:
        db.execute(text("DROP TABLE IF EXISTS model_prompt_overrides"))
        db.commit()
    except Exception:
        db.rollback()

    templates_to_seed = [
        {
            "key": "default",
            "name": "Default Prompt",
            "description": "Baseline prompt used for AI trading decisions.",
            "template_text": DEFAULT_PROMPT_TEMPLATE,
        },
        {
            "key": "pro",
            "name": "Pro Prompt",
            "description": "Structured prompt inspired by Alpha Arena with richer context.",
            "template_text": PRO_PROMPT_TEMPLATE,
        },
        {
            "key": "hyperliquid",
            "name": "Hyperliquid Prompt",
            "description": "Specialized prompt for Hyperliquid perpetual contract trading with detailed margin and leverage information.",
            "template_text": HYPERLIQUID_PROMPT_TEMPLATE,
        },
    ]

    updated = False

    for item in templates_to_seed:
        existing = prompt_repo.get_template_by_key(db, item["key"])
        if not existing:
            prompt_repo.create_template(
                db,
                key=item["key"],
                name=item["name"],
                description=item["description"],
                template_text=item["template_text"],
                system_template_text=item["template_text"],
                updated_by=SYSTEM_USER,
            )
            updated = True
        else:
            has_changes = False
            if existing.name != item["name"]:
                existing.name = item["name"]
                has_changes = True
            if existing.description != item["description"]:
                existing.description = item["description"]
                has_changes = True
            if existing.system_template_text != item["template_text"]:
                existing.system_template_text = item["template_text"]
                has_changes = True

            if has_changes:
                existing.updated_by = SYSTEM_USER
                db.add(existing)
                updated = True

    if updated:
        db.commit()
