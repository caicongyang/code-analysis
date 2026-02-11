# -*- coding: utf-8 -*-
"""
================================================================================
工具注册表模块（Tool Registry Module）
================================================================================

模块功能描述：
本模块提供了 nanobot 代理系统的工具注册表（ToolRegistry）实现。注册表是
代理系统中管理工具的核心组件，负责工具的注册、注销、查询、执行等全生命周期
管理功能。通过注册表机制，系统支持动态地添加、移除工具，实现灵活的扩展能力。

核心设计理念：
1. 集中管理：所有工具实例通过注册表统一管理，避免全局变量污染
2. 动态注册：支持在运行时注册和注销工具，无需重启系统
3. 安全执行：内置参数验证和异常处理机制
4. 标准接口：提供统一的工具定义获取方式，支持与大语言模型集成

主要组件：
- ToolRegistry：工具注册表类
  - register()：注册工具实例
  - unregister()：注销工具实例
  - get()：获取工具实例
  - has()：检查工具是否存在
  - execute()：执行工具
  - get_definitions()：获取所有工具定义
  - tool_names：已注册工具名称列表

使用场景：
1. 代理初始化时注册核心工具集
2. 插件系统加载第三方工具
3. 动态启用/禁用特定功能
4. 获取工具列表用于 LLM 上下文

与 LLM 的集成：
注册表提供的 get_definitions() 方法返回 OpenAI 格式的工具定义列表，
可直接传递给 LLM 的 tools 参数，实现工具调用功能。

使用示例：
```python
from agent.tools.registry import ToolRegistry
from agent.tools.filesystem import ReadFileTool, WriteFileTool

# 创建注册表实例
registry = ToolRegistry()

# 注册工具
registry.register(ReadFileTool())
registry.register(WriteFileTool())

# 获取工具定义并传递给 LLM
tools = registry.get_definitions()

# 执行工具
result = await registry.execute("read_file", {"file_path": "/test.txt"})
```

依赖关系：
- 依赖于 agent.tools.base.Tool 基类
- 使用 typing 模块进行类型注解
- 无外部硬依赖

版本信息：1.0.0
创建日期：2024年
最后修改：2024年
================================================================================
"""

from typing import Any

from nanobot.agent.tools.base import Tool


class ToolRegistry:
    """
    代理工具注册表（Agent Tool Registry）
    
    功能描述：
    ToolRegistry 类是代理系统中工具管理的核心组件。它提供了一个集中式的
    工具注册和管理机制，支持工具的动态注册、注销、查询和执行。该类是
    代理系统与各类工具之间的桥梁，负责协调工具的加载和使用。

    设计特点：
    1. 单例模式：通常作为全局唯一的注册表实例使用
    2. 字典存储：使用内部字典存储工具实例，键为工具名称
    3. 异步执行：execute 方法支持异步调用
    4. 安全验证：执行前自动验证参数有效性

    主要职责：
    1. 工具注册：接收工具实例并添加到注册表
    2. 工具注销：从注册表中移除工具实例
    3. 工具查询：根据名称获取工具实例
    4. 工具执行：调用工具的 execute 方法
    5. 定义导出：生成工具定义供 LLM 使用

    使用场景：
    - 代理初始化时批量注册工具
    - 插件系统动态加载工具
    - 运行时启用/禁用特定功能
    - 获取工具列表用于文档生成

    与其他组件的交互：
    - 与 Tool 基类交互：管理和调用具体工具
    - 与 LLM 交互：提供工具定义，支持函数调用
    - 与代理主逻辑交互：执行工具并返回结果
    """

    def __init__(self):
        """
        初始化工具注册表（Initialize Tool Registry）
        
        功能描述：
        创建注册表实例，初始化内部工具存储字典。

        参数说明：
        - 无参数

        内部初始化：
        - self._tools：dict[str, Tool]
          - 键：工具的唯一名称（str）
          - 值：工具实例（Tool）
          - 用于存储所有已注册的工具实例

        使用示例：
        ```python
        registry = ToolRegistry()
        print(f"已注册工具数量: {len(registry)}")
        ```
        """
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """
        注册工具实例（Register a Tool Instance）
        
        功能描述：
        将工具实例添加到注册表中。如果已存在同名工具，新工具将替换旧工具。

        参数说明：
        - tool：Tool，待注册的工具实例
          - 必须继承自 Tool 基类
          - 必须具有有效的 name、description、parameters 属性
          - 必须实现 async execute 方法

        返回值：
        - 无返回值

        处理流程：
        1. 验证工具实例是否有效（非空）
        2. 获取工具的 name 属性作为注册键
        3. 将工具实例存入内部字典

        注意事项：
        - 如果已存在同名工具将被替换（静默覆盖）
        - 建议在注册前检查工具是否存在
        - 工具名称在注册表中应保持唯一

        使用示例：
        ```python
        from agent.tools.filesystem import ReadFileTool

        registry = ToolRegistry()
        registry.register(ReadFileTool())
        print(f"已注册: {tool.name}" for tool in registry._tools.values())
        ```

        异常情况：
        - 如果 tool 为 None 或不具有 name 属性，可能引发 AttributeError
        - 建议在注册前验证工具的有效性
        """
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """
        注销工具实例（Unregister a Tool by Name）
        
        功能描述：
        从注册表中移除指定名称的工具实例。如果工具不存在，静默返回而不报错。

        参数说明：
        - name：str，要注销的工具名称
          - 应与注册时使用的名称一致
          - 区分大小写

        返回值：
        - 无返回值

        处理流程：
        1. 使用工具名称作为键尝试从字典中移除
        2. 使用 pop(name, None) 避免 KeyError
        3. 如果工具不存在，方法静默返回

        使用示例：
        ```python
        registry = ToolRegistry()
        registry.unregister("read_file")
        print("read_file 已注销" if not registry.has("read_file") else "注销失败")
        ```

        注意事项：
        - 注销后尝试执行该工具将返回错误信息
        - 注销操作不可逆，需要重新注册才能使用
        - 注销不会自动清理相关资源（如文件句柄）
        """
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        """
        获取工具实例（Get Tool Instance by Name）
        
        功能描述：
        根据工具名称从注册表中获取对应的工具实例。

        参数说明：
        - name：str，要获取的工具名称
          - 区分大小写
          - 必须与注册时的名称完全一致

        返回值：
        - Tool | None：工具实例或 None
          - 如果工具存在，返回对应的 Tool 实例
          - 如果工具不存在，返回 None

        使用示例：
        ```python
        registry = ToolRegistry()
        registry.register(ReadFileTool())
        
        tool = registry.get("read_file")
        if tool:
            print(f"找到工具: {tool.name}")
            print(f"描述: {tool.description}")
        else:
            print("工具不存在")
        ```

        进阶用法：
        ```python
        # 链式调用示例
        if (tool := registry.get("read_file")) is not None:
            result = await tool.execute(file_path="/test.txt")
        ```
        """
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """
        检查工具是否已注册（Check if Tool is Registered）
        
        功能描述：
        判断指定名称的工具是否存在于注册表中。

        参数说明：
        - name：str，要检查的工具名称
          - 区分大小写

        返回值：
        - bool：工具是否存在
          - True：工具已注册
          - False：工具未注册

        使用示例：
        ```python
        registry = ToolRegistry()
        
        if registry.has("read_file"):
            print("read_file 工具已安装")
        else:
            print("read_file 工具未安装")
        
        # 条件注册
        if not registry.has("write_file"):
            registry.register(WriteFileTool())
        ```
        """
        return name in self._tools

    def get_definitions(self) -> list[dict[str, Any]]:
        """
        获取所有工具定义（Get All Tool Definitions）
        
        功能描述：
        将注册表中所有工具转换为 OpenAI 函数调用格式的定义列表。
        该列表可直接传递给大语言模型的 tools 参数。

        参数说明：
        - 无参数

        返回值：
        - list[dict[str, Any]]：工具定义列表
          - 每个元素是一个符合 OpenAI 函数调用格式的字典
          - 包含 type、function.name、function.description、function.parameters
          - 顺序与注册顺序一致（Python 3.7+ 字典顺序保证）

        处理流程：
        1. 遍历注册表中所有工具实例
        2. 调用每个工具的 to_schema() 方法
        3. 收集所有定义到列表中
        4. 返回完整列表

        与 LLM 的集成：
        ```python
        registry = ToolRegistry()
        registry.register(ReadFileTool())
        registry.register(WriteFileTool())

        # 获取工具定义
        tool_definitions = registry.get_definitions()

        # 传递给 LLM（示例）
        response = await openai_client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": "读取文件"}],
            tools=tool_definitions
        )
        ```

        注意事项：
        - 返回的列表可被 JSON 序列化
        - 工具定义是只读的，不应修改
        - 如果工具注册后定义发生变化，需要重新获取
        """
        return [tool.to_schema() for tool in self._tools.values()]

    async def execute(self, name: str, params: dict[str, Any]) -> str:
        """
        执行工具（Execute Tool by Name with Parameters）
        
        功能描述：
        根据工具名称和参数执行对应的工具功能。该方法是工具执行的主要入口，
        包含了工具查找、参数验证、异常处理等完整流程。

        参数说明：
        - name：str，要执行的工具名称
          - 必须与已注册工具的名称一致
          - 区分大小写
        - params：dict[str, Any]，执行工具所需的参数
          - 键为参数名，值为参数值
          - 应符合工具的 parameters 定义

        返回值：
        - str：工具执行的字符串结果
          - 成功时返回执行结果描述
          - 失败时返回错误信息描述
          - 格式统一，便于 LLM 理解和处理

        处理流程：
        1. 工具查找：在注册表中查找对应名称的工具
        2. 参数验证：调用工具的 validate_params 方法验证参数
        3. 错误收集：如果验证失败，收集并返回错误信息
        4. 执行调用：调用工具的 async execute 方法
        5. 异常处理：捕获执行过程中的异常并返回错误信息

        错误处理：
        - 工具不存在：返回 "Error: Tool '{name}' not found"
        - 参数验证失败：返回 "Error: Invalid parameters for tool '{name}': {errors}"
        - 执行异常：返回 "Error executing {name}: {exception_message}"

        使用示例：
        ```python
        # 基础用法
        result = await registry.execute(
            "read_file",
            {"file_path": "/test.txt", "limit": 100}
        )
        print(result)

        # 在代理循环中使用
        async def handle_request(registry, tool_name, arguments):
            result = await registry.execute(tool_name, arguments)
            return result
        ```

        最佳实践：
        1. 执行前确保工具已注册
        2. 参数应经过适当的类型转换
        3. 妥善处理返回的错误信息
        4. 考虑添加超时机制防止长时间阻塞

        性能考虑：
        - 使用异步方法，支持并发执行多个工具调用
        - 参数验证在执行前完成，避免无效执行
        - 内部异常处理减少外部错误处理负担
        """
        tool = self._tools.get(name)
        if not tool:
            return f"Error: Tool '{name}' not found"

        try:
            errors = tool.validate_params(params)
            if errors:
                return f"Error: Invalid parameters for tool '{name}': " + "; ".join(errors)
            return await tool.execute(**params)
        except Exception as e:
            return f"Error executing {name}: {str(e)}"

    @property
    def tool_names(self) -> list[str]:
        """
        获取所有已注册工具名称列表（Get All Registered Tool Names）
        
        功能描述：
        返回注册表中所有已注册工具的名称列表。该属性提供了快速获取
        工具列表的方式，便于展示、调试和管理。

        参数说明：
        - 无参数（属性访问）

        返回值：
        - list[str]：工具名称列表
          - 包含所有已注册工具的唯一名称
          - 顺序与注册顺序一致
          - 如果无工具，返回空列表

        使用示例：
        ```python
        registry = ToolRegistry()
        registry.register(ReadFileTool())
        registry.register(WriteFileTool())

        print("已注册工具:", registry.tool_names)
        # 输出: ['read_file', 'write_file']

        # 遍历工具名称
        for name in registry.tool_names:
            tool = registry.get(name)
            print(f"{name}: {tool.description}")
        ```

        注意事项：
        - 返回的是名称列表，而非工具实例
        - 返回的是副本，修改不会影响注册表
        - 如果需要工具实例，使用 list(registry._tools.values())
        """
        return list(self._tools.keys())

    def __len__(self) -> int:
        """
        获取已注册工具数量（Get Number of Registered Tools）
        
        功能描述：
        实现 len(registry) 语法支持，返回注册表中的工具数量。

        参数说明：
        - 无参数

        返回值：
        - int：已注册工具的数量
          - 整数类型
          - 最小值为 0

        使用示例：
        ```python
        registry = ToolRegistry()
        print(f"工具数量: {len(registry)}")
        
        if len(registry) > 0:
            print("已安装工具")
        else:
            print("未安装任何工具")
        ```

        与其他方法的配合：
        ```python
        # 结合 tool_names 使用
        for i, name in enumerate(registry.tool_names):
            print(f"{i + 1}. {name}")
        print(f"共计 {len(registry)} 个工具")
        ```
        """
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        """
        实现 'name in registry' 语法（Support 'name in registry' Syntax）
        
        功能描述：
        实现 Python 的 in 运算符支持，允许使用更直观的语法检查工具是否存在。

        参数说明：
        - name：str，要检查的工具名称

        返回值：
        - bool：工具是否存在
          - True：工具已注册
          - False：工具未注册

        使用示例：
        ```python
        registry = ToolRegistry()
        registry.register(ReadFileTool())

        # 使用 in 运算符检查
        if "read_file" in registry:
            print("read_file 已注册")
        
        if "write_file" not in registry:
            print("write_file 未注册")
        ```

        与 has() 方法的关系：
        - __contains__ 提供运算符语法糖
        - has() 提供显式方法调用
        - 两者功能等效，可互换使用
        """
        return name in self._tools
