from ..models import Topology, NodeType

class MermaidFormatter:
    def format(self, topology: Topology) -> str:
        lines = ["graph TD"]
        
        # Helper map for container handling
        node_to_container = {}
        container_dict = {c.id: c for c in topology.containers}
        
        # Build hierarchy map
        parent_to_children = {} # container_id -> list of child_ids (nodes or containers)
        
        # 1. Initialize logic
        # We need to render containers as subgraphs
        # We'll use a recursive function or simple 2-level loop for MVP
        
        # Identify nodes that are NOT in any container
        # And nodes that ARE in containers
        
        # A set of ID strings that have been rendered
        rendered_ids = set()

        # Render Containers (Subgraphs)
        # Note: Mermaid subgraphs are linear in code, nesting is lexical
        # subgraph ID
        #   A
        #   B
        # end
        
        # We assume 1 level of nesting for simplicity in MVP mostly (DataCenter -> Zone)
        # But let's try to do it properly with recursion if needed, 
        # or simplified: Iterate top-level containers first.
        
        # Find root containers (those without parents in the list of containers)
        # But our Model has `children` list in Container.
        
        # Strategy:
        # 1. Render all containers recursively
        # 2. Render remaining nodes
        # 3. Render edges
        
        # However, Mermaid requires nodes to be defined INSIDE the subgraph block.
        
        def render_container(container_id):
            container = container_dict.get(container_id)
            if not container:
                return
            
            lines.append(f'    subgraph {container.id}["{container.label}"]')
            rendered_ids.add(container.id)
            
            # Render children nodes
            for child_id in container.children:
                # Check if child is a node
                node = next((n for n in topology.nodes if n.id == child_id), None)
                if node:
                    lines.append(f'        {self._format_node(node)}')
                    rendered_ids.add(node.id)
                else:
                    # Check if child is a nested container
                    if child_id in container_dict:
                        render_container(child_id)
            
            lines.append("    end")

        # Start rendering
        # 1. Render Root Containers (containers that are not children of other containers)
        all_child_containers = set()
        for c in topology.containers:
            for child in c.children:
                if child in container_dict:
                    all_child_containers.add(child)
        
        root_containers = [c for c in topology.containers if c.id not in all_child_containers]
        
        for c in root_containers:
            render_container(c.id)
            
        # 2. Render Nodes not in any rendered container
        for node in topology.nodes:
            if node.id not in rendered_ids:
                lines.append(f'    {self._format_node(node)}')

        # 3. Render Edges
        # Style: A --> B
        for edge in topology.edges:
            label = edge.label
            if label:
                lines.append(f'    {edge.source} -- "{label}" --> {edge.target}')
            else:
                lines.append(f'    {edge.source} --> {edge.target}')
            
        return "\n".join(lines)

    def _format_node(self, node) -> str:
        # Shapes based on NodeType
        # ref: https://mermaid.js.org/syntax/flowchart.html#node-shapes
        # router: hexagon {{ }}? No, using standard shapes for compatibility
        # database: [()]
        # cloud: (())
        
        shape_open = "["
        shape_close = "]"
        
        if node.type == NodeType.DATABASE:
            shape_open = "[("
            shape_close = ")]"
        elif node.type == NodeType.CLOUD:
            shape_open = "(("
            shape_close = "))"
        elif node.type == NodeType.ROUTER:
             # loose approximation
            shape_open = "{{"
            shape_close = "}}"
        elif node.type == "decision": # if we had it
            shape_open = "{"
            shape_close = "}"
            
        return f'{node.id}{shape_open}"{node.label}"{shape_close}'
