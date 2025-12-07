"""
ReAct Think Node
思考节点：LLM 观察当前状态并决定下一步行动
"""
from typing import Dict, Any
from loguru import logger
from ..state import GraphState
from ..utils import smart_truncate, get_tool_type, extract_result_summary, compress_execution_history
from utils import get_config_manager, load_agent_config
import re
import json


def get_llm():
    """获取或创建 LLM 实例（使用配置管理器）"""
    config_manager = get_config_manager()
    return config_manager.get_llm("react_think")


def _get_agent_config(target_agent: str) -> Dict[str, Any]:
    """
    获取 Agent 配置

    Args:
        target_agent: 目标 Agent 名称（如 "network_agent", "database_agent"）

    Returns:
        Agent 配置字典，包含 system_prompt、tools_prefix 等
    """
    from utils import load_agent_mapping_config

    # 加载 Agent 映射配置
    mapping_config = load_agent_mapping_config()
    agents_mapping = mapping_config.get("agents", {})

    # 查找对应的 config_key
    config_key = None
    for agent_info in agents_mapping.values():
        if agent_info.get("full_name") == target_agent:
            config_key = agent_info.get("config_key")
            break

    if not config_key:
        logger.warning(f"未找到 Agent {target_agent} 的映射配置，使用默认配置")
        return {}

    # 加载 Agent 配置
    agent_config = load_agent_config()
    agents = agent_config.get("agents", {})

    return agents.get(config_key, {})


def build_think_prompt(state: GraphState, available_tools: list) -> str:
    """
    构建思考 Prompt

    Args:
        state: 当前状态
        available_tools: 可用工具列表

    Returns:
        Prompt 字符串
    """
    # 获取当前 Agent 的配置
    target_agent = state.get("target_agent", "network_agent")
    agent_config = _get_agent_config(target_agent)

    # 获取 system_prompt（如果没有配置，使用默认值）
    system_prompt = agent_config.get("system_prompt", "你是一个有用的AI助手。请分析用户问题并决定下一步行动。")

    # 获取当前任务描述
    # 注意：switch_agent_node 会将前一个 Agent 的输出拼接到 state["user_query"] 中
    # 所以后续 Agent 应该直接使用 state["user_query"]，而不是从 agent_plan 取原始任务描述
    user_query = state['user_query']
    agent_plan = state.get("agent_plan")
    current_agent_index = state.get("current_agent_index", 0)

    if agent_plan and current_agent_index < len(agent_plan):
        if current_agent_index == 0:
            # 第一个 Agent：使用 agent_plan 中的任务描述
            task_desc = agent_plan[current_agent_index].get("task", user_query)
            user_query = task_desc
        # else: 后续 Agent 直接使用 state["user_query"]（已经被 switch_agent_node 增强过，包含前面 Agent 的输出）

    # 工具列表
    tools_desc = "\n".join([
        f"- {tool['name']}: {tool['description']}"
        for tool in available_tools
    ])

    # 执行历史 - 使用压缩历史，减少 token 消耗
    history_desc = ""
    if state.get("execution_history"):
        history_desc = compress_execution_history(state["execution_history"])

    # 上一步观察
    last_obs = state.get("last_observation", "")
    last_obs_desc = f"\n\n上一步观察结果:\n{last_obs}\n" if last_obs else ""

    # 检查是否启用批量规划
    from utils import load_optimization_config
    opt_config = load_optimization_config()
    batch_config = opt_config.get("optimization", {}).get("batch_planning", {})
    batch_enabled = batch_config.get("enabled", False)
    max_batch_size = batch_config.get("max_batch_size", 5)

    # 构建完整 prompt
    if batch_enabled:
        # 批量规划模式
        prompt = f"""{system_prompt}

用户问题: {user_query}

可用工具:
{tools_desc}
{history_desc}{last_obs_desc}

请按照以下格式输出（支持批量规划多个工具）:

THOUGHT: [你的思考过程，分析当前情况和需要做什么]
ACTION: [TOOL 或 FINISH]

如果 ACTION 是 TOOL，可以规划多个工具（最多 {max_batch_size} 个）:
TOOL_1: [第一个工具名称]
PARAMS_1: [第一个工具的 JSON 参数]
TOOL_2: [第二个工具名称（可选）]
PARAMS_2: [第二个工具的 JSON 参数（可选）]
...

或者只规划一个工具:
TOOL: [工具名称]
PARAMS: [JSON 参数]

重要提示:
1. 如果需要使用前面步骤的结果（如 IP 地址），请从"上一步观察结果"中提取
2. 只有相互独立的工具才能批量规划，有依赖关系的工具需要分步执行
3. 如果任务已完成，ACTION 设为 FINISH
4. PARAMS 必须是有效的 JSON 格式

现在请开始分析并输出你的决策:"""
    else:
        # 单工具模式（默认）
        prompt = f"""{system_prompt}

用户问题: {user_query}

可用工具:
{tools_desc}
{history_desc}{last_obs_desc}

请按照以下格式输出:

THOUGHT: [你的思考过程，分析当前情况和需要做什么]
ACTION: [TOOL 或 FINISH]
TOOL: [如果 ACTION 是 TOOL，写工具名称，如 network.ping]
PARAMS: [如果 ACTION 是 TOOL，写 JSON 格式的参数，如 {{"target": "baidu.com", "count": 4}}]

重要提示:
1. 如果需要使用前面步骤的结果（如 IP 地址），请从"上一步观察结果"中提取
2. 例如：如果上一步查询到 IP 是 109.244.5.94，下一步 mtr 应该使用这个 IP，而不是域名
3. 如果任务已完成，ACTION 设为 FINISH
4. 每次只执行一个工具
5. PARAMS 必须是有效的 JSON 格式

现在请开始分析并输出你的决策:"""

    return prompt


def parse_llm_output(output: str, tools_prefix: str = None) -> Dict[str, Any]:
    """
    解析 LLM 输出

    支持两种格式：
    1. 纯文本格式：THOUGHT: ... ACTION: ... TOOL: ... PARAMS: ...
    2. JSON 格式：{"THOUGHT": "...", "ACTION": "...", "TOOL": "...", "PARAMS": {...}}

    Args:
        output: LLM 输出字符串
        tools_prefix: 工具前缀（如 "network"、"mysql"），用于自动补全工具名称

    Returns:
        解析后的字典
    """
    # 默认值设为 UNKNOWN，最后再决定是否返回 FINISH
    result = {
        "thought": "",
        "action_type": "UNKNOWN",  # 先标记为未知，避免误判为 FINISH
        "tool_name": None,
        "params": {}
    }

    # 记录是否成功解析到有效的 ACTION
    action_parsed = False

    # 尝试解析 JSON 格式（多种方式）
    # 方式 1: ```json { ... } ```
    json_match = re.search(r'```json\s*(\{.+?\})\s*```', output, re.DOTALL | re.IGNORECASE)
    # 方式 2: ``` { ... } ``` (没有 json 标记)
    if not json_match:
        json_match = re.search(r'```\s*(\{.+?\})\s*```', output, re.DOTALL)
    # 方式 3: 直接的 JSON 对象
    if not json_match:
        json_match = re.search(r'(\{[^{}]*"(?:ACTION|THOUGHT|TOOL)"[^{}]*\})', output, re.DOTALL | re.IGNORECASE)

    if json_match:
        try:
            json_data = json.loads(json_match.group(1))
            result["thought"] = json_data.get("THOUGHT", json_data.get("thought", ""))
            action = json_data.get("ACTION", json_data.get("action", ""))

            if action:
                action_parsed = True
                if action.upper() == "FINISH":
                    result["action_type"] = "FINISH"
                elif action.upper() == "TOOL":
                    result["action_type"] = "TOOL"
                    result["tool_name"] = json_data.get("TOOL", json_data.get("tool"))
                    result["params"] = json_data.get("PARAMS", json_data.get("params", {}))
                else:
                    # 直接写了工具名
                    result["action_type"] = "TOOL"
                    result["tool_name"] = action
                    result["params"] = json_data.get("PARAMS", json_data.get("params", {}))

                # 自动补全工具名称前缀
                if result["tool_name"] and tools_prefix:
                    result["tool_name"] = _ensure_tool_prefix(result["tool_name"], tools_prefix)

                logger.debug(f"JSON 解析成功: action_type={result['action_type']}, tool={result['tool_name']}")
                return result

        except json.JSONDecodeError as e:
            logger.warning(f"解析 JSON 格式失败: {e}, 继续尝试纯文本格式")

    # 纯文本格式解析
    # 提取 THOUGHT（支持多种分隔符）
    thought_patterns = [
        r'THOUGHT:\s*(.+?)(?=\nACTION:|\nTOOL:|\n\n|$)',
        r'"THOUGHT":\s*"([^"]+)"',
        r'思考[:：]\s*(.+?)(?=\n行动[:：]|\n工具[:：]|\n\n|$)',
    ]
    for pattern in thought_patterns:
        thought_match = re.search(pattern, output, re.DOTALL | re.IGNORECASE)
        if thought_match:
            result["thought"] = thought_match.group(1).strip()
            break

    # 提取 ACTION（支持多种格式）
    action_patterns = [
        r'ACTION:\s*(TOOL|FINISH|[a-zA-Z_][a-zA-Z0-9_.]*)',
        r'"ACTION":\s*"?(TOOL|FINISH|[a-zA-Z_][a-zA-Z0-9_.]*)"?',
        r'行动[:：]\s*(工具|完成|TOOL|FINISH)',
    ]
    for pattern in action_patterns:
        action_match = re.search(pattern, output, re.IGNORECASE)
        if action_match:
            action_value = action_match.group(1).strip()
            action_parsed = True
            if action_value.upper() in ["FINISH", "完成"]:
                result["action_type"] = "FINISH"
            elif action_value.upper() in ["TOOL", "工具"]:
                result["action_type"] = "TOOL"
            else:
                # 直接写了工具名，如 ACTION: mysql.list_tables
                result["action_type"] = "TOOL"
                result["tool_name"] = action_value
            break

    # 如果 ACTION 是 TOOL 或未解析到 ACTION，尝试提取工具名和参数
    if result["action_type"] == "TOOL" or not action_parsed:
        # 如果还没有提取到工具名，从 TOOL: 行提取
        if not result["tool_name"]:
            tool_patterns = [
                r'TOOL:\s*([a-zA-Z_][a-zA-Z0-9_.]*)',
                r'"TOOL":\s*"?([a-zA-Z_][a-zA-Z0-9_.]*)"?',
                r'工具[:：]\s*([a-zA-Z_][a-zA-Z0-9_.]*)',
            ]
            for pattern in tool_patterns:
                tool_match = re.search(pattern, output, re.IGNORECASE)
                if tool_match:
                    result["tool_name"] = tool_match.group(1).strip()
                    # 如果找到了工具名，说明 ACTION 应该是 TOOL
                    result["action_type"] = "TOOL"
                    action_parsed = True
                    break

        # 提取 PARAMS（支持多种格式）
        params_patterns = [
            r'PARAMS:\s*(\{.+?\})(?=\n[A-Z]|\n\n|$)',
            r'"PARAMS":\s*(\{.+?\})',
            r'参数[:：]\s*(\{.+?\})',
        ]
        for pattern in params_patterns:
            params_match = re.search(pattern, output, re.DOTALL | re.IGNORECASE)
            if params_match:
                try:
                    result["params"] = json.loads(params_match.group(1))
                    break
                except json.JSONDecodeError as e:
                    logger.warning(f"解析参数 JSON 失败: {e}")

        # 自动补全工具名称前缀
        if result["tool_name"] and tools_prefix:
            result["tool_name"] = _ensure_tool_prefix(result["tool_name"], tools_prefix)

    # 最终决策：如果没有成功解析到有效的 ACTION
    if not action_parsed or result["action_type"] == "UNKNOWN":
        # 检查是否输出中明确包含 FINISH 相关内容
        if re.search(r'\b(FINISH|完成任务|任务完成)\b', output, re.IGNORECASE):
            result["action_type"] = "FINISH"
            logger.warning(f"未能解析到明确的 ACTION，但检测到 FINISH 关键词，标记为 FINISH")
        else:
            # 关键修复：如果解析失败且没有明确的 FINISH 信号，保持为 UNKNOWN
            # 这将在调用方触发重试或错误处理，而不是错误地终止任务
            logger.warning(f"解析 LLM 输出失败，未能识别有效的 ACTION。原始输出前 500 字符: {output[:500]}")
            # 为了向后兼容，如果找到了工具名则认为是 TOOL 调用
            if result["tool_name"]:
                result["action_type"] = "TOOL"
                logger.info(f"检测到工具名 {result['tool_name']}，推断 ACTION 为 TOOL")
            else:
                # 最后的兜底：默认为 FINISH，但记录详细警告
                result["action_type"] = "FINISH"
                logger.warning(f"无法解析 ACTION 且无工具名，默认为 FINISH。请检查 LLM 输出格式。")

    # 尝试解析批量工具（TOOL_1, PARAMS_1, TOOL_2, PARAMS_2, ...）
    batch_tools = []
    for i in range(1, 10):  # 最多支持 9 个批量工具
        tool_pattern = rf'TOOL_{i}:\s*([a-zA-Z_][a-zA-Z0-9_.]*)'
        params_pattern = rf'PARAMS_{i}:\s*(\{{.+?\}})(?=\n[A-Z]|\nTOOL_|\n\n|$)'

        tool_match = re.search(tool_pattern, output, re.IGNORECASE)
        if tool_match:
            tool_name = tool_match.group(1).strip()
            params = {}

            params_match = re.search(params_pattern, output, re.DOTALL | re.IGNORECASE)
            if params_match:
                try:
                    params = json.loads(params_match.group(1))
                except json.JSONDecodeError:
                    pass

            # 自动补全工具名称前缀
            if tools_prefix:
                tool_name = _ensure_tool_prefix(tool_name, tools_prefix)

            batch_tools.append({
                "tool_name": tool_name,
                "params": params
            })
        else:
            break

    # 如果解析到批量工具，存储到结果中
    if batch_tools:
        result["action_type"] = "TOOL"
        result["tool_name"] = batch_tools[0]["tool_name"]
        result["params"] = batch_tools[0]["params"]
        result["batch_tools"] = batch_tools  # 存储所有批量工具
        logger.info(f"解析到 {len(batch_tools)} 个批量工具: {[t['tool_name'] for t in batch_tools]}")

    logger.debug(f"最终解析结果: action_type={result['action_type']}, tool={result['tool_name']}, params={result['params']}")
    return result


def _ensure_tool_prefix(tool_name: str, tools_prefix: str) -> str:
    """
    确保工具名称包含前缀

    如果工具名称已经包含前缀（如 "mysql.list_tables"），则不做修改
    如果工具名称没有前缀（如 "list_tables"），则自动添加前缀（变成 "mysql.list_tables"）

    Args:
        tool_name: 工具名称
        tools_prefix: 工具前缀（如 "network"、"mysql"）

    Returns:
        包含前缀的工具名称
    """
    if not tool_name or not tools_prefix:
        return tool_name

    # 如果工具名称已经包含前缀，直接返回
    if tool_name.startswith(tools_prefix + "."):
        return tool_name

    # 如果工具名称包含其他前缀（如 "network.ping"），也直接返回
    if "." in tool_name:
        return tool_name

    # 否则，自动添加前缀
    full_tool_name = f"{tools_prefix}.{tool_name}"
    logger.info(f"自动补全工具名称: {tool_name} -> {full_tool_name}")
    return full_tool_name


async def react_think_node(state: GraphState) -> GraphState:
    """
    ReAct 思考节点

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    state["current_node"] = "react_think"

    try:
        # 检查是否跳过首次 Think（Router + Think 合并优化）
        metadata = state.get("metadata", {})
        if metadata.get("skip_first_think") and state.get("next_action"):
            logger.info("ReAct Think: 跳过首次 Think（使用 Router 的首次行动决策）")
            # 清除标记，下次不再跳过
            state["metadata"]["skip_first_think"] = False
            return state

        # 检查工具队列（批量规划优化）
        tool_queue = state.get("tool_queue", [])
        if tool_queue:
            # 从队列中取出下一个工具
            next_tool = tool_queue.pop(0)
            state["tool_queue"] = tool_queue
            state["next_action"] = {
                "action_type": "TOOL",
                "tool_name": next_tool["tool_name"],
                "params": next_tool.get("params", {}),
                "thought": f"批量规划: 执行队列中的工具 {next_tool['tool_name']}"
            }
            logger.info(f"ReAct Think: 使用队列中的工具 {next_tool['tool_name']}（剩余 {len(tool_queue)} 个）")
            return state

        # 检查是否达到最大迭代次数
        if state["current_step"] >= state["max_iterations"]:
            logger.warning(f"达到最大迭代次数: {state['max_iterations']}")
            state["is_finished"] = True
            state["next_action"] = {
                "action_type": "FINISH",
                "tool_name": None,
                "params": {}
            }
            return state

        # 获取可用工具列表
        from mcp_manager import McpClientManager
        from utils import load_tools_config

        tools_config = load_tools_config()

        # 根据 target_agent 决定使用哪些工具
        target_agent = state.get("target_agent", "network_agent")
        agent_config = _get_agent_config(target_agent)

        # 从 agent_config 获取 tools_prefix
        tools_prefix = agent_config.get("tools_prefix", "network")

        available_tools = []
        prefix_tools = tools_config.get("tools", {}).get(tools_prefix, {})
        for tool_key, tool_config in prefix_tools.items():
            available_tools.append({
                "name": tool_config["name"],
                "description": tool_config["description"]
            })

        # 构建 Prompt
        prompt = build_think_prompt(state, available_tools)

        # 调用 LLM（使用 token 统计）
        from utils.llm_wrapper import invoke_llm_with_tracking

        logger.info(f"ReAct Think - 步骤 {state['current_step']}")
        llm = get_llm()
        llm_output = invoke_llm_with_tracking(llm, prompt, "react_think")

        # 从 AIMessage 对象中提取文本内容
        llm_output_text = llm_output.content if hasattr(llm_output, 'content') else str(llm_output)
        logger.info(f"LLM 输出:\n{llm_output_text[:500]}...")

        # 解析 LLM 输出（传递 tools_prefix 用于自动补全工具名称）
        parsed = parse_llm_output(llm_output_text, tools_prefix=tools_prefix)

        logger.info(f"解析结果: action_type={parsed['action_type']}, tool={parsed.get('tool_name')}")

        # 结果质量验证
        from utils import load_optimization_config
        opt_config = load_optimization_config()
        validation_config = opt_config.get("optimization", {}).get("result_validation", {})

        if validation_config.get("enabled", False):
            from ..utils.result_validator import validate_think_output

            # 获取可用工具名称列表
            available_tool_names = [t["name"] for t in available_tools]

            is_valid, errors = validate_think_output(parsed, available_tool_names)

            if not is_valid:
                logger.warning(f"ReAct Think 输出验证失败: {errors}")
                # 如果是幻觉（工具不存在），尝试修正
                if any("不存在" in e for e in errors):
                    logger.warning("检测到工具幻觉，标记为 FINISH")
                    parsed["action_type"] = "FINISH"
                    parsed["thought"] = f"工具验证失败: {errors}"

        # 保存决策
        state["next_action"] = {
            "action_type": parsed["action_type"],
            "tool_name": parsed.get("tool_name"),
            "params": parsed.get("params", {}),
            "thought": parsed.get("thought", "")
        }

        # 如果有批量工具，存储到工具队列中
        batch_tools = parsed.get("batch_tools", [])
        if batch_tools and len(batch_tools) > 1:
            # 第一个工具已经在 next_action 中，剩余的存入队列
            state["tool_queue"] = batch_tools[1:]
            logger.info(f"批量规划: 当前执行 {batch_tools[0]['tool_name']}，队列中还有 {len(batch_tools) - 1} 个工具")

        # 如果决定 FINISH，标记为完成
        if parsed["action_type"] == "FINISH":
            state["is_finished"] = True
            logger.info("LLM 决定完成任务")

    except Exception as e:
        error_msg = f"ReAct Think 失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        state["errors"].append(error_msg)
        state["is_finished"] = True
        state["next_action"] = {
            "action_type": "FINISH",
            "tool_name": None,
            "params": {}
        }

    return state

