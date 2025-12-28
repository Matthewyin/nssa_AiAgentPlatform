"""
DrawIO XML 生成器
将拓扑数据生成为 Draw.io 格式的 XML

参考实现：https://github.com/Matthewyin/topfac/blob/main/server/services/DrawIOService.js

Draw.io 文件格式说明：
- Draw.io 支持两种格式：压缩格式和明文格式
- 压缩格式：<diagram> 内容是 deflate 压缩 + base64 编码 + URL 编码
- 明文格式：<diagram> 内直接包含 <mxGraphModel> XML
- 本实现输出压缩格式，确保与 Draw.io 桌面版/网页版兼容
"""
import zlib
import base64
import urllib.parse
from xml.etree.ElementTree import Element, SubElement, tostring
from typing import Dict, Optional
from ..models import Topology, NodeType, Container, Node


class DrawIOFormatter:
    """Draw.io XML 格式化器"""
    
    # 容器颜色配置
    CONTAINER_COLORS = {
        NodeType.ENVIRONMENT: {"fill": "#CCCCFF", "stroke": "#9999FF"},
        NodeType.DATACENTER: {"fill": "#FFE6CC", "stroke": "#D6B656"},
        NodeType.NETWORK_AREA: {"fill": "#E6FFCC", "stroke": "#82B366"},
        NodeType.ZONE: {"fill": "#E6FFCC", "stroke": "#82B366"},
    }
    
    # 设备边框颜色配置
    DEVICE_COLORS = {
        NodeType.ROUTER: "#4CAF50",      # 绿色
        NodeType.SWITCH: "#2196F3",      # 蓝色
        NodeType.FIREWALL: "#F44336",    # 红色
        NodeType.SERVER: "#FF9800",      # 橙色
        NodeType.DATABASE: "#607D8B",    # 灰色
    }
    
    def __init__(self):
        self.cell_id = 2  # 0 和 1 被根节点占用
        self.component_id_map: Dict[str, str] = {}  # 原始 ID -> Cell ID 映射
    
    def format(self, topology: Topology) -> str:
        """
        生成 Draw.io XML
        
        Args:
            topology: 拓扑数据
            
        Returns:
            Draw.io XML 字符串（明文格式，便于调试）
        """
        self.cell_id = 2
        self.component_id_map = {}
        
        # 构建映射
        container_map = {c.id: c for c in topology.containers}
        node_map = {n.id: n for n in topology.nodes}
        
        # 生成 XML 单元格
        cells = []
        
        # 根节点
        cells.append('<mxCell id="0"/>')
        cells.append('<mxCell id="1" parent="0"/>')
        
        # 按层级顺序渲染容器（父容器先渲染）
        rendered_containers = set()
        
        def render_container(container: Container, parent_cell_id: str = "1"):
            """递归渲染容器及其子容器"""
            if container.id in rendered_containers:
                return
            
            cell_id = f"container_{self.cell_id}"
            self.cell_id += 1
            self.component_id_map[container.id] = cell_id
            rendered_containers.add(container.id)
            
            # 计算相对坐标
            rel_x, rel_y = container.x or 0, container.y or 0
            if container.parent and container.parent in container_map:
                parent = container_map[container.parent]
                rel_x = (container.x or 0) - (parent.x or 0)
                rel_y = (container.y or 0) - (parent.y or 0)
            
            # 生成容器单元格
            cells.append(self._generate_container_cell(
                cell_id=cell_id,
                label=container.label,
                x=rel_x,
                y=rel_y,
                width=container.width or 200,
                height=container.height or 200,
                node_type=container.type,
                parent_id=parent_cell_id
            ))
            
            # 递归渲染子容器
            for child_id in container.children:
                if child_id in container_map:
                    render_container(container_map[child_id], cell_id)
        
        # 找出根容器并渲染
        for container in topology.containers:
            if not container.parent or container.parent not in container_map:
                render_container(container)
        
        # 渲染节点（设备）
        for node in topology.nodes:
            cell_id = f"node_{self.cell_id}"
            self.cell_id += 1
            self.component_id_map[node.id] = cell_id
            
            # 确定父容器
            parent_cell_id = "1"
            rel_x, rel_y = node.x or 0, node.y or 0
            
            if node.container and node.container in container_map:
                parent_cell_id = self.component_id_map.get(node.container, "1")
                parent = container_map[node.container]
                rel_x = (node.x or 0) - (parent.x or 0)
                rel_y = (node.y or 0) - (parent.y or 0)
            
            cells.append(self._generate_node_cell(
                cell_id=cell_id,
                label=node.label,
                x=rel_x,
                y=rel_y,
                width=node.width or 180,
                height=node.height or 50,
                node_type=node.type,
                parent_id=parent_cell_id
            ))
        
        # 渲染连接线
        for i, edge in enumerate(topology.edges):
            edge_id = f"edge_{self.cell_id}"
            self.cell_id += 1
            
            source_id = self.component_id_map.get(edge.source)
            target_id = self.component_id_map.get(edge.target)
            
            if source_id and target_id:
                cells.append(self._generate_edge_cell(
                    cell_id=edge_id,
                    label=edge.label or "",
                    source_id=source_id,
                    target_id=target_id
                ))
        
        # 组装完整 XML
        xml_content = self._assemble_xml(cells)
        return xml_content
    
    def _generate_container_cell(self, cell_id: str, label: str, x: float, y: float,
                                  width: float, height: float, node_type: NodeType,
                                  parent_id: str) -> str:
        """生成容器单元格"""
        colors = self.CONTAINER_COLORS.get(node_type, {"fill": "#F5F5F5", "stroke": "#666666"})
        
        # 使用 swimlane 但不使用 childLayout（手动布局）
        style = (
            f"swimlane;whiteSpace=wrap;html=1;"
            f"fillColor={colors['fill']};strokeColor={colors['stroke']};"
            f"fontStyle=1;fontSize=14;startSize=30;"
        )
        
        return (
            f'<mxCell id="{cell_id}" value="{self._escape_xml(label)}" '
            f'style="{style}" vertex="1" parent="{parent_id}">\n'
            f'          <mxGeometry x="{x}" y="{y}" width="{width}" height="{height}" as="geometry"/>\n'
            f'        </mxCell>'
        )
    
    def _generate_node_cell(self, cell_id: str, label: str, x: float, y: float,
                            width: float, height: float, node_type: NodeType,
                            parent_id: str) -> str:
        """生成设备节点单元格"""
        stroke_color = self.DEVICE_COLORS.get(node_type, "#333333")
        
        # 圆角矩形，白色填充，18号黑色粗体字
        style = (
            f"rounded=1;whiteSpace=wrap;html=1;"
            f"fillColor=#FFFFFF;strokeColor={stroke_color};strokeWidth=2;"
            f"fontColor=#000000;fontSize=18;fontStyle=1;"
        )
        
        return (
            f'<mxCell id="{cell_id}" value="{self._escape_xml(label)}" '
            f'style="{style}" vertex="1" parent="{parent_id}">\n'
            f'          <mxGeometry x="{x}" y="{y}" width="{width}" height="{height}" as="geometry"/>\n'
            f'        </mxCell>'
        )
    
    def _generate_edge_cell(self, cell_id: str, label: str, source_id: str, target_id: str) -> str:
        """生成连接线单元格"""
        style = (
            "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;"
            "jettySize=auto;html=1;strokeColor=#666666;strokeWidth=2;"
        )
        
        return (
            f'<mxCell id="{cell_id}" value="{self._escape_xml(label)}" '
            f'style="{style}" edge="1" parent="1" source="{source_id}" target="{target_id}">\n'
            f'          <mxGeometry relative="1" as="geometry"/>\n'
            f'        </mxCell>'
        )
    
    def _assemble_xml(self, cells: list) -> str:
        """
        组装完整的 Draw.io XML
        
        使用明文格式（与 Draw.io 桌面版导出格式一致）
        注意：生成的 .drawio 文件需要通过 "文件 → 打开" 方式打开，
        而不是复制粘贴 XML 代码到画布上。
        """
        from datetime import datetime
        
        cells_str = "\n        ".join(cells)
        
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="Electron" modified="{datetime.now().isoformat()}" agent="NSSA AI Agent" version="21.0.0" type="device">
  <diagram name="网络拓扑图" id="topology">
    <mxGraphModel dx="2000" dy="1500" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="3000" pageHeight="2000" math="0" shadow="0">
      <root>
        {cells_str}
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>'''
    
    def _escape_xml(self, text: str) -> str:
        """XML 特殊字符转义"""
        if not text:
            return ""
        return (
            text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )
