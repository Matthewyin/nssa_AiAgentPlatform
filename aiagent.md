---
title: "UALMT架构"
subtitle: ""
description: "UALMT是一套旨在解决传统烟囱式开发弊病的统一大模型架构。它通过标准化的特征、训练、服务流程，整合了搜索、推荐等多个业务场景的模型开发。该架构注重模块化与高效率，旨在提升模型迭代速度，降低资源成本，为业务的快速创新和增长提供强大的技术支持。"
tags: ["大模型", "系统架构", "推荐系统", "机器学习", "模型训练", "在线服务"]
readingTime: ""
date: "2025-12-02T14:42:52.453Z"
lastmod: "2025-12-02T14:42:52.453Z"
categories: ["技术专题"]
---
# UI+Agent+LLM+MCP+Tools架构(UALMT)

你要的清单里这些全都会出现：

**OpenWebUI, LangGraph, LangChain, Ollama+LLM, RAG, MCP client, MCP server, MCP Client Library, tools**

---

## **一、总体分层视图(先有个大画面)**

本架构采用**3层设计**,每层职责清晰:

```
┌─────────────────────────────────────────────────────┐
│  第1层: UI层 - OpenWebUI                            │
│  - 用户交互入口                                      │
│  - 流式展示Agent执行进度                             │
└─────────────────────────────────────────────────────┘
                    │ HTTP / WebSocket
                    ▼
┌─────────────────────────────────────────────────────┐
│  第2层: 编排层 - LangGraph                          │
│  - 多Agent流程编排                                   │
│  - 节点: Router → NetworkAgent → RagAgent          │
│  - 内存状态管理                                      │
└─────────────────────────────────────────────────────┘
                    │ 并行调用
        ┌───────────┴───────────┐
        ▼                       ▼
┌──────────────────┐    ┌──────────────────┐
│  LangChain Agent │    │   MCP Tools      │
│  - 业务逻辑      │    │   - 工具调用     │
│  - 结果解析     │    │   - 结果解析     │
└──────────────────┘    └──────────────────┘
        │                       │
        └───────────┬───────────┘
                    ▼
┌─────────────────────────────────────────────────────┐
│  第3层: 执行层 (并行,非串行)                        │
│  ┌─────────────┐  ┌──────────────────────────────┐ │
│  │ Ollama+LLM  │  │  MCP Servers (配置化管理)    │ │
│  │ - 推理引擎  │  │  - network-mcp: 网络工具     │ │
│  └─────────────┘  │  - rag-mcp: 知识库工具       │ │
│                   │  - 其他MCP服务               │ │
│                   └──────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
                    │ 调用原子能力
                    ▼
            ┌───────────────────┐
            │  原子工具          │
            │  - OS命令          │
            │  - VectorDB        │
            │  - 日志/CMDB       │
            └───────────────────┘
```

**关键设计原则**:
- **3层而非7层**: UI → 编排 → 执行,层次清晰
- **并行而非串行**: Agent和MCP Tools是并行选择,不是串行调用
- **本地优先**: 针对本地部署优化,简化不必要的分布式复杂度  
---

## **二、逐个组件说明（是谁 / 干嘛 / 上下游）**

###  **1\. OpenWebUI（UI 层）**

* **角色**：统一人机交互入口。  
* **上游**：用户（浏览器）。  
* **下游**：你的「Graph Service」HTTP API，看起来像一个“自定义模型”。  
* **职责**：  
  * 展示对话界面、历史记录。  
  * 每一轮对话，把用户输入打包成请求发送给 Graph Service。  
  * 展示 Graph Service 返回的自然语言回复（以及必要时的中间结果，如诊断报告、图表链接）。

 这里 OpenWebUI 不直接连 Ollama / MCP，而是只当「前端」，所有智能逻辑都在后端 Graph Service。

---

### **2\. LangGraph Graph Service(编排层)**

独立服务,内部是一张LangGraph图,负责流程编排。

- **角色**: 工作流编排器,多Agent协作的总控
- **上游**: OpenWebUI
- **下游**: LangChain Agents + LLM + MCP Tools

#### **核心节点**

```python
# 简化的节点设计
UserInputNode → RouterNode → [NetworkAgentNode | RagAgentNode] → FinalAnswerNode
```

- **UserInputNode**: 接收用户消息,初始化state
- **RouterNode**: 意图识别,路由到对应Agent
  - **简化方案**: 优先用关键词规则,必要时才用LLM
  - 示例: "ping" → NetworkAgent, "历史案例" → RagAgent
- **NetworkAgentNode**: 网络诊断Agent
- **RagAgentNode**: 知识库检索Agent
- **FinalAnswerNode**: 结果汇总

#### **状态管理(内存)**

```python
class GraphState(TypedDict):
    user_query: str           # 用户原始问题
    current_node: str         # 当前执行节点(用于进度展示)
    diag_results: dict        # 诊断结果
    rag_results: list         # RAG检索结果
    final_answer: str         # 最终回复
    errors: list              # 错误记录
```

**本地部署特点**:

- ✅ 内存状态,会话结束即清理
- ✅ 不需要持久化
- ✅ 不需要分布式状态同步

#### **流式输出支持**

```python
async def stream_progress(state):
    """向OpenWebUI推送执行进度"""
    yield {"node": state["current_node"], 
           "status": "running",
           "message": "正在执行ping命令..."}
```

---

### **3\. LangChain Agents（Agent 层）**

 每个业务场景一个 Agent，内部用 LangChain 做：

* LLM 调用。  
* 工具调用（通过 MCP Client Library 的 adapter）。

#### **3.1 NetworkDiagAgent**

* **职责**：  
  * 根据用户或 Router 的意图，规划诊断步骤：  
    * 先 network.ping  
    * 再视情况 network.trace / network.mtr  
    * 必要时 network.dns\_lookup  
  * 将多个工具调用结果整理成一个结构化的「诊断结果」对象 \+ 人类可读总结。  
* **使用的工具**：  
  * 来自 MCP Bus 的 network.\* 工具，如：  
    * network.ping  
    * network.traceroute  
    * network.mtr  
    * network.nslookup  
    * system.ls（看某些日志目录等）

####  **3.2 RagAgent**

* **职责**：  
  * 接收诊断结果（甚至用户环境信息），在知识库/日志中搜索：  
    * 相似案例  
    * 历史故障记录  
    * 官方规范 / SOP  
  * 结合 RAG 检索结果，给出更“解释性”的分析、长期优化建议。  
* **使用的工具**：  
  * 来自 MCP Bus 的 rag.\* 工具，如：  
    * rag.search\_cases  
    * rag.search\_docs  
    * rag.summarize\_context  
    * rag.similar\_incidents

####  **3.3 其他 Agent（未来）**

* CapacityAgent：容量规划。  
* SecurityAgent：安全基线检查。  
* TicketAgent：故障工单生成/更新。

**共同点**：

所有 Agent 的 tools 都不是自己手工写 @tool ping，而是 **动态从 MCP Client Library 拉回来的 Tool 列表**。

---

### **4\. LLM 层：Ollama \+ LLM**

* **角色**：所有 Agent 的语言模型 Backend。  
* **上游**：LangChain（Ollama wrapper 或 OpenAI-compatible wrapper）。  
* **下游**：Ollama 本地进程。  
* **职责**：  
  * 处理自然语言理解 / 推理 / 工具调用计划。  
  * 形成对 tools 的调用决定（如 ReAct/Tools 风格）。  
  * 把工具结果整合成自然语言回复 / 结构化 JSON 报告。

 可以统一用一个模型（比如 llama3 / deepseek-r1），也可以给不同 Agent 配不同模型配置，LangChain 很好切换。

---

### **5\. MCP工具管理(简化设计)**

**设计原则**: 本地部署,配置化管理,避免过度设计。

#### **5.1 配置文件驱动**

```yaml
# mcp_config.yaml
mcp_servers:
  - name: network-mcp
    command: python
    args: ["network_mcp_server.py"]
    tools_prefix: "network"
    
  - name: rag-mcp
    command: python
    args: ["rag_mcp_server.py"]
    tools_prefix: "rag"
```

#### **5.2 简化的职责**

1. **启动时加载**: 读取配置文件,启动MCP Server进程
2. **工具映射**: 维护简单的 `{tool_name: mcp_server}` 映射表
3. **LangChain适配**: 提供 `get_tools(prefix)` 方法给Agent使用
4. **基础错误处理**:
   - 工具调用失败时返回友好错误信息
   - 简单重试机制(1次)
   - 记录错误日志

#### **5.3 核心代码结构**

```python
class McpManager:
    def __init__(self, config_path):
        self.servers = {}  # {name: McpConnection}
        self.tools = {}    # {tool_name: server_name}
        
    def call_tool(self, tool_name, params):
        """调用工具,带错误处理和重试"""
        try:
            server = self.tools.get(tool_name)
            return server.call(tool_name, params)
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            # 重试一次
            return server.call(tool_name, params)
    
    def get_langchain_tools(self, prefix):
        """返回指定前缀的LangChain工具列表"""
        pass
```

**关键点**:

- ✅ 配置化,不需要复杂的动态注册
- ✅ 本地进程,不需要心跳重连(挂了就重启)
- ✅ 简单映射表,不需要复杂的路由器

---

### **6\. 多个 MCP Server（工具服务层）**

####  **6.1 network-mcp**

* **提供工具**：  
  * network.ping  
  * network.traceroute  
  * network.mtr  
  * network.nslookup  
  * system.ls / system.cat\_log 等  
* **内部实现**：  
  * Python subprocess 调用系统命令  
  * 对输出做解析，返回结构化 JSON \+ 原始文本

####  **6.2 rag-mcp**

* **提供工具**：  
  * rag.search\_cases(query, tags, limit)  
  * rag.search\_docs(query, filters, limit)  
  * rag.summarize\_context(context, question)  
  * rag.similar\_incidents(diag\_json, limit)  
* **内部实现（RAG）**：  
  * 调用向量库（Chroma / Qdrant / pgvector…）  
  * 调 embeddings 模型构向量（可以也是 Ollama 模型，或专用 embedding）  
  * 组合检索结果（文档片段 / 历史 case）返回

####  **6.3 将来可以挂更多：**

* cmdb-mcp：查机器、链路、配置。  
* ticket-mcp：生成/更新工单。  
* metrics-mcp：查监控指标。

**对 MCP Bus 来说**，只是多了几个 server，多了几组 xxx.\* 前缀工具。

---

### **7\. 原子工具层（本地命令 / 存储）**

* 系统命令：  
  * ping, traceroute, mtr, nslookup, dig, ls, cat, …  
* 存储：  
  * vector DB、日志库（ES、ClickHouse）、CMDB DB  
* HTTP：  
  * 内部 API、云服务 API、监控平台 API

 这些都不直接暴露给 Agent，而是包在 MCP Server 里面，统一通过 MCP 协议对上公开。

---

## **三、典型调用链（用两个场景说明关系）**

###  **场景 1：用户要求「帮我诊断 8.8.8.8 网络情况」**

1\. 用户在 OpenWebUI 输入：  
  “帮我诊断一下到 8.8.8.8 的网络，看看丢包、路径和 DNS。”  
​  
2\. OpenWebUI → Graph Service（LangGraph HTTP API）  
  \- body: {message: "...", session\_id: ...}  
​  
3\. LangGraph:  
  3.1 UserInputNode：把 message 写入 state  
  3.2 RouterNode：  
      \- 判断这是“网络诊断”意图  
      \- 将 flow 导向 NetworkAgentNode  
​  
4\. NetworkAgentNode（内部是 LangChain NetworkDiagAgent）：  
  4.1 从 MCP Bus adapter 拿 tools \= build\_langchain\_tools(prefix="network.")  
  4.2 用 LLM（Ollama）+ ReAct / Tools 规划：  
      \- 调用 network.ping(target="8.8.8.8", count=4)  
      \- 如果有丢包，再调用 network.traceroute(...)  
  4.3 对每次工具调用：  
      \- 实际函数调用：lc\_tool(...) → adapter → mcp\_bus.call\_tool(...)  
      \- mcp\_bus → router → network-mcp → ping/traceroute → 系统命令  
      \- 结果 JSON 回到 Agent  
  4.4 Agent 聚合结果，生成一个结构化诊断 JSON \+ 文本总结  
  4.5 把这些写入 LangGraph state  
​  
5\. FinalAnswerNode：  
  \- 根据 state 中的诊断结果，生成给用户看的最终说明  
  \- 返回给 Graph Service → OpenWebUI → 用户看到结果

### **场景 2：诊断完再请 RAG 分析历史案例**

在场景 1 的基础上：  
6\. LangGraph Router 发现：  
  \- “有诊断结果了，可以让 RAG 再分析一下历史案例/最佳实践”  
  → 流程进入 RagAgentNode  
​  
7\. RagAgentNode（LangChain RagAgent）：  
  7.1 tools \= build\_langchain\_tools(prefix="rag.")  
  7.2 把 NetworkDiagAgent 的诊断 JSON \+ 用户问题整理成 prompt  
  7.3 通过 LLM 规划：  
      \- 调用 rag.search\_cases(query="BGP 丢包 8.8.8.8 类似场景")  
      \- 调用 rag.summarize\_context(context=\<检索结果 \+ 诊断 JSON\>)  
  7.4 对工具调用仍然走：  
      rag.\* Tool → LangChain Tool → MCP Bus → rag-mcp → vectorDB/日志库  
​  
8\. RagAgent 输出：  
  \- 历史上类似故障的解决方案  
  \- 是否存在已知 bug 或运营商问题  
  \- 建议的下一步（如提工单、扩容、改路由策略）  
​  
9\. FinalAnswerNode：  
  \- 把“实时诊断 \+ RAG 分析”融合成一个完整的报告：  
    \- 当前状态：可达/不可达、丢包、路径问题点  
    \- 历史案例：类似问题的原因/解决方案  
    \- 建议操作：xx 步骤  
  \- 返回给 OpenWebUI。  
---

## **四、扩展性设计(简化版)**

### **1\. 新增MCP Server**

```yaml
# 在mcp_config.yaml中添加
- name: cmdb-mcp
  command: python
  args: ["cmdb_mcp_server.py"]
  tools_prefix: "cmdb"
```

重启服务即可,无需代码修改。

### **2\. 新增Agent**

1. 创建新的Agent类(继承LangChain Agent)
2. 在LangGraph中添加节点
3. 在RouterNode添加路由规则(关键词或LLM判断)

### **3\. 更换LLM**

通过LangChain抽象,修改配置即可:

```python
# 从Ollama切换到OpenAI
llm = ChatOpenAI(model="gpt-4")  # 原来是 Ollama(model="llama3")
```

MCP层完全不受影响。

### **4\. 新增UI**

新UI只需调用Graph Service的HTTP API,后端无需改动。

---

---

## **五、架构总结与核心价值**

### **核心组件**

- **OpenWebUI**: 统一交互入口,流式展示进度
- **LangGraph**: 多Agent编排,流程控制
- **LangChain Agents**: 业务逻辑封装,LLM推理
- **Ollama+LLM**: 本地推理引擎
- **MCP协议**: 工具标准化接口(配置化管理)
- **MCP Servers**: 领域工具服务(network/rag/...)

### **设计亮点**

✅ **3层清晰**: UI → 编排 → 执行,职责分明  
✅ **配置化**: MCP Server通过配置文件管理,易扩展  
✅ **本地优化**: 内存状态,简化部署,降低复杂度  
✅ **标准化**: MCP协议统一工具接口,Agent无需关心实现  
✅ **可观测**: 流式输出执行进度,错误日志记录

### **关键补充功能**

#### **1. 错误处理**

- 工具调用失败的友好提示
- 简单重试机制(1次)
- 错误日志记录

```python
try:
    result = mcp_manager.call_tool("network.ping", params)
except ToolCallError as e:
    logger.error(f"工具调用失败: {e}")
    return {"error": "网络诊断工具暂时不可用,请稍后重试"}
```

#### **2. 流式输出**

```python
# OpenWebUI实时展示
"正在执行: ping 8.8.8.8..."
"正在执行: traceroute..."
"正在检索历史案例..."
```

#### **3. 调试日志**

```python
logger.info(f"[NetworkAgent] 调用工具: network.ping")
logger.info(f"[RagAgent] 检索到 {len(results)} 条案例")
logger.error(f"[MCP] 工具调用失败: {error}")
```

### **适用场景**

✅ 本地部署的AI Agent系统  
✅ 需要多工具协作的复杂任务  
✅ 需要流程编排的多步骤场景  
✅ 需要扩展性但不想过度设计

---

**这套架构在保证核心价值(扩展性、可维护性)的同时,针对本地部署做了合理简化,避免了过度设计。**
