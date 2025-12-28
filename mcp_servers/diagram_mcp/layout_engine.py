import networkx as nx
from typing import Dict, Tuple, List
from .models import Topology, Node, Container

class LayoutEngine:
    def __init__(self):
        pass

    def calculate_layout(self, topology: Topology, canvas_width=2000, canvas_height=2000) -> Topology:
        """
        Calculates layout ensuring hierarchy containment.
        1. Build hierarchy tree.
        2. Calculate size of each container recursively (bottom-up).
        3. Assign coordinates recursively (top-down).
        """
        if not topology.nodes and not topology.containers:
            return topology

        # 1. Map building
        node_map = {n.id: n for n in topology.nodes}
        container_map = {c.id: c for c in topology.containers}
        
        # Identify roots (containers with no valid parent in this topology)
        # Note: Container.parent might be set, but if parent is not in topology.containers, it's a root here.
        container_ids = set(c.id for c in topology.containers)
        root_containers = []
        for c in topology.containers:
            if not c.parent or c.parent not in container_ids:
                root_containers.append(c)
        
        # Identify orphan nodes (nodes with no valid container)
        orphan_nodes = []
        for n in topology.nodes:
            if not n.container or n.container not in container_ids:
                orphan_nodes.append(n)
        
        # 2. Recursive Size Calculation (Bottom-Up)
        # We need to know the size of everything before we position them.
        
        def calculate_size(items: List[object]) -> Tuple[float, float]:
            """
            Calculate total size needed for a list of items (nodes or containers).
            Simple strategy: Pack in a square-ish grid.
            """
            if not items:
                return 0, 0
            
            # Simple grid packing
            count = len(items)
            cols = int(count**0.5) + 1
            
            current_x = 0
            current_y = 0
            row_height = 0
            max_w = 0
            
            padding = 40
            
            for i, item in enumerate(items):
                # Get item dimensions
                w, h = 0, 0
                if isinstance(item, Node):
                    w, h = item.width or 80, item.height or 80
                elif isinstance(item, Container):
                    # Recurse!
                    # Check its children
                    child_nodes = [node_map[nid] for nid in item.children if nid in node_map]
                    child_containers = [container_map[cid] for cid in item.children if cid in container_map]
                    all_children = child_nodes + child_containers
                    
                    cw, ch = calculate_size(all_children)
                    # Update container size
                    item.width = max(cw + padding * 2, 200) # Min size
                    item.height = max(ch + padding * 2, 200) # Min size
                    w, h = item.width, item.height

                # Position in local grid (just for size calc)
                if i > 0 and i % cols == 0:
                    current_x = 0
                    current_y += row_height + padding
                    row_height = 0
                
                current_x += w + padding
                row_height = max(row_height, h)
                max_w = max(max_w, current_x)
            
            total_w = max_w
            total_h = current_y + row_height
            return total_w, total_h

        # Calculate all sizes
        # We treat roots + orphans as the top level items
        top_level_items = root_containers + orphan_nodes
        calculate_size(top_level_items) # This triggers recursion
        
        # 3. Recursive Positioning (Top-Down)
        
        def apply_positions(items: List[object], start_x: float, start_y: float):
            if not items:
                return

            count = len(items)
            cols = int(count**0.5) + 1
            padding = 40
            
            current_x = start_x
            current_y = start_y
            row_height = 0
            
            for i, item in enumerate(items):
                w, h = 0, 0
                if isinstance(item, Node):
                    w = item.width or 80
                    h = item.height or 80
                elif isinstance(item, Container):
                    w = item.width
                    h = item.height
                
                if i > 0 and i % cols == 0:
                    current_x = start_x
                    current_y += row_height + padding
                    row_height = 0
                
                # Center item in its cell? For now key is top-left
                item.x = current_x + w / 2  # Model uses center coordinates
                item.y = current_y + h / 2
                
                # If container, position its children relative to its new top-left
                if isinstance(item, Container):
                    child_nodes = [node_map[nid] for nid in item.children if nid in node_map]
                    child_containers = [container_map[cid] for cid in item.children if cid in container_map]
                    all_children = child_nodes + child_containers
                    
                    # Offset for children (inside container padding)
                    child_start_x = current_x + padding
                    child_start_y = current_y + padding
                    
                    apply_positions(all_children, child_start_x, child_start_y)

                current_x += w + padding
                row_height = max(row_height, h)

        # Apply positions starting from 0,0
        apply_positions(top_level_items, 0, 0)
        
        return topology
