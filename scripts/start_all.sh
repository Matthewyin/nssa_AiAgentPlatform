#!/bin/bash
# 启动所有服务的脚本

echo "=== AI Agent Network Tools 启动脚本 ==="

# 检查是否在项目根目录
if [ ! -f "pyproject.toml" ]; then
    echo "错误: 请在项目根目录运行此脚本"
    exit 1
fi

# 检查.env文件
if [ ! -f ".env" ]; then
    echo "警告: .env文件不存在,从.env.example复制..."
    cp .env.example .env
    echo "请编辑.env文件配置环境变量"
fi

# 创建日志目录
mkdir -p data/logs

# 激活uv虚拟环境
echo "激活虚拟环境..."
source .venv/bin/activate

# 检查服务是否已经在运行
EXISTING_PID=$(ps aux | grep "graph_service.main" | grep -v grep | awk '{print $2}')
if [ -n "$EXISTING_PID" ]; then
    echo "警告: Graph Service 已经在运行 (PID: $EXISTING_PID)"
    echo "如需重启，请先运行: bash scripts/stop_all.sh"
    exit 1
fi

# 使用nohup启动Graph Service
echo "启动Graph Service (后台运行)..."
nohup python -m graph_service.main > data/logs/graph_service.log 2>&1 &
GRAPH_PID=$!

# 保存PID到文件
echo $GRAPH_PID > data/logs/graph_service.pid

# 等待服务启动
sleep 2

# 检查服务是否成功启动
if ps -p $GRAPH_PID > /dev/null; then
    echo "✅ Graph Service 已启动成功"
    echo "   PID: $GRAPH_PID"
    echo "   日志文件: data/logs/graph_service.log"
    echo "   API文档: http://localhost:30021/docs"
    echo ""
    echo "查看日志: tail -f data/logs/graph_service.log"
    echo "停止服务: bash scripts/stop_all.sh"
else
    echo "❌ Graph Service 启动失败"
    echo "请查看日志: cat data/logs/graph_service.log"
    exit 1
fi
