"""
集成测试：测试完整的工作流
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


async def test_integration():
    """测试完整的集成流程"""
    logger.info("=" * 60)
    logger.info("开始集成测试")
    logger.info("=" * 60)
    
    try:
        # 编译图
        logger.info("\n1. 编译 LangGraph 工作流...")
        graph = compile_graph()
        logger.info("工作流编译成功")
        
        # 测试用例1：简单的 ping 测试
        logger.info("\n2. 测试用例1：ping baidu.com")
        initial_state: GraphState = {
            "user_query": "ping baidu.com",
            "current_node": "",
            "target_agent": "",
            "network_diag_result": None,
            "rag_result": None,
            "final_answer": "",
            "errors": [],
            "metadata": {}
        }
        
        final_state = await graph.ainvoke(initial_state)
        
        logger.info(f"\n最终回复:\n{final_state['final_answer'][:500]}...")
        
        if final_state.get("errors"):
            logger.error(f"错误: {final_state['errors']}")
        else:
            logger.info("✓ 测试用例1通过")
        
        # 测试用例2：nslookup 测试
        logger.info("\n3. 测试用例2：查询 google.com 的 IP 地址")
        initial_state2: GraphState = {
            "user_query": "查询 google.com 的 IP 地址",
            "current_node": "",
            "target_agent": "",
            "network_diag_result": None,
            "rag_result": None,
            "final_answer": "",
            "errors": [],
            "metadata": {}
        }
        
        final_state2 = await graph.ainvoke(initial_state2)
        
        logger.info(f"\n最终回复:\n{final_state2['final_answer'][:500]}...")
        
        if final_state2.get("errors"):
            logger.error(f"错误: {final_state2['errors']}")
        else:
            logger.info("✓ 测试用例2通过")
        
        logger.info("\n" + "=" * 60)
        logger.info("集成测试完成！")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"集成测试失败: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(test_integration())

