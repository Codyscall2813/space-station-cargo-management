from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import date, datetime
from enum import Enum

# Enums for API schemas
class ActionTypeEnum(str, Enum):
    PLACEMENT = "placement"
    RETRIEVAL = "retrieval"
    REARRANGEMENT = "rearrangement"
    DISPOSAL = "disposal"
    SIMULATION = "simulation"

class WasteReasonEnum(str, Enum):
    EXPIRED = "Expired"
    DEPLETED = "Out of Uses"
    DAMAGED = "Damaged"
    OTHER = "Other"

# Coordinate schemas
class Coordinates(BaseModel):
    width: float
    depth: float
    height: float

class Position(BaseModel):
    startCoordinates: Coordinates
    endCoordinates: Coordinates

# Item schemas
class ItemBase(BaseModel):
    itemId: str
    name: str
    width: float
    depth: float
    height: float
    mass: float
    priority: int = Field(ge=1, le=100)
    expiryDate: Optional[str] = None
    usageLimit: Optional[int] = None
    preferredZone: Optional[str] = None

class ItemCreate(ItemBase):
    pass

class ItemResponse(ItemBase):
    currentUsage: int = 0
    status: str = "active"

    class Config:
        orm_mode = True

# Container schemas
class ContainerBase(BaseModel):
    containerId: str
    zone: str
    width: float
    depth: float
    height: float
    openFace: Optional[str] = "front"
    maxWeight: Optional[float] = None

class ContainerCreate(ContainerBase):
    pass

class ContainerResponse(ContainerBase):
    class Config:
        orm_mode = True

# Placement schemas
class PlacementRequest(BaseModel):
    items: List[ItemBase]
    containers: List[ContainerBase]

class PlacementPositionResponse(BaseModel):
    itemId: str
    containerId: str
    position: Position

class RearrangementStep(BaseModel):
    step: int
    action: str  # "move", "remove", "place"
    itemId: str
    fromContainer: Optional[str] = None
    fromPosition: Optional[Position] = None
    toContainer: Optional[str] = None
    toPosition: Optional[Position] = None

class PlacementResponse(BaseModel):
    success: bool
    placements: List[PlacementPositionResponse]
    rearrangements: List[RearrangementStep]

# Retrieval schemas
class SearchRequest(BaseModel):
    itemId: Optional[str] = None
    itemName: Optional[str] = None
    userId: Optional[str] = None

class RetrievalStep(BaseModel):
    step: int
    action: str  # "remove", "setAside", "retrieve", "placeBack"
    itemId: str
    itemName: str

class SearchResponse(BaseModel):
    success: bool
    found: bool
    item: Optional[Dict[str, Any]] = None
    retrievalSteps: Optional[List[RetrievalStep]] = None

class RetrievalRequest(BaseModel):
    itemId: str
    userId: Optional[str] = None
    timestamp: Optional[str] = None

class RetrievalResponse(BaseModel):
    success: bool

class PlaceRequest(BaseModel):
    itemId: str
    userId: Optional[str] = None
    timestamp: Optional[str] = None
    containerId: str
    position: Position

class PlaceResponse(BaseModel):
    success: bool

# Waste management schemas
class WasteItemResponse(BaseModel):
    itemId: str
    name: str
    reason: str  # "Expired", "Out of Uses"
    containerId: Optional[str] = None
    position: Optional[Position] = None

class WasteIdentifyResponse(BaseModel):
    success: bool
    wasteItems: List[WasteItemResponse]

class ReturnPlanRequest(BaseModel):
    undockingContainerId: str
    undockingDate: str
    maxWeight: float

class ReturnPlanStep(BaseModel):
    step: int
    itemId: str
    itemName: str
    fromContainer: str
    toContainer: str

class ReturnManifestItem(BaseModel):
    itemId: str
    name: str
    reason: str

class ReturnManifest(BaseModel):
    undockingContainerId: str
    undockingDate: str
    returnItems: List[ReturnManifestItem]
    totalVolume: float
    totalWeight: float

class ReturnPlanResponse(BaseModel):
    success: bool
    returnPlan: List[ReturnPlanStep]
    retrievalSteps: List[RetrievalStep]
    returnManifest: ReturnManifest

class UndockingRequest(BaseModel):
    undockingContainerId: str
    timestamp: Optional[str] = None

class UndockingResponse(BaseModel):
    success: bool
    itemsRemoved: int

# Simulation schemas
class SimulationItem(BaseModel):
    itemId: str
    name: Optional[str] = None

class SimulationRequest(BaseModel):
    numOfDays: Optional[int] = None
    toTimestamp: Optional[str] = None
    itemsToBeUsedPerDay: List[SimulationItem]

class SimulationItemResponse(BaseModel):
    itemId: str
    name: str
    remainingUses: Optional[int] = None

class SimulationChanges(BaseModel):
    itemsUsed: List[SimulationItemResponse]
    itemsExpired: List[SimulationItemResponse]
    itemsDepletedToday: List[SimulationItemResponse]

class SimulationResponse(BaseModel):
    success: bool
    newDate: str
    changes: SimulationChanges

# Import/Export schemas
class ImportResponse(BaseModel):
    success: bool
    itemsImported: Optional[int] = None
    containersImported: Optional[int] = None
    errors: Optional[List[Dict[str, Any]]] = None

# Logging schemas
class LogEntry(BaseModel):
    timestamp: str
    userId: Optional[str] = None
    actionType: str
    itemId: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

class LogResponse(BaseModel):
    logs: List[LogEntry]
