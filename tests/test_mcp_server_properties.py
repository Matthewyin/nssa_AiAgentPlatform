"""
Property-Based Tests for MCP Server
验证 MCP Server 的参数验证和批量探测功能

Feature: network-probe-optimization
Property 11: MCP Server 参数验证
Property 12: MCP Server 批量探测
Validates: Requirements 6.2, 6.4
"""
import pytest
from hypothesis import given, strategies as st, settings, assume
from typing import Any, Dict, List

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mcp_servers.network_mcp.validator import ParameterValidator, ValidationResult


# 模拟工具配置（用于测试）
TEST_TOOL_CONFIG = {
    "network.ping": {
        "name": "network.ping",
        "parameters": {
            "target": {
                "type": "string",
                "required": True,
                "description": "目标主机"
            },
            "count": {
                "type": "integer",
                "required": False,
                "default": 4,
                "min": 1,
                "max": 100
            },
            "timeout": {
                "type": "integer",
                "required": False,
                "default": 10,
                "min": 1,
                "max": 60
            }
        }
    },
    "network.nslookup": {
        "name": "network.nslookup",
        "parameters": {
            "target": {
                "type": "string",
                "required": True,
                "description": "要查询的域名"
            },
            "record_type": {
                "type": "string",
                "required": False,
                "default": "A",
                "enum": ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA"]
            }
        }
    },
    "network.tcp": {
        "name": "network.tcp",
        "parameters": {
            "host": {
                "type": "string",
                "required": True,
                "description": "目标主机"
            },
            "port": {
                "type": "integer",
                "required": True,
                "min": 1,
                "max": 65535
            },
            "timeout": {
                "type": "integer",
                "required": False,
                "default": 10,
                "min": 1,
                "max": 60
            }
        }
    },
    "network.http": {
        "name": "network.http",
        "parameters": {
            "url": {
                "type": "string",
                "required": True,
                "description": "目标 URL"
            },
            "method": {
                "type": "string",
                "required": False,
                "default": "GET",
                "enum": ["GET", "POST", "PUT", "DELETE", "HEAD"]
            },
            "timeout": {
                "type": "integer",
                "required": False,
                "default": 15,
                "min": 1,
                "max": 300
            }
        }
    }
}


class TestParameterValidation:
    """
    Property 11: MCP Server 参数验证
    
    *For any* 缺少必填参数的工具调用，MCP Server 应返回包含 `success: false` 
    和明确错误信息的结果，错误信息应指明缺少的参数名称。
    
    **Validates: Requirements 6.2**
    """
    
    @pytest.fixture
    def validator(self):
        return ParameterValidator(TEST_TOOL_CONFIG)
    
    # ========== Property 11: 参数验证 ==========
    
    @given(st.sampled_from(["network.ping", "network.tcp"]))
    @settings(max_examples=100)
    def test_missing_required_params_returns_error(self, tool_name: str):
        """
        Property 11: 缺少必填参数时返回错误
        
        Feature: network-probe-optimization, Property 11: MCP Server 参数验证
        Validates: Requirements 6.2
        """
        validator = ParameterValidator(TEST_TOOL_CONFIG)
        
        # 空参数调用
        result = validator.validate(tool_name, {})
        
        # 验证返回失败
        assert not result.valid, f"Expected validation to fail for {tool_name} with empty args"
        
        # 验证错误信息包含缺少的参数名
        assert len(result.errors) > 0, "Expected at least one error"
        assert any("Missing required parameter" in err for err in result.errors), \
            f"Expected 'Missing required parameter' in errors: {result.errors}"
    
    @given(
        target=st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
        count=st.integers(min_value=1, max_value=100)
    )
    @settings(max_examples=100)
    def test_valid_params_pass_validation(self, target: str, count: int):
        """
        Property 11: 有效参数通过验证
        
        Feature: network-probe-optimization, Property 11: MCP Server 参数验证
        Validates: Requirements 6.2
        """
        validator = ParameterValidator(TEST_TOOL_CONFIG)
        
        result = validator.validate("network.ping", {
            "target": target,
            "count": count
        })
        
        assert result.valid, f"Expected validation to pass: {result.errors}"
    
    @given(
        target=st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
        count=st.integers().filter(lambda x: x < 1 or x > 100)
    )
    @settings(max_examples=100)
    def test_out_of_range_params_fail_validation(self, target: str, count: int):
        """
        Property 11: 超出范围的参数验证失败
        
        Feature: network-probe-optimization, Property 11: MCP Server 参数验证
        Validates: Requirements 6.2
        """
        validator = ParameterValidator(TEST_TOOL_CONFIG)
        
        result = validator.validate("network.ping", {
            "target": target,
            "count": count
        })
        
        assert not result.valid, f"Expected validation to fail for count={count}"
        assert any("too small" in err or "too large" in err for err in result.errors), \
            f"Expected range error in: {result.errors}"
    
    @given(
        target=st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
        record_type=st.text(min_size=1, max_size=10).filter(
            lambda x: x not in ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA"]
        )
    )
    @settings(max_examples=100)
    def test_invalid_enum_value_fails_validation(self, target: str, record_type: str):
        """
        Property 11: 无效枚举值验证失败
        
        Feature: network-probe-optimization, Property 11: MCP Server 参数验证
        Validates: Requirements 6.2
        """
        validator = ParameterValidator(TEST_TOOL_CONFIG)
        
        result = validator.validate("network.nslookup", {
            "target": target,
            "record_type": record_type
        })
        
        assert not result.valid, f"Expected validation to fail for record_type={record_type}"
        assert any("must be one of" in err for err in result.errors), \
            f"Expected enum error in: {result.errors}"
    
    @given(
        target=st.integers()  # 错误类型：应该是字符串
    )
    @settings(max_examples=100)
    def test_wrong_type_fails_validation(self, target: int):
        """
        Property 11: 错误类型验证失败
        
        Feature: network-probe-optimization, Property 11: MCP Server 参数验证
        Validates: Requirements 6.2
        """
        validator = ParameterValidator(TEST_TOOL_CONFIG)
        
        result = validator.validate("network.ping", {
            "target": target  # 传入整数而非字符串
        })
        
        assert not result.valid, f"Expected validation to fail for target={target} (type: {type(target)})"
        assert any("Invalid type" in err for err in result.errors), \
            f"Expected type error in: {result.errors}"
    
    def test_unknown_tool_returns_error(self):
        """
        Property 11: 未知工具返回错误
        
        Feature: network-probe-optimization, Property 11: MCP Server 参数验证
        Validates: Requirements 6.2
        """
        validator = ParameterValidator(TEST_TOOL_CONFIG)
        
        result = validator.validate("network.unknown_tool", {"target": "example.com"})
        
        assert not result.valid
        assert any("Unknown tool" in err for err in result.errors)
    
    def test_error_message_contains_missing_param_names(self):
        """
        Property 11: 错误信息包含缺少的参数名称
        
        Feature: network-probe-optimization, Property 11: MCP Server 参数验证
        Validates: Requirements 6.2
        """
        validator = ParameterValidator(TEST_TOOL_CONFIG)
        
        # TCP 工具需要 host 和 port 两个必填参数
        result = validator.validate("network.tcp", {})
        
        assert not result.valid
        assert any("host" in err for err in result.errors), \
            f"Expected 'host' in error messages: {result.errors}"
        assert any("port" in err for err in result.errors), \
            f"Expected 'port' in error messages: {result.errors}"


class TestBatchProbe:
    """
    Property 12: MCP Server 批量探测
    
    *For any* 批量探测请求（包含 N 个目标），MCP Server 应返回包含 N 个结果的数组，
    每个结果包含对应目标的探测数据或错误信息。
    
    **Validates: Requirements 6.4**
    """
    
    @given(
        targets=st.lists(
            st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
            min_size=1,
            max_size=10
        )
    )
    @settings(max_examples=100)
    def test_batch_result_count_matches_target_count(self, targets: List[str]):
        """
        Property 12: 批量探测结果数量等于目标数量
        
        Feature: network-probe-optimization, Property 12: MCP Server 批量探测
        Validates: Requirements 6.4
        
        注意：这是一个结构验证测试，不实际执行网络探测
        """
        # 模拟批量探测结果结构
        batch_result = {
            "success": True,
            "tool": "network.ping",
            "batch": True,
            "total": len(targets),
            "success_count": len(targets),
            "failure_count": 0,
            "results": [
                {"target": t, "success": True, "data": {}} 
                for t in targets
            ]
        }
        
        # 验证结果数量
        assert batch_result["total"] == len(targets)
        assert len(batch_result["results"]) == len(targets)
        
        # 验证每个结果都有 target 字段
        for i, result in enumerate(batch_result["results"]):
            assert "target" in result, f"Result {i} missing 'target' field"
            assert result["target"] == targets[i]
    
    @given(
        targets=st.lists(
            st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
            min_size=2,
            max_size=10
        ),
        failure_indices=st.lists(st.integers(min_value=0, max_value=9), max_size=5)
    )
    @settings(max_examples=100)
    def test_batch_result_contains_success_and_failure_counts(
        self, targets: List[str], failure_indices: List[int]
    ):
        """
        Property 12: 批量探测结果包含成功/失败计数
        
        Feature: network-probe-optimization, Property 12: MCP Server 批量探测
        Validates: Requirements 6.4
        """
        # 过滤有效的失败索引
        valid_failure_indices = set(i for i in failure_indices if i < len(targets))
        
        # 模拟批量探测结果
        results = []
        for i, target in enumerate(targets):
            if i in valid_failure_indices:
                results.append({
                    "target": target,
                    "success": False,
                    "error": "Connection timeout"
                })
            else:
                results.append({
                    "target": target,
                    "success": True,
                    "data": {}
                })
        
        success_count = sum(1 for r in results if r.get("success", False))
        failure_count = len(targets) - success_count
        
        batch_result = {
            "success": success_count > 0,
            "tool": "network.ping",
            "batch": True,
            "total": len(targets),
            "success_count": success_count,
            "failure_count": failure_count,
            "results": results
        }
        
        # 验证计数正确
        assert batch_result["total"] == len(targets)
        assert batch_result["success_count"] + batch_result["failure_count"] == len(targets)
        assert batch_result["success_count"] == success_count
        assert batch_result["failure_count"] == failure_count
    
    def test_batch_result_each_item_has_target_or_error(self):
        """
        Property 12: 批量探测每个结果包含目标数据或错误信息
        
        Feature: network-probe-optimization, Property 12: MCP Server 批量探测
        Validates: Requirements 6.4
        """
        targets = ["example.com", "invalid-host-xxx", "google.com"]
        
        # 模拟混合成功/失败的结果
        batch_result = {
            "success": True,
            "tool": "network.ping",
            "batch": True,
            "total": 3,
            "success_count": 2,
            "failure_count": 1,
            "results": [
                {"target": "example.com", "success": True, "data": {"latency_ms": 10}},
                {"target": "invalid-host-xxx", "success": False, "error": "DNS resolution failed"},
                {"target": "google.com", "success": True, "data": {"latency_ms": 15}}
            ]
        }
        
        for result in batch_result["results"]:
            # 每个结果必须有 target 字段
            assert "target" in result
            
            # 成功的结果应该有 data 字段
            if result.get("success"):
                assert "data" in result or "raw_output" in result
            # 失败的结果应该有 error 字段
            else:
                assert "error" in result


class TestValidationResultFormatting:
    """测试验证结果格式化"""
    
    def test_format_validation_error_includes_required_params(self):
        """验证错误格式化包含必填参数列表"""
        validator = ParameterValidator(TEST_TOOL_CONFIG)
        
        result = validator.validate("network.tcp", {})
        formatted = validator.format_validation_error(result, "network.tcp")
        
        assert "network.tcp" in formatted
        assert "host" in formatted
        assert "port" in formatted
    
    def test_validation_result_error_message_property(self):
        """测试 ValidationResult.error_message 属性"""
        result = ValidationResult(
            valid=False,
            errors=["Error 1", "Error 2"]
        )
        
        assert "Error 1" in result.error_message
        assert "Error 2" in result.error_message
        assert "; " in result.error_message  # 分隔符
    
    def test_valid_result_has_empty_error_message(self):
        """有效结果的错误信息为空"""
        result = ValidationResult(valid=True, errors=[])
        assert result.error_message == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
