from sqlalchemy.orm import Session
import uuid
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Tuple
from src.models.container import Container
from src.models.item import Item, ItemStatus
from src.models.position import Position
from src.models.log import LogEntry, ActionType
from src.models.return_mission import ReturnMission, WasteItem, WasteReason

# Container CRUD operations

def get_container(db: Session, container_id: str) -> Optional[Container]:
    """Get a container by ID."""
    return db.query(Container).filter(Container.id == container_id).first()

def get_containers(db: Session, skip: int = 0, limit: int = 100) -> List[Container]:
    """Get a list of containers with pagination."""
    return db.query(Container).offset(skip).limit(limit).all()

def get_containers_by_zone(db: Session, zone: str) -> List[Container]:
    """Get containers filtered by zone."""
    return db.query(Container).filter(Container.zone == zone).all()

def create_container(db: Session, container_data: Dict[str, Any]) -> Container:
    """Create a new container."""
    db_container = Container(
        id=container_data.get("containerId", f"cont_{uuid.uuid4().hex[:8]}"),
        name=container_data.get("name", ""),
        zone=container_data.get("zone", ""),
        width=container_data.get("width"),
        depth=container_data.get("depth"),
        height=container_data.get("height"),
        open_face=container_data.get("openFace", "front"),
        max_weight=container_data.get("maxWeight")
    )
    db.add(db_container)
    db.commit()
    db.refresh(db_container)
    return db_container

# Item CRUD operations

def get_item(db: Session, item_id: str) -> Optional[Item]:
    """Get an item by ID."""
    return db.query(Item).filter(Item.id == item_id).first()

def get_item_by_name(db: Session, name: str) -> Optional[Item]:
    """Get an item by name."""
    return db.query(Item).filter(Item.name == name).first()

def get_items(db: Session, skip: int = 0, limit: int = 100) -> List[Item]:
    """Get a list of items with pagination."""
    return db.query(Item).offset(skip).limit(limit).all()

def get_active_items(db: Session) -> List[Item]:
    """Get all active (non-waste) items."""
    return db.query(Item).filter(Item.status == ItemStatus.ACTIVE).all()

def create_item(db: Session, item_data: Dict[str, Any]) -> Item:
    """Create a new item."""
    # Parse expiry date if provided
    expiry_date = None
    if item_data.get("expiryDate"):
        try:
            expiry_date = datetime.fromisoformat(item_data["expiryDate"]).date()
        except ValueError:
            # Handle invalid date format
            pass
    
    db_item = Item(
        id=item_data.get("itemId", f"item_{uuid.uuid4().hex[:8]}"),
        name=item_data.get("name", ""),
        width=item_data.get("width"),
        height=item_data.get("height"),
        depth=item_data.get("depth"),
        mass=item_data.get("mass"),
        priority=item_data.get("priority", 50),
        expiry_date=expiry_date,
        usage_limit=item_data.get("usageLimit"),
        current_usage=item_data.get("currentUsage", 0),
        preferred_zone=item_data.get("preferredZone"),
        status=ItemStatus.ACTIVE
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

def update_item(db: Session, item_id: str, item_data: Dict[str, Any]) -> Optional[Item]:
    """Update an existing item."""
    db_item = get_item(db, item_id)
    if not db_item:
        return None
    
    # Update fields if provided in item_data
    for key, value in item_data.items():
        if key == "expiryDate" and value:
            try:
                setattr(db_item, "expiry_date", datetime.fromisoformat(value).date())
            except ValueError:
                # Skip invalid date format
                pass
        elif hasattr(db_item, key):
            setattr(db_item, key, value)
    
    db.commit()
    db.refresh(db_item)
    return db_item

def mark_item_as_waste(db: Session, item_id: str, reason: WasteReason, notes: str = None) -> Tuple[Optional[Item], Optional[WasteItem]]:
    """Mark an item as waste and create a waste record."""
    db_item = get_item(db, item_id)
    if not db_item:
        return None, None
    
    # Update item status
    db_item.status = ItemStatus.WASTE if reason != WasteReason.DEPLETED else ItemStatus.DEPLETED
    
    # Create waste item record
    waste_id = f"waste_{uuid.uuid4().hex[:8]}"
    db_waste = WasteItem(
        id=waste_id,
        item_id=item_id,
        reason=reason,
        waste_date=date.today(),
        notes=notes
    )
    
    db.add(db_waste)
    db.commit()
    db.refresh(db_item)
    db.refresh(db_waste)
    return db_item, db_waste

# Position CRUD operations

def get_position(db: Session, position_id: str) -> Optional[Position]:
    """Get a position by ID."""
    return db.query(Position).filter(Position.id == position_id).first()

def get_item_position(db: Session, item_id: str) -> Optional[Position]:
    """Get the current position of an item."""
    return db.query(Position).filter(Position.item_id == item_id).order_by(Position.timestamp.desc()).first()

def get_container_positions(db: Session, container_id: str) -> List[Position]:
    """Get all positions in a specific container."""
    return db.query(Position).filter(Position.container_id == container_id).all()

def create_position(db: Session, position_data: Dict[str, Any]) -> Position:
    """Create a new position for an item in a container."""
    db_position = Position(
        id=position_data.get("id", f"pos_{uuid.uuid4().hex[:8]}"),
        item_id=position_data.get("itemId"),
        container_id=position_data.get("containerId"),
        x=position_data.get("position", {}).get("startCoordinates", {}).get("width", 0),
        y=position_data.get("position", {}).get("startCoordinates", {}).get("height", 0),
        z=position_data.get("position", {}).get("startCoordinates", {}).get("depth", 0),
        orientation=position_data.get("orientation", 0),
        visible=position_data.get("visible", False)
    )
    db.add(db_position)
    db.commit()
    db.refresh(db_position)
    return db_position

def delete_position(db: Session, position_id: str) -> bool:
    """Delete a position record."""
    db_position = get_position(db, position_id)
    if db_position:
        db.delete(db_position)
        db.commit()
        return True
    return False

# Log CRUD operations

def create_log_entry(
    db: Session, 
    operation: ActionType, 
    user_id: str = None, 
    details: Dict[str, Any] = None, 
    item_ids: List[str] = None, 
    container_ids: List[str] = None
) -> LogEntry:
    """Create a new log entry."""
    db_log = LogEntry(
        operation=operation,
        user_id=user_id,
        details=details,
        item_ids=item_ids,
        container_ids=container_ids
    )
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return db_log

def get_logs(
    db: Session, 
    start_date: datetime = None, 
    end_date: datetime = None, 
    user_id: str = None, 
    operation: ActionType = None,
    skip: int = 0, 
    limit: int = 100
) -> List[LogEntry]:
    """Get log entries with various filters."""
    query = db.query(LogEntry)
    
    if start_date:
        query = query.filter(LogEntry.timestamp >= start_date)
    if end_date:
        query = query.filter(LogEntry.timestamp <= end_date)
    if user_id:
        query = query.filter(LogEntry.user_id == user_id)
    if operation:
        query = query.filter(LogEntry.operation == operation)
    
    return query.order_by(LogEntry.timestamp.desc()).offset(skip).limit(limit).all()

# ReturnMission CRUD operations

def get_return_mission(db: Session, mission_id: str) -> Optional[ReturnMission]:
    """Get a return mission by ID."""
    return db.query(ReturnMission).filter(ReturnMission.id == mission_id).first()

def get_active_return_missions(db: Session) -> List[ReturnMission]:
    """Get all active (planned or loading) return missions."""
    return db.query(ReturnMission).filter(
        ReturnMission.status.in_([MissionStatus.PLANNED, MissionStatus.LOADING])
    ).all()

def create_return_mission(db: Session, mission_data: Dict[str, Any]) -> ReturnMission:
    """Create a new return mission."""
    scheduled_date = None
    if mission_data.get("scheduledDate"):
        try:
            scheduled_date = datetime.fromisoformat(mission_data["scheduledDate"]).date()
        except ValueError:
            # Handle invalid date format
            scheduled_date = date.today()
    
    db_mission = ReturnMission(
        id=mission_data.get("id", f"mission_{uuid.uuid4().hex[:8]}"),
        scheduled_date=scheduled_date or date.today(),
        max_weight=mission_data.get("maxWeight", 0),
        max_volume=mission_data.get("maxVolume", 0),
        current_weight=mission_data.get("currentWeight", 0),
        current_volume=mission_data.get("currentVolume", 0),
        status=MissionStatus.PLANNED
    )
    db.add(db_mission)
    db.commit()
    db.refresh(db_mission)
    return db_mission

def assign_waste_to_mission(db: Session, waste_id: str, mission_id: str) -> Optional[WasteItem]:
    """Assign a waste item to a return mission."""
    db_waste = db.query(WasteItem).filter(WasteItem.id == waste_id).first()
    db_mission = get_return_mission(db, mission_id)
    
    if not db_waste or not db_mission:
        return None
    
    # Update waste item with mission ID
    db_waste.return_mission_id = mission_id
    
    # Update mission's current weight and volume
    if db_waste.item:
        db_mission.current_weight += db_waste.item.mass
        db_mission.current_volume += db_waste.item.volume()
    
    db.commit()
    db.refresh(db_waste)
    return db_waste
