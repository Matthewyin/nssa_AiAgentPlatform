"""
FinalAnswer节点
生成最终回复
"""
from typing import Dict, Any
import json
from loguru import logger
from ..state import GraphState
from ..utils import smart_truncate, get_tool_type, extract_result_summary, format_full_result
from utils import load_langgraph_config, get_config_manager, load_optimization_config


def get_llm():
    """获取或创建 LLM 实例（使用配置管理器）"""
    config_manager = get_config_manager()
    return config_manager.get_llm("final_answer")


def _should_skip_llm_analysis(state: GraphState) -> bool:
    """
    判断是否应该跳过 LLM 综合分析

    优化后的策略：
    1. 配置启用跳过功能
    2. 没有错误
    3. 单 Agent + 步骤数 ≤ 阈值：跳过
    4. 多 Agent + 步骤数 ≤ 多Agent阈值：跳过（新增）
    5. 步骤数 > 阈值：不跳过

    Args:
        state: 当前状态

    Returns:
        是否跳过 LLM 分析
    """
    try:
        config = load_optimization_config()
        skip_config = config.get("optimization", {}).get("skip_final_analysis", {})

        if not skip_config.get("enabled", False):
            return False

        step_threshold = skip_config.get("step_threshold", 2)
        # 多 Agent 场景的步骤阈值（新增配置，默认为 3）
        multi_agent_step_threshold = skip_config.get("multi_agent_step_threshold", 3)
        always_analyze_on_error = skip_config.get("always_analyze_on_error", True)

        execution_history = state.get("execution_history", [])
        agent_plan = state.get("agent_plan", [])

        # 计算实际执行的工具数
        tool_calls = [r for r in execution_history if r.get("action", {}).get("type") == "TOOL"]
        tool_count = len(tool_calls)
        agent_count = len(agent_plan or [])

        # 检查是否有错误
        has_error = False
        if always_analyze_on_error:
            for record in tool_calls:
                observation = record.get("observation", "")
                if any(err in str(observation) for err in ["Error", "错误", "失败", "failed", "exception"]):
                    has_error = True
                    break

        # 判断是否跳过
        if has_error:
            logger.info("Final Answer: 检测到错误，不跳过 LLM 分析")
            return False

        # 单 Agent 场景
        if agent_count <= 1:
            if tool_count <= step_threshold:
                logger.info(f"Final Answer: 单 Agent 简单任务（{tool_count} 个工具 ≤ {step_threshold}），跳过 LLM 分析")
                return True
            else:
                logger.info(f"Final Answer: 单 Agent 复杂任务（{tool_count} 个工具 > {step_threshold}），需要 LLM 分析")
                return False

        # 多 Agent 场景
        if tool_count <= multi_agent_step_threshold:
            logger.info(f"Final Answer: 多 Agent 简单任务（{agent_count} Agent, {tool_count} 个工具 ≤ {multi_agent_step_threshold}），跳过 LLM 分析")
            return True
        else:
            logger.info(f"Final Answer: 多 Agent 复杂任务（{agent_count} Agent, {tool_count} 个工具 > {multi_agent_step_threshold}），需要 LLM 分析")
            return False

    except Exception as e:
        logger.warning(f"判断是否跳过 LLM 分析失败: {e}")
        return False


def _generate_llm_analysis(user_query: str, execution_history: list, agent_plan: list = None) -> str:
    """
    生成 LLM 综合分析 - 专注于分析工具返回的结果内容

    Args:
        user_query: 用户的原始问题
        execution_history: 执行历史记录
        agent_plan: Agent 执行计划（多 Agent 场景）

    Returns:
        LLM 生成的综合分析
    """
    try:
        # 提取工具执行的结果内容（不是执行步骤，而是实际返回的数据）
        tool_results = []
        tool_calls = [record for record in execution_history if record.get("action", {}).get("type") == "TOOL"]

        for record in tool_calls:
            action = record.get("action", {})
            tool_name = action.get("tool", "")
            observation = record.get("observation", "")

            # 提取实际的结果数据
            result_data = observation
            if "结果:" in observation:
                result_data = observation.split("结果:", 1)[1].strip()
            elif "结果：" in observation:
                result_data = observation.split("结果：", 1)[1].strip()

            # 判断是否执行失败
            is_error = any(err in observation for err in [
                "执行失败", "错误", "Error", "失败", "Connection not available"
            ])

            # RAG 类工具不截断（这些工具返回的是精确检索结果，截断会导致信息丢失）
            rag_tools = ["gemini.rag_search", "gemini.rag_list_stores", "gemini.rag_list_documents"]
            is_rag_tool = any(rag in tool_name for rag in rag_tools)

            if not is_rag_tool:
                # 非 RAG 工具：限制结果长度
                max_result_len = 3000
                if len(result_data) > max_result_len:
                    result_data = result_data[:max_result_len] + "\n... [数据已截断]"

            tool_results.append({
                "tool": tool_name,
                "result": result_data,
                "is_error": is_error
            })

        # 构建结果内容
        results_content = ""
        if tool_results:
            for i, tr in enumerate(tool_results, 1):
                status = "❌ 失败" if tr["is_error"] else "✅ 成功"
                results_content += f"\n【工具 {i}】{tr['tool']} - {status}\n"
                results_content += f"返回数据:\n{tr['result']}\n"

        # 确定分析专家类型
        agent_type_desc = "数据分析专家"
        if agent_plan and len(agent_plan) >= 1:
            agent_name = agent_plan[0].get("agent", "")
            if "network" in agent_name.lower():
                agent_type_desc = "网络诊断专家"
            elif "database" in agent_name.lower():
                agent_type_desc = "数据库分析专家"
            elif "rag" in agent_name.lower():
                agent_type_desc = "知识检索专家"

        # 构建 Prompt - 专注于分析结果内容
        prompt = f"""你是一个专业的{agent_type_desc}。请根据以下工具返回的结果数据，进行分析并回答用户的问题。

## 用户问题
{user_query}

## 工具执行结果
{results_content}

## 分析要求

请基于上述工具返回的**实际数据**进行分析，提供以下内容：

1. **结果解读**：解释工具返回的数据含义
2. **关键发现**：从数据中提取对用户问题有价值的信息
3. **结论**：直接回答用户的问题
4. **建议**（可选）：如果有优化或后续操作建议

## 重要规则

- **只分析实际返回的数据**，不要分析执行过程
- **禁止编造数据**：如果工具执行失败，明确告知用户失败原因
- **基于事实**：所有分析必须基于上述工具返回的实际数据
- 使用中文回复
- 简洁明了，重点突出

请开始分析："""

        # 调用 LLM（使用 token 统计）
        from utils.llm_wrapper import invoke_llm_with_tracking

        llm = get_llm()
        analysis = invoke_llm_with_tracking(llm, prompt, "final_answer")

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

                # 添加完整执行结果（使用纯 Markdown 格式，默认展开）
                # 只展示工具执行的结果，不展示思考过程（因为流式输出已展示）
                tool_results = [
                    record for record in execution_history
                    if record.get("action", {}).get("type") == "TOOL" and record.get("observation")
                ]

                if tool_results:
                    final_answer += f"### 📋 完整执行结果（共 {len(tool_results)} 个工具）\n\n"

                    for i, record in enumerate(tool_results, 1):
                        action = record.get("action", {})
                        tool_name = action.get("tool", "")
                        params = action.get("params", {})
                        observation = record.get("observation", "")

                        # 工具标题
                        final_answer += f"#### 🔧 {tool_name}\n\n"

                        # 显示参数（简洁格式）
                        if params:
                            params_display = ", ".join(f"`{k}={v}`" for k, v in params.items())
                            final_answer += f"**参数**: {params_display}\n\n"

                        # 显示完整结果（使用 Markdown 表格或代码块）
                        final_answer += "**结果**:\n\n"
                        formatted_result = format_full_result(tool_name, observation)
                        final_answer += formatted_result
                        final_answer += "\n\n"

                        if i < len(tool_results):
                            final_answer += "---\n\n"

                # 添加 LLM 综合分析（使用纯 Markdown 格式）
                # 检查是否应该跳过 LLM 分析（简单任务优化）
                if _should_skip_llm_analysis(state):
                    logger.info("Final Answer: 跳过 LLM 综合分析（简单任务优化）")
                else:
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
