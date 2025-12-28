
import sys
import os
import json
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from mcp_servers.diagram_mcp.models import Topology, Node, Edge, Container, NodeType
from mcp_servers.diagram_mcp.layout_engine import LayoutEngine
from mcp_servers.diagram_mcp.formatters.mermaid_fmt import MermaidFormatter
from mcp_servers.diagram_mcp.formatters.excalidraw_fmt import ExcalidrawFormatter
from mcp_servers.diagram_mcp.formatters.drawio_fmt import DrawIOFormatter

def test_generation():
    print("Testing Diagram Generation...")
    
    # 1. Create sample topology
    topo = Topology(
        nodes=[
            Node(id="r1", label="Core Router", type=NodeType.ROUTER),
            Node(id="s1", label="Access Switch", type=NodeType.SWITCH, container="datacenter"),
            Node(id="pc1", label="User PC", type=NodeType.PC, container="office")
        ],
        edges=[
            Edge(source="r1", target="s1", label="Uplink"),
            Edge(source="s1", target="pc1", label="LAN")
        ],
        containers=[
            Container(id="datacenter", label="Data Center", children=["s1"]),
            Container(id="office", label="Office Area", children=["pc1"])
        ]
    )
    
    # 2. Layout
    engine = LayoutEngine()
    topo = engine.calculate_layout(topo)
    print("Layout calculated.")
    
    # 3. Mermaid
    mermaid_fmt = MermaidFormatter()
    mermaid_out = mermaid_fmt.format(topo)
    print("\n[Mermaid Output]:")
    print(mermaid_out[:100] + "...")
    assert "subgraph datacenter" in mermaid_out
    
    # 4. Excalidraw
    excalidraw_fmt = ExcalidrawFormatter()
    excalidraw_out = excalidraw_fmt.format(topo)
    print("\n[Excalidraw Output]:")
    print(excalidraw_out[:100] + "...")
    assert "excalidraw" in excalidraw_out
    
    # 5. Draw.io
    drawio_fmt = DrawIOFormatter()
    drawio_out = drawio_fmt.format(topo)
    print("\n[Draw.io Output]:")
    print(drawio_out[:100] + "...")
    assert "<mxfile" in drawio_out
    
    print("\nAll formatters executed successfully.")

if __name__ == "__main__":
    test_generation()
