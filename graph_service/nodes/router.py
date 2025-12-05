"""
Router节点
根据用户问题路由到不同的Agent
"""
import json
import re
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger
from langchain_community.llms import Ollama
from ..state import GraphState
from utils import load_langgraph_config, load_router_prompt_config, settings, get_config_manager


def router_node(state: GraphState) -> GraphState:
    """
    路由节点,决定使用哪个Agent

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    state["current_node"] = "router"

    user_query = state["user_query"]

    # 过滤掉 OpenWebUI 的 follow-up questions 请求
    if "follow_up" in user_query.lower() or "suggest" in user_query.lower() and "question" in user_query.lower():
        logger.info("Router: 检测到 follow-up questions 请求,跳过路由")
        state["target_agent"] = "skip"
        state["final_answer"] = '{"follow_ups": []}'
        return state

    # 路由优先级：
    # 1. 手动路由（@agent 语法）
    # 2. 工作流模板匹配
    # 3. LLM 自动路由

    # 优先检查手动路由（@agent 语法）
    agent_plan = _parse_manual_routing(user_query)

    if agent_plan:
        # 使用手动路由
        logger.info(f"Router: 使用手动路由")
    else:
        # 检查工作流模板匹配
        agent_plan = _match_workflow_template(user_query)

        if agent_plan:
            # 使用工作流模板
            logger.info(f"Router: 使用工作流模板")
        else:
            # 使用 LLM 路由
            logger.info(f"Router: 使用 LLM 自动路由")
            agent_plan = _llm_router(user_query)

    if agent_plan and len(agent_plan) > 0:
        # 设置 agent_plan
        state["agent_plan"] = agent_plan
        state["current_agent_index"] = 0

        # 为了向后兼容，设置 target_agent 为第一个 agent
        state["target_agent"] = agent_plan[0]["name"]
    else:
        # 如果路由失败，使用默认路由
        logger.warning("Router: 路由失败，使用默认路由 -> network_agent")
        state["target_agent"] = "network_agent"
        state["agent_plan"] = None
        state["current_agent_index"] = 0

    # 初始化 ReAct 状态
    _initialize_react_state(state)

    return state


def _load_workflow_templates() -> Dict[str, Any]:
    """
    加载工作流模板配置

    Returns:
        工作流模板配置字典
    """
    try:
        config_path = Path(__file__).parent.parent.parent / "config" / "workflow_templates.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        logger.error(f"加载工作流模板配置失败: {e}")
        return {"templates": []}


def _match_workflow_template(user_query: str) -> Optional[List[Dict[str, Any]]]:
    """
    匹配工作流模板

    Args:
        user_query: 用户问题

    Returns:
        Agent 执行计划列表，如果没有匹配的模板则返回 None
    """
    try:
        # 加载模板配置
        config = _load_workflow_templates()
        templates = config.get("templates", [])

        # 遍历所有模板，查找匹配的关键词
        for template in templates:
            keywords = template.get("keywords", [])

            # 检查用户问题是否包含任何关键词
            for keyword in keywords:
                if keyword in user_query:
                    logger.info(f"Router: 匹配到工作流模板: {template['name']} (关键词: {keyword})")

                    # 提取参数
                    parameters = _extract_template_parameters(user_query, template)

                    # 检查必填参数是否都已提取
                    missing_params = []
                    for param in template.get("parameters", []):
                        if param.get("required", False) and param["name"] not in parameters:
                            missing_params.append(param["name"])

                    if missing_params:
                        logger.warning(f"Router: 模板 {template['name']} 缺少必填参数: {missing_params}")
                        continue

                    # 生成 Agent 执行计划
                    agent_plan = _generate_agent_plan_from_template(template, parameters)

                    if agent_plan:
                        logger.info(f"Router: 使用模板 {template['name']} 生成执行计划")
                        return agent_plan

        return None

    except Exception as e:
        logger.error(f"Router: 匹配工作流模板失败: {e}")
        return None


def _extract_template_parameters(user_query: str, template: Dict[str, Any]) -> Dict[str, str]:
    """
    从用户问题中提取模板参数

    Args:
        user_query: 用户问题
        template: 模板配置

    Returns:
        参数字典
    """
    parameters = {}

    for param in template.get("parameters", []):
        param_name = param["name"]
        extract_pattern = param.get("extract_pattern")

        if extract_pattern:
            # 使用正则表达式提取参数
            match = re.search(extract_pattern, user_query)
            if match:
                parameters[param_name] = match.group(0)
        else:
            # 使用默认值
            if "default" in param:
                parameters[param_name] = param["default"]

    return parameters


def _generate_agent_plan_from_template(template: Dict[str, Any], parameters: Dict[str, str]) -> Optional[List[Dict[str, Any]]]:
    """
    根据模板和参数生成 Agent 执行计划

    Args:
        template: 模板配置
        parameters: 参数字典

    Returns:
        Agent 执行计划列表
    """
    try:
        agent_plan = []

        for agent_config in template.get("agents", []):
            agent_name = agent_config["name"]
            task_template = agent_config["task_template"]

            # 替换模板中的参数
            task = task_template
            for param_name, param_value in parameters.items():
                task = task.replace(f"{{{param_name}}}", param_value)

            agent_plan.append({
                "name": agent_name,
                "task": task,
                "status": "pending"
            })

        logger.info(f"Router: 生成了 {len(agent_plan)} 个 Agent 的执行计划")
        for i, agent in enumerate(agent_plan):
            logger.info(f"  Agent {i+1}: {agent['name']} - {agent['task']}")

        return agent_plan

    except Exception as e:
        logger.error(f"Router: 生成 Agent 执行计划失败: {e}")
        return None


def _parse_manual_routing(user_query: str) -> Optional[List[Dict[str, Any]]]:
    """
    解析手动指定的 Agent 路由（@agent 语法）

    语法格式：@agent_name 任务描述 [@agent_name 任务描述 ...]

    示例：
    - @database 查询 iteams_db 数据库中有哪些表
    - @database 查询 IP 地址 @network ping 测试连通性

    Args:
        user_query: 用户问题

    Returns:
        Agent 执行计划列表，如果没有找到 @agent 标记则返回 None
    """
    # Agent 名称映射
    agent_mapping = {
        "database": "database_agent",
        "network": "network_agent",
    }

    # 查找所有 @agent_name 标记
    pattern = r'@(\w+)\s+([^@]+)'
    matches = re.findall(pattern, user_query)

    if not matches:
        return None

    agent_plan = []
    for agent_short_name, task_desc in matches:
        # 映射到完整的 agent 名称
        agent_name = agent_mapping.get(agent_short_name.lower())

        if not agent_name:
            logger.warning(f"未知的 Agent 名称: @{agent_short_name}，跳过")
            continue

        agent_plan.append({
            "name": agent_name,
            "task": task_desc.strip(),
            "status": "pending"
        })

    if not agent_plan:
        return None

    logger.info(f"Router: 手动路由 -> {len(agent_plan)} 个 Agent")
    for i, agent in enumerate(agent_plan):
        logger.info(f"  Agent {i+1}: {agent['name']} - {agent['task']}")

    return agent_plan


def _llm_router(user_query: str) -> Optional[List[Dict[str, Any]]]:
    """
    使用 LLM 进行路由决策

    Args:
        user_query: 用户问题

    Returns:
        Agent 执行计划列表，格式: [{"name": "agent_name", "task": "任务描述", "status": "pending"}]
    """
    try:
        # 加载配置
        router_config = load_router_prompt_config()
        llm_router_config = router_config.get("llm_router", {})

        system_prompt = llm_router_config.get("system_prompt", "")
        user_prompt_template = llm_router_config.get("user_prompt_template", "")
        llm_config = llm_router_config.get("llm_config", {})

        # 构建提示词
        user_prompt = user_prompt_template.format(user_query=user_query)
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        # 调用 LLM（使用配置管理器）
        config_manager = get_config_manager()
        llm = config_manager.get_llm("router")

        logger.info(f"Router: 调用 LLM 进行路由决策...")
        response = llm.invoke(full_prompt)
        logger.info(f"Router: LLM 响应: {response[:200]}...")

        # 解析 LLM 响应
        agent_plan = _parse_llm_response(response)

        return agent_plan

    except Exception as e:
        logger.error(f"Router: LLM 路由失败: {e}")
        return None


def _parse_llm_response(response: str) -> Optional[List[Dict[str, Any]]]:
    """
    解析 LLM 响应，提取 Agent 执行计划

    Args:
        response: LLM 响应文本

    Returns:
        Agent 执行计划列表
    """
    try:
        # 尝试提取 JSON（可能被包裹在其他文本中）
        json_match = re.search(r'\{[\s\S]*"agents"[\s\S]*\}', response)
        if json_match:
            json_str = json_match.group(0)
            data = json.loads(json_str)
        else:
            # 尝试直接解析整个响应
            data = json.loads(response)

        # 提取 agents 列表
        agents = data.get("agents", [])

        if not agents:
            logger.warning("Router: LLM 响应中没有 agents 字段")
            return None

        # 为每个 agent 添加 status 字段
        agent_plan = []
        for agent in agents:
            agent_plan.append({
                "name": agent.get("name", ""),
                "task": agent.get("task", ""),
                "status": "pending"
            })

        logger.info(f"Router: 解析出 {len(agent_plan)} 个 Agent")
        return agent_plan

    except json.JSONDecodeError as e:
        logger.error(f"Router: 解析 LLM 响应失败（JSON 格式错误）: {e}")
        logger.error(f"Router: 原始响应: {response}")
        return None
    except Exception as e:
        logger.error(f"Router: 解析 LLM 响应失败: {e}")
        return None


def _initialize_react_state(state: GraphState):
    """初始化 ReAct 循环状态"""
    if "execution_history" not in state or state.get("execution_history") is None:
        state["execution_history"] = []
    if "current_step" not in state or state.get("current_step") == 0:
        state["current_step"] = 1
    if "max_iterations" not in state or state.get("max_iterations") == 0:
        state["max_iterations"] = 10
    if "is_finished" not in state or state.get("is_finished") is None:
        state["is_finished"] = False
    if "last_observation" not in state or state.get("last_observation") is None:
        state["last_observation"] = ""
    if "next_action" not in state or state.get("next_action") is None:
        state["next_action"] = None
