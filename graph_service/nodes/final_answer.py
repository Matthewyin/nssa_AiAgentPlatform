"""
FinalAnswer节点
生成最终回复
"""
from typing import Dict, Any
import json
from loguru import logger
from ..state import GraphState
from ..utils import smart_truncate, get_tool_type, extract_result_summary
from utils import load_langgraph_config, get_config_manager


def get_llm():
    """获取或创建 LLM 实例（使用配置管理器）"""
    config_manager = get_config_manager()
    return config_manager.get_llm("final_answer")


def _generate_llm_analysis(user_query: str, execution_history: list, agent_plan: list = None) -> str:
    """
    生成 LLM 综合分析

    Args:
        user_query: 用户的原始问题
        execution_history: 执行历史记录
        agent_plan: Agent 执行计划（多 Agent 场景）

    Returns:
        LLM 生成的综合分析
    """
    try:
        # 构建执行摘要，包含实际的观察结果（特别是错误信息）
        execution_summary = ""
        tool_calls = [record for record in execution_history if record.get("action", {}).get("type") == "TOOL"]

        if tool_calls:
            execution_summary += "执行步骤：\n"
            for i, record in enumerate(tool_calls, 1):
                action = record.get("action", {})
                tool_name = action.get("tool", "")
                observation = record.get("observation", "")

                # 提取工具执行结果的关键信息
                result_summary = ""
                if "执行失败" in observation or "错误" in observation or "Error" in observation:
                    result_summary = "失败"
                    # 提取错误详情（截取前300字符，确保 LLM 看到错误原因）
                    error_detail = observation[:300]
                    if len(observation) > 300:
                        error_detail += "..."
                    execution_summary += f"{i}. 使用工具 {tool_name} - {result_summary}\n   错误详情: {error_detail}\n"
                elif "执行成功" in observation:
                    result_summary = "成功"
                    # 提取成功结果摘要（截取前200字符）
                    result_detail = observation[:200]
                    if len(observation) > 200:
                        result_detail += "..."
                    execution_summary += f"{i}. 使用工具 {tool_name} - {result_summary}\n   结果: {result_detail}\n"
                else:
                    result_summary = "完成"
                    execution_summary += f"{i}. 使用工具 {tool_name} - {result_summary}\n"

        # 构建多 Agent 信息
        agent_info = ""
        agent_type_desc = "分析专家"  # 默认描述

        if agent_plan and len(agent_plan) > 1:
            agent_info = "\n多 Agent 协作：\n"
            for i, plan in enumerate(agent_plan, 1):
                agent_name = plan.get("agent", "")
                task = plan.get("task", "")
                agent_info += f"{i}. {agent_name}: {task}\n"
            agent_type_desc = "多 Agent 协作分析专家"
        elif agent_plan and len(agent_plan) == 1:
            # 单 Agent 场景，根据 Agent 类型确定描述
            agent_name = agent_plan[0].get("agent", "")
            if "network" in agent_name.lower():
                agent_type_desc = "网络诊断分析专家"
            elif "database" in agent_name.lower():
                agent_type_desc = "数据库查询分析专家"
            elif "rag" in agent_name.lower():
                agent_type_desc = "知识库检索分析专家"

        # 构建 Prompt
        prompt = f"""你是一个专业的{agent_type_desc}。请根据以下信息，生成一份综合分析报告。

用户问题：
{user_query}
{agent_info}
{execution_summary}

请提供以下内容：

1. **任务完成情况**：简要说明任务是否完成，完成了哪些工作
2. **关键发现**：从执行结果中提取关键信息和发现
3. **问题诊断**：如果发现问题，进行诊断和分析
4. **建议**：给出后续操作建议或优化建议

【重要规则 - 禁止幻觉】：
- 如果工具执行失败（如"MySQL Connection not available"），必须明确告知用户任务失败及原因
- 绝对禁止在工具执行失败时编造虚假的查询结果或数据
- 如果无法获取数据，直接说明"由于XXX原因，无法完成查询"
- 只能基于实际的工具执行结果进行分析，不能假设或推测不存在的数据

要求：
- 使用中文回复
- 简洁明了，重点突出
- 使用 Markdown 格式
- 如实报告错误和失败情况
- 专注于分析和洞察

请开始分析："""

        # 调用 LLM
        llm = get_llm()
        analysis = llm.invoke(prompt)

        # 从 AIMessage 对象中提取文本内容
        analysis_text = analysis.content if hasattr(analysis, 'content') else str(analysis)
        return analysis_text.strip()

    except Exception as e:
        logger.error(f"生成 LLM 分析失败: {e}")
        return "抱歉，无法生成综合分析。"


def _format_tool_result_three_sections(tool_name: str, params: Dict[str, Any], result_json: str) -> str:
    """
    格式化工具结果为三段式输出

    Args:
        tool_name: 工具名称
        params: 工具参数
        result_json: 工具返回的JSON字符串

    Returns:
        格式化后的三段式文本
    """
    try:
        # 解析JSON结果
        result = json.loads(result_json)
    except json.JSONDecodeError:
        # 如果不是JSON，直接返回原始结果
        return f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 工具: {tool_name}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📝 原始输出:
{result_json}
"""

    # 工具名称映射（更友好的显示）
    tool_display_names = {
        "network.ping": "Ping 连通性测试",
        "network.traceroute": "Traceroute 路径追踪",
        "network.nslookup": "DNS 域名解析",
        "network.mtr": "MTR 网络质量测试"
    }
    display_name = tool_display_names.get(tool_name, tool_name)

    # 构建输出
    output = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 工具: {display_name}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""

    # 第一部分：原始输出（使用纯 Markdown 格式，美观展示）
    raw_output = result.get("raw_output", "")
    if raw_output:
        output += "### 📝 原始输出\n\n"
        output += "```text\n"
        output += raw_output.strip()
        output += "\n```\n\n"

    # 第二部分：结构化结果（使用纯 Markdown 格式）
    output += "### 📈 结构化结果\n\n"

    # 根据不同工具类型，提取关键信息
    if tool_name == "network.ping":
        success = result.get("success", False)
        target = result.get("target", "N/A")
        count = result.get("count", 0)
        summary = result.get("summary", {})

        status_icon = "✅" if success else "❌"
        output += f"{status_icon} 连接状态: {'正常' if success else '失败'}\n"
        output += f"📍 目标地址: {target}\n"
        output += f"📊 统计数据:\n"
        output += f"   • 发送: {count} 包\n"

        if summary:
            packet_loss = summary.get("packet_loss_line", "")
            rtt_line = summary.get("rtt_line", "")
            if packet_loss:
                output += f"   • {packet_loss}\n"
            if rtt_line:
                output += f"   • {rtt_line}\n"

    elif tool_name == "network.nslookup":
        success = result.get("success", False)
        domain = result.get("domain", "N/A")
        record_type = result.get("record_type", "A")

        status_icon = "✅" if success else "❌"
        output += f"{status_icon} 查询状态: {'成功' if success else '失败'}\n"
        output += f"🌐 域名: {domain}\n"
        output += f"🔍 记录类型: {record_type}\n"

        # 尝试从原始输出中提取IP地址
        if raw_output and success:
            import re
            ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
            ips = re.findall(ip_pattern, raw_output)
            # 过滤掉DNS服务器的IP（通常在前面）
            if len(ips) > 1:
                output += f"📍 解析结果: {', '.join(ips[1:])}\n"
            elif ips:
                output += f"📍 解析结果: {ips[0]}\n"

    elif tool_name == "network.traceroute":
        success = result.get("success", False)
        target = result.get("target", "N/A")
        max_hops = result.get("max_hops", 30)

        status_icon = "✅" if success else "❌"
        output += f"{status_icon} 追踪状态: {'完成' if success else '失败'}\n"
        output += f"🎯 目标: {target}\n"
        output += f"🔢 最大跳数: {max_hops}\n"

        # 统计实际跳数
        if raw_output:
            hop_count = raw_output.count('\n')
            output += f"📊 实际跳数: 约 {hop_count} 跳\n"

    elif tool_name == "network.mtr":
        success = result.get("success", False)
        target = result.get("target", "N/A")
        count = result.get("count", 10)
        summary = result.get("summary", {})

        status_icon = "✅" if success else "❌"
        output += f"{status_icon} 测试状态: {'完成' if success else '失败'}\n"
        output += f"🎯 目标: {target}\n"
        output += f"📊 测试包数: {count}\n"

        if summary:
            hops = summary.get("hops", [])
            total_hops = summary.get("total_hops", 0)
            output += f"🔢 总跳数: {total_hops} 跳\n"

            # 检查是否有丢包
            if hops:
                has_loss = any(float(hop.get("loss_percent", "0%").rstrip('%')) > 0 for hop in hops)
                if has_loss:
                    output += "⚠️  检测到丢包\n"
                else:
                    output += "✅ 全程无丢包\n"

    else:
        # 通用格式
        success = result.get("success", False)
        status_icon = "✅" if success else "❌"
        output += f"{status_icon} 执行状态: {'成功' if success else '失败'}\n"
        output += f"📋 参数: {json.dumps(params, ensure_ascii=False)}\n"

    # 如果有错误信息
    error = result.get("error")
    if error:
        output += f"\n❌ 错误信息: {error}\n"

    output += "\n"

    return output


def final_answer_node(state: GraphState) -> GraphState:
    """
    最终回复节点
    
    Args:
        state: 当前状态
        
    Returns:
        更新后的状态
    """
    state["current_node"] = "final_answer"
    
    # 加载配置
    config = load_langgraph_config()
    node_config = config.get("langgraph", {}).get("nodes", {}).get("final_answer", {})
    
    # 组合结果
    final_answer = ""

    # 检查是否已经有预设的 final_answer (例如被 router 跳过的请求)
    if state.get("final_answer"):
        final_answer = state["final_answer"]
    else:
        # 优先处理 ReAct 模式的 execution_history
        if state.get("execution_history") and len(state["execution_history"]) > 0:
            # ReAct 模式：从 execution_history 提取结果
            execution_history = state["execution_history"]

            # 统计工具调用次数
            tool_calls = [record for record in execution_history if record.get("action", {}).get("type") == "TOOL"]
            tool_count = len(tool_calls)

            if tool_count > 0:
                # 根据 target_agent 确定结果标题
                target_agent = (state.get("target_agent") or "").lower()
                if "database" in target_agent:
                    base_title = "📊 数据库查询结果"
                elif "rag" in target_agent:
                    base_title = "📊 知识库检索结果"
                elif "network" in target_agent:
                    base_title = "📊 网络诊断结果"
                else:
                    base_title = "📊 任务执行结果"

                # 添加标题
                final_answer += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                if tool_count == 1:
                    final_answer += f"{base_title}\n"
                else:
                    final_answer += f"{base_title}（共执行 {tool_count} 个工具）\n"
                final_answer += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

                # 格式化每个工具的结果
                for i, record in enumerate(tool_calls, 1):
                    action = record.get("action", {})
                    tool_name = action.get("tool")
                    params = action.get("params", {})
                    observation = record.get("observation", "")

                    if tool_count > 1:
                        final_answer += f"\n【工具 {i}/{tool_count}】"

                    # 从观察结果中提取工具返回的 JSON
                    # 观察结果格式：工具 network.ping 执行成功。结果:\n{json}
                    if "执行成功" in observation and "结果:" in observation:
                        try:
                            result_json = observation.split("结果:")[1].strip()
                            formatted = _format_tool_result_three_sections(tool_name, params, result_json)
                            final_answer += formatted
                        except Exception as e:
                            logger.warning(f"解析工具结果失败: {e}")
                            final_answer += f"\n{observation}\n"
                    else:
                        # 工具执行失败或格式不符
                        final_answer += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 工具: {tool_name}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{observation}

"""

                # 添加分隔线
                final_answer += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

                # 添加执行过程详情（使用纯 Markdown 格式，默认展开）
                final_answer += f"### 📋 执行过程详情（共 {len(execution_history)} 步）\n\n"
                for i, record in enumerate(execution_history, 1):
                    thought = record.get("thought", "")
                    action = record.get("action", {})
                    action_type = action.get("type", "")
                    observation = record.get("observation", "")

                    # 使用 Markdown 格式展示每一步
                    final_answer += f"#### 步骤 {i}\n\n"

                    # 展示思考过程
                    if thought:
                        final_answer += "**🤔 思考:**\n\n"
                        final_answer += f"```\n{thought}\n```\n\n"

                    # 展示行动
                    if action_type == "TOOL":
                        tool_name = action.get("tool", "")
                        params = action.get("params", {})
                        final_answer += "**🔧 行动:**\n\n"
                        final_answer += f"- 工具: `{tool_name}`\n"
                        if params:
                            params_json = json.dumps(params, ensure_ascii=False, indent=2)
                            final_answer += f"- 参数:\n```json\n{params_json}\n```\n\n"
                        else:
                            final_answer += "\n"
                    elif action_type == "FINISH":
                        final_answer += "**✅ 行动:** 完成任务\n\n"

                    # 展示观察结果
                    if observation:
                        # 获取工具名称和类型，使用智能截断
                        obs_tool_name = action.get("tool", "") if isinstance(action, dict) else ""
                        obs_tool_type = get_tool_type(obs_tool_name) if obs_tool_name else "default"

                        # 尝试提取结构化摘要
                        summary = extract_result_summary(obs_tool_name, observation) if obs_tool_name else None

                        final_answer += "**📊 观察:**\n\n"
                        if summary:
                            final_answer += f"> 📌 **摘要**: {summary}\n\n"

                        # 使用智能截断
                        observation_display = smart_truncate(observation, obs_tool_type)
                        final_answer += f"```\n{observation_display}\n```\n\n"

                    final_answer += "---\n\n"

                # 添加 LLM 综合分析（使用纯 Markdown 格式）
                try:
                    user_query = state.get("user_query", "")
                    agent_plan = state.get("agent_plan", [])

                    llm_analysis = _generate_llm_analysis(user_query, execution_history, agent_plan)

                    if llm_analysis:
                        final_answer += "### 💡 综合分析\n\n"
                        final_answer += llm_analysis
                        final_answer += "\n\n"
                except Exception as e:
                    logger.error(f"生成 LLM 分析时出错: {e}")

        # 向后兼容：处理旧模式的 network_diag_result
        elif state.get("network_diag_result"):
            diag_result = state["network_diag_result"]

            # 获取所有工具的执行结果
            all_results = diag_result.get("all_results", [])

            if all_results:
                # 添加标题（根据 target_agent 区分）
                tool_count = len(all_results)
                target_agent = (state.get("target_agent") or "").lower()
                if "database" in target_agent:
                    base_title = "📊 数据库查询结果"
                elif "rag" in target_agent:
                    base_title = "📊 知识库检索结果"
                elif "network" in target_agent:
                    base_title = "📊 网络诊断结果"
                else:
                    base_title = "📊 任务执行结果"

                final_answer += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                if tool_count == 1:
                    final_answer += f"{base_title}\n"
                else:
                    final_answer += f"{base_title}（共执行 {tool_count} 个工具）\n"
                final_answer += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

                # 格式化每个工具的结果
                for i, result in enumerate(all_results, 1):
                    tool_name = result.get("tool_name", "unknown")
                    params = result.get("params", {})
                    tool_result = result.get("result", "")
                    success = result.get("success", False)

                    if tool_count > 1:
                        final_answer += f"\n【工具 {i}/{tool_count}】"

                    if success:
                        # 格式化为三段式输出
                        formatted = _format_tool_result_three_sections(tool_name, params, tool_result)
                        final_answer += formatted
                    else:
                        # 工具执行失败
                        error = result.get("error", "未知错误")
                        final_answer += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 工具: {tool_name}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ 执行失败: {error}

"""

                # 添加分隔线
                final_answer += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

                # 添加 LLM 的综合分析（第三部分，使用纯 Markdown）
                llm_analysis = diag_result.get("output", "")
                if llm_analysis:
                    final_answer += "### 💡 综合分析\n\n"
                    final_answer += llm_analysis
                    final_answer += "\n\n"
            else:
                # 没有工具结果，只显示 LLM 的输出
                if "output" in diag_result:
                    final_answer += diag_result["output"]

        # 添加RAG结果(如果有)
        if state.get("rag_result"):
            rag_result = state["rag_result"]
            if "output" in rag_result:
                final_answer += "\n\n" + rag_result["output"]

        # 如果有错误,添加错误信息
        if state.get("errors"):
            final_answer += "\n\n⚠️ 执行过程中遇到以下问题:\n"
            for error in state["errors"]:
                final_answer += f"- {error}\n"

        # 如果没有任何结果,返回默认消息
        if not final_answer:
            final_answer = "抱歉,无法处理您的请求。"
    
    state["final_answer"] = final_answer
    
    # 添加元数据
    if node_config.get("include_metadata", True):
        end_time = __import__("time").time()
        start_time = state.get("metadata", {}).get("start_time", end_time)
        duration = end_time - start_time
        
        state["metadata"]["end_time"] = end_time
        state["metadata"]["duration"] = duration
        
        logger.info(f"请求处理完成,耗时: {duration:.2f}秒")
    
    return state
