"""
ReAct 循环模式测试
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from graph_service import compile_graph
from graph_service.state import GraphState
from loguru import logger


async def test_react_simple():
    """测试用例1：简单场景（单个工具）"""
    logger.info("=" * 60)
    logger.info("测试用例1：简单场景 - ping baidu.com")
    logger.info("=" * 60)
    
    try:
        # 编译 ReAct 图
        graph = compile_graph(use_react=True)
        
        # 初始化状态
        initial_state: GraphState = {
            "user_query": "ping baidu.com",
            "current_node": "",
            "target_agent": "",
            "network_diag_result": None,
            "rag_result": None,
            "final_answer": "",
            "errors": [],
            "metadata": {},
            # ReAct 状态
            "execution_history": [],
            "current_step": 1,
            "max_iterations": 10,
            "is_finished": False,
            "next_action": None,
            "last_observation": ""
        }
        
        # 执行图
        final_state = await graph.ainvoke(initial_state)
        
        # 检查结果
        logger.info(f"\n执行历史记录数: {len(final_state.get('execution_history', []))}")
        logger.info(f"是否完成: {final_state.get('is_finished')}")
        logger.info(f"\n最终回复:\n{final_state['final_answer'][:800]}...")
        
        if final_state.get("errors"):
            logger.error(f"错误: {final_state['errors']}")
            return False
        else:
            logger.info("✓ 测试用例1通过")
            return True
            
    except Exception as e:
        logger.error(f"测试用例1失败: {e}", exc_info=True)
        return False


async def test_react_dependency():
    """测试用例2：参数依赖场景（nslookup + mtr）"""
    logger.info("\n" + "=" * 60)
    logger.info("测试用例2：参数依赖场景 - 先查询 IP，再用 IP 执行 mtr")
    logger.info("=" * 60)
    
    try:
        # 编译 ReAct 图
        graph = compile_graph(use_react=True)
        
        # 初始化状态
        initial_state: GraphState = {
            "user_query": "先用 nslookup 查询 g3xjtls.lottery-it.com 的 IP 地址，然后用查询到的 IP 地址执行 mtr 测试",
            "current_node": "",
            "target_agent": "",
            "network_diag_result": None,
            "rag_result": None,
            "final_answer": "",
            "errors": [],
            "metadata": {},
            # ReAct 状态
            "execution_history": [],
            "current_step": 1,
            "max_iterations": 10,
            "is_finished": False,
            "next_action": None,
            "last_observation": ""
        }
        
        # 执行图
        final_state = await graph.ainvoke(initial_state)
        
        # 检查结果
        execution_history = final_state.get('execution_history', [])
        logger.info(f"\n执行历史记录数: {len(execution_history)}")
        logger.info(f"是否完成: {final_state.get('is_finished')}")
        
        # 打印执行历史
        logger.info("\n执行历史:")
        for i, record in enumerate(execution_history, 1):
            action = record.get("action", {})
            logger.info(f"  步骤 {i}: {action.get('type')} - {action.get('tool')}")
            if action.get('params'):
                logger.info(f"    参数: {action.get('params')}")
        
        logger.info(f"\n最终回复:\n{final_state['final_answer'][:800]}...")
        
        # 验证：应该执行了 nslookup 和 mtr 两个工具
        tool_calls = [r for r in execution_history if r.get("action", {}).get("type") == "TOOL"]
        if len(tool_calls) >= 2:
            # 检查第一个工具是否是 nslookup
            first_tool = tool_calls[0].get("action", {}).get("tool")
            second_tool = tool_calls[1].get("action", {}).get("tool")
            
            logger.info(f"\n第一个工具: {first_tool}")
            logger.info(f"第二个工具: {second_tool}")
            
            if "nslookup" in first_tool and "mtr" in second_tool:
                # 检查 mtr 的参数是否使用了 IP 地址
                mtr_params = tool_calls[1].get("action", {}).get("params", {})
                mtr_target = mtr_params.get("target", "")
                
                logger.info(f"MTR 目标: {mtr_target}")
                
                # 检查是否是 IP 地址（简单判断：包含数字和点）
                import re
                if re.match(r'^\d+\.\d+\.\d+\.\d+$', mtr_target):
                    logger.info("✓ 测试用例2通过：MTR 使用了 IP 地址")
                    return True
                else:
                    logger.warning(f"⚠ MTR 使用的不是 IP 地址: {mtr_target}")
                    return False
            else:
                logger.warning(f"⚠ 工具顺序不正确: {first_tool} -> {second_tool}")
                return False
        else:
            logger.warning(f"⚠ 工具调用次数不足: {len(tool_calls)}")
            return False
            
    except Exception as e:
        logger.error(f"测试用例2失败: {e}", exc_info=True)
        return False


async def main():
    """运行所有测试"""
    logger.info("开始 ReAct 循环模式测试\n")
    
    results = []
    
    # 测试用例1
    result1 = await test_react_simple()
    results.append(("简单场景", result1))
    
    # 测试用例2
    result2 = await test_react_dependency()
    results.append(("参数依赖场景", result2))
    
    # 汇总结果
    logger.info("\n" + "=" * 60)
    logger.info("测试结果汇总")
    logger.info("=" * 60)
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        logger.info(f"{name}: {status}")
    
    all_passed = all(r for _, r in results)
    if all_passed:
        logger.info("\n🎉 所有测试通过！")
    else:
        logger.error("\n❌ 部分测试失败")
    
    return all_passed


if __name__ == "__main__":
    asyncio.run(main())

