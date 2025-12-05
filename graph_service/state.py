"""
GraphState定义
LangGraph的状态管理
"""
from typing import TypedDict, List, Dict, Any, Optional


class GraphState(TypedDict):
    """
    LangGraph的状态定义
    所有节点共享这个状态
    """
    # 用户输入
    user_query: str  # 用户原始问题

    # 当前执行状态
    current_node: str  # 当前执行的节点名称,用于进度展示

    # 路由信息
    target_agent: str  # Router决定的目标Agent（单Agent模式，向后兼容）
    agent_plan: Optional[List[Dict[str, Any]]]  # 多Agent执行计划（新增）
    # agent_plan 格式: [{"name": "agent_name", "task": "任务描述", "status": "pending/running/completed/failed"}]
    current_agent_index: int  # 当前执行的Agent索引（用于多Agent串行执行）

    # Agent执行结果（旧模式，向后兼容）
    network_diag_result: Optional[Dict[str, Any]]  # 网络诊断结果
    rag_result: Optional[Dict[str, Any]]  # RAG检索结果

    # ReAct 循环状态（新增）
    execution_history: List[Dict[str, Any]]  # 执行历史记录
    current_step: int  # 当前步骤号（从1开始）
    max_iterations: int  # 最大迭代次数（默认10）
    is_finished: bool  # 是否完成任务
    next_action: Optional[Dict[str, Any]]  # LLM决定的下一步行动
    last_observation: str  # 上一步的观察结果

    # 最终输出
    final_answer: str  # 最终回复给用户的答案

    # 错误记录
    errors: List[str]  # 执行过程中的错误列表

    # 元数据
    metadata: Dict[str, Any]  # 其他元数据信息
