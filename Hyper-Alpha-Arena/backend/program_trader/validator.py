"""
Code validator for Program Trader.
Validates strategy code for syntax, security, and template compliance.
"""
"""
程序交易者代码验证器

在执行策略代码前进行安全性检查，防止恶意代码的执行。
验证内容包括：语法正确性、安全性检查、模板规范检查。

验证流程：
1. 语法检查 - 确保代码是有效的Python代码
2. 安全检查 - 禁止危险的导入和函数调用
3. 模板检查 - 确保代码符合策略模板规范

安全原则：
- 白名单机制：只允许预定义的安全函数
- 黑名单过滤：明确禁止危险操作
- 代码静态分析：不执行代码，只分析语法树
"""

import ast  # 抽象语法树(Abstract Syntax Tree)模块，用于解析和分析Python代码结构
from typing import List, Tuple, Optional  # 类型提示：List=列表, Tuple=元组, Optional=可选
from dataclasses import dataclass  # 数据类装饰器，简化类定义


@dataclass
class ValidationResult:
    """Result of code validation."""
    """
    代码验证结果数据类

    封装验证过程的结果，包括是否通过、错误列表和警告列表。
    """
    is_valid: bool        # 验证是否通过，True=通过，False=不通过
    errors: List[str]     # 错误列表，包含所有验证失败的原因
    warnings: List[str]   # 警告列表，不影响验证结果但建议修复


# ========== 安全规则配置 ==========

# Forbidden imports - 禁止导入的模块
# 这些模块可能被用于执行危险操作，如文件系统访问、网络请求、进程控制等
FORBIDDEN_IMPORTS = {
    # 文件系统相关 - 可能读写任意文件
    "os",           # 操作系统接口，可执行系统命令
    "sys",          # 系统参数和函数，可修改运行时环境
    "subprocess",   # 子进程管理，可执行任意系统命令
    "shutil",       # 高级文件操作，可删除整个目录
    "pathlib",      # 路径操作，可遍历文件系统

    # 网络相关 - 可能发送数据到外部服务器
    "socket",       # 底层网络接口
    "requests",     # HTTP请求库
    "urllib",       # URL处理库
    "http",         # HTTP协议库

    # 序列化相关 - 可能执行反序列化攻击
    "pickle",       # Python对象序列化，可执行任意代码
    "marshal",      # 低级序列化
    "shelve",       # 基于pickle的持久化

    # 系统底层相关 - 可能绕过安全限制
    "ctypes",       # C语言类型库，可调用任意C函数
    "multiprocessing",  # 多进程，可能逃逸沙箱
    "threading",    # 多线程
    "importlib",    # 动态导入，可能导入任意模块
    "builtins",     # 内置函数模块
    "__builtins__", # 内置命名空间
}

# Forbidden functions - 禁止调用的函数
# 这些函数可能被用于执行危险操作或绕过安全限制
FORBIDDEN_FUNCTIONS = {
    # 代码执行类 - 可执行任意代码
    "eval",         # 执行字符串表达式
    "exec",         # 执行字符串代码
    "compile",      # 编译代码对象

    # 文件和输入类 - 可能读写文件或获取用户输入
    "open",         # 打开文件
    "input",        # 获取用户输入

    # 元编程类 - 可能绕过安全限制
    "__import__",   # 动态导入模块
    "globals",      # 获取全局命名空间
    "locals",       # 获取局部命名空间
    "vars",         # 获取对象属性字典
    "getattr",      # 获取对象属性（可能访问私有属性）
    "setattr",      # 设置对象属性
    "delattr",      # 删除对象属性
    "hasattr",      # 检查属性是否存在

    # 其他危险函数
    "breakpoint",   # 调试断点
    "exit",         # 退出程序
    "quit",         # 退出程序
}

# Allowed builtins - 允许使用的内置函数
# 这些是安全的、策略代码可能需要的基本函数
ALLOWED_BUILTINS = {
    # 数学函数
    "abs", "min", "max", "sum", "len", "round",
    # 类型转换
    "int", "float", "str", "bool", "list", "dict", "tuple", "set",
    # 迭代工具
    "range", "enumerate", "zip", "map", "filter", "sorted", "reversed",
    # 逻辑判断
    "any", "all", "isinstance", "type",
    # 常量
    "True", "False", "None",
}


class CodeValidator:
    """Validates strategy code for safety and correctness."""
    """
    代码验证器类

    对策略代码进行安全性和正确性验证。
    使用静态分析技术，不执行代码，只分析代码结构。
    """

    def validate(self, code: str) -> ValidationResult:
        """
        Run all validation checks on code.
        对代码运行所有验证检查

        Args:
            code: 要验证的Python代码字符串

        Returns:
            ValidationResult: 验证结果，包含是否通过、错误和警告
        """
        errors = []    # 存储错误信息的列表
        warnings = []  # 存储警告信息的列表

        # 1. Syntax check - 语法检查
        # 首先确保代码是有效的Python语法
        syntax_result = self._check_syntax(code)
        if syntax_result:  # 如果有语法错误
            errors.append(syntax_result)
            # 语法错误直接返回，无法继续其他检查
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        # 2. Parse AST - 解析抽象语法树
        # 将代码转换为语法树结构，便于分析
        try:
            tree = ast.parse(code)  # 解析代码为AST
        except SyntaxError as e:
            errors.append(f"Syntax error: {e}")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        # 3. Security check - 安全检查
        # 检查是否有危险的导入和函数调用
        security_errors = self._check_security(tree)
        errors.extend(security_errors)  # 将安全错误添加到错误列表

        # 4. Template compliance check - 模板规范检查
        # 检查代码是否符合策略模板要求
        template_errors, template_warnings = self._check_template(tree)
        errors.extend(template_errors)      # 添加模板错误
        warnings.extend(template_warnings)  # 添加模板警告

        # 返回最终验证结果
        return ValidationResult(
            is_valid=len(errors) == 0,  # 没有错误则验证通过
            errors=errors,
            warnings=warnings,
        )

    def _check_syntax(self, code: str) -> Optional[str]:
        """
        Check Python syntax.
        检查Python语法是否正确

        Args:
            code: 要检查的代码字符串

        Returns:
            None: 语法正确
            str: 语法错误的描述信息
        """
        try:
            ast.parse(code)  # 尝试解析代码
            return None      # 成功则返回None
        except SyntaxError as e:
            # 返回错误信息，包含行号和错误描述
            return f"Line {e.lineno}: {e.msg}"

    def _check_security(self, tree: ast.AST) -> List[str]:
        """
        Check for forbidden imports and function calls.
        检查禁止的导入和函数调用

        遍历整个语法树，检查每个节点是否包含危险操作。

        Args:
            tree: 代码的抽象语法树

        Returns:
            List[str]: 安全错误列表
        """
        errors = []  # 存储发现的安全问题

        # ast.walk遍历语法树中的每个节点
        for node in ast.walk(tree):
            # 检查import语句，如: import os
            if isinstance(node, ast.Import):
                for alias in node.names:
                    # 获取模块名的第一部分（如 os.path 取 os）
                    module = alias.name.split(".")[0]
                    if module in FORBIDDEN_IMPORTS:
                        errors.append(f"Forbidden import: {alias.name}")

            # 检查from import语句，如: from os import path
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module = node.module.split(".")[0]
                    if module in FORBIDDEN_IMPORTS:
                        errors.append(f"Forbidden import: {node.module}")

            # 检查函数调用，如: eval("code")
            elif isinstance(node, ast.Call):
                # 检查是否是简单的函数名调用（不是方法调用）
                if isinstance(node.func, ast.Name):
                    if node.func.id in FORBIDDEN_FUNCTIONS:
                        errors.append(f"Forbidden function: {node.func.id}()")

        return errors

    def _check_template(self, tree: ast.AST) -> Tuple[List[str], List[str]]:
        """
        Check strategy template compliance.
        检查策略模板规范合规性

        确保代码符合策略模板的要求：
        1. 必须定义一个类
        2. 类必须有should_trade方法
        3. should_trade方法必须接受data参数

        Args:
            tree: 代码的抽象语法树

        Returns:
            Tuple[List[str], List[str]]: (错误列表, 警告列表)
        """
        errors = []
        warnings = []

        # Find class definitions - 查找所有类定义
        # 使用列表推导式收集所有ClassDef节点
        classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]

        # 检查是否有类定义
        if not classes:
            errors.append("No class definition found. Strategy must define a class.")
            # 没有类定义，中文：未找到类定义。策略必须定义一个类。
            return errors, warnings

        # Check for Strategy-like class - 查找策略类
        # 策略类必须有should_trade方法
        strategy_class = None
        for cls in classes:
            # 获取类中所有方法的名称
            methods = [n.name for n in cls.body if isinstance(n, ast.FunctionDef)]
            if "should_trade" in methods:
                strategy_class = cls
                break  # 找到就停止

        # 检查是否找到策略类
        if not strategy_class:
            errors.append("Strategy class must have 'should_trade' method.")
            # 中文：策略类必须有'should_trade'方法
            return errors, warnings

        # Check should_trade signature - 检查should_trade方法签名
        for node in strategy_class.body:
            if isinstance(node, ast.FunctionDef) and node.name == "should_trade":
                args = node.args
                # 应该有self和data两个参数
                if len(args.args) < 2:
                    errors.append("should_trade must accept 'data' parameter.")
                    # 中文：should_trade必须接受'data'参数

        # Check for init method - 检查init方法（可选）
        methods = [n.name for n in strategy_class.body if isinstance(n, ast.FunctionDef)]
        if "init" not in methods and "__init__" not in methods:
            # 建议添加init方法，但不是错误
            warnings.append("Consider adding 'init' method for parameter initialization.")
            # 中文：建议添加'init'方法用于参数初始化

        return errors, warnings


def validate_strategy_code(code: str) -> ValidationResult:
    """
    Convenience function to validate strategy code.
    验证策略代码的便捷函数

    这是一个快捷函数，创建CodeValidator实例并执行验证。

    Args:
        code: 要验证的策略代码字符串

    Returns:
        ValidationResult: 验证结果
    """
    validator = CodeValidator()  # 创建验证器实例
    return validator.validate(code)  # 执行验证并返回结果
