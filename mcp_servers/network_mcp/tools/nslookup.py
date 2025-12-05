"""
NSLookup 工具实现
查询DNS记录
"""
import asyncio
import json
from typing import Dict, Any


async def nslookup_tool(target: str, record_type: str = "A") -> str:
    """
    执行nslookup命令查询DNS记录
    
    Args:
        target: 要查询的域名
        record_type: DNS记录类型 (A, AAAA, MX, NS, TXT, CNAME, SOA)
        
    Returns:
        JSON格式的查询结果
    """
    try:
        # 验证域名格式 (简单验证)
        if not target or target.startswith("-"):
            return f"错误: 无效的域名 '{target}'"
            
        # 构建命令
        cmd = ["nslookup"]
        if record_type and record_type.upper() != "A":
            cmd.append(f"-type={record_type}")
            
        cmd.append(target)
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        output = stdout.decode('utf-8', errors='ignore')
        
        result = {
            "success": process.returncode == 0,
            "domain": target,
            "record_type": record_type,
            "raw_output": output,
            "error": stderr.decode('utf-8', errors='ignore') if stderr else None
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {
            "success": False,
            "domain": target,
            "record_type": record_type,
            "error": str(e)
        }
        return json.dumps(error_result, ensure_ascii=False, indent=2)
