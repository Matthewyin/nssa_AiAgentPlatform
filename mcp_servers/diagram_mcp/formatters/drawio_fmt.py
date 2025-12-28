import zlib
import base64
import urllib.parse
from xml.etree.ElementTree import Element, SubElement, tostring
from ..models import Topology, NodeType

class DrawIOFormatter:
    def format(self, topology: Topology) -> str:
        # 1. Build standard MXGraphModel XML
        mxfile = Element('mxfile', host="nssa-agent", type="device")
        diagram = SubElement(mxfile, 'diagram', id="diagram-1", name="Page-1")
        
        mxGraphModel = Element('mxGraphModel', dx="1000", dy="1000", grid="1", gridSize="10", guides="1", tooltips="1", connect="1", arrows="1", fold="1", page="1", pageScale="1", pageWidth="827", pageHeight="1169", math="0", shadow="0")
        root = SubElement(mxGraphModel, 'root')
        
        # Layer 0 & 1
        SubElement(root, 'mxCell', id="0")
        SubElement(root, 'mxCell', id="1", parent="0")
        
        # 2. Render Nodes and Containers
        # Need to handle parenting for containers
        # Map: container_id -> parent_id (default "1")
        
        # First, render all containers
        for container in topology.containers:
            parent_id = "1"
            if container.parent:
                parent_id = container.parent
                
            style = "group"
            cell = SubElement(root, 'mxCell', id=container.id, value=container.label, style=style, vertex="1", connectable="0", parent=parent_id)
            geo = SubElement(cell, 'mxGeometry', x=str(container.x or 0), y=str(container.y or 0), width=str(container.width or 200), height=str(container.height or 200))
            geo.set("as", "geometry")

        # Render Nodes
        for node in topology.nodes:
            parent_id = "1"
            if node.container:
                parent_id = node.container
                
            style = self._get_style_for_type(node.type)
            cell = SubElement(root, 'mxCell', id=node.id, value=node.label, style=style, vertex="1", parent=parent_id)
            
            # Position is relative to parent in Draw.io if parent != 1
            # But LayoutEngine gives absolute coords usually?
            # LayoutEngine as implemented assumes global coords.
            # If using groups in Draw.io, coords are relative.
            # Adapter needed: If parent is container, subtract parent.x/y
            
            x = node.x or 0
            y = node.y or 0
            
            if node.container:
                # Find container
                cont = next((c for c in topology.containers if c.id == node.container), None)
                if cont and cont.x and cont.y:
                    x = x - cont.x
                    y = y - cont.y
            
            geo = SubElement(cell, 'mxGeometry', x=str(x), y=str(y), width=str(node.width or 80), height=str(node.height or 80))
            geo.set("as", "geometry")

        # 3. Render Edges
        for i, edge in enumerate(topology.edges):
            id = f"edge-{i}"
            style = "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;"
            cell = SubElement(root, 'mxCell', id=id, value=(edge.label or ""), style=style, edge="1", parent="1", source=edge.source, target=edge.target)
            geo = SubElement(cell, 'mxGeometry', relative="1")
            geo.set("as", "geometry")

        # 4. XML Generation & Compression
        xml_str = tostring(mxGraphModel, encoding='utf-8')
        
        # Draw.io compression format: Deflate -> Base64
        # Standard format inside <diagram>:
        # <mxfile ...><diagram ...> [Compressed Content] </diagram></mxfile>
        
        # Note: raw Deflate (no header), python zlib.compress has header by default. -15 tells zlib to suppress header.
        compressed = zlib.compress(xml_str, wbits=-15)
        encoded = base64.b64encode(compressed).decode('utf-8')
        
        diagram.text = encoded
        
        return tostring(mxfile, encoding='utf-8', method='xml').decode('utf-8')

    def _get_style_for_type(self, node_type: NodeType) -> str:
        # Simple mapping to standard shapes
        if node_type == NodeType.ROUTER:
             return "shape=mxgraph.cisco.routers.router;html=1;pointerEvents=1;dashed=0;fillColor=#036897;strokeColor=#ffffff;strokeWidth=2;verticalLabelPosition=bottom;verticalAlign=top;align=center;outlineConnect=0;"
        elif node_type == NodeType.SWITCH:
             return "shape=mxgraph.cisco.switches.workgroup_switch;html=1;pointerEvents=1;dashed=0;fillColor=#036897;strokeColor=#ffffff;strokeWidth=2;verticalLabelPosition=bottom;verticalAlign=top;align=center;outlineConnect=0;"
        elif node_type == NodeType.FIREWALL:
             return "shape=mxgraph.cisco.security.firewall;html=1;pointerEvents=1;dashed=0;fillColor=#036897;strokeColor=#ffffff;strokeWidth=2;verticalLabelPosition=bottom;verticalAlign=top;align=center;outlineConnect=0;"
        elif node_type == NodeType.CLOUD:
            return "shape=cloud;whiteSpace=wrap;html=1;"
        elif node_type == NodeType.DATABASE:
            return "shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=15;"
        else:
            return "rounded=1;whiteSpace=wrap;html=1;"
