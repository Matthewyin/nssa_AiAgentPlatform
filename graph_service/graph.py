"""
LangGraph图定义
构建完整的工作流
"""
from typing import List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from loguru import logger

from .state import GraphState
from .nodes import (
    user_input_node,
    router_node,
    network_agent_node,
    database_agent_node,
    final_answer_node
)
from .nodes.react_think import react_think_node
from .nodes.react_act import react_act_node
from .nodes.react_observe import react_observe_node
from utils import load_langgraph_config


def _extract_agent_output(execution_history: List[Dict[str, Any]]) -> Optional[str]:
    """
    从 execution_history 中提取 Agent 的输出

    策略：提取最后一个成功的工具调用结果

    Args:
        execution_history: 执行历史记录

    Returns:
        Agent 的输出摘要，如果没有工具调用则返回 None
    """
    if not execution_history:
        return None

    # 从后往前查找最后一个成功的工具调用
    for step in reversed(execution_history):
        action_dict = step.get("action", {})
        action_type = action_dict.get("type")
        tool_name = action_dict.get("tool")
        observation = step.get("observation", "")

        # 只保留 TOOL 类型的操作，且有 observation
        if action_type == "TOOL" and tool_name and observation:
            # 排除错误信息
            if any(keyword in observation for keyword in ["失败", "错误", "Error", "error", "Failed", "failed"]):
                continue

            # 找到了最后一个成功的工具调用，返回结果
            # 限制长度
            if len(observation) > 500:
                observation = observation[:500] + "..."

            return f"工具 {tool_name} 的执行结果：\n{observation}"

    return None


def _build_agent_routing_map() -> Dict[str, str]:
    """
    从配置文件构建 Agent 路由映射

    Returns:
        Agent 名称到节点名称的映射字典
        例如：{"network_agent": "network_agent", "database_agent": "database_agent"}
    """
    from utils import load_agent_mapping_config

    mapping_config = load_agent_mapping_config()
    agents = mapping_config.get("agents", {})

    # 构建路由映射
    routing_map = {}

    for agent_info in agents.values():
        full_name = agent_info.get("full_name")
        # 节点名称 = Agent 完整名称
        routing_map[full_name] = full_name

    # 添加特殊路由
    routing_map["skip"] = "final_answer"  # 跳过 Agent，直接返回

    return routing_map


def create_graph() -> StateGraph:
    """
    创建LangGraph工作流图

    Returns:
        StateGraph实例
    """
    # 创建图
    workflow = StateGraph(GraphState)

    # 添加节点
    workflow.add_node("user_input", user_input_node)
    workflow.add_node("router", router_node)
    workflow.add_node("network_agent", network_agent_node)
    workflow.add_node("database_agent", database_agent_node)
    workflow.add_node("final_answer", final_answer_node)

    # 设置入口点
    workflow.set_entry_point("user_input")

    # 添加边
    # user_input -> router
    workflow.add_edge("user_input", "router")

    # router -> agent (根据target_agent条件路由)
    def route_to_agent(state: GraphState) -> str:
        """根据target_agent路由到对应节点"""
        from utils import load_agent_mapping_config

        mapping_config = load_agent_mapping_config()
        default_agent = mapping_config.get("default_agent", "network_agent")

        target = state.get("target_agent", default_agent)
        logger.info(f"路由到: {target}")
        return target

    # 从配置文件构建路由映射
    routing_map = _build_agent_routing_map()

    workflow.add_conditional_edges(
        "router",
        route_to_agent,
        routing_map
    )

    # 所有 Agent -> final_answer
    workflow.add_edge("network_agent", "final_answer")
    workflow.add_edge("database_agent", "final_answer")

    # final_answer -> END
    workflow.add_edge("final_answer", END)

    logger.info("LangGraph工作流图创建完成")
    logger.info(f"Agent 路由映射: {routing_map}")

    return workflow


def create_react_graph() -> StateGraph:
    """
    创建 ReAct 循环模式的工作流图

    Returns:
        StateGraph实例
    """
    # 创建图
    workflow = StateGraph(GraphState)

    # 添加节点
    workflow.add_node("user_input", user_input_node)
    workflow.add_node("router", router_node)
    workflow.add_node("react_think", react_think_node)
    workflow.add_node("react_act", react_act_node)
    workflow.add_node("react_observe", react_observe_node)
    workflow.add_node("final_answer", final_answer_node)

    # 设置入口点
    workflow.set_entry_point("user_input")

    # 添加边
    # user_input -> router
    workflow.add_edge("user_input", "router")

    # router -> react_think 或 skip
    def route_to_agent(state: GraphState) -> str:
        """根据target_agent路由到对应节点"""
        from utils import load_agent_mapping_config

        target = state.get("target_agent", "react_think")
        logger.info(f"路由到: {target}")

        # 从配置文件获取所有已注册的 Agent
        mapping_config = load_agent_mapping_config()
        registered_agents = set()
        for agent_info in mapping_config.get("agents", {}).values():
            full_name = agent_info.get("full_name")
            if full_name:
                registered_agents.add(full_name)

        # 所有已注册的 Agent 都使用 ReAct 模式
        if target in registered_agents:
            return "react_think"

        # 兜底：如果是未知的 agent 名称，也使用 react_think
        if target.endswith("_agent"):
            logger.warning(f"未知的 Agent '{target}'，使用 react_think 模式")
            return "react_think"

        return target

    workflow.add_conditional_edges(
        "router",
        route_to_agent,
        {
            "react_think": "react_think",
            "skip": "final_answer",
        }
    )

    # react_think -> react_act
    workflow.add_edge("react_think", "react_act")

    # react_act -> react_observe
    workflow.add_edge("react_act", "react_observe")

    # Agent 切换节点
    def switch_agent_node(state: GraphState) -> GraphState:
        """切换到下一个 Agent"""
        agent_plan = state.get("agent_plan")
        current_agent_index = state.get("current_agent_index", 0)
        execution_history = state.get("execution_history", [])

        # 提取当前 Agent 的输出（从 execution_history）
        agent_output = _extract_agent_output(execution_history)

        # 标记当前 Agent 为已完成，并存储输出
        if agent_plan and len(agent_plan) > current_agent_index:
            agent_plan[current_agent_index]["status"] = "completed"
            agent_plan[current_agent_index]["output"] = agent_output
            logger.info(f"Agent {agent_plan[current_agent_index]['name']} 输出: {agent_output[:100] if agent_output else 'None'}...")

        # 切换到下一个 Agent
        next_index = current_agent_index + 1
        state["current_agent_index"] = next_index
        state["target_agent"] = agent_plan[next_index]["name"]

        # 将前面 Agent 的输出添加到 user_query 中，传递给下一个 Agent
        if agent_output:
            next_task = agent_plan[next_index]["task"]
            # 格式化：在任务描述后添加前面 Agent 的输出
            enhanced_query = f"{next_task}\n\n前面的 Agent 已完成任务，结果如下：\n{agent_output}"
            state["user_query"] = enhanced_query
            logger.info(f"将前面 Agent 的输出传递给 {agent_plan[next_index]['name']}")
        else:
            # 如果没有输出，使用原始任务描述
            state["user_query"] = agent_plan[next_index]["task"]

        # 重置 ReAct 状态（关键：重置 execution_history）
        state["is_finished"] = False
        state["current_step"] = 1
        state["last_observation"] = ""
        state["next_action"] = None
        state["execution_history"] = []  # 重置执行历史，避免下一个 Agent 继承前面 Agent 的历史
        state["tool_queue"] = []  # 重置工具队列，避免下一个 Agent 继承前面 Agent 的队列

        logger.info(f"切换到下一个 Agent: {agent_plan[next_index]['name']} ({next_index + 1}/{len(agent_plan)})")
        return state

    # react_observe -> react_think 或 final_answer 或 switch_agent（循环判断）
    def should_continue(state: GraphState) -> str:
        """判断是否继续循环或切换到下一个 Agent"""
        is_finished = state.get("is_finished", False)
        agent_plan = state.get("agent_plan")
        current_agent_index = state.get("current_agent_index", 0)

        if is_finished:
            # 当前 Agent 完成任务
            if agent_plan and len(agent_plan) > 0:
                # 检查是否还有下一个 Agent
                next_index = current_agent_index + 1
                if next_index < len(agent_plan):
                    # 需要切换到下一个 Agent
                    return "switch_agent"
                else:
                    # 所有 Agent 都已完成
                    logger.info("所有 Agent 执行完成，进入 final_answer")
                    return "final_answer"
            else:
                # 单 Agent 模式
                logger.info("ReAct 循环结束，进入 final_answer")
                return "final_answer"
        else:
            logger.info(f"继续 ReAct 循环，步骤 {state.get('current_step', 0)}")
            return "react_think"

    # 添加 switch_agent 节点
    workflow.add_node("switch_agent", switch_agent_node)

    workflow.add_conditional_edges(
        "react_observe",
        should_continue,
        {
            "react_think": "react_think",
            "switch_agent": "switch_agent",
            "final_answer": "final_answer"
        }
    )

    # switch_agent -> react_think
    workflow.add_edge("switch_agent", "react_think")

    # final_answer -> END
    workflow.add_edge("final_answer", END)

    logger.info("ReAct 循环模式工作流图创建完成")

    return workflow


def compile_graph(use_react: bool = True) -> StateGraph:
    """
    编译LangGraph图

    Args:
        use_react: 是否使用 ReAct 循环模式（默认 True）

    Returns:
        编译后的图
    """
    if use_react:
        workflow = create_react_graph()
        logger.info("使用 ReAct 循环模式")
    else:
        workflow = create_graph()
        logger.info("使用传统模式")

    # 增加递归限制，支持多 Agent 串行执行
    compiled = workflow.compile(
        checkpointer=None,
        interrupt_before=None,
        interrupt_after=None,
        debug=False
    )

    logger.info("LangGraph图编译完成")

    return compiled
