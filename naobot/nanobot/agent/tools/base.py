"""Base class for agent tools."""
# 代理工具基类模块
# 定义了所有代理工具的抽象基类，提供了工具的基本接口和参数验证功能

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """
    Abstract base class for agent tools.
    # 代理工具的抽象基类
    
    Tools are capabilities that the agent can use to interact with
    the environment, such as reading files, executing commands, etc.
    # 工具是代理与外部环境交互的能力，例如读取文件、执行命令等
    """
    
    # 类型映射表，将JSON Schema类型转换为Python类型
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
        """Tool name used in function calls."""
        # 工具名称，用于函数调用
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Description of what the tool does."""
        # 工具的功能描述
        pass
    
    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for tool parameters."""
        # 工具参数的JSON Schema定义
        pass
    
    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """
        Execute the tool with given parameters.
        # 使用给定参数执行工具
        
        Args:
            **kwargs: Tool-specific parameters.
            # 工具特定的参数
        
        Returns:
            String result of the tool execution.
            # 工具执行的字符串结果
        """
        pass

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """Validate tool parameters against JSON schema. Returns error list (empty if valid)."""
        # 根据JSON Schema验证工具参数，返回错误列表（空表示验证通过）
        schema = self.parameters or {}
        if schema.get("type", "object") != "object":
            raise ValueError(f"Schema must be object type, got {schema.get('type')!r}")
        return self._validate(params, {**schema, "type": "object"}, "")

    def _validate(self, val: Any, schema: dict[str, Any], path: str) -> list[str]:
        # 内部验证方法，递归验证嵌套结构
        t, label = schema.get("type"), path or "parameter"
        if t in self._TYPE_MAP and not isinstance(val, self._TYPE_MAP[t]):
            return [f"{label} should be {t}"]
        
        errors = []
        # 枚举值验证
        if "enum" in schema and val not in schema["enum"]:
            errors.append(f"{label} must be one of {schema['enum']}")
        # 数值类型验证
        if t in ("integer", "number"):
            if "minimum" in schema and val < schema["minimum"]:
                errors.append(f"{label} must be >= {schema['minimum']}")
            if "maximum" in schema and val > schema["maximum"]:
                errors.append(f"{label} must be <= {schema['maximum']}")
        # 字符串类型验证
        if t == "string":
            if "minLength" in schema and len(val) < schema["minLength"]:
                errors.append(f"{label} must be at least {schema['minLength']} chars")
            if "maxLength" in schema and len(val) > schema["maxLength"]:
                errors.append(f"{label} must be at most {schema['maxLength']} chars")
        # 对象类型验证
        if t == "object":
            props = schema.get("properties", {})
            for k in schema.get("required", []):
                if k not in val:
                    errors.append(f"missing required {path + '.' + k if path else k}")
            for k, v in val.items():
                if k in props:
                    errors.extend(self._validate(v, props[k], path + '.' + k if path else k))
        # 数组类型验证
        if t == "array" and "items" in schema:
            for i, item in enumerate(val):
                errors.extend(self._validate(item, schema["items"], f"{path}[{i}]" if path else f"[{i}]"))
        return errors
    
    def to_schema(self) -> dict[str, Any]:
        """Convert tool to OpenAI function schema format."""
        # 将工具转换为OpenAI函数模式格式
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }
