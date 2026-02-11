"""
Entry point for running nanobot as a module: python -m nanobot
# 作为模块运行 nanobot 的入口点: python -m nanobot
"""

from nanobot.cli.commands import app  # 导入 CLI 命令应用

if __name__ == "__main__":
    # 当直接运行此脚本时，启动 CLI 应用
    app()
