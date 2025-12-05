# OpenWebUI集成指南

## 概述

本项目已实现OpenAI兼容的API接口,可以直接集成到OpenWebUI作为自定义模型。

## API端点

### 1. 列出模型
```
GET http://localhost:8000/v1/models
```

### 2. 聊天补全
```
POST http://localhost:8000/v1/chat/completions
Content-Type: application/json

{
  "model": "aiagent-network-tools",
  "messages": [
    {"role": "user", "content": "帮我ping一下8.8.8.8"}
  ],
  "stream": false
}
```

## 在OpenWebUI中配置

### 方法1: 通过Web界面添加

1. 打开OpenWebUI (通常是 http://localhost:3000)
2. 登录后,点击右上角的设置图标
3. 进入 **Settings** > **Connections**
4. 在 **OpenAI API** 部分:
   - **API Base URL**: `http://localhost:8000/v1`
   - **API Key**: 随便填写(例如: `sk-aiagent`)
   - 点击 **Verify Connection** 测试连接
5. 保存设置
6. 在聊天界面的模型选择器中,选择 `aiagent-network-tools`

### 方法2: 通过环境变量配置

如果您使用Docker运行OpenWebUI,可以通过环境变量配置:

```bash
docker run -d \
  -p 3000:8080 \
  -e OPENAI_API_BASE_URLS="http://host.docker.internal:8000/v1" \
  -e OPENAI_API_KEYS="sk-aiagent" \
  --name open-webui \
  ghcr.io/open-webui/open-webui:main
```

**注意**: 
- 如果OpenWebUI和Graph Service都在本地运行,使用 `http://localhost:8000/v1`
- 如果OpenWebUI在Docker中,使用 `http://host.docker.internal:8000/v1` (Mac/Windows) 或 `http://172.17.0.1:8000/v1` (Linux)

## 测试集成

### 1. 测试模型列表
```bash
curl http://localhost:8000/v1/models
```

应该返回:
```json
{
  "object": "list",
  "data": [
    {
      "id": "aiagent-network-tools",
      "object": "model",
      ...
    }
  ]
}
```

### 2. 测试聊天补全
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "aiagent-network-tools",
    "messages": [
      {"role": "user", "content": "帮我ping一下8.8.8.8"}
    ]
  }'
```

## 使用示例

在OpenWebUI中,您可以这样使用:

1. **网络诊断**:
   - "帮我ping一下8.8.8.8"
   - "traceroute到baidu.com"
   - "查询google.com的DNS记录"

2. **故障排查**:
   - "我无法访问某个网站,帮我诊断一下"
   - "网络很慢,帮我检查一下"

## 故障排查

### 问题1: 无法连接到API
- 确保Graph Service正在运行: `curl http://localhost:8000/health`
- 检查防火墙设置
- 检查端口是否被占用

### 问题2: 模型不显示
- 检查API Base URL是否正确
- 确保URL以 `/v1` 结尾
- 查看OpenWebUI的日志

### 问题3: 响应很慢
- 这是正常的,因为需要调用LLM
- 可以在配置中调整超时时间
- 考虑使用更快的LLM模型

## 高级配置

### 启用流式响应

在聊天请求中设置 `"stream": true`:

```json
{
  "model": "aiagent-network-tools",
  "messages": [...],
  "stream": true
}
```

### 自定义参数

可以通过修改 `config/llm_config.yaml` 来调整:
- `temperature`: 控制回复的随机性
- `max_tokens`: 最大生成长度
- `timeout`: 超时时间

## 下一步

- 优化响应速度
- 添加更多网络诊断工具
- 集成RAG功能
- 添加历史对话记忆
