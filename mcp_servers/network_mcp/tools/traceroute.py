"""
Traceroute 工具实现
追踪到目标主机的网络路径
"""
import asyncio
import platform
import json
from typing import Dict, Any


async def traceroute_tool(target: str, max_hops: int = 30) -> str:
    """
    执行traceroute命令
    
    Args:
        target: 目标主机IP或域名
        max_hops: 最大跳数
        
    Returns:
        JSON格式的traceroute结果
    """
    # 根据操作系统选择命令
    system = platform.system().lower()
    if system == "windows":
        cmd = ["tracert", "-h", str(max_hops), target]
    else:  # Linux, macOS
        cmd = ["traceroute", "-m", str(max_hops), target]
    
    try:
        # 执行traceroute命令
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # 设置超时(traceroute可能需要较长时间)
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=60.0  # 60秒超时
            )
        except asyncio.TimeoutError:
            process.kill()
            return json.dumps({
                "success": False,
                "target": target,
                "error": "traceroute命令执行超时(60秒)"
            }, ensure_ascii=False, indent=2)
        
        output = stdout.decode('utf-8', errors='ignore')
        
        result = {
            "success": process.returncode == 0,
            "target": target,
            "max_hops": max_hops,
            "raw_output": output,
            "error": stderr.decode('utf-8', errors='ignore') if stderr else None
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {
            "success": False,
            "target": target,
            "error": str(e)
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2)
