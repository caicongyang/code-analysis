# -*- coding: utf-8 -*-
"""
================================================================================
代理工具基类模块（Agent Tools Base Module）
================================================================================

模块功能描述：
本模块定义了 nanobot 代理系统中所有工具（Tool）的抽象基类。作为工具体系的
基础设施，它提供了工具的基本接口规范、参数验证机制以及与 OpenAI 函数调用
格式的转换功能。所有具体的工具实现都必须继承自此类，并实现其抽象方法。

核心设计理念：
1. 抽象化设计：通过 ABC（抽象基类）定义工具的通用接口，确保所有工具实现
   的一致性和规范性。
2. 类型安全：内置参数验证机制，支持 JSON Schema 规范的参数检查，保证
   工具执行的正确性。
3. 标准化输出：提供 to_schema 方法将工具转换为 OpenAI 函数调用格式，
   便于与大语言模型集成。

主要组件：
- Tool：抽象基类，定义所有工具必须实现的核心接口
  - name：工具名称属性
  - description：工具描述属性
  - parameters：参数模式属性
  - execute：异步执行方法
  - validate_params：参数验证方法
  - to_schema：模式转换方法

类型映射系统：
- 支持 JSON Schema 类型到 Python 类型的映射转换
- 自动验证参数类型是否符合预期
- 支持复杂嵌套结构的递归验证

使用示例：
```python
from agent.tools.base import Tool

class CustomTool(Tool):
    @property
    def name(self) -> str:
        return "custom_tool"
    
    @property
    def description(self) -> str:
        return "自定义工具，用于执行特定任务"
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "input_text": {
                    "type": "string",
                    "description": "输入的文本内容"
                }
            },
            "required": ["input_text"]
        }
    
    async def execute(self, **kwargs) -> str:
        input_text = kwargs.get("input_text", "")
        return f"处理结果: {input_text}"
```

依赖关系：
- 继承自 abc.ABC，使用 abc.abstractmethod 标记抽象方法
- 使用 typing 模块进行类型注解
- 无外部硬依赖，可独立使用

版本信息：1.0.0
创建日期：2024年
最后修改：2024年
================================================================================
"""

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """
    代理工具的抽象基类（Abstract Base Class for Agent Tools）
    
    功能描述：
    Tool 类是所有代理工具的基类，定义了工具的基本接口和行为规范。它采用
    抽象基类的方式，确保所有具体工具实现都遵循统一的接口标准。该类是
    代理系统与外部环境交互的核心桥梁。

    设计特点：
    1. 抽象方法：强制子类实现必要的接口方法
    2. 参数验证：内置基于 JSON Schema 的参数验证机制
    3. 类型映射：自动转换 JSON Schema 类型为 Python 类型
    4. 模式转换：支持转换为 OpenAI 函数调用格式

    继承要求：
    子类必须实现以下抽象属性和方法：
    - name：返回工具的唯一标识名称
    - description：返回工具的功能描述
    - parameters：返回参数的 JSON Schema 定义
    - execute：实现工具的具体执行逻辑

    使用场景：
    - 文件操作工具（读取、写入、编辑、列表）
    - 系统命令执行工具
    - 网络搜索和数据获取工具
    - 消息发送和通信工具
    - 定时任务和调度工具
    - 子代理创建和管理工具

    与大语言模型的集成：
    该类的设计考虑了与 LLM 的无缝集成。通过 to_schema 方法，可以将工具
    定义转换为 OpenAI 函数调用格式，使 LLM 能够：
    1. 理解工具的功能和用途
    2. 根据用户请求智能选择合适的工具
    3. 生成符合参数规范的工具调用
    """

    # =====================================================================
    # 类型映射字典（Type Mapping Dictionary）
    # =====================================================================
    # 功能说明：将 JSON Schema 类型规范映射到对应的 Python 类型
    # 处理流程：在参数验证阶段使用，用于检查参数类型是否正确
    # 支持类型：string→str, integer→int, number→(int/float), boolean→bool,
    #          array→list, object→dict
    # =====================================================================
    _TYPE_MAP = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    @property
    @abstractmethod
    def name(self) -> str:
        """
        获取工具名称（Get Tool Name）
        
        功能描述：
        返回工具的唯一标识名称，该名称在代理系统中必须唯一。
        LLM 在生成函数调用时会使用此名称来指定要调用的工具。

        参数说明：
        - 无参数

        返回值：
        - 类型：str
        - 说明：工具的唯一名称字符串
        - 示例：return "read_file"

        使用示例：
        ```python
        @property
        def name(self) -> str:
            return "read_file"
        ```

        命名规范：
        - 使用小写字母和下划线
        - 保持简洁且具有描述性
        - 避免与系统内置函数重名
        """
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """
        获取工具描述（Get Tool Description）
        
        功能描述：
        返回工具的功能描述信息。该描述会被传递给 LLM，帮助其理解
        工具的用途、适用场景以及何时应该使用此工具。

        参数说明：
        - 无参数

        返回值：
        - 类型：str
        - 说明：工具的功能描述文本
        - 示例：return "读取文件内容，支持指定行范围"

        编写指南：
        1. 描述工具的主要功能
        2. 说明输入参数的类型和用途
        3. 描述返回值的格式和内容
        4. 提及使用时的注意事项
        5. 提供简单的使用示例

        使用示例：
        ```python
        @property
        def description(self) -> str:
            return "读取指定文件的全部内容或部分行范围。" \
                   "参数：file_path（必需）- 文件路径；" \
                   "limit（可选）- 最大行数；offset（可选）- 起始行号"
        ```

        最佳实践：
        - 描述应清晰简洁（50-100字）
        - 避免使用专业术语或提供必要的解释
        - 包含输入输出的关键信息
        """
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """
        获取参数模式定义（Get Parameters JSON Schema）
        
        功能描述：
        返回工具参数的 JSON Schema 定义。该定义用于：
        1. 参数验证：确保传入参数符合预期格式
        2. LLM 提示：帮助 LLM 生成正确的参数值
        3. API 文档：描述工具接受的输入参数

        参数说明：
        - 无参数

        返回值：
        - 类型：dict[str, Any]
        - 说明：符合 JSON Schema 规范的参数字典
        - 结构包含：type、properties、required 等标准字段

        JSON Schema 结构说明：
        ```python
        {
            "type": "object",                          # 顶级类型必须是对象
            "properties": {
                "param_name": {
                    "type": "string",                  # 参数类型
                    "description": "参数说明",          # 参数描述
                    "enum": ["a", "b"],               # 可选值列表
                    "default": "a",                    # 默认值
                    "minimum": 1,                      # 最小值（数值类型）
                    "maximum": 100,                    # 最大值（数值类型）
                    "minLength": 1,                     # 最小长度（字符串）
                    "maxLength": 255                   # 最大长度（字符串）
                }
            },
            "required": ["param_name"]                 # 必需参数列表
        }
        ```

        使用示例：
        ```python
        @property
        def parameters(self) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "要读取的文件路径"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最大返回行数",
                        "default": 100
                    }
                },
                "required": ["file_path"]
            }
        ```

        注意事项：
        - 顶级 type 必须为 "object"
        - 所有自定义参数必须在 properties 中定义
        - required 数组列出必需参数（可选）
        - 支持嵌套对象和数组结构
        """
        pass

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """
        执行工具功能（Execute Tool Functionality）
        
        功能描述：
        异步执行工具的核心功能。该方法是工具的入口点，接收经过
        验证的参数，执行相应的操作，并返回执行结果。

        参数说明：
        - **kwargs：工具特定的命名参数
          - 参数名和类型应与 parameters 属性中定义的一致
          - 参数已通过 validate_params 验证（如果调用了验证）
          - 必需参数必须提供，可选参数可省略

        返回值：
        - 类型：str
        - 说明：工具执行的字符串结果描述
        - 建议：返回格式化的、人类可读的结果信息
        - 示例："成功读取文件，内容共 150 行"

        处理流程：
        1. 从 kwargs 中提取所需参数
        2. 执行工具的核心逻辑
        3. 处理可能的异常情况
        4. 返回格式化的结果字符串

        使用示例：
        ```python
        async def execute(self, **kwargs: Any) -> str:
            file_path = kwargs.get("file_path")
            limit = kwargs.get("limit", 100)
            
            try:
                with open(file_path, 'r') as f:
                    lines = f.readlines()[:limit]
                return f"成功读取 {len(lines)} 行内容"
            except Exception as e:
                return f"读取失败: {str(e)}"
        ```

        异步说明：
        - 使用 async def 定义以支持异步执行
        - 调用者应使用 await 等待结果
        - 适用于 I/O 密集型操作（文件、网络等）

        错误处理：
        - 建议捕获可能发生的异常
        - 返回错误信息而非抛出异常
        - 保持错误信息的可读性
        """
        pass

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """
        验证工具参数（Validate Tool Parameters）
        
        功能描述：
        根据 JSON Schema 定义验证传入的参数是否合法。该方法提供
        了一层安全保障，确保只有符合规范的参数才会被执行。

        参数说明：
        - params：dict[str, Any]，待验证的参数字典
          - 键为参数名（应与 properties 中定义一致）
          - 值为参数的实际值

        返回值：
        - list[str]：验证错误列表
          - 空列表表示验证通过
          - 非空列表包含所有验证错误的描述信息
          - 每个错误信息描述一个具体的验证失败原因

        处理流程：
        1. 获取工具的 parameters 定义（JSON Schema）
        2. 检查顶级类型是否为 "object"
        3. 调用内部 _validate 方法进行递归验证
        4. 收集并返回所有验证错误

        错误类型检测：
        - 类型错误：参数类型与预期不符
        - 必需参数缺失：required 中定义的参数未提供
        - 枚举值错误：参数值不在允许的枚举列表中
        - 数值范围错误：超出 minimum/maximum 范围
        - 字符串长度错误：超出 minLength/maxLength 限制
        - 嵌套对象验证：递归验证子属性
        - 数组元素验证：递归验证每个数组元素

        使用示例：
        ```python
        tool = ReadFileTool()
        params = {"file_path": "/test.txt", "limit": 50}
        errors = tool.validate_params(params)
        if errors:
            print("参数验证失败:")
            for error in errors:
                print(f"  - {error}")
        else:
            print("参数验证通过")
        ```

        调用建议：
        - 在 execute 方法开始处调用
        - 或在工具调用前进行预验证
        - 验证失败时应返回友好的错误信息
        """
        schema = self.parameters or {}
        if schema.get("type", "object") != "object":
            raise ValueError(f"Schema must be object type, got {schema.get('type')!r}")
        return self._validate(params, {**schema, "type": "object"}, "")

    def _validate(self, val: Any, schema: dict[str, Any], path: str) -> list[str]:
        """
        内部递归验证方法（Internal Recursive Validation Method）
        
        功能描述：
        内部使用的递归验证方法，处理嵌套结构的参数验证。
        该方法直接操作底层数据结构，不对外暴露。

        参数说明：
        - val：Any，当前验证的值
        - schema：dict[str, Any]，当前值的 JSON Schema 定义
        - path：str，当前验证路径（用于错误信息定位）

        返回值：
        - list[str]：验证错误列表

        内部处理逻辑：
        1. 类型检查：验证值类型是否符合 schema 定义
        2. 枚举检查：验证值是否在允许的枚举列表中
        3. 数值范围：检查 minimum/maximum 约束
        4. 字符串长度：检查 minLength/maxLength 约束
        5. 对象属性：递归验证子属性
        6. 数组元素：递归验证每个数组元素

        路径构建：
        - 顶级参数：使用参数名作为 path
        - 嵌套对象：使用 "parent.child" 格式
        - 数组元素：使用 "array[index]" 格式
        - 目的：在错误信息中精确定位问题位置

        使用注意：
        - 此方法为内部方法，不建议外部直接调用
        - 由 validate_params 方法内部调用
        """
        t, label = schema.get("type"), path or "parameter"
        
        # 类型验证：检查值是否符合预期的 Python 类型
        if t in self._TYPE_MAP and not isinstance(val, self._TYPE_MAP[t]):
            return [f"{label} should be {t}"]

        errors = []

        # 枚举值验证：检查值是否在允许的枚举列表中
        if "enum" in schema and val not in schema["enum"]:
            errors.append(f"{label} must be one of {schema['enum']}")

        # 数值类型验证：检查数值是否在允许范围内
        if t in ("integer", "number"):
            if "minimum" in schema and val < schema["minimum"]:
                errors.append(f"{label} must be >= {schema['minimum']}")
            if "maximum" in schema and val > schema["maximum"]:
                errors.append(f"{label} must be <= {schema['maximum']}")

        # 字符串类型验证：检查字符串长度
        if t == "string":
            if "minLength" in schema and len(val) < schema["minLength"]:
                errors.append(f"{label} must be at least {schema['minLength']} chars")
            if "maxLength" in schema and len(val) > schema["maxLength"]:
                errors.append(f"{label} must be at most {schema['maxLength']} chars")

        # 对象类型验证：递归验证子属性
        if t == "object":
            props = schema.get("properties", {})
            # 检查必需参数是否存在
            for k in schema.get("required", []):
                if k not in val:
                    errors.append(f"missing required {path + '.' + k if path else k}")
            # 递归验证每个提供的属性
            for k, v in val.items():
                if k in props:
                    errors.extend(self._validate(v, props[k], path + '.' + k if path else k))

        # 数组类型验证：递归验证每个元素
        if t == "array" and "items" in schema:
            for i, item in enumerate(val):
                errors.extend(self._validate(item, schema["items"], f"{path}[{i}]" if path else f"[{i}]"))

        return errors

    def to_schema(self) -> dict[str, Any]:
        """
        转换为 OpenAI 函数模式（Convert to OpenAI Function Schema）
        
        功能描述：
        将工具定义转换为 OpenAI 函数调用格式的 schema。该方法使工具
        能够与大语言模型的函数调用功能无缝集成。

        参数说明：
        - 无参数

        返回值：
        - dict[str, Any]：OpenAI 格式的函数定义
          - 包含 type 和 function 两个顶层键
          - function 中包含 name、description、parameters

        返回结构说明：
        ```python
        {
            "type": "function",
            "function": {
                "name": "tool_name",
                "description": "工具功能描述",
                "parameters": {
                    # JSON Schema 定义
                }
            }
        }
        ```

        使用示例：
        ```python
        tool = ReadFileTool()
        schema = tool.to_schema()
        # 输出可用于 OpenAI API 的 function calling
        ```

        与 LLM 的集成：
        1. 将 schema 列表传递给 LLM 的 tools 参数
        2. LLM 会分析工具描述，理解何时应该调用
        3. 当需要调用时，LLM 生成符合参数规范的工具调用
        4. 系统接收调用请求，调用对应的 execute 方法
        5. 将执行结果返回给 LLM 进行后续处理

        版本兼容性：
        - 适配 OpenAI Chat Completions API 的 function calling
        - 兼容支持 OpenAI 工具调用格式的其他 LLM 服务

        最佳实践：
        - 在初始化代理时将所有工具的 schema 传递给 LLM
        - 保持工具描述的准确性和完整性
        - 定期审查工具定义与实际功能的匹配度
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }
