"""
ReAct Think Node
思考节点：LLM 观察当前状态并决定下一步行动
"""
from typing import Dict, Any, Union
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


def _extract_text_content(llm_output) -> str:
    """
    从 LLM 响应中提取文本内容
    
    兼容不同 LLM provider 的响应格式：
    - DeepSeek/OpenAI/Ollama: content 是 str
    - Gemini: content 可能是 list（多模态响应格式）
    
    Args:
        llm_output: LLM 响应对象（AIMessage）
        
    Returns:
        提取的文本字符串
    """
    if not hasattr(llm_output, 'content'):
        return str(llm_output)
    
    content = llm_output.content
    
    # 如果是字符串，直接返回（DeepSeek/OpenAI/Ollama）
    if isinstance(content, str):
        return content
    
    # 如果是 list，提取所有文本部分（Gemini 多模态格式）
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict):
                # Gemini 格式: {"type": "text", "text": "..."}
                if 'text' in part:
                    text_parts.append(part['text'])
                elif 'content' in part:
                    text_parts.append(part['content'])
        return '\n'.join(text_parts)
    
    # 其他情况，转为字符串
    return str(content)


def _extract_json_object(text: str) -> str:
    """
    从文本中提取完整的 JSON 对象（支持嵌套大括号）
    
    Args:
        text: 以 { 开头的文本
        
    Returns:
        完整的 JSON 字符串，如果无法提取则返回 None
    """
    text = text.strip()
    if not text.startswith('{'):
        return None
    
    depth = 0
    in_string = False
    escape_next = False
    
    for i, char in enumerate(text):
        if escape_next:
            escape_next = False
            continue
            
        if char == '\\' and in_string:
            escape_next = True
            continue
            
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
            
        if in_string:
            continue
            
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return text[:i+1]
    
    return None


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

    # 查找对应的 config_key 和 tools_prefix
    config_key = None
    tools_prefix = None
    for agent_info in agents_mapping.values():
        if agent_info.get("full_name") == target_agent:
            config_key = agent_info.get("config_key")
            tools_prefix = agent_info.get("tools_prefix")
            break

    if not config_key:
        logger.warning(f"未找到 Agent {target_agent} 的映射配置，使用默认配置")
        return {}

    # 加载 Agent 配置
    agent_config = load_agent_config()
    agents = agent_config.get("agents", {})

    result = agents.get(config_key, {})
    
    # 优先使用 agent_mapping.yaml 中的 tools_prefix
    if tools_prefix:
        result["tools_prefix"] = tools_prefix
    
    return result


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
    user_query = state['user_query']
    agent_plan = state.get("agent_plan")
    current_agent_index = state.get("current_agent_index", 0)

    if agent_plan and current_agent_index < len(agent_plan):
        if current_agent_index == 0:
            task_desc = agent_plan[current_agent_index].get("task", user_query)
            user_query = task_desc

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

请分析当前情况，决定下一步行动。

输出格式要求：
THOUGHT: [你的思考过程]
ACTION: [TOOL 或 FINISH]

如果 ACTION 是 TOOL，可以规划多个独立工具（最多 {max_batch_size} 个）:
TOOL_1: [工具名称]
PARAMS_1: [JSON 参数]
TOOL_2: [工具名称（可选）]
PARAMS_2: [JSON 参数（可选）]

或者只规划一个工具:
TOOL: [工具名称]
PARAMS: [JSON 参数]

注意：
1. 只有当所有任务都完成时才能 ACTION: FINISH
2. 只有相互独立的工具才能批量规划
3. PARAMS 必须是有效的 JSON 格式"""
    else:
        # 单工具模式（默认）
        prompt = f"""{system_prompt}

用户问题: {user_query}

可用工具:
{tools_desc}
{history_desc}{last_obs_desc}

请分析当前情况，决定下一步行动。

输出格式：
THOUGHT: [你的思考过程]
ACTION: [TOOL 或 FINISH]
TOOL: [如果 ACTION 是 TOOL，写工具名称]
PARAMS: [如果 ACTION 是 TOOL，写 JSON 格式的参数]

注意：只有当所有任务都完成时才能 ACTION: FINISH"""

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
    result = {
        "thought": "",
        "action_type": "FINISH",
        "tool_name": None,
        "params": {}
    }

    # 尝试解析 JSON 格式
    json_match = re.search(r'```json\s*(\{.+?\})\s*```', output, re.DOTALL | re.IGNORECASE)
    if not json_match:
        json_match = re.search(r'```\s*(\{.+?\})\s*```', output, re.DOTALL)
    if not json_match:
        json_match = re.search(r'(\{[^{}]*"(?:ACTION|THOUGHT|TOOL)"[^{}]*\})', output, re.DOTALL | re.IGNORECASE)

    if json_match:
        try:
            json_data = json.loads(json_match.group(1))
            result["thought"] = json_data.get("THOUGHT", json_data.get("thought", ""))
            action = json_data.get("ACTION", json_data.get("action", ""))

            if action:
                if action.upper() == "FINISH":
                    result["action_type"] = "FINISH"
                elif action.upper() == "TOOL":
                    result["action_type"] = "TOOL"
                    result["tool_name"] = json_data.get("TOOL", json_data.get("tool"))
                    result["params"] = json_data.get("PARAMS", json_data.get("params", {}))
                else:
                    result["action_type"] = "TOOL"
                    result["tool_name"] = action
                    result["params"] = json_data.get("PARAMS", json_data.get("params", {}))

                if result["tool_name"] and tools_prefix:
                    result["tool_name"] = _ensure_tool_prefix(result["tool_name"], tools_prefix)

                return result

        except json.JSONDecodeError as e:
            logger.warning(f"解析 JSON 格式失败: {e}, 继续尝试纯文本格式")

    # 纯文本格式解析
    # 提取 THOUGHT
    thought_match = re.search(r'THOUGHT:\s*(.+?)(?=\nACTION:|\nTOOL:|\n\n|$)', output, re.DOTALL | re.IGNORECASE)
    if thought_match:
        result["thought"] = thought_match.group(1).strip()

    # 提取 ACTION
    action_match = re.search(r'ACTION:\s*(TOOL|FINISH|[a-zA-Z_][a-zA-Z0-9_.]*)', output, re.IGNORECASE)
    if action_match:
        action_value = action_match.group(1).strip()
        if action_value.upper() == "FINISH":
            result["action_type"] = "FINISH"
        elif action_value.upper() == "TOOL":
            result["action_type"] = "TOOL"
        else:
            result["action_type"] = "TOOL"
            result["tool_name"] = action_value
            # 修正工具前缀
            if tools_prefix:
                result["tool_name"] = _ensure_tool_prefix(result["tool_name"], tools_prefix)

    # 提取 TOOL
    if result["action_type"] == "TOOL" and not result["tool_name"]:
        tool_match = re.search(r'TOOL:\s*([a-zA-Z_][a-zA-Z0-9_.]*)', output, re.IGNORECASE)
        if tool_match:
            result["tool_name"] = tool_match.group(1).strip()
            # 修正工具前缀
            if tools_prefix:
                result["tool_name"] = _ensure_tool_prefix(result["tool_name"], tools_prefix)

    # 提取 PARAMS
    if result["action_type"] == "TOOL":
        params_start_match = re.search(r'PARAMS:\s*', output, re.IGNORECASE)
        if params_start_match:
            start_pos = params_start_match.end()
            params_text = _extract_json_object(output[start_pos:])
            if params_text:
                try:
                    result["params"] = json.loads(params_text)
                except json.JSONDecodeError as e:
                    logger.warning(f"解析参数 JSON 失败: {e}")

        if result["tool_name"] and tools_prefix:
            result["tool_name"] = _ensure_tool_prefix(result["tool_name"], tools_prefix)

    # 尝试解析批量工具
    batch_tools = []
    for i in range(1, 10):
        tool_match = re.search(rf'TOOL_{i}:\s*([a-zA-Z_][a-zA-Z0-9_.]*)', output, re.IGNORECASE)
        if tool_match:
            tool_name = tool_match.group(1).strip()
            params = {}

            params_start_match = re.search(rf'PARAMS_{i}:\s*', output, re.IGNORECASE)
            if params_start_match:
                start_pos = params_start_match.end()
                params_text = _extract_json_object(output[start_pos:])
                if params_text:
                    try:
                        params = json.loads(params_text)
                    except json.JSONDecodeError:
                        pass

            if tools_prefix:
                tool_name = _ensure_tool_prefix(tool_name, tools_prefix)

            batch_tools.append({
                "tool_name": tool_name,
                "params": params
            })
        else:
            break

    if batch_tools:
        result["action_type"] = "TOOL"
        result["tool_name"] = batch_tools[0]["tool_name"]
        result["params"] = batch_tools[0]["params"]
        result["batch_tools"] = batch_tools
        logger.info(f"解析到 {len(batch_tools)} 个批量工具: {[t['tool_name'] for t in batch_tools]}")

    return result


def _ensure_tool_prefix(tool_name: str, tools_prefix: str) -> str:
    """确保工具名称包含正确的前缀"""
    if not tool_name or not tools_prefix:
        return tool_name

    # 如果已经是正确的前缀，直接返回
    if tool_name.startswith(tools_prefix + "."):
        return tool_name

    # 如果包含其他前缀（如 network.xxx），需要替换为正确的前缀
    if "." in tool_name:
        # 提取工具名（去掉错误的前缀）
        actual_tool_name = tool_name.split(".", 1)[1]
        full_tool_name = f"{tools_prefix}.{actual_tool_name}"
        logger.info(f"修正工具前缀: {tool_name} -> {full_tool_name}")
        return full_tool_name

    # 没有前缀，添加前缀
    full_tool_name = f"{tools_prefix}.{tool_name}"
    logger.info(f"自动补全工具名称: {tool_name} -> {full_tool_name}")
    return full_tool_name


async def react_think_node(state: GraphState) -> GraphState:
    """
    ReAct 思考节点
    """
    state["current_node"] = "react_think"

    try:
        # 检查是否跳过首次 Think
        metadata = state.get("metadata", {})
        if metadata.get("skip_first_think") and state.get("next_action"):
            logger.info("ReAct Think: 跳过首次 Think（使用 Router 的首次行动决策）")
            state["metadata"]["skip_first_think"] = False
            return state

        # 检查工具队列（批量规划优化）
        tool_queue = state.get("tool_queue", [])
        if tool_queue:
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
        from utils import load_tools_config

        tools_config = load_tools_config()
        target_agent = state.get("target_agent", "network_agent")
        agent_config = _get_agent_config(target_agent)
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

        # 调用 LLM
        from utils.llm_wrapper import invoke_llm_with_tracking

        logger.info(f"ReAct Think - 步骤 {state['current_step']}")
        llm = get_llm()
        llm_output = invoke_llm_with_tracking(llm, prompt, "react_think")

        llm_output_text = _extract_text_content(llm_output)
        logger.info(f"LLM 输出:\n{llm_output_text[:500]}...")

        # 解析 LLM 输出
        parsed = parse_llm_output(llm_output_text, tools_prefix=tools_prefix)
        logger.info(f"解析结果: action_type={parsed['action_type']}, tool={parsed.get('tool_name')}")

        # 结果质量验证
        from utils import load_optimization_config
        opt_config = load_optimization_config()
        validation_config = opt_config.get("optimization", {}).get("result_validation", {})

        if validation_config.get("enabled", False):
            from ..utils.result_validator import validate_think_output
            available_tool_names = [t["name"] for t in available_tools]
            is_valid, errors = validate_think_output(parsed, available_tool_names)

            if not is_valid:
                logger.warning(f"ReAct Think 输出验证失败: {errors}")
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
