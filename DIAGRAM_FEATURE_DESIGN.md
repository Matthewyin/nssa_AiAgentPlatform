# NSSA AI Agent Platform - 绘图功能增强方案设计文档

## 1. 方案概述

本项目旨在增强现有 NSSA AI Agent 平台的运维可视化能力，通过自然语言驱动，自动生成符合行业标准的网络拓扑图、架构图或流程图。

方案采用 **"1 个 MCP Server + 3 个 Tools"** 的架构模式，结合 **"静态制品管理"** 机制，实现 Mermaid、Excalidraw、Draw.io 三种主流格式的按需生成、预览与下载。

---

## 2. 架构设计

在 "2 控制平面 + 1 执行平面" 的整体架构中，本次新增/修改的内容如下：

### 2.1. 执行平面 (Execution Plane)
*   **新增 `Diagram MCP Server`**：这是一个独立的 MCP 服务进程，负责图形计算、布局算法和文件生成。它不直接处理复杂的自然语言理解，只接收结构化的拓扑数据。

### 2.2. 控制平面 2 (Tool/MCP Control Plane)
*   **扩展 `Tool Gateway`**：增加 **静态文件服务 (Static File Server)** 能力。
    *   职责：将底层存储的生成的图片和源文件映射为 HTTP URL，供前端 WebUI 访问。

### 2.3. 控制平面 1 (Interaction Plane)
*   **复用 `Graph Service`**：现有的 Router 和 ReAct Agent 逻辑保持不变，只需感知新注册的绘图工具即可。

---

## 3. 技术栈

*   **开发语言**：Python 3.11+
*   **核心库**：
    *   `mcp`: MCP 协议 SDK（现有）。
    *   `networkx`: 图论算法库，用于计算节点与边的关系及基础布局（Spring layout 等），为 Excalidraw/Draw.io 计算 (x,y) 坐标。
    *   `lxml`: 用于构建 Draw.io 的 XML 结构。
    *   `graphviz` (可选) 或 `matplotlib`: 用于在服务端生成轻量级的 PNG 快照（Snapshot），用于 WebUI 预览。

---

## 4. 业务流程与组件交互

### 4.1. 完整调用链路

1.  **用户输入**：用户通过 WebUI 输入自然语言（例如：“扫描 192.168.1.0/24 网段，并用 Excalidraw 画出拓扑”）。
2.  **Graph Service (LLM)**：
    *   `Router` 识别意图，将任务分发给 `Network Agent`。
    *   `ReAct Agent` (调用 DeepSeek/OpenAI 等 LLM) 进行推理。
    *   **步骤 A (Think)**: Agent 决定先调用 `Network MCP` 获取扫描数据。
    *   **步骤 B (Context)**: Agent 拿到 IP 列表后，LLM 将这些离散数据转化为 **标准拓扑 JSON**。
    *   **步骤 C (Act)**: Agent 根据用户指令中的“Excalidraw”关键词，选择调用 `diagram_mcp` 服务的 `generate_excalidraw` 工具。
3.  **Tool Gateway**:
    *   接收 `call_tool` 请求，通过 `Server Registry` 查找到 `diagram_mcp` 的物理地址，转发请求。
4.  **Diagram MCP Server**:
    *   接收 JSON 数据。
    *   **Layout**: 使用 `networkx` 计算每个节点的坐标 `(x, y)`。
    *   **Render**:
        *   生成 `.excalidraw` 源文件。
        *   生成 `.png` 预览快照。
    *   **Save**: 将文件保存到共享存储 `data/artifacts/` 下。
    *   **Return**: 返回文件的访问 URL（如 `/files/20240520/topo_01.excalidraw`）。
5.  **Graph Service**:
    *   获得 URL。
    *   LLM 生成最终回复，包含 Markdown 图片语法 `![预览](/files/...)` 和下载链接 `[下载](/files/...)`。
6.  **WebUI**:
    *   用户看到预览图，点击链接下载源文件。

---

## 5. 策略分发 (Strategy Dispatch)

Agent 拥有工具调用的自主决策权（ReAct 模式）：

*   **明确指定场景**：若用户指令包含 "Mermaid", "Drawio", "Visio" (Drawio兼容) 等关键词，Agent 强制调用对应工具。
*   **模糊指令场景**（“帮我画个图”）：
    *   默认策略：优先调用 `generate_mermaid`（响应最快，WebUI 原生支持最好）。
    *   备选策略：如果节点数量巨大（>50），Mermaid 渲染可能会卡顿，Agent 可选择生成 PNG 图片工具（如果有）。
*   **多格式场景**（“生成全套格式”）：Agent 会在一次回答周期内连续调用多个工具，最后汇总输出。

---

## 6. 组件设计与复用

| 组件 | 类型 | 状态 | 职责说明 |
| :--- | :--- | :--- | :--- |
| **Graph Service** | Backend | **复用** | 负责意图理解、数据清洗（自然语言->JSON）、工具调度。 |
| **Tool Gateway** | Gateway | **修改** | 新增静态文件挂载逻辑 (`Mount /files -> data/artifacts`)。 |
| **Diagram MCP** | MCP Server | **新增** | 核心绘图服务。包含 Layout 算法、格式转换器、文件写入逻辑。 |
| **LLM Provider** | Model | **复用** | 负责提取实体关系，生成 JSON 参数。 |
| **WebUI** | Frontend | **复用** | 负责 Markdown/HTML 渲染。 |

---

## 7. 数据交互格式

Agent 调用工具时，需传入统一的中间格式（Intermediate Representation），以解耦 LLM 与具体绘图实现。

```json
{
  "title": "数据中心网络拓扑",
  "layout": "hierarchical", // 可选: spring, circular, hierarchical
  "nodes": [
    {
      "id": "dev_1",
      "label": "Core-Router-01",
      "type": "router",    // 类型决定图标: router, switch, firewall, server, cloud
      "group": "core_zone" // 分组/泳道信息
    },
    {
      "id": "dev_2",
      "label": "Access-Switch-01",
      "type": "switch",
      "group": "access_zone"
    }
  ],
  "edges": [
    {
      "source": "dev_1",
      "target": "dev_2",
      "label": "10GbE",
      "relation": "connects" // 决定连线样式: solid, dashed
    }
  ]
}
```

---

## 8. 目录结构设计

```text
nssa_AiAgentPlatform/
├── data/
│   └── artifacts/               # [新增] 静态制品存储根目录
│       └── <YYYY-MM-DD>/        # 按日期归档
│           └── <uuid>/          # 按任务ID隔离
│               ├── topology.mmd
│               ├── topology.excalidraw
│               ├── topology.drawio
│               └── preview.png
├── mcp_servers/
│   └── diagram_mcp/             # [新增] 绘图 MCP 服务
│       ├── __init__.py
│       ├── main.py              # Server 入口
│       ├── models.py            # Pydantic 数据模型 (Nodes/Edges)
│       ├── layout_engine.py     # 坐标计算引擎 (基于 NetworkX)
│       └── formatters/          # 格式转换器
│           ├── mermaid_fmt.py
│           ├── excalidraw_fmt.py
│           └── drawio_fmt.py
└── tool_gateway/
    └── static_handler.py        # [修改] 增加静态文件路由
```

---

## 9. 日志与审计

*   **审计日志**：所有的绘图请求（作为 Tool Call）都会被现有的 `Audit Logger` 自动记录，包含输入的 JSON 数据和生成的输出 URL。
*   **文件元数据**：在 `data/artifacts` 下可生成附属的 `.meta.json` 文件，记录生成时间、对应的 Session ID、Request ID，方便日后清理或追溯。


---

## 10. Tools 详细实现设计

### 10.1. 通用拓扑模型 (Universal Topology Schema)

定义一个包容性的数据结构，能够描述简单的“点-边”关系，也能描述复杂的“层级嵌套”（如 数据中心 -> 区域 -> 云 -> 应用）。这是所有 Tool 的标准输入。

```json
{
  "topology_type": "network_path", // 或 "logical_architecture", "infra_map"
  "containers": [  // 描述层级/包含关系 (机房、区域、云、子网)
    {
      "id": "dc_daguan",
      "label": "大观园生产机房",
      "type": "datacenter",
      "children": ["zone_prod"]
    },
    {
      "id": "cloud_huawei",
      "label": "华为私有云",
      "type": "cloud",
      "parent": "zone_prod",
      "children": ["app_cs"]
    }
  ],
  "nodes": [ // 具体的实体设备/应用
    {
      "id": "app_cs",
      "label": "客服应用",
      "type": "application",
      "container": "cloud_huawei", // 归属关系
      "ip": "3.251.1.x" // 可选属性
    }
  ],
  "edges": [ // 连接关系
    {
      "source": "app_cs",
      "target": "router_core",
      "label": "访问请求",
      "metadata": { "protocol": "TCP", "port": "80" }
    }
  ]
}
```

### 10.2. 布局引擎 (Layout Engine)

Excalidraw 和 Draw.io 必须依赖坐标。我们在 `layout_engine.py` 中实现核心算法：

*   **输入**：Standard Topology JSON
*   **计算逻辑**：
    1.  **构建 NetworkX 图**：将 nodes 和 edges 转化为 `nx.Graph` 对象。
    2.  **容器感知布局**：
        *   先计算 `containers` 的层级和包围盒（Bounding Box）。
        *   使用 `nx.spring_layout` 或 `multipartite_layout` 计算子节点的相对坐标，将其限制在父容器的包围盒内。
    3.  **坐标注入**：遍历所有 Node，注入 `x, y` 坐标属性。
*   **输出**：Enhanced JSON (with coordinates)

### 10.3. 各工具具体实现策略

| 工具 | 核心逻辑 | 难点与对策 |
| :--- | :--- | :--- |
| **Mermaid Formatter** | **文本拼接**<br>1. 遍历 Containers 生成 `subgraph`<br>2. 遍历 Nodes 生成节点语法<br>3. 遍历 Edges 生成连接线 | 层级嵌套语法通过递归 `subgraph` 实现。 |
| **Excalidraw Formatter** | **JSON 构造**<br>1. **Template**: 加载预定义的 Excalidraw Element JSON 模版。<br>2. **Mapping**: `type="router"` -> 组合图形(矩形+图标)。<br>3. **Position**: 应用 Layout 引擎计算的 `x,y`。<br>4. **Container**: 在底层绘制虚线大矩形框作为容器背景。 | 连线箭头路径计算复杂，MVP 阶段仅计算起点和终点，让 Excalidraw 自动连直线。 |
| **Draw.io Formatter** | **XML 构建 + 压缩**<br>1. **XML Tree**: 构建 `<mxGraphModel>...`。<br>2. **Stencils**: 建立 `type` 到 Draw.io 复杂 `style` 字符串的映射字典。<br>3. **Container**: 使用 `<mxCell group="1">` 实现嵌套。<br>4. **Encoding**: XML -> Deflate 压缩 -> Base64 编码。 | 需要维护一份完整的 Stencil 映射表，以支持路由器、防火墙等专业图标。 |

