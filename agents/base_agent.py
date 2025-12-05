"""
Agent基类
所有Agent的基础类,提供LLM配置和工具加载功能
"""
from typing import List, Optional, Dict, Any
from langchain_community.llms import Ollama
from langchain_core.tools import Tool
from loguru import logger
import json
import re

from utils import load_llm_config, load_agent_config, load_langchain_config


class BaseAgent:
    """Agent基类 - 简化实现"""
    
    def __init__(
        self,
        agent_name: str,
        tools: List[Tool],
        llm_config: Optional[Dict[str, Any]] = None,
        agent_config: Optional[Dict[str, Any]] = None,
        langchain_config: Optional[Dict[str, Any]] = None
    ):
        """
        初始化Agent
        
        Args:
            agent_name: Agent名称
            tools: 工具列表
            llm_config: LLM配置,如果为None则从配置文件加载
            agent_config: Agent配置,如果为None则从配置文件加载
            langchain_config: LangChain配置,如果为None则从配置文件加载
        """
        self.agent_name = agent_name
        self.tools = tools
        self.tools_dict = {tool.name: tool for tool in tools}
        
        # 加载配置
        self.llm_config = llm_config or load_llm_config()
        self.agent_config = agent_config or load_agent_config()
        self.langchain_config = langchain_config or load_langchain_config()
        
        # 初始化LLM
        self.llm = self._init_llm()
        
        # 获取配置
        agent_configs = self.agent_config.get("agents", {})
        self.config = agent_configs.get(self.agent_name, {})
        self.system_prompt = self.config.get("system_prompt", "你是一个有用的AI助手。")
        
        # 获取执行器配置
        lc_config = self.langchain_config.get("langchain", {})
        executor_config = lc_config.get("agent_executor", {})
        self.max_iterations = executor_config.get("max_iterations", 5)
        
        logger.info(f"Agent {agent_name} 初始化完成,工具数量: {len(tools)}")
    
    def _init_llm(self):
        """初始化LLM"""
        llm_conf = self.llm_config.get("llm", {})
        
        # 使用Ollama
        llm = Ollama(
            base_url=llm_conf.get("base_url", "http://localhost:11434"),
            model=llm_conf.get("model", "deepseek-r1:8b"),
            temperature=llm_conf.get("temperature", 0.7),
            num_predict=llm_conf.get("max_tokens", 2000),
        )
        
        logger.info(f"LLM初始化完成: {llm_conf.get('model')}")
        return llm
    
    async def run(self, query: str) -> Dict[str, Any]:
        """
        运行Agent - 实现真正的工具调用
        
        Args:
            query: 用户查询
            
        Returns:
            Agent执行结果
        """
        try:
            logger.info(f"Agent {self.agent_name} 开始处理查询: {query}")
            
            # 构建工具描述
            tools_desc = "\n".join([
                f"- {tool.name}: {tool.description}"
                for tool in self.tools
            ])
            
            # 第一步:让LLM快速分析并决定工具
            # 简化提示词,减少LLM思考时间
            analysis_prompt = f"""分析用户问题,选择工具并提取参数。

可用工具及参数:
- network.ping: {{"target": "IP或域名", "count": 4}}
- network.traceroute: {{"target": "IP或域名", "max_hops": 30}}
- network.nslookup: {{"target": "域名", "record_type": "A"}}
- network.mtr: {{"target": "IP或域名", "count": 10}}

用户问题: {query}

直接返回:
TOOL: 工具名
PARAMS: {{"参数": "值"}}

如果需要多个工具,每个工具单独一行:
TOOL: 工具名1
PARAMS: {{"参数": "值"}}
TOOL: 工具名2
PARAMS: {{"参数": "值"}}

示例1（单个工具）:
TOOL: network.nslookup
PARAMS: {{"target": "example.com", "record_type": "A"}}

示例2（多个工具）:
TOOL: network.nslookup
PARAMS: {{"target": "google.com", "record_type": "A"}}
TOOL: network.mtr
PARAMS: {{"target": "google.com", "count": 10}}
"""
            
            # 调用LLM分析
            analysis = self.llm.invoke(analysis_prompt)
            logger.info(f"LLM分析结果（前500字符）: {analysis[:500]}...")
            logger.info(f"LLM分析结果（完整长度）: {len(analysis)} 字符")

            # 解析LLM的响应,提取所有工具名称和参数
            import re

            # 构建工具调用列表
            tool_calls = []

            # 方法1: 尝试解析 JSON 格式 (LLM 可能返回 JSON 数组)
            try:
                # 提取 JSON 部分 (可能在 ```json 代码块中)
                json_match = re.search(r'```json\s*(\[.*?\])\s*```', analysis, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    # 尝试直接解析整个响应
                    json_str = analysis

                # 解析 JSON
                tools_array = json.loads(json_str)

                if isinstance(tools_array, list):
                    for tool_obj in tools_array:
                        if isinstance(tool_obj, dict) and 'tool' in tool_obj:
                            tool_name = tool_obj['tool']
                            params = tool_obj.get('params', {})

                            # 清理参数中的反引号和其他 Markdown 格式
                            cleaned_params = {}
                            for key, value in params.items():
                                if isinstance(value, str):
                                    # 移除反引号
                                    value = value.strip('`')
                                cleaned_params[key] = value

                            tool_calls.append({
                                "tool_name": tool_name,
                                "params": cleaned_params
                            })

                    if tool_calls:
                        logger.info(f"从 JSON 格式提取到 {len(tool_calls)} 个工具")
            except (json.JSONDecodeError, AttributeError):
                # JSON 解析失败,尝试方法2
                pass

            # 方法2: 使用正则表达式提取 TOOL: 和 PARAMS: 格式
            if not tool_calls:
                tool_matches = re.findall(r'TOOL:\s*(\S+)', analysis)
                # 修复正则表达式：使用非贪婪匹配和多行模式
                params_matches = re.findall(r'PARAMS:\s*(\{.+?\})', analysis, re.DOTALL)

                logger.info(f"工具匹配结果: {tool_matches}")
                logger.info(f"参数匹配结果数量: {len(params_matches)}, 内容: {[p[:100] for p in params_matches]}")

                if tool_matches:
                    logger.info(f"从 TOOL/PARAMS 格式提取到 {len(tool_matches)} 个工具: {tool_matches}")

                    # 配对工具和参数
                    for i, tool_name in enumerate(tool_matches):
                        tool_name = tool_name.strip()
                        params = {}

                        # 如果有对应的参数,解析它
                        if i < len(params_matches):
                            try:
                                params_str = params_matches[i]
                                params = json.loads(params_str)

                                # 清理参数中的反引号和其他 Markdown 格式
                                cleaned_params = {}
                                for key, value in params.items():
                                    if isinstance(value, str):
                                        # 移除反引号
                                        value = value.strip('`')
                                    cleaned_params[key] = value
                                params = cleaned_params

                                logger.info(f"工具 {tool_name} 的参数: {params}")
                            except json.JSONDecodeError:
                                logger.warning(f"参数解析失败: {params_str}")

                        tool_calls.append({
                            "tool_name": tool_name,
                            "params": params
                        })

            # 如果没有提取到工具,尝试从用户查询中智能推断
            if not tool_calls:
                query_lower = query.lower()
                tool_name = None
                params = {}

                if 'ping' in query_lower:
                    tool_name = 'network.ping'
                    # 尝试提取目标
                    target_match = re.search(r'ping\s+(\S+)', query_lower)
                    if target_match:
                        params = {"target": target_match.group(1), "count": 4}
                elif 'traceroute' in query_lower or 'trace' in query_lower:
                    tool_name = 'network.traceroute'
                    target_match = re.search(r'(?:traceroute|trace)\s+(\S+)', query_lower)
                    if target_match:
                        params = {"target": target_match.group(1)}
                elif 'nslookup' in query_lower or 'dns' in query_lower:
                    tool_name = 'network.nslookup'
                    # 提取域名
                    domain_match = re.search(r'(?:nslookup|dns|查询)\s+(\S+)', query_lower)
                    if domain_match:
                        params = {"target": domain_match.group(1)}
                elif 'mtr' in query_lower:
                    tool_name = 'network.mtr'
                    target_match = re.search(r'mtr\s+(\S+)', query_lower)
                    if target_match:
                        params = {"target": target_match.group(1)}

                if tool_name:
                    tool_calls.append({
                        "tool_name": tool_name,
                        "params": params
                    })

            # 如果找到了工具,执行它们
            if tool_calls:
                import asyncio

                # 存储所有工具的执行结果
                all_results = []
                tools_used = []

                # 循环执行所有工具
                for tool_call in tool_calls:
                    tool_name = tool_call["tool_name"]
                    params = tool_call["params"]

                    # 检查工具是否存在
                    if tool_name not in self.tools_dict:
                        logger.warning(f"工具 {tool_name} 不存在,跳过")
                        all_results.append({
                            "tool_name": tool_name,
                            "success": False,
                            "error": f"工具 {tool_name} 不存在"
                        })
                        continue

                    # 替换参数中的占位符
                    # 检查是否有前一个工具的结果可以用来替换占位符
                    if all_results:
                        # 获取最近一个成功的工具结果
                        last_success_result = None
                        for result in reversed(all_results):
                            if result.get("success"):
                                last_success_result = result
                                break

                        if last_success_result:
                            # 尝试从结果中提取 IP 地址
                            result_str = str(last_success_result.get("result", ""))

                            # 查找 IP 地址模式
                            import re
                            ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
                            ip_matches = re.findall(ip_pattern, result_str)

                            if ip_matches:
                                # 使用找到的第一个 IP 地址
                                extracted_ip = ip_matches[0]

                                # 替换参数中的占位符
                                for key, value in params.items():
                                    if isinstance(value, str):
                                        # 检查是否是占位符
                                        if any(placeholder in value.lower() for placeholder in [
                                            'ip地址', 'ip', 'nslookup', '查到', '返回'
                                        ]):
                                            params[key] = extracted_ip
                                            logger.info(f"替换占位符 '{value}' 为 '{extracted_ip}'")

                    logger.info(f"准备调用工具: {tool_name}, 参数: {params}")

                    tool = self.tools_dict[tool_name]

                    # 调用工具
                    try:
                        # 工具函数都是async的,需要await
                        if hasattr(tool, 'afunc'):
                            tool_result = await tool.afunc(**params)
                        elif hasattr(tool, 'func'):
                            # func也可能是async的
                            result = tool.func(**params)
                            # 检查是否是协程
                            if asyncio.iscoroutine(result):
                                tool_result = await result
                            else:
                                tool_result = result
                        else:
                            raise AttributeError(f"工具 {tool_name} 没有func或afunc方法")

                        # 保存结果
                        all_results.append({
                            "tool_name": tool_name,
                            "params": params,
                            "result": tool_result,
                            "success": True
                        })
                        tools_used.append(tool_name)

                        logger.info(f"工具 {tool_name} 执行成功")

                    except Exception as tool_error:
                        logger.error(f"工具 {tool_name} 执行失败: {tool_error}")
                        all_results.append({
                            "tool_name": tool_name,
                            "params": params,
                            "error": str(tool_error),
                            "success": False
                        })

                # 构建所有工具结果的汇总文本
                results_text = ""
                for i, result in enumerate(all_results, 1):
                    results_text += f"\n## 工具 {i}: {result['tool_name']}\n"
                    if result['success']:
                        results_text += f"参数: {result['params']}\n"
                        results_text += f"结果:\n{result['result']}\n"
                    else:
                        results_text += f"执行失败: {result.get('error', '未知错误')}\n"

                # 让LLM汇总所有结果
                summary_prompt = f"""用户问题: {query}

执行了 {len(all_results)} 个工具,结果如下:
{results_text}

请用中文汇总所有诊断结果和建议,确保包含所有工具的关键信息。"""

                summary = self.llm.invoke(summary_prompt)

                return {
                    "output": summary,
                    "tools_used": tools_used,
                    "all_results": all_results,
                    "success": True
                }
            else:
                # 没有找到合适的工具,让LLM直接回答
                logger.warning(f"未找到合适的工具,LLM直接回答")
                response = self.llm.invoke(f"{self.system_prompt}\n\n用户问题: {query}")
                
                return {
                    "output": response,
                    "success": True
                }
            
        except Exception as e:
            logger.error(f"Agent {self.agent_name} 执行失败: {e}")
            return {
                "output": f"执行失败: {str(e)}",
                "error": str(e),
                "success": False
            }
