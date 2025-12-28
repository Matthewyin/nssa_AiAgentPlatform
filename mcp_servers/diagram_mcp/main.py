import asyncio
import sys
import os
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from mcp.server import Server
from mcp.types import Tool, TextContent
from loguru import logger

from .models import Topology
from .layout_engine import LayoutEngine
from .formatters.mermaid_fmt import MermaidFormatter
from .formatters.excalidraw_fmt import ExcalidrawFormatter
from .formatters.drawio_fmt import DrawIOFormatter

# Initialize Server
app = Server("diagram-mcp")

# Configuration
# Artifacts root: nssa_AiAgentPlatform/data/artifacts
PROJECT_ROOT = Path(__file__).parent.parent.parent
ARTIFACTS_ROOT = PROJECT_ROOT / "data" / "artifacts"

def _ensure_artifact_dir() -> Path:
    date_str = datetime.now().strftime("%Y-%m-%d")
    task_id = str(uuid.uuid4())[:8] # Short UUID for grouping if needed, or just day bucket
    # Actually, let's just use date bucket and random filenames for now. 
    # Or create a new folder per request? 
    # For MVP, Date bucket is fine.
    
    path = ARTIFACTS_ROOT / date_str
    path.mkdir(parents=True, exist_ok=True)
    return path

def _save_file(content: str, ext: str) -> str:
    """
    Saves content to file and returns the relative URL path (e.g., /files/2023-10-xx/uuid.ext).
    """
    path = _ensure_artifact_dir()
    file_id = str(uuid.uuid4())
    filename = f"{file_id}.{ext}"
    full_path = path / filename
    
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    # Construct URL path. ToolGateway maps /files to data/artifacts
    relative_path = full_path.relative_to(ARTIFACTS_ROOT)
    
    # Load environment variables to construct absolute URL
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
    
    host = os.getenv("GRAPH_SERVICE_HOST", "localhost")
    if host == "0.0.0.0":
        host = "localhost"
    port = os.getenv("GRAPH_SERVICE_PORT", "30021")
    
    base_url = f"http://{host}:{port}"
    
    return f"{base_url}/files/{relative_path}"

@app.list_tools()
async def list_tools() -> List[Tool]:
    """
    List available diagram generation tools.
    Reads from config/tools_config.yaml under tools.network section, but filters for diagram tools.
    """
    tools = []
    
    try:
        config = load_tools_config()
        # Read from 'network' section now
        network_tools = config.get("tools", {}).get("network", {})
        
        # Filter for our specific tools
        target_tools = ["network.generate_mermaid", "network.generate_excalidraw", "network.generate_drawio"]
        
        for tool_key, tool_config in network_tools.items():
            name = tool_config.get("name")
            
            # Key filter: Only include the diagram tools we care about
            if name not in target_tools:
                continue

            description = tool_config.get("description")
            
            # Construct input schema
            # We assume the config in YAML closely matches the JSON Schema structure 
            # or is simplified. Here we reconstruct it.
            properties = {}
            required_params = []
            
            for param_name, param_cfg in tool_config.get("parameters", {}).items():
                properties[param_name] = {
                    "type": param_cfg.get("type"),
                    "description": param_cfg.get("description")
                }
                if param_cfg.get("required"):
                    required_params.append(param_name)
            
            # Create Tool object
            tool = Tool(
                name=name,
                description=description,
                inputSchema={
                    "type": "object",
                    "properties": properties,
                    "required": required_params,
                    "additionalProperties": False # Enforce strict schema if needed
                }
            )
            tools.append(tool)
            
    except Exception as e:
        # Fallback or log error if config fails
        # For now, let's just log and return empty list or re-raise
        print(f"Error loading tools config: {e}")
        import traceback
        traceback.print_exc()

    return tools

@app.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    logger.info(f"Tool Call: {name}")
    
    try:
        # 1. Models Validation
        # arguments passed from LLM might be the Topology dictionary directly
        topology = Topology(**arguments)
        
        # 2. Layout Calculation
        # Only needed for Excalidraw and Drawio, but good to have consistent data
        layout_engine = LayoutEngine()
        topology = layout_engine.calculate_layout(topology)
        
        result_text = ""
        
        if name == "network.generate_mermaid":
            formatter = MermaidFormatter()
            mermaid_code = formatter.format(topology)
            
            # Save it anyway for record
            url = _save_file(mermaid_code, "mmd")
            
            # Return code block for rendering
            result_text = f"Mermaid Source (saved to {url}):\n\n```mermaid\n{mermaid_code}\n```"
            
        elif name == "network.generate_excalidraw":
            formatter = ExcalidrawFormatter()
            content = formatter.format(topology)
            url = _save_file(content, "excalidraw")
            result_text = f"Excalidraw file generated successfully.\n[📥 Download .excalidraw]({url})"
            
        elif name == "network.generate_drawio":
            formatter = DrawIOFormatter()
            content = formatter.format(topology)
            url = _save_file(content, "drawio")
            result_text = f"Draw.io file generated successfully.\n[📥 Download .drawio]({url})"
            
        else:
            raise ValueError(f"Unknown tool: {name}")
            
        return [TextContent(type="text", text=result_text)]
        
    except Exception as e:
        logger.exception("Error executing tool")
        return [TextContent(type="text", text=f"Error generating diagram: {str(e)}")]

async def main():
    logger.info("Starting Diagram MCP Server...")
    from mcp.server.stdio import stdio_server
    
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    asyncio.run(main())
