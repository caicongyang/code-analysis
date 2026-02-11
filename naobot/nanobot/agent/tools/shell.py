# -*- coding: utf-8 -*-
"""
================================================================================
Shell Execution Tool - Shell 执行工具模块
================================================================================

功能描述:
    提供安全的 Shell 命令执行功能，是 Agent 与操作系统交互的主要方式。
    包含多层次的安全防护机制，防止执行危险命令。

安全防护机制:
    1. 危险命令拦截:
       - rm -rf, del /f 等删除命令
       - dd 命令（磁盘操作）
       - mkfs, format 等格式化命令
       - fork bomb（递归定义的函数）
       - shutdown, reboot 等系统关机命令
    
    2. 工作目录限制:
       - restrict_to_workspace=True 时只能操作指定目录
       - 阻止路径遍历攻击（../）
       - 检查绝对路径是否在工作目录外
    
    3. 命令白名单（可选）:
       - allow_patterns 配置允许执行的命令模式
       - 未匹配白名单的命令将被阻止
    
    4. 超时控制:
       - 默认 60 秒超时
       - 超时后自动杀死进程

主要组件:
    - ExecTool: Shell 命令执行工具类

使用示例:
    # 基本使用
    exec_tool = ExecTool()
    result = await exec_tool.execute("ls -la")
    
    # 带工作目录
    result = await exec_tool.execute("python script.py", working_dir="/path/to/dir")
    
    # 安全模式（限制在 workspace）
    exec_tool = ExecTool(
        working_dir="/workspace",
        restrict_to_workspace=True,
        timeout=30
    )

================================================================================
"""

import asyncio
import os
import re
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool


class ExecTool(Tool):
    """
    ========================================================================
    ExecTool - Shell 命令执行工具类
    ========================================================================
    
    允许 Agent 执行 Shell 命令与操作系统交互。
    
    功能特点:
        1. 异步执行：不阻塞事件循环
        2. 超时控制：防止命令无限挂起
        3. 输出捕获：返回 stdout 和 stderr
        4. 安全防护：多层次命令检查
    
    危险命令拦截示例:
        - rm -rf /      → 拦截
        - rm -rf .*     → 拦截
        - :(){:|:&};:   → 拦截（fork bomb）
        - dd if=/dev/zero of=/dev/sda → 拦截
        - shutdown now  → 拦截
    
    ========================================================================
    """
    
    def __init__(
        self,
        timeout: int = 60,
        working_dir: str | None = None,
        deny_patterns: list[str] | None = None,
        allow_patterns: list[str] | None = None,
        restrict_to_workspace: bool = False,
    ):
        """
        初始化 Shell 执行工具
        
        参数说明:
            timeout: int，命令执行超时时间（秒），默认为 60
            working_dir: str | None，默认工作目录
            deny_patterns: list[str] | None，自定义的危险命令拦截模式
            allow_patterns: list[str] | None，命令白名单模式
            restrict_to_workspace: bool，是否限制在 workspace 内操作
        
        默认拦截的危险模式:
            - rm -rf, rm -r 等强制删除命令
            - del /f, del /q 等强制删除命令
            - format, mkfs, diskpart 等磁盘操作命令
            - dd 命令（数据复制）
            - 写入 /dev/sd* 设备文件
            - shutdown, reboot, poweroff 等关机命令
            - fork bomb（递归函数定义）
        """
        # 命令执行超时时间（秒）
        self.timeout = timeout
        
        # 默认工作目录
        self.working_dir = working_dir
        
        # 危险命令拦截模式列表
        # 如果未提供，使用默认的危险模式
        self.deny_patterns = deny_patterns or [
            # 匹配 rm -rf, rm -fr 等强制删除命令
            r"\brm\s+-[rf]{1,2}\b",
            # 匹配 Windows del /f, del /q 命令
            r"\bdel\s+/[fq]\b",
            # 匹配 rmdir /s 命令
            r"\brmdir\s+/s\b",
            # 匹配磁盘格式化操作
            r"\b(format|mkfs|diskpart)\b",
            # 匹配 dd 命令
            r"\bdd\s+if=",
            # 匹配写入磁盘设备
            r">\s*/dev/sd",
            # 匹配系统关机命令
            r"\b(shutdown|reboot|poweroff)\b",
            # 匹配 fork bomb
            r":\(\)\s*\{.*\};\s*:",
        ]
        
        # 命令白名单模式
        self.allow_patterns = allow_patterns or []
        
        # 是否限制在 workspace 内操作
        self.restrict_to_workspace = restrict_to_workspace
    
    @property
    def name(self) -> str:
        """
        获取工具名称
        
        返回值:
            str，工具名称为 "exec"
        """
        return "exec"
    
    @property
    def description(self) -> str:
        """
        获取工具描述
        
        返回值:
            str，描述信息
        """
        return "Execute a shell command and return its output. Use with caution."
    
    @property
    def parameters(self) -> dict[str, Any]:
        """
        获取工具参数定义
        
        返回值:
            dict，OpenAI 格式的工具参数定义
        
        参数说明:
            - command: 要执行的 Shell 命令（必填）
            - working_dir: 命令执行的工作目录（可选）
        """
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute"
                },
                "working_dir": {
                    "type": "string",
                    "description": "Optional working directory for the command"
                }
            },
            "required": ["command"]
        }
    
    async def execute(self, command: str, working_dir: str | None = None, **kwargs: Any) -> str:
        """
        执行 Shell 命令
        
        功能描述:
            异步执行给定的 Shell 命令，返回命令输出。
        
        参数说明:
            command: str，要执行的 Shell 命令
            working_dir: str | None，指定工作目录（覆盖默认值）
            **kwargs: 额外的关键字参数（忽略）
        
        返回值:
            str，命令的执行输出
                - stdout 内容
                - 如果有 stderr，附带 STDERR: 前缀
                - 如果命令失败，附带退出码
                - 超时返回超时错误信息
                - 安全拦截返回拦截原因
        
        处理流程:
            1. 确定工作目录
            2. 安全检查（_guard_command）
            3. 创建子进程执行命令
            4. 等待命令完成（或超时）
            5. 捕获并格式化输出
            6. 截断超长输出
        
        超长输出处理:
            - 最大返回 10000 字符
            - 超过部分截断并显示剩余字符数
        
        使用示例:
            # 执行简单命令
            result = await exec_tool.execute("ls -la")
            
            # 指定工作目录
            result = await exec_tool.execute(
                "python build.py",
                working_dir="/project"
            )
        """
        # 确定工作目录
        cwd = working_dir or self.working_dir or os.getcwd()
        
        # 安全检查
        guard_error = self._guard_command(command, cwd)
        if guard_error:
            return guard_error
        
        try:
            # 创建子进程
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            
            try:
                # 等待命令完成，设置超时
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout
                )
            except asyncio.TimeoutError:
                # 超时：杀死进程
                process.kill()
                return f"Error: Command timed out after {self.timeout} seconds"
            
            # 构建输出
            output_parts = []
            
            # 添加 stdout
            if stdout:
                output_parts.append(stdout.decode("utf-8", errors="replace"))
            
            # 添加 stderr（如果有内容）
            if stderr:
                stderr_text = stderr.decode("utf-8", errors="replace")
                if stderr_text.strip():
                    output_parts.append(f"STDERR:\n{stderr_text}")
            
            # 如果命令失败，添加退出码
            if process.returncode != 0:
                output_parts.append(f"\nExit code: {process.returncode}")
            
            # 组合输出
            result = "\n".join(output_parts) if output_parts else "(no output)"
            
            # 截断超长输出
            max_len = 10000
            if len(result) > max_len:
                result = result[:max_len] + f"\n... (truncated, {len(result) - max_len} more chars)"
            
            return result
            
        except Exception as e:
            return f"Error executing command: {str(e)}"

    def _guard_command(self, command: str, cwd: str) -> str | None:
        """
        安全检查：验证命令是否安全
        
        功能描述:
            对命令进行多层安全检查，包括：
            1. 危险模式匹配
            2. 白名单检查
            3. 工作目录限制
            4. 路径遍历检测
        
        参数说明:
            command: str，要检查的命令
            cwd: str，当前工作目录
        
        返回值:
            str | None，如果命令不安全返回错误信息，否则返回 None
        
        检查项目:
            1. deny_patterns: 匹配到危险模式
            2. allow_patterns: 未匹配任何白名单
            3. restrict_to_workspace:
               - 包含 ..\ 或 ../
               - 绝对路径在工作目录外
        """
        cmd = command.strip()
        lower = cmd.lower()

        # ====================================================================
        # 1. 检查危险模式
        # ====================================================================
        for pattern in self.deny_patterns:
            if re.search(pattern, lower):
                return "Error: Command blocked by safety guard (dangerous pattern detected)"

        # ====================================================================
        # 2. 检查白名单
        # ====================================================================
        if self.allow_patterns:
            if not any(re.search(p, lower) for p in self.allow_patterns):
                return "Error: Command blocked by safety guard (not in allowlist)"

        # ====================================================================
        # 3. 工作目录限制
        # ====================================================================
        if self.restrict_to_workspace:
            # 检查路径遍历
            if "../" in cmd or "..\\" in cmd:
                return "Error: Command blocked by safety guard (path traversal detected)"

            # 解析工作目录为绝对路径
            cwd_path = Path(cwd).resolve()

            # 提取 Windows 绝对路径
            win_paths = re.findall(r"[A-Za-z]:\\[^\\\"']+", cmd)
            
            # 提取 POSIX 绝对路径
            # 只匹配以 / 开头的绝对路径，避免误匹配相对路径
            posix_paths = re.findall(r"(?:^|[\s|>])(/[^\s\"'>]+)", cmd)

            # 检查每个绝对路径是否在工作目录内
            for raw in win_paths + posix_paths:
                try:
                    p = Path(raw.strip()).resolve()
                except Exception:
                    continue
                # 如果路径是绝对的且不在工作目录内
                if p.is_absolute() and cwd_path not in p.parents and p != cwd_path:
                    return "Error: Command blocked by safety guard (path outside working dir)"

        # 所有检查通过
        return None
