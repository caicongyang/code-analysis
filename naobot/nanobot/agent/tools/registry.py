"""Tool registry for dynamic tool management."""
# 工具注册表模块
# 提供动态工具管理功能，支持工具的注册、注销和执行

from typing import Any

from nanobot.agent.tools.base import Tool


class ToolRegistry:
    """
    Registry for agent tools.
    # 代理工具注册表
    
    Allows dynamic registration and execution of tools.
    # 支持工具的动态注册和执行
    """
    
    def __init__(self):
        self._tools: dict[str, Tool] = {}
        # 内部字典，存储工具名称到工具实例的映射
    
    def register(self, tool: Tool) -> None:
        """Register a tool."""
        # 注册工具
        self._tools[tool.name] = tool
    
    def unregister(self, name: str) -> None:
        """Unregister a tool by name."""
        # 根据名称注销工具
        self._tools.pop(name, None)
    
    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        # 根据名称获取工具
        return self._tools.get(name)
    
    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        # 检查工具是否已注册
        return name in self._tools
    
    def get_definitions(self) -> list[dict[str, Any]]:
        """Get all tool definitions in OpenAI format."""
        # 获取所有工具的OpenAI格式定义
        return [tool.to_schema() for tool in self._tools.values()]
    
    async def execute(self, name: str, params: dict[str, Any]) -> str:
        """
        Execute a tool by name with given parameters.
        # 使用给定参数按名称执行工具
        
        Args:
            name: Tool name.
            # 工具名称
            params: Tool parameters.
            # 工具参数
        
        Returns:
            Tool execution result as string.
            # 工具执行的字符串结果
        
        Raises:
            KeyError: If tool not found.
            # 如果工具未找到会引发异常
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
        """Get list of registered tool names."""
        # 获取所有已注册工具名称的列表
        return list(self._tools.keys())
    
    def __len__(self) -> int:
        return len(self._tools)
        # 返回已注册工具的数量
    
    def __contains__(self, name: str) -> bool:
        return name in self._tools
        # 支持 'name in registry' 语法
