"""
LayoutEngine - 统一布局引擎
使用左上角坐标系，支持多层级嵌套容器布局
"""
from typing import Dict, Tuple, List, Optional
from dataclasses import dataclass
from .models import Topology, Node, Container, NodeType


@dataclass
class LayoutConfig:
    """布局配置参数"""
    # 环境层
    env_padding: int = 30
    env_spacing: int = 50
    env_title_height: int = 40
    
    # 数据中心层
    dc_padding: int = 25
    dc_spacing: int = 40
    dc_title_height: int = 35
    
    # 区域层
    area_padding: int = 20
    area_spacing: int = 30
    area_title_height: int = 30
    
    # 设备层
    comp_width: int = 180
    comp_height: int = 50
    comp_spacing: int = 20
    comp_padding: int = 15  # 设备距离区域边缘的距离
    
    # 最小尺寸
    min_container_width: int = 250
    min_container_height: int = 150


class LayoutEngine:
    """
    布局引擎 - 计算拓扑图中所有元素的位置和尺寸
    
    坐标系统：左上角坐标 (x, y 表示元素左上角位置)
    子元素坐标：相对于父容器的左上角
    """
    
    def __init__(self, config: LayoutConfig = None):
        self.config = config or LayoutConfig()
    
    def calculate_layout(self, topology: Topology) -> Topology:
        """
        计算布局，返回更新后的 Topology
        
        步骤：
        1. 规范化数据（ID 大小写、父子关系同步）
        2. 自底向上计算尺寸
        3. 自顶向下计算位置
        """
        if not topology.nodes and not topology.containers:
            return topology
        
        # 1. 规范化并构建映射
        node_map, container_map = self._normalize_data(topology)
        
        # 2. 同步父子关系
        self._sync_hierarchy(node_map, container_map)
        
        # 3. 找出根容器和孤立节点
        root_ids, orphan_node_ids = self._find_roots(node_map, container_map)
        
        # 4. 自底向上计算尺寸
        for rid in root_ids:
            self._calculate_size(rid, node_map, container_map)
        
        # 为孤立节点设置默认尺寸
        for nid in orphan_node_ids:
            node = node_map[nid]
            node.width = self.config.comp_width
            node.height = self.config.comp_height
        
        # 5. 自顶向下计算位置（绝对坐标）
        current_x = 50  # 起始 X 坐标
        start_y = 50    # 起始 Y 坐标
        
        for rid in root_ids:
            container = container_map[rid]
            container.x = current_x
            container.y = start_y
            self._calculate_positions(rid, node_map, container_map)
            current_x += container.width + self.config.env_spacing
        
        # 孤立节点放在最右边
        for nid in orphan_node_ids:
            node = node_map[nid]
            node.x = current_x
            node.y = start_y
            current_x += node.width + self.config.comp_spacing
        
        return topology
    
    def _normalize_data(self, topology: Topology) -> Tuple[Dict[str, Node], Dict[str, Container]]:
        """规范化数据，构建 ID 映射"""
        def _norm(i: str) -> str:
            return str(i).strip() if i else ""
        
        node_map = {}
        for n in topology.nodes:
            n.id = _norm(n.id)
            if n.container:
                n.container = _norm(n.container)
            node_map[n.id] = n
        
        container_map = {}
        for c in topology.containers:
            c.id = _norm(c.id)
            if c.parent:
                c.parent = _norm(c.parent)
            c.children = [_norm(child) for child in c.children] if c.children else []
            container_map[c.id] = c
        
        return node_map, container_map
    
    def _sync_hierarchy(self, node_map: Dict[str, Node], container_map: Dict[str, Container]):
        """同步父子关系（双向）"""
        # 节点 -> 容器
        for nid, n in node_map.items():
            if n.container and n.container in container_map:
                if nid not in container_map[n.container].children:
                    container_map[n.container].children.append(nid)
        
        # 容器 -> 父容器
        for cid, c in container_map.items():
            if c.parent and c.parent in container_map:
                if cid not in container_map[c.parent].children:
                    container_map[c.parent].children.append(cid)
    
    def _find_roots(self, node_map: Dict[str, Node], container_map: Dict[str, Container]) -> Tuple[List[str], List[str]]:
        """找出根容器和孤立节点"""
        root_ids = []
        for cid, c in container_map.items():
            if not c.parent or c.parent not in container_map:
                root_ids.append(cid)
        
        orphan_node_ids = []
        for nid, n in node_map.items():
            if not n.container or n.container not in container_map:
                orphan_node_ids.append(nid)
        
        return root_ids, orphan_node_ids
    
    def _get_config_for_type(self, node_type: NodeType) -> Tuple[int, int, int, int]:
        """根据容器类型获取配置参数 (padding, spacing, title_height, child_spacing)"""
        if node_type == NodeType.ENVIRONMENT:
            return (self.config.env_padding, self.config.env_spacing, 
                    self.config.env_title_height, self.config.dc_spacing)
        elif node_type == NodeType.DATACENTER:
            return (self.config.dc_padding, self.config.dc_spacing,
                    self.config.dc_title_height, self.config.area_spacing)
        elif node_type == NodeType.NETWORK_AREA or node_type == NodeType.ZONE:
            return (self.config.area_padding, self.config.area_spacing,
                    self.config.area_title_height, self.config.comp_spacing)
        else:
            # 默认使用区域配置
            return (self.config.area_padding, self.config.area_spacing,
                    self.config.area_title_height, self.config.comp_spacing)
    
    def _calculate_size(self, item_id: str, node_map: Dict[str, Node], 
                        container_map: Dict[str, Container]) -> Tuple[float, float]:
        """
        自底向上计算尺寸
        返回 (width, height)
        """
        # 如果是节点
        if item_id in node_map:
            node = node_map[item_id]
            node.width = self.config.comp_width
            node.height = self.config.comp_height
            return node.width, node.height
        
        # 如果是容器
        if item_id not in container_map:
            return 0, 0
        
        container = container_map[item_id]
        padding, _, title_height, child_spacing = self._get_config_for_type(container.type)
        
        child_ids = container.children
        
        # 空容器
        if not child_ids:
            container.width = self.config.min_container_width
            container.height = self.config.min_container_height
            return container.width, container.height
        
        # 收集子元素
        children = []
        for cid in child_ids:
            if cid in container_map:
                children.append((cid, True))  # (id, is_container)
            elif cid in node_map:
                children.append((cid, False))
        
        # 递归计算子元素尺寸
        child_sizes = []
        for cid, is_cont in children:
            w, h = self._calculate_size(cid, node_map, container_map)
            child_sizes.append((cid, is_cont, w, h))
        
        # 布局策略：子容器横向排列，节点纵向排列
        sub_containers = [(cid, w, h) for cid, is_cont, w, h in child_sizes if is_cont]
        nodes = [(cid, w, h) for cid, is_cont, w, h in child_sizes if not is_cont]
        
        # 计算子容器区域尺寸（横向排列）
        sub_cont_width = 0
        sub_cont_height = 0
        if sub_containers:
            sub_cont_width = sum(w for _, w, _ in sub_containers) + child_spacing * (len(sub_containers) - 1)
            sub_cont_height = max(h for _, _, h in sub_containers)
        
        # 计算节点区域尺寸（纵向排列）
        nodes_width = 0
        nodes_height = 0
        if nodes:
            nodes_width = max(w for _, w, _ in nodes)
            nodes_height = sum(h for _, _, h in nodes) + self.config.comp_spacing * (len(nodes) - 1)
        
        # 容器总尺寸
        content_width = max(sub_cont_width, nodes_width)
        content_height = sub_cont_height + (child_spacing if sub_containers and nodes else 0) + nodes_height
        
        container.width = max(content_width + padding * 2, self.config.min_container_width)
        container.height = max(content_height + title_height + padding * 2, self.config.min_container_height)
        
        return container.width, container.height
    
    def _calculate_positions(self, container_id: str, node_map: Dict[str, Node],
                             container_map: Dict[str, Container]):
        """
        自顶向下计算位置
        容器的 x, y 已经设置好（绝对坐标）
        需要计算子元素的绝对坐标
        """
        if container_id not in container_map:
            return
        
        container = container_map[container_id]
        padding, _, title_height, child_spacing = self._get_config_for_type(container.type)
        
        # 子元素起始位置（绝对坐标）
        content_start_x = container.x + padding
        content_start_y = container.y + title_height + padding
        
        # 收集子元素
        sub_containers = []
        nodes = []
        for cid in container.children:
            if cid in container_map:
                sub_containers.append(container_map[cid])
            elif cid in node_map:
                nodes.append(node_map[cid])
        
        # 布局子容器（横向排列）
        current_x = content_start_x
        for sub_cont in sub_containers:
            sub_cont.x = current_x
            sub_cont.y = content_start_y
            self._calculate_positions(sub_cont.id, node_map, container_map)
            current_x += sub_cont.width + child_spacing
        
        # 布局节点（纵向排列，在子容器下方）
        nodes_start_y = content_start_y
        if sub_containers:
            max_sub_height = max(sc.height for sc in sub_containers)
            nodes_start_y = content_start_y + max_sub_height + child_spacing
        
        current_y = nodes_start_y
        for node in nodes:
            # 节点水平居中于容器
            node.x = container.x + (container.width - node.width) / 2
            node.y = current_y
            current_y += node.height + self.config.comp_spacing
