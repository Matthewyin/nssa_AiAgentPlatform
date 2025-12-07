#!/bin/bash
# 重启所有服务的脚本（不论是否在运行都可以重启）

echo "=== AI Agent Network Tools 重启脚本 ==="

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

# 创建日志目录（分类存储）
mkdir -p data/logs/app
mkdir -p data/logs/graph_service
mkdir -p data/logs/token_usage

# 检查 uv 是否安装
if ! command -v uv &> /dev/null; then
    echo "错误: uv 未安装，请先安装 uv"
    echo "安装命令: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# ============================================
# 第一步：停止现有服务
# ============================================
echo ""
echo "步骤 1/2: 停止现有服务..."

# 方法1: 从PID文件读取
if [ -f "data/logs/graph_service.pid" ]; then
    GRAPH_PID=$(cat data/logs/graph_service.pid)
    if ps -p $GRAPH_PID > /dev/null 2>&1; then
        echo "  停止 Graph Service (PID: $GRAPH_PID)..."
        kill $GRAPH_PID
        rm -f data/logs/graph_service.pid
    else
        echo "  清理过期的 PID 文件..."
        rm -f data/logs/graph_service.pid
    fi
fi

# 方法2: 查找并停止所有Graph Service进程
GRAPH_PIDS=$(pgrep -f "graph_service.main")

if [ -n "$GRAPH_PIDS" ]; then
    echo "  发现运行中的 Graph Service 进程: $GRAPH_PIDS"
    for PID in $GRAPH_PIDS; do
        echo "  停止进程 $PID..."
        kill $PID 2>/dev/null
    done

    # 等待进程结束
    sleep 1

    # 检查是否还有进程存在，如果有则强制杀死
    REMAINING_PIDS=$(pgrep -f "graph_service.main")
    if [ -n "$REMAINING_PIDS" ]; then
        echo "  强制停止残留进程: $REMAINING_PIDS"
        for PID in $REMAINING_PIDS; do
            kill -9 $PID 2>/dev/null
        done
    fi

    echo "  ✅ 所有 Graph Service 进程已停止"
else
    echo "  ℹ️  Graph Service 未运行"
fi

# ============================================
# 第二步：启动服务
# ============================================
echo ""
echo "步骤 2/2: 启动服务..."

# 使用 uv run 启动 Graph Service
echo "  启动 Graph Service (后台运行)..."
TODAY=$(date +%Y-%m-%d)
nohup uv run python -m graph_service.main > data/logs/graph_service/graph_service_${TODAY}.log 2>&1 &
GRAPH_PID=$!

# 保存PID到文件
echo $GRAPH_PID > data/logs/graph_service.pid

# 等待服务启动
sleep 2

# 检查服务是否成功启动
if ps -p $GRAPH_PID > /dev/null; then
    echo ""
    echo "✅ Graph Service 重启成功！"
    echo "   PID: $GRAPH_PID"
    echo "   日志目录: data/logs/"
    echo "   - 应用日志: data/logs/app/"
    echo "   - 服务日志: data/logs/graph_service/"
    echo "   - Token统计: data/logs/token_usage/"
    echo "   API文档: http://localhost:30021/docs"
    echo ""
    echo "查看实时日志: tail -f data/logs/app/app_${TODAY}.log"
    echo "停止服务: bash scripts/stop_all.sh"
else
    echo ""
    echo "❌ Graph Service 启动失败"
    echo "请查看日志: cat data/logs/graph_service/graph_service_${TODAY}.log"
    exit 1
fi

