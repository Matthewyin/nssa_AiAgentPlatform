#!/bin/bash
# 停止所有服务的脚本

echo "=== 停止AI Agent Network Tools服务 ==="

# 方法1: 从PID文件读取
if [ -f "data/logs/graph_service.pid" ]; then
    GRAPH_PID=$(cat data/logs/graph_service.pid)
    if ps -p $GRAPH_PID > /dev/null 2>&1; then
        echo "停止Graph Service (PID: $GRAPH_PID)..."
        kill $GRAPH_PID
        rm -f data/logs/graph_service.pid
        echo "✅ Graph Service已停止"
    else
        echo "⚠️  PID文件存在但进程不存在，清理PID文件..."
        rm -f data/logs/graph_service.pid
    fi
fi

# 方法2: 查找并停止所有Graph Service进程
GRAPH_PIDS=$(pgrep -f "graph_service.main")

if [ -n "$GRAPH_PIDS" ]; then
    echo "发现运行中的Graph Service进程: $GRAPH_PIDS"
    for PID in $GRAPH_PIDS; do
        echo "停止进程 $PID..."
        kill $PID
    done

    # 等待进程结束
    sleep 1

    # 检查是否还有进程存在，如果有则强制杀死
    REMAINING_PIDS=$(pgrep -f "graph_service.main")
    if [ -n "$REMAINING_PIDS" ]; then
        echo "强制停止残留进程: $REMAINING_PIDS"
        for PID in $REMAINING_PIDS; do
            kill -9 $PID
        done
    fi

    echo "✅ 所有Graph Service进程已停止"
else
    echo "ℹ️  Graph Service未运行"
fi

echo ""
echo "所有服务已停止"
