from typing import List, Optional, Dict, Any, Union
from enum import Enum
from pydantic import BaseModel, Field

class NodeType(str, Enum):
    ENVIRONMENT = "environment"
    DATACENTER = "datacenter"
    NETWORK_AREA = "network_area" # Logical Zone/Area
    ZONE = "zone"
    CLOUD = "cloud"
    NETWORK_SEGMENT = "network_segment"  # Subnet
    ROUTER = "router"
    SWITCH = "switch"
    FIREWALL = "firewall"
    SERVER = "server"
    APPLICATION = "application"
    DATABASE = "database"
    STORAGE = "storage"
    INTERNET = "internet"
    USER = "user"
    PC = "pc"
    UNKNOWN = "unknown"

class EdgeRelation(str, Enum):
    CONNECTS = "connects"
    HOSTS = "hosts" # Parent-child relationship if not using containers explicitly
    ACCESSES = "accesses"
    DEPENDS_ON = "depends_on"

class Container(BaseModel):
    """
    Represents a logical grouping or physical container (e.g., Datacenter, Zone, VPC).
    """
    id: str
    label: str
    type: NodeType = NodeType.UNKNOWN
    parent: Optional[str] = None  # ID of parent container
    children: List[str] = Field(default_factory=list)  # IDs of child containers or nodes
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Layout properties (calculated by LayoutEngine)
    # 坐标系统：左上角坐标（x, y 表示元素左上角的绝对位置）
    x: Optional[float] = None
    y: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None

class Node(BaseModel):
    """
    Represents a specific entity in the topology (e.g., Device, App).
    """
    id: str
    label: str
    type: NodeType = NodeType.UNKNOWN
    container: Optional[str] = None  # ID of the container it belongs to
    ip: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Layout properties (calculated by LayoutEngine)
    # 坐标系统：左上角坐标（x, y 表示元素左上角的绝对位置）
    x: Optional[float] = None
    y: Optional[float] = None
    width: Optional[float] = None  # 由 LayoutEngine 计算
    height: Optional[float] = None  # 由 LayoutEngine 计算

class Edge(BaseModel):
    """
    Represents a connection between nodes or containers.
    """
    source: str # ID of source node/container
    target: str # ID of target node/container
    label: Optional[str] = None
    relation: EdgeRelation = EdgeRelation.CONNECTS
    metadata: Dict[str, Any] = Field(default_factory=dict)

class Topology(BaseModel):
    """
    Universal Topology Schema.
    """
    topology_type: str = "network_path"
    title: Optional[str] = "Generated Topology"
    containers: List[Container] = Field(default_factory=list)
    nodes: List[Node] = Field(default_factory=list)
    edges: List[Edge] = Field(default_factory=list)

    class Config:
        extra = "ignore"

