from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional, Tuple
from datetime import date

from src.models.item import ItemStatus
from src.models.return_mission import ReturnMission, WasteReason
from src.db import crud
from src.algorithms import retrieval

def generate_return_plan(db: Session, mission_id: str, undocking_container_id: str, max_weight: float) -> Dict[str, Any]:
    """
    Generate a plan for returning waste items in a return mission.
    
    This algorithm selects waste items to be included in the return mission
    based on priority and constraints, and generates a plan for moving them
    to the undocking container.
    
    Args:
        db: Database session
        mission_id: ID of the return mission
        undocking_container_id: ID of the container that will be undocked
        max_weight: Maximum weight capacity of the return mission
    
    Returns:
        Dict containing the return plan, retrieval steps, and manifest
    """
    # Get the return mission
    mission = crud.get_return_mission(db, mission_id)
    if not mission:
        return {
            "success": False,
            "return_plan": [],
            "retrieval_steps": [],
            "return_manifest": {
                "return_items": [],
                "total_volume": 0,
                "total_weight": 0
            }
        }
    
    # Get the undocking container
    undocking_container = crud.get_container(db, undocking_container_id)
    if not undocking_container:
        return {
            "success": False,
            "return_plan": [],
            "retrieval_steps": [],
            "return_manifest": {
                "return_items": [],
                "total_volume": 0,
                "total_weight": 0
            }
        }
    
    # Get all waste items not already assigned to a return mission
    waste_items = []
    all_items = crud.get_items(db)
    
    for item in all_items:
        if item.status in [ItemStatus.WASTE, ItemStatus.DEPLETED]:
            # Check if the item is already in a return mission
            if not item.waste_info or not item.waste_info.return_mission_id:
                waste_items.append(item)
    
    # Sort waste items by priority (highest first)
    waste_items.sort(key=lambda x: x.priority, reverse=True)
    
    # Select items to include in the return mission using a knapsack algorithm
    selected_items, total_weight, total_volume = knapsack_selection(waste_items, max_weight, undocking_container.volume())
    
    # Generate return plan steps
    return_plan = []
    retrieval_steps = []
    
    for item in selected_items:
        # Get current position
        position = crud.get_item_position(db, item.id)
        if not position:
            continue
        
        current_container_id = position.container_id
        
        # Skip if already in the undocking container
        if current_container_id == undocking_container_id:
            continue
        
        # Add to return plan
        return_plan.append({
            "item_id": item.id,
            "item_name": item.name,
            "from_container": current_container_id,
            "to_container": undocking_container_id
        })
        
        # Generate retrieval steps if needed
        if not position.visible:
            item_retrieval_steps = retrieval.generate_retrieval_steps(db, item.id, current_container_id)
            retrieval_steps.extend(item_retrieval_steps)
        
        # Assign item to the return mission in the database
        if item.waste_info:
            crud.assign_waste_to_mission(db, item.waste_info.id, mission_id)
    
    # Create return manifest
    return_manifest = {
        "return_items": [
            {
                "item_id": item.id,
                "name": item.name,
                "reason": WasteReason.EXPIRED.value if item.is_expired() else WasteReason.DEPLETED.value
            } for item in selected_items
        ],
        "total_volume": total_volume,
        "total_weight": total_weight
    }
    
    return {
        "success": True,
        "return_plan": return_plan,
        "retrieval_steps": retrieval_steps,
        "return_manifest": return_manifest
    }

def knapsack_selection(items: List[Any], max_weight: float, max_volume: float) -> Tuple[List[Any], float, float]:
    """
    Select items to include in the return mission using a modified knapsack algorithm.
    
    This algorithm selects items to maximize the total priority while staying
    within weight and volume constraints.
    
    Args:
        items: List of items to consider
        max_weight: Maximum weight capacity
        max_volume: Maximum volume capacity
    
    Returns:
        Tuple of (selected_items, total_weight, total_volume)
    """
    # This is a simplification of the multi-dimensional knapsack problem
    # A real implementation would use more sophisticated algorithms
    
    # Sort items by priority per unit weight (highest first)
    items.sort(key=lambda x: x.priority / (x.mass * x.volume()), reverse=True)
    
    selected_items = []
    total_weight = 0
    total_volume = 0
    
    for item in items:
        if total_weight + item.mass <= max_weight and total_volume + item.volume() <= max_volume:
            selected_items.append(item)
            total_weight += item.mass
            total_volume += item.volume()
    
    return selected_items, total_weight, total_volume
