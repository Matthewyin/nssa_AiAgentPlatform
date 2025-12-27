"""
ToolGateway - 工具网关
统一的工具调用入口，负责：
1. 逻辑工具名 → 物理端点路由
2. 服务发现与负载均衡
3. 权限检查
4. 审计日志
5. 错误处理与重试
"""

from pathlib import Path
from typing import Any, Dict, Optional
import yaml

from utils.logger import get_logger
from .catalog import ToolCatalog
from .audit import AuditLogger
from .registry import ServerRegistry, ServerStatus
from .router import RoutingStrategyFactory
from .models import ToolCallRequest, ToolCallResult, ToolCallStatus

logger = get_logger(__name__)


class ToolGateway:
    """工具网关 - 统一的工具调用入口"""

    _instance: Optional["ToolGateway"] = None
    _mcp_manager = None

    def __new__(cls, *args, **kwargs):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """初始化工具网关"""
        if self._initialized:
            return

        self._initialized = True
        self.catalog = ToolCatalog()
        self.audit_logger = AuditLogger()
        self.registry = ServerRegistry()

        # 加载路由配置
        self.routing_config = self._load_routing_config()

        logger.info("ToolGateway 初始化完成（含 ServerRegistry 和路由策略）")

    def _load_routing_config(self) -> Dict[str, Any]:
        """加载路由配置"""
        config_path = Path(__file__).parent.parent / "config" / "server_registry.yaml"
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                return config.get("routing", {})
        except Exception as e:
            logger.warning(f"加载路由配置失败: {e}，使用默认配置")
            return {"default_strategy": "round_robin"}

    def _get_routing_strategy(self, strategy_name: Optional[str] = None):
        """获取路由策略"""
        if strategy_name is None:
            strategy_name = self.routing_config.get("default_strategy", "round_robin")

        # 获取策略配置
        strategies_config = self.routing_config.get("strategies", {})
        strategy_config = strategies_config.get(strategy_name, {})

        return RoutingStrategyFactory.get(strategy_name, strategy_config)
    
    async def _get_mcp_manager(self):
        """获取 MCP Manager 实例"""
        if self._mcp_manager is None:
            from graph_service.mcp_integration import get_mcp_manager
            self._mcp_manager = await get_mcp_manager()
        return self._mcp_manager
    
    async def call_tool(
        self,
        logical_name: str,
        params: Dict[str, Any],
        caller_agent: str,
        session_id: Optional[str] = None,
        environment: str = "default",
    ) -> ToolCallResult:
        """
        调用工具（通过逻辑工具名）
        
        Args:
            logical_name: 逻辑工具名（如 ping, sql_query）
            params: 调用参数
            caller_agent: 调用者 Agent
            session_id: 会话 ID
            environment: 环境标识
        
        Returns:
            ToolCallResult 工具调用结果
        """
        # 创建请求
        request = ToolCallRequest(
            logical_name=logical_name,
            params=params,
            caller_agent=caller_agent,
            session_id=session_id,
        )
        
        # 初始化结果
        result = ToolCallResult(
            request_id=request.request_id,
            logical_name=logical_name,
            physical_tool="",
            mcp_server="",
            status=ToolCallStatus.PENDING,
        )

        # 用于追踪选中的 Server（负载均衡）
        selected_server = None

        try:
            # 1. 查找工具绑定
            binding = self.catalog.get_binding(logical_name, environment)
            if not binding:
                result.complete(
                    ToolCallStatus.FAILED,
                    error=f"未找到工具: {logical_name}"
                )
                self.audit_logger.log_call(request, result)
                return result
            
            result.physical_tool = binding.physical_tool
            result.mcp_server = binding.mcp_server
            
            # 2. 权限检查
            tool_def = self.catalog.get_tool(logical_name)
            if tool_def and tool_def.permissions:
                perm = tool_def.permissions
                if perm.allowed_agents and caller_agent not in perm.allowed_agents:
                    result.complete(
                        ToolCallStatus.PERMISSION_DENIED,
                        error=f"Agent '{caller_agent}' 无权调用工具 '{logical_name}'"
                    )
                    self.audit_logger.log_call(request, result)
                    return result
            
            # 3. 获取可用的 Server 实例（用于负载均衡）
            servers = self.registry.get_servers_for_tool(binding.physical_tool)

            if servers:
                # 使用路由策略选择 Server
                strategy = self._get_routing_strategy()
                selected_server = strategy.select(servers, params)
                if selected_server:
                    result.mcp_server = selected_server.name
                    logger.debug(f"[{request.request_id}] 路由选择 Server: {selected_server.name}")

            # 4. 调用物理工具
            result.status = ToolCallStatus.RUNNING
            logger.info(
                f"[{request.request_id}] 调用工具: {logical_name} -> "
                f"{binding.physical_tool}@{result.mcp_server}, 参数: {params}"
            )

            mcp_manager = await self._get_mcp_manager()
            tool_result = await mcp_manager.call_tool(binding.physical_tool, params)

            # 5. [中间件] 结果增强与标准化
            from graph_service.utils.result_summarizer import enhance_result
            enhanced_result = enhance_result(logical_name, tool_result)

            # 6. 完成调用，记录成功
            result.complete(ToolCallStatus.SUCCESS, result=enhanced_result)
            logger.info(f"[{request.request_id}] 工具调用成功: {logical_name}")

            # 更新 Server 统计
            if selected_server:
                self.registry.record_request(selected_server.name, success=True)
                self.registry.mark_healthy(selected_server.name)
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[{request.request_id}] 工具调用失败: {logical_name}, 错误: {error_msg}")
            result.complete(ToolCallStatus.FAILED, error=error_msg)

            # 更新 Server 统计（如果有选中的 Server）
            if selected_server:
                self.registry.record_request(selected_server.name, success=False)
                self.registry.mark_unhealthy(selected_server.name)

        # 7. 记录审计日志
        self.audit_logger.log_call(request, result)

        return result
    
    async def call_tool_by_physical_name(
        self,
        physical_name: str,
        params: Dict[str, Any],
        caller_agent: str,
        session_id: Optional[str] = None,
    ) -> ToolCallResult:
        """
        通过物理工具名调用（向后兼容）
        
        会自动查找对应的逻辑工具名
        """
        # 尝试查找逻辑工具名
        logical_name = self.catalog.get_logical_name(physical_name)
        if logical_name:
            return await self.call_tool(logical_name, params, caller_agent, session_id)
        
        # 如果没有映射，直接调用物理工具（向后兼容）
        request = ToolCallRequest(
            logical_name=physical_name,
            params=params,
            caller_agent=caller_agent,
            session_id=session_id,
        )
        
        result = ToolCallResult(
            request_id=request.request_id,
            logical_name=physical_name,
            physical_tool=physical_name,
            mcp_server="unknown",
            status=ToolCallStatus.PENDING,
        )
        
        try:
            mcp_manager = await self._get_mcp_manager()
            tool_result = await mcp_manager.call_tool(physical_name, params)
            
            # [中间件] 结果增强
            from graph_service.utils.result_summarizer import enhance_result
            enhanced_result = enhance_result(physical_name, tool_result)
            
            result.complete(ToolCallStatus.SUCCESS, result=enhanced_result)
        except Exception as e:
            result.complete(ToolCallStatus.FAILED, error=str(e))
        
        self.audit_logger.log_call(request, result)
        return result

