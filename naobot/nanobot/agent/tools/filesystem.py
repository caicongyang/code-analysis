# -*- coding: utf-8 -*-
"""
================================================================================
文件系统工具模块（File System Tools Module）
================================================================================

模块功能描述：
本模块提供了 nanobot 代理系统的基础文件系统操作工具集。包括文件的读取、
写入、编辑以及目录内容的列出等核心功能。这些工具使代理能够与本地文件
系统进行交互，实现数据持久化、代码读写、日志查看等常见操作。

核心设计理念：
1. 安全性优先：所有文件操作都经过路径解析和安全检查
2. 沙箱支持：通过 allowed_dir 参数限制可访问的目录范围
3. 统一接口：遵循 Tool 基类的标准接口规范
4. 错误处理：所有操作都包含完善的异常处理和错误信息返回

主要组件：
1. 路径解析工具函数
   - _resolve_path()：路径解析和安全检查

2. 文件工具类
   - ReadFileTool：文件读取工具
   - WriteFileTool：文件写入工具
   - EditFileTool：文件编辑工具
   - ListDirTool：目录列表工具

安全特性：
- 路径遍历防护：防止 "../" 等路径遍历攻击
- 目录限制：可选的 allowed_dir 参数限制可访问范围
- 用户扩展：支持 "~" 等用户目录扩展
- 权限检查：验证路径是否为文件或目录

使用示例：
```python
from agent.tools.filesystem import (
    ReadFileTool,
    WriteFileTool,
    EditFileTool,
    ListDirTool
)
from pathlib import Path

# 创建允许访问的目录（可选，用于沙箱限制）
allowed_dir = Path("/workspace")

# 创建工具实例
read_tool = ReadFileTool(allowed_dir=allowed_dir)
write_tool = WriteFileTool(allowed_dir=allowed_dir)
edit_tool = EditFileTool(allowed_dir=allowed_dir)
list_tool = ListDirTool(allowed_dir=allowed_dir)

# 注册到工具注册表
registry = ToolRegistry()
registry.register(read_tool)
registry.register(write_tool)
registry.register(edit_tool)
registry.register(list_tool)

# 执行文件读取
result = await registry.execute("read_file", {"path": "/workspace/test.txt"})
print(result)
```

依赖关系：
- 依赖于 agent.tools.base.Tool 基类
- 使用 pathlib.Path 进行跨平台路径处理
- 使用 typing.Any 进行类型注解
- 无外部硬依赖

版本信息：1.0.0
创建日期：2024年
最后修改：2024年
================================================================================
"""

from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool


def _resolve_path(path: str, allowed_dir: Path | None = None) -> Path:
    """
    路径解析与安全检查函数（Resolve Path with Security Check）
    
    功能描述：
    将用户提供的路径字符串解析为绝对路径，并进行安全检查。该函数是
    文件系统工具的核心安全组件，负责防止路径遍历攻击和越权访问。

    参数说明：
    - path：str，用户提供的文件或目录路径
      - 可以是相对路径或绝对路径
      - 支持 "~" 用户目录扩展
      - 示例："./data/file.txt", "/absolute/path.txt", "~/documents"
    - allowed_dir：Path | None，可选的允许访问目录
      - 如果提供，路径必须在该目录范围内
      - 用于实现沙箱限制
      - 默认为 None（不限制访问范围）

    返回值：
    - Path：解析后的绝对路径对象
      - 已展开用户目录（~）
      - 已转换为绝对路径
      - 已规范化路径分隔符

    处理流程：
    1. 使用 Path() 创建 Path 对象
    2. 调用 expanduser() 展开 "~" 用户目录
    3. 调用 resolve() 转换为绝对路径并规范化
    4. 如果设置了 allowed_dir，检查路径是否在允许范围内
    5. 如果越权，抛出 PermissionError
    6. 返回解析后的路径

    异常处理：
    - PermissionError：路径超出允许目录范围时抛出
    - OSError：路径包含无效字符或无法访问时抛出

    安全特性：
    - 防止路径遍历：解析后 "../etc/passwd" 等攻击无效
    - 目录限制：设置 allowed_dir 后无法访问外部文件
    - 符号链接：resolve() 会解析符号链接指向的实际位置

    使用示例：
    ```python
    # 基础用法
    resolved = _resolve_path("./data/file.txt")
    print(f"绝对路径: {resolved}")
    
    # 用户目录扩展
    resolved = _resolve_path("~/documents/file.txt")
    print(f"用户目录: {resolved}")
    
    # 带目录限制的用法
    allowed = Path("/workspace")
    resolved = _resolve_path("/workspace/data/file.txt", allowed_dir=allowed)
    # 正常工作
    
    # 尝试越权访问
    try:
        resolved = _resolve_path("/etc/passwd", allowed_dir=allowed)
    except PermissionError as e:
        print(f"越权访问被阻止: {e}")
    ```

    与其他组件的交互：
    - 被所有文件系统工具（ReadFileTool、WriteFileTool 等）调用
    - 是文件系统工具安全机制的核心
    """
    resolved = Path(path).expanduser().resolve()
    if allowed_dir and not str(resolved).startswith(str(allowed_dir.resolve())):
        raise PermissionError(f"Path {path} is outside allowed directory {allowed_dir}")
    return resolved


class ReadFileTool(Tool):
    """
    文件读取工具（Read File Tool）
    
    功能描述：
    ReadFileTool 提供了从文件系统中读取文件内容的能力。代理可以通过
    此工具读取配置文件、源代码、日志文件等各种文本内容。该工具支持
    可选的目录限制，确保文件访问在安全范围内。

    主要特性：
    1. 文本文件读取：专门用于读取 UTF-8 编码的文本文件
    2. 安全路径检查：防止路径遍历和越权访问
    3. 错误信息友好：返回清晰易懂的错误描述
    4. 沙箱兼容：支持通过 allowed_dir 限制访问范围

    参数说明：
    - allowed_dir：Path | None，可选，限制可访问的根目录
      - 设置后只能读取该目录下的文件
      - 有助于防止代理意外读取敏感文件
      - 默认为 None（无限制）

    使用场景：
    - 读取配置文件获取系统设置
    - 读取源代码进行分析
    - 查看日志文件排查问题
    - 读取数据文件进行处理

    工具名称：read_file

    依赖关系：
    - 继承自 Tool 基类
    - 内部使用 _resolve_path() 进行路径解析
    """

    def __init__(self, allowed_dir: Path | None = None):
        """
        初始化读取工具（Initialize Read File Tool）
        
        功能描述：
        创建 ReadFileTool 实例，可选设置允许访问的目录范围。

        参数说明：
        - allowed_dir：Path | None，可选的目录限制
          - 如果设置，只能访问该目录下的文件
          - 用于实现文件访问沙箱
          - 默认为 None（允许访问任何文件）

        使用示例：
        ```python
        # 无目录限制
        tool = ReadFileTool()
        
        # 限制访问范围
        allowed_dir = Path("/workspace")
        tool = ReadFileTool(allowed_dir=allowed_dir)
        ```
        """
        self._allowed_dir = allowed_dir

    @property
    def name(self) -> str:
        """
        获取工具名称（Get Tool Name）
        
        返回值：
        - str：工具名称 "read_file"
        """
        return "read_file"

    @property
    def description(self) -> str:
        """
        获取工具描述（Get Tool Description）
        
        返回值：
        - str：描述信息 "Read the contents of a file at the given path."
        """
        return "Read the contents of a file at the given path."

    @property
    def parameters(self) -> dict[str, Any]:
        """
        获取参数模式定义（Get Parameters JSON Schema）
        
        返回值：
        - dict：参数模式定义
          - path（必需）：要读取的文件路径
        """
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to read"
                }
            },
            "required": ["path"]
        }

    async def execute(self, path: str, **kwargs: Any) -> str:
        """
        执行文件读取（Execute File Read）
        
        功能描述：
        读取指定路径的文件内容并返回。如果发生错误，返回错误信息描述。

        参数说明：
        - path：str，要读取的文件路径
          - 支持相对路径和绝对路径
          - 支持 "~" 用户目录扩展
        - **kwargs： Additional keyword arguments（忽略）

        返回值：
        - str：文件内容或错误信息
          - 成功：返回文件的全部文本内容
          - 文件不存在：返回 "Error: File not found: {path}"
          - 路径不是文件：返回 "Error: Not a file: {path}"
          - 权限错误：返回 "Error: {permission_error}"
          - 其他错误：返回 "Error reading file: {error_message}"

        处理流程：
        1. 调用 _resolve_path() 解析并验证路径
        2. 检查路径是否存在
        3. 验证路径是否为文件
        4. 读取文件内容（UTF-8 编码）
        5. 返回内容或错误信息

        使用示例：
        ```python
        # 直接使用工具
        tool = ReadFileTool()
        result = await tool.execute("/workspace/config.yaml")
        print(result)
        
        # 通过注册表使用
        result = await registry.execute("read_file", {"path": "/workspace/data.txt"})
        ```

        注意事项：
        - 读取大型文件可能占用大量内存
        - 只支持 UTF-8 编码的文本文件
        - 二进制文件可能产生乱码
        """
        try:
            file_path = _resolve_path(path, self._allowed_dir)
            if not file_path.exists():
                return f"Error: File not found: {path}"
            if not file_path.is_file():
                return f"Error: Not a file: {path}"

            content = file_path.read_text(encoding="utf-8")
            return content
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error reading file: {str(e)}"


class WriteFileTool(Tool):
    """
    文件写入工具（Write File Tool）
    
    功能描述：
    WriteFileTool 提供了将内容写入文件系统的能力。代理可以通过此工具
    创建新文件、覆盖现有文件或追加内容。该工具会自动创建必要的父目录，
    确保写入操作的顺利进行。

    主要特性：
    1. 自动创建目录：自动创建父目录（如果不存在）
    2. 完整文件覆盖：写入时会覆盖整个文件内容
    3. UTF-8 编码：统一使用 UTF-8 编码
    4. 安全路径检查：防止路径遍历攻击

    参数说明：
    - allowed_dir：Path | None，可选，限制可访问的根目录

    使用场景：
    - 创建新的代码文件
    - 保存处理结果
    - 写入配置文件
    - 生成日志文件

    工具名称：write_file

    依赖关系：
    - 继承自 Tool 基类
    - 内部使用 _resolve_path() 进行路径解析
    """

    def __init__(self, allowed_dir: Path | None = None):
        """
        初始化写入工具（Initialize Write File Tool）
        
        参数说明：
        - allowed_dir：Path | None，可选的目录限制
        """
        self._allowed_dir = allowed_dir

    @property
    def name(self) -> str:
        """
        获取工具名称（Get Tool Name）
        
        返回值：
        - str：工具名称 "write_file"
        """
        return "write_file"

    @property
    def description(self) -> str:
        """
        获取工具描述（Get Tool Description）
        
        返回值：
        - str：描述信息 "Write content to a file at the given path. Creates parent directories if needed."
        """
        return "Write content to a file at the given path. Creates parent directories if needed."

    @property
    def parameters(self) -> dict[str, Any]:
        """
        获取参数模式定义（Get Parameters JSON Schema）
        
        返回值：
        - dict：参数模式定义
          - path（必需）：要写入的文件路径
          - content（必需）：要写入的内容
        """
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to write to"
                },
                "content": {
                    "type": "string",
                    "description": "The content to write"
                }
            },
            "required": ["path", "content"]
        }

    async def execute(self, path: str, content: str, **kwargs: Any) -> str:
        """
        执行文件写入（Execute File Write）
        
        功能描述：
        将指定内容写入到文件路径中。如果父目录不存在，会自动创建。

        参数说明：
        - path：str，要写入的文件路径
          - 支持相对路径和绝对路径
          - 目录会自动创建
        - content：str，要写入的内容
          - 任何字符串内容
          - 写入前不会添加额外换行

        返回值：
        - str：操作结果描述
          - 成功：返回 "Successfully wrote {bytes} bytes to {path}"
          - 权限错误：返回 "Error: {permission_error}"
          - 其他错误：返回 "Error writing file: {error_message}"

        处理流程：
        1. 调用 _resolve_path() 解析并验证路径
        2. 创建父目录（如果不存在）
        3. 将内容写入文件（UTF-8 编码）
        4. 返回成功信息和写入字节数

        使用示例：
        ```python
        # 直接使用工具
        tool = WriteFileTool()
        result = await tool.execute(
            "/workspace/output.txt",
            "Hello, World!"
        )
        print(result)
        
        # 自动创建目录
        await tool.execute(
            "/workspace/nested/dir/file.txt",
            "Nested content"
        )
        ```

        注意事项：
        - 写入操作会覆盖整个文件（不是追加）
        - 如果文件已存在，会被静默覆盖
        - 不支持二进制写入（如需二进制，请扩展此工具）
        """
        try:
            file_path = _resolve_path(path, self._allowed_dir)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            return f"Successfully wrote {len(content)} bytes to {path}"
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error writing file: {str(e)}"


class EditFileTool(Tool):
    """
    文件编辑工具（Edit File Tool）
    
    功能描述：
    EditFileTool 提供了精确替换文件内容的能力。它通过查找并替换
    指定文本来实现文件编辑，支持单次替换和精确匹配。该工具适合用于
    小范围的文本修改，如修复拼写错误、调整配置项等。

    主要特性：
    1. 精确文本匹配：old_text 必须完全匹配
    2. 单次替换：默认只替换第一个匹配项
    3. 多重匹配警告：如果出现多次匹配会提示用户
    4. 安全路径检查：防止路径遍历攻击

    参数说明：
    - allowed_dir：Path | None，可选，限制可访问的根目录

    使用场景：
    - 修改配置文件中的特定值
    - 修复代码中的拼写错误
    - 调整文本格式
    - 替换特定的代码片段

    工具名称：edit_file

    依赖关系：
    - 继承自 Tool 基类
    - 内部使用 _resolve_path() 进行路径解析
    """

    def __init__(self, allowed_dir: Path | None = None):
        """
        初始化编辑工具（Initialize Edit File Tool）
        
        参数说明：
        - allowed_dir：Path | None，可选的目录限制
        """
        self._allowed_dir = allowed_dir

    @property
    def name(self) -> str:
        """
        获取工具名称（Get Tool Name）
        
        返回值：
        - str：工具名称 "edit_file"
        """
        return "edit_file"

    @property
    def description(self) -> str:
        """
        获取工具描述（Get Tool Description）
        
        返回值：
        - str：描述信息 "Edit a file by replacing old_text with new_text. The old_text must exist exactly in the file."
        """
        return "Edit a file by replacing old_text with new_text. The old_text must exist exactly in the file."

    @property
    def parameters(self) -> dict[str, Any]:
        """
        获取参数模式定义（Get Parameters JSON Schema）
        
        返回值：
        - dict：参数模式定义
          - path（必需）：要编辑的文件路径
          - old_text（必需）：要查找的原文
          - new_text（必需）：要替换成的新内容
        """
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to edit"
                },
                "old_text": {
                    "type": "string",
                    "description": "The exact text to find and replace"
                },
                "new_text": {
                    "type": "string",
                    "description": "The text to replace with"
                }
            },
            "required": ["path", "old_text", "new_text"]
        }

    async def execute(self, path: str, old_text: str, new_text: str, **kwargs: Any) -> str:
        """
        执行文件编辑（Execute File Edit）
        
        功能描述：
        在指定文件中查找 old_text 并替换为 new_text。采用精确匹配，
        确保编辑的准确性。

        参数说明：
        - path：str，要编辑的文件路径
        - old_text：str，要查找的原文内容
          - 必须与文件中的内容完全匹配（包括空白字符）
          - 如果匹配多次会返回警告
        - new_text：str，替换后的新内容
          - 任意字符串内容

        返回值：
        - str：操作结果描述
          - 成功：返回 "Successfully edited {path}"
          - 文件不存在：返回 "Error: File not found: {path}"
          - 匹配失败：返回 "Error: old_text not found in file..."
          - 多次匹配：返回 "Warning: old_text appears {count} times..."
          - 权限错误：返回 "Error: {permission_error}"
          - 其他错误：返回 "Error editing file: {error_message}"

        处理流程：
        1. 调用 _resolve_path() 解析并验证路径
        2. 检查文件是否存在
        3. 读取文件内容
        4. 检查 old_text 是否存在
        5. 如果存在多次匹配，返回警告
        6. 执行单次替换
        7. 写入新内容
        8. 返回成功信息

        使用示例：
        ```python
        # 直接使用工具
        tool = EditFileTool()
        result = await tool.execute(
            "/workspace/config.yaml",
            "old_value",
            "new_value"
        )
        print(result)
        
        # 处理多次匹配（提供更长的上下文）
        await tool.execute(
            "/workspace/large_file.txt",
            "specific line content to replace",
            "new line content"
        )
        ```

        注意事项：
        - old_text 必须完全匹配（包括空格和换行）
        - 只替换第一个匹配项
        - 如果匹配多次需要用户提供更具体的 old_text
        - 建议在编辑前先读取文件内容确认
        """
        try:
            file_path = _resolve_path(path, self._allowed_dir)
            if not file_path.exists():
                return f"Error: File not found: {path}"

            content = file_path.read_text(encoding="utf-8")

            if old_text not in content:
                return f"Error: old_text not found in file. Make sure it matches exactly."

            # Count occurrences - 统计出现次数
            count = content.count(old_text)
            if count > 1:
                return f"Warning: old_text appears {count} times. Please provide more context to make it unique."

            new_content = content.replace(old_text, new_text, 1)
            file_path.write_text(new_content, encoding="utf-8")

            return f"Successfully edited {path}"
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error editing file: {str(e)}"


class ListDirTool(Tool):
    """
    目录列表工具（List Directory Tool）
    
    功能描述：
    ListDirTool 提供了列出目录内容的能力。代理可以通过此工具查看
    指定目录下有哪些文件和子目录，便于了解文件结构和进行后续操作。

    主要特性：
    1. 目录内容枚举：列出所有文件和子目录
    2. 类型标识：使用图标区分文件和目录
    3. 排序输出：按名称排序便于查找
    4. 安全路径检查：防止路径遍历攻击

    参数说明：
    - allowed_dir：Path | None，可选，限制可访问的根目录

    使用场景：
    - 浏览项目结构
    - 查找特定文件
    - 确认目录是否存在
    - 了解文件组织方式

    工具名称：list_dir

    依赖关系：
    - 继承自 Tool 基类
    - 内部使用 _resolve_path() 进行路径解析
    """

    def __init__(self, allowed_dir: Path | None = None):
        """
        初始化列表工具（Initialize List Directory Tool）
        
        参数说明：
        - allowed_dir：Path | None，可选的目录限制
        """
        self._allowed_dir = allowed_dir

    @property
    def name(self) -> str:
        """
        获取工具名称（Get Tool Name）
        
        返回值：
        - str：工具名称 "list_dir"
        """
        return "list_dir"

    @property
    def description(self) -> str:
        """
        获取工具描述（Get Tool Description）
        
        返回值：
        - str：描述信息 "List the contents of a directory."
        """
        return "List the contents of a directory."

    @property
    def parameters(self) -> dict[str, Any]:
        """
        获取参数模式定义（Get Parameters JSON Schema）
        
        返回值：
        - dict：参数模式定义
          - path（必需）：要列出的目录路径
        """
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The directory path to list"
                }
            },
            "required": ["path"]
        }

    async def execute(self, path: str, **kwargs: Any) -> str:
        """
        执行目录列表（Execute Directory Listing）
        
        功能描述：
        列出指定目录下的所有文件和子目录，使用图标进行类型区分。

        参数说明：
        - path：str，要列出的目录路径
          - 支持相对路径和绝对路径
          - 支持 "~" 用户目录扩展

        返回值：
        - str：目录内容列表或错误信息
          - 成功：返回格式化的内容列表，每项一行
            - 📁 前缀表示目录
            - 📄 前缀表示文件
          - 目录不存在：返回 "Error: Directory not found: {path}"
          - 路径不是目录：返回 "Error: Not a directory: {path}"
          - 空目录：返回 "Directory {path} is empty"
          - 权限错误：返回 "Error: {permission_error}"
          - 其他错误：返回 "Error listing directory: {error_message}"

        处理流程：
        1. 调用 _resolve_path() 解析并验证路径
        2. 检查路径是否存在
        3. 验证路径是否为目录
        4. 遍历目录内容
        5. 按名称排序
        6. 添加类型前缀图标
        7. 返回格式化列表

        使用示例：
        ```python
        # 直接使用工具
        tool = ListDirTool()
        result = await tool.execute("/workspace")
        print(result)
        
        # 示例输出：
        # 📁 src
        # 📄 README.md
        # 📄 main.py
        # 📄 config.yaml
        ```

        注意事项：
        - 不会递归列出子目录内容
        - 隐藏文件（以 . 开头）会被显示
        - 大目录可能产生大量输出
        """
        try:
            dir_path = _resolve_path(path, self._allowed_dir)
            if not dir_path.exists():
                return f"Error: Directory not found: {path}"
            if not dir_path.is_dir():
                return f"Error: Not a directory: {path}"

            items = []
            for item in sorted(dir_path.iterdir()):
                prefix = "📁 " if item.is_dir() else "📄 "
                items.append(f"{prefix}{item.name}")

            if not items:
                return f"Directory {path} is empty"

            return "\n".join(items)
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error listing directory: {str(e)}"
