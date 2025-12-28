"""
Parameter Validator for Network MCP Server
验证工具参数的必填性、类型和枚举值
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ValidationResult:
    """参数验证结果"""
    valid: bool
    errors: List[str] = field(default_factory=list)
    
    @property
    def error_message(self) -> str:
        """返回格式化的错误信息"""
        if not self.errors:
            return ""
        return "; ".join(self.errors)


class ParameterValidator:
    """
    参数验证器
    
    验证工具参数是否符合配置定义：
    - 必填参数检查
    - 类型检查
    - 枚举值检查
    - 范围检查（min/max）
    """
    
    # 类型映射：配置中的类型名 -> Python 类型
    TYPE_MAP = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    
    def __init__(self, tool_config_map: Dict[str, Dict[str, Any]]):
        """
        初始化验证器
        
        Args:
            tool_config_map: 工具配置映射 {tool_name: tool_config}
        """
        self.tool_config_map = tool_config_map
    
    def validate(self, tool_name: str, arguments: Dict[str, Any]) -> ValidationResult:
        """
        验证工具参数
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            ValidationResult: 验证结果
        """
        tool_config = self.tool_config_map.get(tool_name)
        if not tool_config:
            return ValidationResult(
                valid=False,
                errors=[f"Unknown tool: {tool_name}"]
            )
        
        errors = []
        parameters_config = tool_config.get("parameters", {})
        
        # 检查必填参数
        for param_name, param_config in parameters_config.items():
            if param_config.get("required", False):
                if param_name not in arguments or arguments[param_name] is None:
                    errors.append(f"Missing required parameter: {param_name}")
        
        # 检查提供的参数
        for param_name, value in arguments.items():
            if value is None:
                continue
                
            param_config = parameters_config.get(param_name)
            if not param_config:
                # 未知参数，跳过（允许额外参数）
                continue
            
            # 类型检查
            expected_type = param_config.get("type")
            if expected_type:
                type_error = self._check_type(param_name, value, expected_type)
                if type_error:
                    errors.append(type_error)
                    continue  # 类型错误时跳过后续检查
            
            # 枚举检查
            if "enum" in param_config:
                enum_values = param_config["enum"]
                if value not in enum_values:
                    errors.append(
                        f"Invalid value for {param_name}: '{value}' must be one of {enum_values}"
                    )
            
            # 范围检查（仅对数值类型）
            if expected_type in ("integer", "number"):
                range_error = self._check_range(param_name, value, param_config)
                if range_error:
                    errors.append(range_error)
        
        return ValidationResult(valid=len(errors) == 0, errors=errors)
    
    def _check_type(self, param_name: str, value: Any, expected_type: str) -> Optional[str]:
        """
        检查参数类型
        
        Args:
            param_name: 参数名
            value: 参数值
            expected_type: 期望类型
            
        Returns:
            错误信息，如果类型正确则返回 None
        """
        python_type = self.TYPE_MAP.get(expected_type)
        if python_type is None:
            return None  # 未知类型，跳过检查
        
        if not isinstance(value, python_type):
            actual_type = type(value).__name__
            return f"Invalid type for {param_name}: expected {expected_type}, got {actual_type}"
        
        return None
    
    def _check_range(
        self, param_name: str, value: Any, param_config: Dict[str, Any]
    ) -> Optional[str]:
        """
        检查数值范围
        
        Args:
            param_name: 参数名
            value: 参数值
            param_config: 参数配置
            
        Returns:
            错误信息，如果范围正确则返回 None
        """
        min_val = param_config.get("min")
        max_val = param_config.get("max")
        
        if min_val is not None and value < min_val:
            return f"Value for {param_name} is too small: {value} < {min_val}"
        
        if max_val is not None and value > max_val:
            return f"Value for {param_name} is too large: {value} > {max_val}"
        
        return None
    
    def get_missing_required_params(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> List[str]:
        """
        获取缺失的必填参数列表
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            缺失的必填参数名列表
        """
        tool_config = self.tool_config_map.get(tool_name)
        if not tool_config:
            return []
        
        missing = []
        parameters_config = tool_config.get("parameters", {})
        
        for param_name, param_config in parameters_config.items():
            if param_config.get("required", False):
                if param_name not in arguments or arguments[param_name] is None:
                    missing.append(param_name)
        
        return missing
    
    def format_validation_error(self, result: ValidationResult, tool_name: str) -> str:
        """
        格式化验证错误为友好的错误提示
        
        Args:
            result: 验证结果
            tool_name: 工具名称
            
        Returns:
            格式化的错误信息
        """
        if result.valid:
            return ""
        
        error_lines = [f"Parameter validation failed for tool '{tool_name}':"]
        for error in result.errors:
            error_lines.append(f"  - {error}")
        
        # 添加参数说明
        tool_config = self.tool_config_map.get(tool_name)
        if tool_config:
            parameters_config = tool_config.get("parameters", {})
            required_params = [
                name for name, cfg in parameters_config.items()
                if cfg.get("required", False)
            ]
            if required_params:
                error_lines.append(f"Required parameters: {', '.join(required_params)}")
        
        return "\n".join(error_lines)
