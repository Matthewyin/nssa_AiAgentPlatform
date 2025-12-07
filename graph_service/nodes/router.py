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
from ..state import GraphState
from utils import load_langgraph_config, load_router_prompt_config, settings, get_config_manager, load_optimization_config


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

    # 加载优化配置
    opt_config = _load_skip_router_config()

    # 检查路由缓存
    from utils.query_cache import get_query_cache
    query_cache = get_query_cache()
    cached_router = query_cache.get_router_cache(user_query)

    if cached_router:
        agent_plan = cached_router.get("agent_plan")
        first_action = cached_router.get("first_action")
        routing_method = "缓存"
        logger.info(f"Router: 使用缓存的路由结果")
    else:
        # 路由优先级：
        # 1. 手动路由（@agent 语法）
        # 2. 工作流模板匹配
        # 3. 规则引擎关键词匹配（新增）
        # 4. LLM 自动路由

        # 优先检查手动路由（@agent 语法）
        agent_plan = None
        routing_method = None
        first_action = None

        if opt_config.get("skip_on_manual_routing", True):
            agent_plan = _parse_manual_routing(user_query)
            if agent_plan:
                routing_method = "手动路由"
                logger.info(f"Router: 使用手动路由（跳过 LLM）")

        # 检查工作流模板匹配
        if not agent_plan and opt_config.get("skip_on_workflow_template", True):
            agent_plan = _match_workflow_template(user_query)
            if agent_plan:
                routing_method = "工作流模板"
                logger.info(f"Router: 使用工作流模板（跳过 LLM）")

        # 规则引擎关键词匹配（新增）
        if not agent_plan and opt_config.get("skip_on_keyword_match", True):
            agent_plan = _keyword_router(user_query)
            if agent_plan:
                routing_method = "规则引擎"
                logger.info(f"Router: 使用规则引擎关键词匹配（跳过 LLM）")

        # LLM 自动路由（兜底）
        if not agent_plan:
            logger.info(f"Router: 使用 LLM 自动路由")
            llm_result = _llm_router(user_query)
            if llm_result:
                agent_plan = llm_result.get("agent_plan")
                first_action = llm_result.get("first_action")

                # 缓存 LLM 路由结果
                query_cache.set_router_cache(user_query, {
                    "agent_plan": agent_plan,
                    "first_action": first_action
                })
            routing_method = "LLM"

    # 记录路由方法到 state
    if "metadata" not in state:
        state["metadata"] = {}
    state["metadata"]["routing_method"] = routing_method

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

    # 自适应 Think 深度：根据任务复杂度调整 max_iterations
    from ..utils.complexity_analyzer import analyze_complexity
    complexity, max_iterations = analyze_complexity(user_query, agent_plan)
    state["max_iterations"] = max_iterations
    state["metadata"]["task_complexity"] = complexity
    logger.info(f"Router: 任务复杂度={complexity}, max_iterations={max_iterations}")

    # 如果有首次行动决策，设置到 state 中（跳过首次 Think）
    if first_action and first_action.get("tool"):
        logger.info(f"Router: 设置首次行动决策: {first_action.get('tool')}")
        state["next_action"] = {
            "action_type": "TOOL",
            "tool_name": first_action.get("tool"),
            "params": first_action.get("params", {}),
            "thought": first_action.get("thought", "")
        }
        state["metadata"]["skip_first_think"] = True

    return state


def _load_skip_router_config() -> Dict[str, Any]:
    """
    加载跳过 LLM Router 的配置

    Returns:
        配置字典
    """
    try:
        config = load_optimization_config()
        return config.get("optimization", {}).get("skip_llm_router", {})
    except Exception as e:
        logger.warning(f"加载跳过 Router 配置失败: {e}")
        return {"enabled": True, "skip_on_manual_routing": True, "skip_on_workflow_template": True, "skip_on_keyword_match": True}


def _keyword_router(user_query: str) -> Optional[List[Dict[str, Any]]]:
    """
    规则引擎关键词路由（增强版）

    根据 langgraph_config.yaml 中的 keyword_rules 进行匹配
    支持置信度评估：匹配多个关键词时置信度更高

    Args:
        user_query: 用户问题

    Returns:
        Agent 执行计划列表，如果没有匹配则返回 None
    """
    try:
        # 加载配置
        config = load_langgraph_config()
        router_config = config.get("langgraph", {}).get("router", {})
        keyword_rules = router_config.get("keyword_rules", [])

        # 加载意图分类配置
        opt_config = load_optimization_config()
        intent_config = opt_config.get("optimization", {}).get("intent_classification", {})
        confidence_threshold = intent_config.get("rule_confidence_threshold", 0.5)

        query_lower = user_query.lower()

        # 计算每个规则的匹配分数
        best_match = None
        best_score = 0.0

        for rule in keyword_rules:
            keywords = rule.get("keywords", [])
            target_node = rule.get("target_node", "")
            exclude_keywords = rule.get("exclude_keywords", [])
            priority = rule.get("priority", 1)

            # 检查排除关键词
            excluded = False
            for exclude_kw in exclude_keywords:
                if exclude_kw.lower() in query_lower:
                    excluded = True
                    break

            if excluded:
                continue

            # 计算匹配分数
            matched_keywords = []
            for keyword in keywords:
                if keyword.lower() in query_lower:
                    matched_keywords.append(keyword)

            if matched_keywords:
                # 分数 = 匹配关键词数 / 总关键词数 * 优先级
                score = (len(matched_keywords) / len(keywords)) * priority

                if score > best_score:
                    best_score = score
                    best_match = {
                        "target_node": target_node,
                        "matched_keywords": matched_keywords,
                        "score": score
                    }

        # 检查是否达到置信度阈值
        if best_match and best_score >= confidence_threshold:
            logger.info(
                f"Router: 规则引擎匹配 -> {best_match['target_node']} "
                f"(关键词: {best_match['matched_keywords']}, 置信度: {best_score:.2f})"
            )

            return [{
                "name": best_match["target_node"],
                "task": user_query,
                "status": "pending"
            }]

        if best_match:
            logger.info(
                f"Router: 规则引擎匹配置信度不足 "
                f"({best_score:.2f} < {confidence_threshold})，回退到 LLM"
            )

        return None

    except Exception as e:
        logger.warning(f"规则引擎路由失败: {e}")
        return None


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


def _get_agent_name_mapping() -> Dict[str, str]:
    """
    从配置文件获取 Agent 名称映射

    Returns:
        Agent 短名称到完整名称的映射字典
        例如：{"database": "database_agent", "network": "network_agent"}
    """
    from utils import load_agent_mapping_config

    # 加载 Agent 映射配置
    mapping_config = load_agent_mapping_config()
    agents = mapping_config.get("agents", {})

    # 构建映射：短名称 -> 完整名称
    mapping = {}

    for agent_info in agents.values():
        full_name = agent_info.get("full_name")
        short_names = agent_info.get("short_names", [])

        # 为每个短名称创建映射
        for short_name in short_names:
            mapping[short_name.lower()] = full_name

    return mapping


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
    # 从配置文件获取 Agent 名称映射
    agent_mapping = _get_agent_name_mapping()

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


def _build_dynamic_system_prompt() -> str:
    """
    从配置文件动态构建 Router 的 system_prompt

    Returns:
        动态生成的 system_prompt
    """
    from utils import load_agent_mapping_config, load_agent_config, load_tools_config

    # 加载配置
    mapping_config = load_agent_mapping_config()
    agent_config = load_agent_config()
    tools_config = load_tools_config()

    agents = mapping_config.get("agents", {})

    # 构建 Agent 列表描述
    agent_descriptions = []

    for i, (agent_key, agent_info) in enumerate(agents.items(), 1):
        full_name = agent_info.get("full_name")
        description = agent_info.get("description", "")
        config_key = agent_info.get("config_key")
        tools_prefix = agent_info.get("tools_prefix")

        # 获取 Agent 的详细配置
        agent_detail = agent_config.get("agents", {}).get(config_key, {})

        # 获取工具列表
        tools = tools_config.get("tools", {}).get(tools_prefix, {})
        tool_names = [tool.get("name", "") for tool in tools.values()]

        # 构建描述
        agent_desc = f"{i}. {full_name} - {description}\n"
        agent_desc += f"   - 功能：{', '.join(tool_names)}\n"

        # 从 agent_config 中提取适用场景和关键词（如果有）
        # 这里简化处理，可以根据需要扩展
        agent_desc += f"   - 适用场景：{agent_detail.get('description', description)}\n"

        agent_descriptions.append(agent_desc)

    # 构建完整的 system_prompt
    system_prompt = """你是一个智能路由系统，负责分析用户的问题并决定使用哪些 Agent 来处理。

可用的 Agent：
"""
    system_prompt += "\n".join(agent_descriptions)

    # 检查是否启用 Router + Think 合并
    from utils import load_optimization_config
    opt_config = load_optimization_config()
    merge_config = opt_config.get("optimization", {}).get("router_think_merge", {})
    include_first_action = merge_config.get("enabled", False) and merge_config.get("include_first_action", True)

    if include_first_action:
        # 合并模式：同时输出路由决策和首次行动
        system_prompt += """
你的任务：
1. 分析用户的问题
2. 判断需要使用哪些 Agent
3. 如果需要多个 Agent，确定执行顺序
4. 为每个 Agent 提取具体的任务描述
5. 为第一个 Agent 规划首次行动（使用哪个工具、参数是什么）

返回格式（必须是有效的 JSON）：
{
  "agents": [
    {
      "name": "agent_name",
      "task": "具体任务描述"
    }
  ],
  "first_action": {
    "thought": "首次行动的思考过程",
    "tool": "工具名称（如 network.ping, mysql.execute_query）",
    "params": {
      "参数名": "参数值"
    }
  },
  "reasoning": "你的分析过程"
}

注意事项：
1. 如果问题只需要一个 Agent，agents 数组只包含一个元素
2. 如果问题需要多个 Agent 协作，按照执行顺序排列
3. 每个 Agent 的 task 应该清晰具体，包含必要的参数信息
4. 如果问题中提到了具体的数据（如域名、IP、表名），要在 task 中包含
5. first_action 是第一个 Agent 的首次工具调用，必须包含 thought、tool、params
6. 必须返回有效的 JSON 格式，不要包含其他文本
"""
    else:
        # 原有模式：只输出路由决策
        system_prompt += """
你的任务：
1. 分析用户的问题
2. 判断需要使用哪些 Agent
3. 如果需要多个 Agent，确定执行顺序
4. 为每个 Agent 提取具体的任务描述

返回格式（必须是有效的 JSON）：
{
  "agents": [
    {
      "name": "agent_name",
      "task": "具体任务描述"
    }
  ],
  "reasoning": "你的分析过程"
}

注意事项：
1. 如果问题只需要一个 Agent，agents 数组只包含一个元素
2. 如果问题需要多个 Agent 协作，按照执行顺序排列
3. 每个 Agent 的 task 应该清晰具体，包含必要的参数信息
4. 如果问题中提到了具体的数据（如域名、IP、表名），要在 task 中包含
5. 必须返回有效的 JSON 格式，不要包含其他文本
"""

    return system_prompt


def _llm_router(user_query: str) -> Optional[Dict[str, Any]]:
    """
    使用 LLM 进行路由决策

    Args:
        user_query: 用户问题

    Returns:
        包含 agent_plan 和 first_action 的字典
    """
    try:
        # 动态构建 system_prompt
        system_prompt = _build_dynamic_system_prompt()

        # 加载配置
        router_config = load_router_prompt_config()
        llm_router_config = router_config.get("llm_router", {})

        user_prompt_template = llm_router_config.get("user_prompt_template", "用户问题：{user_query}")
        llm_config = llm_router_config.get("llm_config", {})

        # 构建提示词
        user_prompt = user_prompt_template.format(user_query=user_query)
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        # 调用 LLM（使用配置管理器 + token 统计）
        from utils.llm_wrapper import invoke_llm_with_tracking

        config_manager = get_config_manager()
        llm = config_manager.get_llm("router")

        logger.info(f"Router: 调用 LLM 进行路由决策...")
        response = invoke_llm_with_tracking(llm, full_prompt, "router")

        # 从 AIMessage 对象中提取文本内容
        response_text = response.content if hasattr(response, 'content') else str(response)
        logger.info(f"Router: LLM 响应: {response_text[:200]}...")

        # 解析 LLM 响应
        result = _parse_llm_response(response_text)

        return result

    except Exception as e:
        logger.error(f"Router: LLM 路由失败: {e}")
        return None


def _parse_llm_response(response: str) -> Optional[Dict[str, Any]]:
    """
    解析 LLM 响应，提取 Agent 执行计划和首次行动

    Args:
        response: LLM 响应文本

    Returns:
        包含 agent_plan 和 first_action 的字典
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

        # 提取首次行动（如果有）
        first_action = data.get("first_action")
        if first_action:
            logger.info(f"Router: 解析出首次行动: {first_action.get('tool')}")

        return {
            "agent_plan": agent_plan,
            "first_action": first_action
        }

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
