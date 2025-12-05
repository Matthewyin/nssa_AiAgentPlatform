"""
MTR 工具实现
结合ping和traceroute功能,实时监控网络路径质量
"""
import asyncio
import platform
import json
from typing import Dict, Any


async def mtr_tool(target: str, count: int = 10, report_cycles: int = 10) -> str:
    """
    执行mtr命令
    
    Args:
        target: 目标主机IP或域名
        count: 发送的测试包数量
        report_cycles: 报告周期数
        
    Returns:
        JSON格式的mtr结果
    """
    # 根据操作系统选择mtr命令参数
    system = platform.system().lower()
    
    # mtr命令参数
    # -r: 报告模式
    # -c: 发送的包数量
    # -n: 不解析主机名(加快速度)
    if system == "windows":
        # Windows下通常没有mtr,返回提示
        error_result = {
            "success": False,
            "target": target,
            "error": "MTR工具在Windows系统上不可用,请使用Linux或macOS,或安装WinMTR"
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2)
    else:  # Linux, macOS
        cmd = ["sudo", "mtr", "-r", "-c", str(report_cycles), "-n", target]
    
    try:
        # 执行mtr命令
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # 设置超时
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
                "error": "mtr命令执行超时(60秒)"
            }, ensure_ascii=False, indent=2)
        
        output = stdout.decode('utf-8', errors='ignore')
        error_output = stderr.decode('utf-8', errors='ignore')
        
        # 构建结果
        result = {
            "success": process.returncode == 0,
            "target": target,
            "count": count,
            "report_cycles": report_cycles,
            "raw_output": output,
            "error": error_output if error_output else None
        }
        
        # 尝试解析mtr输出
        if process.returncode == 0:
            result["summary"] = _parse_mtr_output(output)
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except FileNotFoundError:
        # mtr命令不存在
        error_result = {
            "success": False,
            "target": target,
            "error": "mtr命令未安装。请安装: sudo apt-get install mtr (Ubuntu/Debian) 或 brew install mtr (macOS)"
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2)
    except Exception as e:
        error_result = {
            "success": False,
            "target": target,
            "error": str(e)
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2)


def _parse_mtr_output(output: str) -> Dict[str, Any]:
    """
    解析mtr输出,提取关键信息
    
    Args:
        output: mtr命令输出
        
    Returns:
        解析后的统计信息
    """
    summary = {
        "hops": [],
        "total_hops": 0
    }
    
    try:
        lines = output.split('\n')
        
        # 跳过标题行,解析每一跳的信息
        for line in lines:
            line = line.strip()
            if not line or line.startswith('Start') or line.startswith('HOST'):
                continue
            
            # mtr输出格式示例:
            # 1. 192.168.1.1    0.0%    10    0.5   0.6   0.5   0.8   0.1
            parts = line.split()
            if len(parts) >= 7:
                try:
                    hop_info = {
                        "hop": int(parts[0].rstrip('.')),
                        "host": parts[1],
                        "loss_percent": parts[2],
                        "sent": parts[3],
                        "last": parts[4],
                        "avg": parts[5],
                        "best": parts[6],
                        "worst": parts[7] if len(parts) > 7 else None
                    }
                    summary["hops"].append(hop_info)
                except (ValueError, IndexError):
                    continue
        
        summary["total_hops"] = len(summary["hops"])
        
    except Exception:
        pass  # 解析失败不影响主要功能
    
    return summary
