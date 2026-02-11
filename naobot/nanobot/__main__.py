"""
NanoBot - 一个轻量级 AI Agent 框架

功能特性:
- 基于消息循环的 Agent 运行时
- 动态工具加载系统
- SubAgent 支持
- 内存管理
- Skills 系统
- Cron 定时任务

使用方法:
    python -m nanobot              # 启动 CLI 界面
    python -m nanobot --help        # 查看帮助信息

作者: Claude
版本: 0.1.0
"""

# 从 nanobot.cli.commands 模块导入 CLI 应用类
# 这个模块包含了所有命令行接口的命令定义，包括启动、配置、工具管理等
from nanobot.cli.commands import app

# __name__ 是 Python 的内置变量，当脚本被直接运行时
# 它的值是 "__main__"，而当脚本被作为模块导入时，它的值是模块名
if __name__ == "__main__":
    # 当用户通过 "python -m nanobot" 直接运行此脚本时
    # 执行 app() 函数启动 CLI 应用，进入交互式命令行界面
    app()
