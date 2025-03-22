from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional, Tuple
from datetime import date, datetime, timedelta

from src.models.item import Item, ItemStatus
from src.models.container import Container
from src.models.position import Position
from src.models.return_mission import ReturnMission, WasteItem, WasteReason, MissionStatus
from src.db import crud
from src.algorithms import retrieval

def identify_waste_items(db: Session, current_date: date = None) -> List[Item]:
    """
    Identify items that should be marked as waste based on expiry date or usage.
    
    Args:
        db: Database session
        current_date: Current date (defaults to today)
    
    Returns:
        List of items identified as waste
    """
    if current_date is None:
        current_date = date.today()
    
    waste_items = []
    
    # Find expired items
    expired_items = find_expired_items(db, current_date)
    for item in expired_items:
        # Mark as waste if not already
        if item.status != ItemStatus.WASTE:
            mark_as_waste(db, item.id, WasteReason.EXPIRED)
        waste_items.append(item)
    
    # Find depleted items
    depleted_items = find_depleted_items(db)
    for item in depleted_items:
        # Mark as waste if not already
        if item.status != ItemStatus.DEPLETED:
            mark_as_waste(db, item.id, WasteReason.DEPLETED)
        waste_items.append(item)
    
    return waste_items

def find_expired_items(db: Session, current_date: date) -> List[Item]:
    """
    Find items that have expired based on the current date.
    
    Args:
        db: Database session
        current_date: Current date
    
    Returns:
        List of expired items
    """
    # Get all active items with expiry dates
    items = db.query(Item).filter(
        Item.status == ItemStatus.ACTIVE,
        Item.expiry_date.isnot(None)
    ).all()
    
    # Filter for expired items
    expired_items = [item for item in items if item.expiry_date <= current_date]
    
    return expired_items

def find_depleted_items(db: Session) -> List[Item]:
    """
    Find items that have been depleted based on usage.
    
    Args:
        db: Database session
    
    Returns:
        List of depleted items
    """
    # Get all active items with usage limits
    items = db.query(Item).filter(
        Item.status == ItemStatus.ACTIVE,
        Item.usage_limit.isnot(None)
    ).all()
    
    # Filter for depleted items
    depleted_items = [item for item in items if item.current_usage >= item.usage_limit]
    
    return depleted_items

def mark_as_waste(db: Session, item_id: str, reason: WasteReason, notes: str = None) -> Tuple[Optional[Item], Optional[WasteItem]]:
    """
    Mark an item as waste and create a waste record.
    
    Args:
        db: Database session
        item_id: ID of the item to mark as waste
        reason: Reason for marking as waste
        notes: Additional notes (optional)
    
    Returns:
        Tuple of (updated item, waste record)
    """
    # Get the item
    item = crud.get_item(db, item_id)
    if not item:
        return None, None
    
    # Update item status
    if reason == WasteReason.DEPLETED:
        item.status = ItemStatus.DEPLETED
    else:
        item.status = ItemStatus.WASTE
    
    # Create waste item record if it doesn't already exist
    existing_waste = db.query(WasteItem).filter(WasteItem.item_id == item_id).first()
    if existing_waste:
        return item, existing_waste
    
    waste_record = WasteItem(
        id=f"waste_{item_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        item_id=item_id,
        reason=reason,
        waste_date=date.today(),
        notes=notes
    )
    
    db.add(waste_record)
    db.commit()
    db.refresh(item)
    db.refresh(waste_record)
    
    # Log the waste operation
    crud.create_log_entry(
        db,
        operation=crud.ActionType.DISPOSAL,
        details={
            "action": "mark_waste",
            "reason": reason.value,
            "notes": notes
        },
        item_ids=[item_id]
    )
    
    return item, waste_record

def get_unassigned_waste_items(db: Session) -> List[Dict[str, Any]]:
    """
    Get all waste items not assigned to a return mission.
    
    Args:
        db: Database session
    
    Returns:
        List of waste items with their details
    """
    # Query waste records with no return mission assigned
    waste_records = db.query(WasteItem).filter(WasteItem.return_mission_id.is_(None)).all()
    
    waste_items = []
    for record in waste_records:
        item = crud.get_item(db, record.item_id)
        if item:
            position = crud.get_item_position(db, item.id)
            container_id = position.container_id if position else None
            
            waste_items.append({
                "item": item,
                "waste_record": record,
                "container_id": container_id,
                "position": position
            })
    
    return waste_items

def plan_return_mission(
    db: Session, 
    undocking_container_id: str, 
    scheduled_date: date, 
    max_weight: float,
    max_volume: Optional[float] = None
) -> Dict[str, Any]:
    """
    Plan a return mission for waste items.
    
    Args:
        db: Database session
        undocking_container_id: ID of the container that will be undocked
        scheduled_date: Scheduled date for the return mission
        max_weight: Maximum weight capacity for the return mission
        max_volume: Maximum volume capacity (optional, if None will use container volume)
    
    Returns:
        Dict containing return mission details
    """
    # Validate undocking container
    undocking_container = crud.get_container(db, undocking_container_id)
    if not undocking_container:
        return {
            "success": False,
            "reason": "Undocking container not found",
            "mission": None,
            "selected_items": [],
            "movement_plan": [],
            "manifest": None
        }
    
    # Set max volume to container volume if not specified
    if max_volume is None:
        max_volume = undocking_container.volume()
    
    # Create a new return mission
    mission = create_return_mission(
        db,
        undocking_container_id=undocking_container_id,
        scheduled_date=scheduled_date,
        max_weight=max_weight,
        max_volume=max_volume
    )
    
    # Get all waste items not assigned to a mission
    waste_items = get_unassigned_waste_items(db)
    
    # Select items to include using knapsack algorithm
    selected_items, total_weight, total_volume = select_items_for_return(
        waste_items, max_weight, max_volume
    )
    
    # Generate movement plan to undocking container
    movement_plan = generate_waste_movement_plan(
        db, selected_items, undocking_container_id
    )
    
    # Assign selected items to the mission
    for waste_item in selected_items:
        assign_to_mission(db, waste_item["waste_record"].id, mission.id)
    
    # Create return manifest
    manifest = create_return_manifest(db, mission.id, selected_items)
    
    # Update mission with current weight and volume
    mission.current_weight = total_weight
    mission.current_volume = total_volume
    mission.status = MissionStatus.LOADING
    db.commit()
    
    # Log the return mission planning
    crud.create_log_entry(
        db,
        operation=crud.ActionType.DISPOSAL,
        details={
            "action": "plan_return_mission",
            "mission_id": mission.id,
            "undocking_container": undocking_container_id,
            "scheduled_date": scheduled_date.isoformat(),
            "item_count": len(selected_items)
        },
        item_ids=[item["item"].id for item in selected_items],
        container_ids=[undocking_container_id]
    )
    
    return {
        "success": True,
        "mission": mission,
        "selected_items": selected_items,
        "movement_plan": movement_plan,
        "manifest": manifest
    }

def create_return_mission(
    db: Session, 
    undocking_container_id: str,
    scheduled_date: date,
    max_weight: float,
    max_volume: float
) -> ReturnMission:
    """
    Create a new return mission.
    
    Args:
        db: Database session
        undocking_container_id: ID of the container that will be undocked
        scheduled_date: Scheduled date for the return mission
        max_weight: Maximum weight capacity for the return mission
        max_volume: Maximum volume capacity for the return mission
    
    Returns:
        Newly created ReturnMission object
    """
    mission_id = f"mission_{datetime.now().strftime('%Y%m%d')}_{undocking_container_id}"
    
    # Check if mission already exists
    existing_mission = crud.get_return_mission(db, mission_id)
    if existing_mission:
        return existing_mission
    
    # Create new mission
    mission = ReturnMission(
        id=mission_id,
        scheduled_date=scheduled_date,
        max_weight=max_weight,
        max_volume=max_volume,
        current_weight=0,
        current_volume=0,
        status=MissionStatus.PLANNED
    )
    
    db.add(mission)
    db.commit()
    db.refresh(mission)
    
    return mission

def select_items_for_return(
    waste_items: List[Dict[str, Any]], 
    max_weight: float, 
    max_volume: float
) -> Tuple[List[Dict[str, Any]], float, float]:
    """
    Select waste items to include in a return mission using the knapsack algorithm.
    
    Prioritizes items based on:
    1. Hazardous/toxic items
    2. Items that have been waste the longest
    3. Items with higher priority values
    
    Args:
        waste_items: List of waste items with their details
        max_weight: Maximum weight capacity
        max_volume: Maximum volume capacity
    
    Returns:
        Tuple of (selected items, total weight, total volume)
    """
    # Sort waste items by priority score
    sorted_items = []
    for waste_item in waste_items:
        item = waste_item["item"]
        waste_record = waste_item["waste_record"]
        
        # Calculate "age" of waste in days
        waste_age = (date.today() - waste_record.waste_date).days
        
        # Calculate priority score (higher is better)
        priority_score = (
            item.priority +  # Base priority of the item
            waste_age * 2 +  # Older waste gets higher priority
            (100 if waste_record.reason == WasteReason.EXPIRED else 0)  # Expired items get higher priority
        )
        
        sorted_items.append({
            "item": item,
            "waste_record": waste_record,
            "container_id": waste_item["container_id"],
            "position": waste_item["position"],
            "priority_score": priority_score,
            "weight": item.mass,
            "volume": item.volume()
        })
    
    # Sort by priority score (highest first)
    sorted_items.sort(key=lambda x: x["priority_score"], reverse=True)
    
    # Run the knapsack algorithm to maximize value within weight and volume constraints
    selected_items = []
    total_weight = 0
    total_volume = 0
    
    for item_data in sorted_items:
        weight = item_data["weight"]
        volume = item_data["volume"]
        
        # If adding this item would exceed capacity, skip it
        if total_weight + weight > max_weight or total_volume + volume > max_volume:
            continue
        
        # Add the item
        selected_items.append(item_data)
        total_weight += weight
        total_volume += volume
    
    return selected_items, total_weight, total_volume

def assign_to_mission(db: Session, waste_record_id: str, mission_id: str) -> Optional[WasteItem]:
    """
    Assign a waste item to a return mission.
    
    Args:
        db: Database session
        waste_record_id: ID of the waste record
        mission_id: ID of the return mission
    
    Returns:
        Updated WasteItem object or None if not found
    """
    # Get the waste record
    waste_record = db.query(WasteItem).filter(WasteItem.id == waste_record_id).first()
    if not waste_record:
        return None
    
    # Get the return mission
    mission = crud.get_return_mission(db, mission_id)
    if not mission:
        return None
    
    # Update waste record with mission ID
    waste_record.return_mission_id = mission_id
    
    # Get the associated item to update mission weight/volume
    item = crud.get_item(db, waste_record.item_id)
    if item:
        mission.current_weight += item.mass
        mission.current_volume += item.volume()
    
    db.commit()
    db.refresh(waste_record)
    
    return waste_record

def generate_waste_movement_plan(
    db: Session, 
    selected_items: List[Dict[str, Any]], 
    target_container_id: str
) -> List[Dict[str, Any]]:
    """
    Generate a plan for moving selected waste items to the target container.
    
    Args:
        db: Database session
        selected_items: List of selected waste items
        target_container_id: ID of the target container
    
    Returns:
        List of movement steps
    """
    movement_plan = []
    retrieval_steps = []
    
    for idx, item_data in enumerate(selected_items):
        item = item_data["item"]
        position = item_data["position"]
        current_container_id = item_data["container_id"]
        
        # Skip if already in the target container
        if current_container_id == target_container_id:
            continue
        
        # If position is None or in a different container, skip
        if not position or position.container_id != current_container_id:
            continue
        
        # Generate retrieval steps if the item isn't visible
        if not position.visible:
            item_retrieval_steps = retrieval.generate_retrieval_steps(
                db, item.id, current_container_id
            )
            retrieval_steps.extend(item_retrieval_steps)
        
        # Add movement step
        movement_plan.append({
            "step": idx + 1,
            "item_id": item.id,
            "item_name": item.name,
            "from_container": current_container_id,
            "to_container": target_container_id
        })
    
    return {
        "movement_steps": movement_plan,
        "retrieval_steps": retrieval_steps
    }

def create_return_manifest(
    db: Session, 
    mission_id: str, 
    selected_items: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Create a manifest for a return mission.
    
    Args:
        db: Database session
        mission_id: ID of the return mission
        selected_items: List of selected waste items
    
    Returns:
        Dict containing the return manifest
    """
    # Get the mission
    mission = crud.get_return_mission(db, mission_id)
    if not mission:
        return None
    
    # Calculate total weight and volume
    total_weight = sum(item_data["weight"] for item_data in selected_items)
    total_volume = sum(item_data["volume"] for item_data in selected_items)
    
    # Create manifest
    manifest = {
        "mission_id": mission_id,
        "scheduled_date": mission.scheduled_date.isoformat(),
        "return_items": [
            {
                "item_id": item_data["item"].id,
                "name": item_data["item"].name,
                "reason": item_data["waste_record"].reason.value,
                "weight": item_data["weight"],
                "volume": item_data["volume"]
            } for item_data in selected_items
        ],
        "total_weight": total_weight,
        "total_volume": total_volume,
        "weight_utilization": total_weight / mission.max_weight if mission.max_weight > 0 else 0,
        "volume_utilization": total_volume / mission.max_volume if mission.max_volume > 0 else 0
    }
    
    return manifest

def complete_undocking(db: Session, undocking_container_id: str) -> Dict[str, Any]:
    """
    Complete the undocking process by removing items from the system.
    
    Args:
        db: Database session
        undocking_container_id: ID of the container that is undocking
    
    Returns:
        Dict containing the outcome of the operation
    """
    # Validate container
    container = crud.get_container(db, undocking_container_id)
    if not container:
        return {
            "success": False,
            "reason": "Undocking container not found",
            "items_removed": 0
        }
    
    # Get all positions in this container
    positions = crud.get_container_positions(db, undocking_container_id)
    
    # Get item IDs and remove positions
    removed_items = []
    item_ids = []
    
    for position in positions:
        item = crud.get_item(db, position.item_id)
        if item:
            item_ids.append(item.id)
            removed_items.append(item)
        
        # Delete the position
        crud.delete_position(db, position.id)
    
    # Update return mission statuses
    affected_missions = set()
    
    for item_id in item_ids:
        # Find the waste record for this item
        waste_record = db.query(WasteItem).filter(WasteItem.item_id == item_id).first()
        if waste_record and waste_record.return_mission_id:
            affected_missions.add(waste_record.return_mission_id)
    
    # Mark affected missions as complete
    for mission_id in affected_missions:
        mission = crud.get_return_mission(db, mission_id)
        if mission:
            mission.status = MissionStatus.COMPLETE
    
    db.commit()
    
    # Log the undocking completion
    crud.create_log_entry(
        db,
        operation=crud.ActionType.DISPOSAL,
        details={
            "action": "complete_undocking",
            "container_id": undocking_container_id,
            "items_removed": len(removed_items)
        },
        item_ids=item_ids,
        container_ids=[undocking_container_id]
    )
    
    return {
        "success": True,
        "items_removed": len(removed_items),
        "removed_items": removed_items,
        "affected_missions": list(affected_missions)
    }
