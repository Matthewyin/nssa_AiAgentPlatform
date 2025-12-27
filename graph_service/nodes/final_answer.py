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
                status = "失败" if tr["is_error"] else "✅ 成功"
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
    # 尝试解析JSON结果
    # 尝试解析JSON结果
    try:
        result = json.loads(result_json)
        # 如果是 JSON，重新格式化以提升可读性
        formatted_raw = json.dumps(result, ensure_ascii=False, indent=2)
        lang = "json"
    except json.JSONDecodeError:
        # 如果不是标准 JSON，尝试检测是否为 Python 列表/元组字符串（常见于 SQL 结果）
        import re
        if result_json.strip().startswith("[") and "), (" in result_json:
            # 针对 Python List[Tuple] 结构的简单格式化：在元组之间插入换行
            formatted_raw = result_json.replace("), (", "),\n  (")
            # 如果开头是 [(' 这种，也在开头加个换行缩进
            if formatted_raw.startswith("[("):
                formatted_raw = formatted_raw.replace("[(", "[\n  (", 1)
            # 结尾处理
            if formatted_raw.endswith(")]"):
                formatted_raw = formatted_raw[:-2] + ")\n]"
            lang = "python"  # 使用 python 高亮
        else:
            # 其他文本，保持原样
            formatted_raw = result_json.strip()
            lang = "text"

    # 工具名称映射（更友好的显示）
    tool_display_names = {
        "network.ping": "Ping 连通性测试",
        "network.traceroute": "Traceroute 路径追踪",
        "network.nslookup": "DNS 域名解析",
        "network.mtr": "MTR 网络质量测试"
    }
    display_name = tool_display_names.get(tool_name, tool_name)

    # 构建输出 - 移除繁琐的分隔线，使用简洁的标题
    output = f"\n**工具**: {display_name}\n\n"

    # 第一部分：原始输出
    # 无论是解析成功的 JSON，还是格式化后的 SQL 结果，都在这里统一展示
    # 第一部分：原始输出
    # 仅当解析完全失败（无法识别为 JSON 或 Python 结构）时，才显示原始文本作为兜底
    if lang == "text":
        output += "**原始输出**\n\n"
        output += f"```text\n"
        output += formatted_raw
        output += "\n```\n\n"

    # 如果是解析失败且非结构化的结果（即 lang != json），我们可能无法提供"结构化结果"部分
    # 除非它是我们能够解析的特定非 JSON 格式（如 SQL）。
    # 但根据当前逻辑，如果是 SQL 结果进入了 except 分支，result 变量是未定义的。
    # 所以我们需要在这里初始化一个空的 result 字典，以防下面的代码报错
    if 'result' not in locals():
        result = {}

    # 第二部分：结构化结果（仅当 result 不为空时显示）
    # 第二部分：结构化结果（仅当 result 不为空时显示）
    if result:
        # 预备结构化数据内容
        structured_content = ""

        # 1. 优先检查标准接口字段 (Scheme 3 预留)
        if "display_data" in result and isinstance(result["display_data"], dict):
            # 如果工具必须返回用于展示的数据
            for k, v in result["display_data"].items():
                if isinstance(v, list):
                    # 如果是列表（如 SQL 结果），强制渲染为表格
                    from ..utils import format_as_markdown_table
                    structured_content += f"\n**{k}**:\n"
                    structured_content += format_as_markdown_table(v) + "\n"
                elif isinstance(v, dict):
                    # 如果是字典（可能是复杂对象），也尝试渲染为表格或代码块
                    from ..utils import format_as_markdown_table
                    structured_content += f"\n**{k}**:\n"
                    structured_content += format_as_markdown_table(v) + "\n"
                else:
                    # 简单类型直接显示
                    structured_content += f"{k}: {v}\n"
        elif "summary" in result and isinstance(result["summary"], str):
             structured_content += f"摘要: {result['summary']}\n"
        
        # 2. 如果没有标准字段，执行通用智能遍历 (Scheme 1 落地)
        else:
            # 过滤黑名单字段
            ignored_keys = {"raw_output", "stdout", "stderr", "error", "success", "is_error", "tool", "action", "thought"}
            
            # 遍历所有字段
            for key, value in result.items():
                if key in ignored_keys:
                    continue
                
                # 简单类型直接显示
                if isinstance(value, (str, int, float, bool)):
                    # 格式化 Key (可选: 把 snake_case 转为 Title Case)
                    label = key.replace("_", " ").title()
                    structured_content += f"{label}: {value}\n"
                
                # 列表类型（如数据库行），尝试渲染为表格
                elif isinstance(value, list) and value:
                    from ..utils import format_as_markdown_table
                    # 仅当列表长度适中时显示表格，避免刷屏
                    if len(value) > 0:
                        label = key.replace("_", " ").title()
                        structured_content += f"\n**{label}**:\n"
                        structured_content += format_as_markdown_table(value) + "\n"

        # 只有当生成了内容时才添加标题
        if structured_content:
            output += "**结构化结果**\n\n"
            output += structured_content
            output += "\n"

        # 如果有错误信息
        error = result.get("error")
        if error:
            output += f"\n错误信息: {error}\n"

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
                    base_title = "数据库查询结果"
                elif "rag" in target_agent:
                    base_title = "知识库检索结果"
                elif "network" in target_agent:
                    base_title = "网络诊断结果"
                else:
                    base_title = "任务执行结果"

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
                        final_answer += f"\n**--- 工具 {i}/{tool_count} ---**\n"

                    # 从观察结果中提取工具返回的 JSON
                    # 观察结果格式：工具 network.ping 执行成功。结果:\n{json}
                    if "执行成功" in observation and "结果:" in observation:
                        try:
                            result_json = observation.split("结果:")[1].strip()
                            formatted = _format_tool_result_three_sections(tool_name, params, result_json)
                            final_answer += formatted
                        except Exception as e:
                            logger.warning(f"解析工具结果失败: {e}")
                            # 降级处理：直接显示
                            final_answer += f"\n**工具**: {tool_name}\n\n"
                            final_answer += "**原始输出**\n\n```text\n"
                            final_answer += f"{observation}\n```\n\n"
                    else:
                        # 工具执行失败或格式不符 (例如 MySQL 查询直接返回了元组列表字符串，非 JSON)
                        final_answer += f"\n**工具**: {tool_name}\n\n"
                        final_answer += "**原始输出**\n\n```text\n"
                        final_answer += f"{observation.strip()}\n```\n\n"

                # [Modify] 移除硬分隔线，改用折叠块
                # final_answer += "\n---\n\n"

                # 添加完整执行结果（使用 HTML <details> 折叠，默认隐藏，点击展开）
                # 模仿类似 Openai API think 的折叠效果
                tool_results = [
                    record for record in execution_history
                    if record.get("action", {}).get("type") == "TOOL" and record.get("observation")
                ]

                if tool_results:
                    final_answer += "<details>\n"
                    final_answer += f"<summary>完整执行结果（共 {len(tool_results)} 个工具）</summary>\n\n"

                    for i, record in enumerate(tool_results, 1):
                        action = record.get("action", {})
                        tool_name = action.get("tool", "")
                        params = action.get("params", {})
                        observation = record.get("observation", "")

                        # 工具标题
                        final_answer += f"#### 工具 {tool_name}\n\n"

                        # 显示参数（简洁格式）
                        if params:
                            params_display = ", ".join(f"`{k}={v}`" for k, v in params.items())
                            final_answer += f"**参数**: {params_display}\n\n"

                        # 显示完整结果（使用 Markdown 表格或代码块）
                        final_answer += "**结果**:\n\n"
                        formatted_result = format_full_result(tool_name, observation)
                        final_answer += formatted_result
                        final_answer += "\n\n"
                    
                    final_answer += "</details>\n\n"



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
                    base_title = "数据库查询结果"
                elif "rag" in target_agent:
                    base_title = "知识库检索结果"
                elif "network" in target_agent:
                    base_title = "网络诊断结果"
                else:
                    base_title = "任务执行结果"

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
工具: {tool_name}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

执行失败: {error}

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
