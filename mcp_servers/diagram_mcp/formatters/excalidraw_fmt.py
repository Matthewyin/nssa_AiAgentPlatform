"""
Excalidraw JSON 生成器
将拓扑数据生成为 Excalidraw 格式的 JSON

参考实现：https://github.com/Matthewyin/topfac/blob/main/server/services/ExcalidrawService.js
坐标系统：左上角坐标（与 LayoutEngine 统一）
"""
import json
import os
import time
import random
from typing import List, Dict, Any, Optional, Tuple
from ..models import Topology, NodeType, Container, Node, Edge


class ExcalidrawFormatter:
    """Excalidraw JSON 格式化器"""
    
    # 容器背景颜色（与 Draw.io 统一）
    CONTAINER_COLORS = {
        NodeType.ENVIRONMENT: "#CCCCFF",   # 淡紫色
        NodeType.DATACENTER: "#FFE6CC",    # 淡橙色
        NodeType.NETWORK_AREA: "#E6FFCC",  # 淡绿色
        NodeType.ZONE: "#E6FFCC",
    }
    
    # 设备背景颜色
    DEVICE_COLORS = {
        NodeType.ROUTER: "#e7f5ff",
        NodeType.SWITCH: "#ebfbee",
        NodeType.FIREWALL: "#fff5f5",
        NodeType.SERVER: "#fff9db",
        NodeType.DATABASE: "#f3f0ff",
    }
    
    # 默认颜色
    DEFAULT_CONTAINER_COLOR = "#f1f3f5"
    DEFAULT_DEVICE_COLOR = "#ffffff"
    
    def __init__(self, template_path: str = None):
        if template_path:
            self.template_path = template_path
        else:
            base_dir = os.path.dirname(os.path.dirname(__file__))
            self.template_path = os.path.join(base_dir, "templates", "excalidraw_schema.json")
        
        # 元素索引计数器
        self._index_counter = 0
        # ID 映射：原始 ID -> Excalidraw 元素 ID
        self._id_map: Dict[str, str] = {}

    def format(self, topology: Topology) -> str:
        """
        生成 Excalidraw JSON
        
        Args:
            topology: 拓扑数据（坐标已由 LayoutEngine 计算，使用左上角坐标系）
            
        Returns:
            Excalidraw JSON 字符串
        """
        # 重置状态
        self._index_counter = 0
        self._id_map = {}
        self._elements_map: Dict[str, Dict] = {}  # 元素 ID -> 元素对象（用于后续更新 boundElements）
        
        # 加载模板
        try:
            with open(self.template_path, 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            # 如果模板不存在，使用默认结构
            data = {
                "type": "excalidraw",
                "version": 2,
                "source": "nssa-agent",
                "elements": [],
                "appState": {
                    "gridSize": None,
                    "viewBackgroundColor": "#ffffff"
                },
                "files": {}
            }
        
        elements = []
        
        # 构建映射
        container_map = {c.id: c for c in topology.containers}
        node_map = {n.id: n for n in topology.nodes}
        
        # 1. 渲染容器（按层级顺序，父容器先渲染）
        rendered_containers = set()
        
        def render_container(container: Container):
            """递归渲染容器"""
            if container.id in rendered_containers:
                return
            
            # 先渲染父容器
            if container.parent and container.parent in container_map:
                parent = container_map[container.parent]
                if parent.id not in rendered_containers:
                    render_container(parent)
            
            rendered_containers.add(container.id)
            
            # 确定分组 ID
            group_ids = []
            if container.parent and container.parent in container_map:
                group_ids.append(f"group-{container.parent}")
            
            # 获取颜色（确保类型匹配）
            bg_color = self._get_container_color(container.type)
            
            # 创建容器矩形
            rect_elements = self._create_container_rectangle(
                id=container.id,
                x=container.x or 0,
                y=container.y or 0,
                width=container.width or 200,
                height=container.height or 200,
                label=container.label,
                background_color=bg_color,
                group_ids=group_ids
            )
            elements.extend(rect_elements)
        
        # 渲染所有容器
        for container in topology.containers:
            render_container(container)
        
        # 2. 渲染节点（设备）
        for node in topology.nodes:
            # 确定分组 ID
            group_ids = []
            if node.container and node.container in container_map:
                group_ids.append(f"group-{node.container}")
            
            # 获取颜色
            bg_color = self._get_device_color(node.type)
            
            # 创建设备矩形
            node_elements = self._create_device_rectangle(
                id=node.id,
                x=node.x or 0,
                y=node.y or 0,
                width=node.width or 180,
                height=node.height or 50,
                label=node.label,
                background_color=bg_color,
                group_ids=group_ids
            )
            elements.extend(node_elements)
        
        # 3. 渲染连接线（并更新节点的 boundElements）
        for edge in topology.edges:
            arrow = self._create_arrow(edge, node_map)
            if arrow:
                elements.append(arrow)
                # 更新源节点和目标节点的 boundElements
                self._add_arrow_binding(edge.source, arrow["id"])
                self._add_arrow_binding(edge.target, arrow["id"])
        
        data["elements"] = elements
        return json.dumps(data, indent=2, ensure_ascii=False)

    def _get_container_color(self, node_type: NodeType) -> str:
        """获取容器颜色"""
        # 处理字符串类型
        if isinstance(node_type, str):
            node_type_str = node_type.lower()
            for nt in NodeType:
                if nt.value == node_type_str or nt.name.lower() == node_type_str:
                    return self.CONTAINER_COLORS.get(nt, self.DEFAULT_CONTAINER_COLOR)
            return self.DEFAULT_CONTAINER_COLOR
        
        return self.CONTAINER_COLORS.get(node_type, self.DEFAULT_CONTAINER_COLOR)

    def _get_device_color(self, node_type: NodeType) -> str:
        """获取设备颜色"""
        # 处理字符串类型
        if isinstance(node_type, str):
            node_type_str = node_type.lower()
            for nt in NodeType:
                if nt.value == node_type_str or nt.name.lower() == node_type_str:
                    return self.DEVICE_COLORS.get(nt, self.DEFAULT_DEVICE_COLOR)
            return self.DEFAULT_DEVICE_COLOR
        
        return self.DEVICE_COLORS.get(node_type, self.DEFAULT_DEVICE_COLOR)

    def _next_index(self) -> str:
        """生成下一个元素索引"""
        self._index_counter += 1
        # 使用 base62 编码生成索引字符串
        return f"b{self._index_counter:02x}"

    def _generate_seed(self) -> int:
        """生成随机种子"""
        return random.randint(1, 2147483647)

    def _generate_nonce(self) -> int:
        """生成版本随机数"""
        return random.randint(1, 2147483647)

    def _current_timestamp(self) -> int:
        """获取当前时间戳（毫秒）"""
        return int(time.time() * 1000)

    def _add_arrow_binding(self, node_id: str, arrow_id: str):
        """
        将箭头绑定添加到节点的 boundElements 中
        
        Args:
            node_id: 节点原始 ID
            arrow_id: 箭头元素 ID
        """
        # 获取 Excalidraw 元素 ID
        element_id = self._id_map.get(node_id, node_id)
        
        # 获取元素对象
        element = self._elements_map.get(element_id)
        if element and "boundElements" in element:
            # 添加箭头绑定
            element["boundElements"].append({
                "id": arrow_id,
                "type": "arrow"
            })

    def _create_container_rectangle(self, id: str, x: float, y: float, 
                                     width: float, height: float, label: str,
                                     background_color: str,
                                     group_ids: List[str] = None) -> List[Dict]:
        """
        创建容器矩形（虚线边框，标签在顶部居中）
        
        Returns:
            [矩形元素, 文本元素]
        """
        rect_id = id
        text_id = f"{id}-text"
        gids = group_ids or []
        timestamp = self._current_timestamp()
        
        # 保存 ID 映射
        self._id_map[id] = rect_id
        
        rect = {
            "id": rect_id,
            "type": "rectangle",
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "angle": 0,
            "strokeColor": "#333333",
            "backgroundColor": background_color,
            "fillStyle": "solid",
            "strokeWidth": 2,
            "strokeStyle": "dashed",
            "roughness": 0,
            "opacity": 100,
            "groupIds": gids,
            "frameId": None,
            "index": self._next_index(),
            "roundness": {"type": 3},
            "seed": self._generate_seed(),
            "version": 1,
            "versionNonce": self._generate_nonce(),
            "isDeleted": False,
            "boundElements": [{"id": text_id, "type": "text"}],
            "updated": timestamp,
            "link": None,
            "locked": False
        }
        
        # 保存元素引用（用于后续添加箭头绑定）
        self._elements_map[rect_id] = rect
        
        # 标签文本（容器中心位置）
        text_width = len(label) * 12  # 估算文本宽度
        text_height = 20
        text_x = x + (width - text_width) / 2
        text_y = y + (height - text_height) / 2
        
        text = {
            "id": text_id,
            "type": "text",
            "x": text_x,
            "y": text_y,
            "width": text_width,
            "height": text_height,
            "angle": 0,
            "strokeColor": "#000000",
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 1,
            "strokeStyle": "solid",
            "roughness": 1,
            "opacity": 100,
            "groupIds": [],
            "frameId": None,
            "index": self._next_index(),
            "roundness": None,
            "seed": self._generate_seed(),
            "version": 1,
            "versionNonce": self._generate_nonce(),
            "isDeleted": False,
            "boundElements": [],
            "updated": timestamp,
            "link": None,
            "locked": False,
            "text": label,
            "rawText": "",
            "fontSize": 16,
            "fontFamily": 1,
            "textAlign": "center",
            "verticalAlign": "middle",
            "containerId": rect_id,
            "originalText": label,
            "autoResize": True,
            "lineHeight": 1.25
        }
        
        return [rect, text]

    def _create_device_rectangle(self, id: str, x: float, y: float,
                                  width: float, height: float, label: str,
                                  background_color: str,
                                  group_ids: List[str] = None) -> List[Dict]:
        """
        创建设备矩形（实线边框，标签居中）
        
        Returns:
            [矩形元素, 文本元素]
        """
        rect_id = id
        text_id = f"{id}-text"
        gids = group_ids or []
        timestamp = self._current_timestamp()
        
        # 保存 ID 映射
        self._id_map[id] = rect_id
        
        rect = {
            "id": rect_id,
            "type": "rectangle",
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "angle": 0,
            "strokeColor": "#333333",
            "backgroundColor": background_color,
            "fillStyle": "solid",
            "strokeWidth": 2,
            "strokeStyle": "solid",
            "roughness": 0,
            "opacity": 100,
            "groupIds": gids,
            "frameId": None,
            "index": self._next_index(),
            "roundness": {"type": 3},
            "seed": self._generate_seed(),
            "version": 1,
            "versionNonce": self._generate_nonce(),
            "isDeleted": False,
            "boundElements": [{"id": text_id, "type": "text"}],
            "updated": timestamp,
            "link": None,
            "locked": False
        }
        
        # 保存元素引用（用于后续添加箭头绑定）
        self._elements_map[rect_id] = rect
        
        # 标签文本（设备中心位置）
        text_width = len(label) * 12
        text_height = 20
        text_x = x + (width - text_width) / 2
        text_y = y + (height - text_height) / 2
        
        text = {
            "id": text_id,
            "type": "text",
            "x": text_x,
            "y": text_y,
            "width": text_width,
            "height": text_height,
            "angle": 0,
            "strokeColor": "#000000",
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 1,
            "strokeStyle": "solid",
            "roughness": 1,
            "opacity": 100,
            "groupIds": [],
            "frameId": None,
            "index": self._next_index(),
            "roundness": None,
            "seed": self._generate_seed(),
            "version": 1,
            "versionNonce": self._generate_nonce(),
            "isDeleted": False,
            "boundElements": [],
            "updated": timestamp,
            "link": None,
            "locked": False,
            "text": label,
            "rawText": "",
            "fontSize": 16,
            "fontFamily": 1,
            "textAlign": "center",
            "verticalAlign": "middle",
            "containerId": rect_id,
            "originalText": label,
            "autoResize": True,
            "lineHeight": 1.25
        }
        
        return [rect, text]

    def _create_arrow(self, edge: Edge, node_map: Dict[str, Node]) -> Optional[Dict]:
        """
        创建箭头连接线
        
        Args:
            edge: 边对象
            node_map: 节点 ID -> 节点对象映射
            
        Returns:
            箭头元素，如果源或目标不存在则返回 None
        """
        source_node = node_map.get(edge.source)
        target_node = node_map.get(edge.target)
        
        if not source_node or not target_node:
            return None
        
        # 获取 Excalidraw 元素 ID
        source_element_id = self._id_map.get(edge.source, edge.source)
        target_element_id = self._id_map.get(edge.target, edge.target)
        
        # 计算连接点（使用节点中心）
        source_width = source_node.width or 180
        source_height = source_node.height or 50
        target_width = target_node.width or 180
        target_height = target_node.height or 50
        
        start_x = (source_node.x or 0) + source_width / 2
        start_y = (source_node.y or 0) + source_height / 2
        end_x = (target_node.x or 0) + target_width / 2
        end_y = (target_node.y or 0) + target_height / 2
        
        # 计算相对位移
        dx = end_x - start_x
        dy = end_y - start_y
        
        timestamp = self._current_timestamp()
        
        return {
            "id": f"edge-{edge.source}-{edge.target}",
            "type": "arrow",
            "x": start_x,
            "y": start_y,
            "width": abs(dx),
            "height": abs(dy),
            "angle": 0,
            "strokeColor": "#000000",
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 1,
            "strokeStyle": "solid",
            "roughness": 1,
            "opacity": 100,
            "groupIds": [],
            "frameId": None,
            "index": self._next_index(),
            "roundness": None,
            "seed": self._generate_seed(),
            "version": 1,
            "versionNonce": self._generate_nonce(),
            "isDeleted": False,
            "boundElements": [],
            "updated": timestamp,
            "link": None,
            "locked": False,
            "startBinding": {
                "elementId": source_element_id,
                "focus": 0.0,
                "gap": 1
            },
            "endBinding": {
                "elementId": target_element_id,
                "focus": 0.0,
                "gap": 1
            },
            "points": [[0, 0], [dx, dy]],
            "lastCommittedPoint": None,
            "startArrowhead": None,
            "endArrowhead": "arrow"
        }
