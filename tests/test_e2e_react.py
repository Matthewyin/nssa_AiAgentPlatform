"""
端到端测试：测试 FastAPI 服务的 ReAct 模式
"""
import requests
import json
from loguru import logger


def test_simple_ping():
    """测试简单的 ping 请求"""
    logger.info("=" * 60)
    logger.info("测试1：简单 ping 请求")
    logger.info("=" * 60)
    
    url = "http://localhost:8000/v1/chat/completions"
    payload = {
        "model": "deepseek-r1:8b",
        "messages": [
            {"role": "user", "content": "ping baidu.com"}
        ],
        "stream": False
    }
    
    try:
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        
        result = response.json()
        answer = result["choices"][0]["message"]["content"]
        
        logger.info(f"响应长度: {len(answer)} 字符")
        logger.info(f"响应内容（前500字符）:\n{answer[:500]}...")
        
        # 检查是否包含关键信息
        if "ping" in answer.lower() or "baidu" in answer.lower():
            logger.info("✓ 测试1通过")
            return True
        else:
            logger.warning("⚠ 响应中未找到预期内容")
            return False
            
    except Exception as e:
        logger.error(f"✗ 测试1失败: {e}")
        return False


def test_dependency():
    """测试参数依赖场景"""
    logger.info("\n" + "=" * 60)
    logger.info("测试2：参数依赖场景（nslookup + mtr）")
    logger.info("=" * 60)
    
    url = "http://localhost:8000/v1/chat/completions"
    payload = {
        "model": "deepseek-r1:8b",
        "messages": [
            {"role": "user", "content": "先用 nslookup 查询 g3xjtls.lottery-it.com 的 IP 地址，然后用查询到的 IP 地址执行 mtr 测试"}
        ],
        "stream": False
    }
    
    try:
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        
        result = response.json()
        answer = result["choices"][0]["message"]["content"]
        
        logger.info(f"响应长度: {len(answer)} 字符")
        logger.info(f"响应内容（前800字符）:\n{answer[:800]}...")
        
        # 检查是否包含两个工具的结果
        has_nslookup = "nslookup" in answer.lower() or "dns" in answer.lower()
        has_mtr = "mtr" in answer.lower()
        has_ip = "198.18" in answer  # 检查是否有 IP 地址
        
        logger.info(f"包含 nslookup: {has_nslookup}")
        logger.info(f"包含 mtr: {has_mtr}")
        logger.info(f"包含 IP 地址: {has_ip}")
        
        if has_nslookup and has_mtr and has_ip:
            logger.info("✓ 测试2通过")
            return True
        else:
            logger.warning("⚠ 响应中缺少预期内容")
            return False
            
    except Exception as e:
        logger.error(f"✗ 测试2失败: {e}")
        return False


def main():
    """运行所有端到端测试"""
    logger.info("开始端到端测试（FastAPI 服务）\n")
    logger.info("请确保 FastAPI 服务已启动在 http://localhost:8000\n")
    
    # 检查服务是否可用
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code == 200:
            logger.info("✓ FastAPI 服务正常运行\n")
        else:
            logger.error("✗ FastAPI 服务响应异常")
            return False
    except Exception as e:
        logger.error(f"✗ 无法连接到 FastAPI 服务: {e}")
        logger.error("请先启动服务: cd aiagent-netools && python -m graph_service.main")
        return False
    
    results = []
    
    # 测试1
    result1 = test_simple_ping()
    results.append(("简单 ping 请求", result1))
    
    # 测试2
    result2 = test_dependency()
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
        logger.info("\n🎉 所有端到端测试通过！")
    else:
        logger.error("\n❌ 部分测试失败")
    
    return all_passed


if __name__ == "__main__":
    main()

