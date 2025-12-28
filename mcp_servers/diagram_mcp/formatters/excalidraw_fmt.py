import json
import uuid
import os
from typing import List, Dict, Any
from ..models import Topology, NodeType

class ExcalidrawFormatter:
    def __init__(self, template_path: str = None):
        if template_path:
             self.template_path = template_path
        else:
            # Default to adjacent templates dir
            base_dir = os.path.dirname(os.path.dirname(__file__))
            self.template_path = os.path.join(base_dir, "templates", "excalidraw_schema.json")

    def format(self, topology: Topology) -> str:
        with open(self.template_path, 'r') as f:
            data = json.load(f)
            
        elements = []
        
        # 1. Render Containers
        for container in topology.containers:
            # Render a dashed rectangle
            rect = self._create_rectangle(
                id=container.id,
                x=container.x or 0,
                y=container.y or 0,
                width=container.width or 200,
                height=container.height or 200,
                label=container.label,
                strokeStyle="dashed",
                backgroundColor="#f0f0f0",
                opacity=30
            )
            elements.extend(rect)
            
        # 2. Render Nodes
        for node in topology.nodes:
            # Render node shape + label
            node_elements = self._create_node_shape(node)
            elements.extend(node_elements)
            
        # 3. Render Edges
        # Simple line connection. In Excalidraw, binding text to arrows requires specific IDs
        # We need to look up component IDs.
        # Since _create_node_shape returns a group or list, we assume the First element is the bindable shape.
        
        # Map node_id -> node object for coordinate lookup
        node_map = {node.id: node for node in topology.nodes}
        
        for edge in topology.edges:
            arrow = self._create_arrow(edge, node_map)
            elements.append(arrow)
            
        data["elements"] = elements
        return json.dumps(data, indent=2)

    def _create_rectangle(self, id, x, y, width, height, label, strokeStyle="solid", backgroundColor="transparent", opacity=100) -> List[Dict]:
        """
        Returns list of elements: [Rectangle, Text]
        """
        rect_id = id
        text_id = f"{id}-text"
        
        rect = {
            "id": rect_id,
            "type": "rectangle",
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "angle": 0,
            "strokeColor": "#000000",
            "backgroundColor": backgroundColor,
            "fillStyle": "solid",
            "strokeWidth": 1,
            "strokeStyle": strokeStyle,
            "roughness": 1,
            "opacity": opacity,
            "groupIds": [],
            "roundness": { "type": 3 },
            "seed": 1,
            "version": 1,
            "versionNonce": 0,
            "isDeleted": False,
            "boundElements": [{"id": text_id, "type": "text"}]
        }
        
        # Centered Text
        text_x = x + width/2 
        text_y = y - 30 # Label above container
        
        text = {
            "id": text_id,
            "type": "text",
            "x": text_x,
            "y": text_y,
            "width": len(label) * 8 + 10, # dynamic width approx
            "height": 20,
            "angle": 0,
            "strokeColor": "#000000",
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 1,
            "strokeStyle": "solid",
            "roughness": 1,
            "opacity": 100,
            "groupIds": [],
            "roundness": None,
            "seed": 1,
            "version": 1,
            "versionNonce": 0,
            "isDeleted": False,
            "text": label,
            "fontSize": 16,
            "fontFamily": 1,
            "textAlign": "center",
            "verticalAlign": "middle",
            "containerId": rect_id
        }
        return [rect, text]

    def _create_node_shape(self, node) -> List[Dict]:
        # Based on type, different shape/color
        bg_color = "transparent"
        if node.type == NodeType.ROUTER:
            bg_color = "#ffcccc" # Light Red
        elif node.type == NodeType.SWITCH:
            bg_color = "#ccffcc" # Light Green
        elif node.type == NodeType.FIREWALL:
            bg_color = "#ffcc99" # Orange
        elif node.type == NodeType.DATABASE:
            bg_color = "#ccccff" # Blue
            
        width = node.width or 80
        height = node.height or 80
        
        # Convert center coordinates (from LayoutEngine) to top-left (for Excalidraw)
        top_left_x = node.x - width / 2
        top_left_y = node.y - height / 2

        return self._create_rectangle(
            id=node.id, 
            x=top_left_x, 
            y=top_left_y, 
            width=width, 
            height=height, 
            label=node.label,
            backgroundColor=bg_color
        )

    def _create_arrow(self, edge, node_map: Dict[str, Any]) -> Dict:
        # Calculate start and end points based on node centers
        source_node = node_map.get(edge.source)
        target_node = node_map.get(edge.target)
        
        start_x, start_y = 0, 0
        end_x, end_y = 100, 100
        
        if source_node:
            start_x = source_node.x
            start_y = source_node.y
            
        if target_node:
            end_x = target_node.x
            end_y = target_node.y
            
        return {
            "id": f"edge-{edge.source}-{edge.target}",
            "type": "arrow",
            "x": start_x, 
            "y": start_y, 
            "width": abs(end_x - start_x),
            "height": abs(end_y - start_y),
            "angle": 0,
            "strokeColor": "#000000",
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 1,
            "strokeStyle": "solid",
            "roughness": 1,
            "opacity": 100,
            "startBinding": {"elementId": edge.source, "focus": 0.0, "gap": 1},
            "endBinding": {"elementId": edge.target, "focus": 0.0, "gap": 1},
            "points": [[0, 0], [end_x - start_x, end_y - start_y]]
        }
