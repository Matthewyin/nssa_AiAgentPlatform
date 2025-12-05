"""
Ping 工具实现
使用系统ping命令检查主机可达性
"""
import asyncio
import platform
import json
from typing import Dict, Any


async def ping_tool(target: str, count: int = 4) -> str:
    """
    执行ping命令
    
    Args:
        target: 目标主机IP或域名
        count: ping次数
        
    Returns:
        JSON格式的ping结果
    """
    # 根据操作系统选择ping命令参数
    system = platform.system().lower()
    if system == "windows":
        cmd = ["ping", "-n", str(count), target]
    else:  # Linux, macOS
        cmd = ["ping", "-c", str(count), target]
    
    try:
        # 执行ping命令
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        # 解析输出
        output = stdout.decode('utf-8', errors='ignore')
        
        # 构建结果
        result = {
            "success": process.returncode == 0,
            "target": target,
            "count": count,
            "raw_output": output,
            "error": stderr.decode('utf-8', errors='ignore') if stderr else None
        }
        
        # 尝试提取统计信息
        if process.returncode == 0:
            result["summary"] = _parse_ping_output(output, system)
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {
            "success": False,
            "target": target,
            "error": str(e)
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2)


def _parse_ping_output(output: str, system: str) -> Dict[str, Any]:
    """
    解析ping输出,提取统计信息
    
    Args:
        output: ping命令输出
        system: 操作系统类型
        
    Returns:
        统计信息字典
    """
    summary = {}
    
    try:
        lines = output.split('\n')
        
        # 查找统计信息行
        for i, line in enumerate(lines):
            # 丢包率
            if 'packet loss' in line.lower() or '丢失' in line:
                summary['packet_loss_line'] = line.strip()
            
            # RTT统计 (Linux/macOS)
            if 'rtt min/avg/max' in line.lower() or 'round-trip' in line.lower():
                summary['rtt_line'] = line.strip()
            
            # Windows的统计信息
            if '最短' in line or 'minimum' in line.lower():
                summary['rtt_line'] = line.strip()
        
    except Exception:
        pass  # 解析失败不影响主要功能
    
    return summary
