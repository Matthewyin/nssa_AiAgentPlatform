#!/usr/bin/env python3
"""测试 MySQL MCP 连接和配置加载"""
import os

def test_config_loading():
    """测试配置加载"""
    print("=" * 50)
    print("测试1: 配置加载")
    print("=" * 50)

    from utils import load_mcp_config

    config = load_mcp_config()
    mysql = next((s for s in config.get('mcp_servers', []) if s['name'] == 'mysql-mcp'), None)

    if mysql:
        print('MySQL MCP 配置 env (从 YAML 加载并展开):')
        for k, v in mysql.get('env', {}).items():
            if 'PASSWORD' in k:
                print(f'  {k}=***')
            else:
                print(f'  {k}={v}')
    else:
        print('未找到 mysql-mcp 配置')

    return mysql

def test_mcp_connection(mysql_config):
    """测试 MCP 连接"""
    import asyncio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client, get_default_environment

    print("\n" + "=" * 50)
    print("测试2: MCP 连接")
    print("=" * 50)

    async def run_test():
        # 使用配置中的环境变量
        env = {
            **get_default_environment(),
            **mysql_config.get('env', {})
        }

        print('传递给 mcp-server-mysql 的环境变量:')
        for k, v in env.items():
            if k.startswith('MYSQL'):
                print(f'  {k}={"***" if "PASSWORD" in k else v}')

        server_params = StdioServerParameters(
            command='uvx',
            args=['mcp-server-mysql'],
            env=env
        )

        print('\n启动 mcp-server-mysql...')

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                print(f'\n可用工具: {[t.name for t in tools.tools]}')

                print('\n执行测试查询: SELECT 1 as test')
                result = await session.call_tool('execute_query', {'query': 'SELECT 1 as test'})
                print(f'结果: {result}')

    asyncio.run(run_test())

if __name__ == '__main__':
    mysql_config = test_config_loading()
    if mysql_config:
        test_mcp_connection(mysql_config)

