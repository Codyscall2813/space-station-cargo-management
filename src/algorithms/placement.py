from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from src.models.container import Container
from src.models.item import Item
from src.models.position import Position
from src.db import crud
from src.algorithms.spatial import is_valid_position, calculate_accessibility

def optimize_placement(db: Session, items: List[Item], containers: List[Container]) -> Dict[str, Any]:
    """
    Optimize the placement of items in containers.
    
    This algorithm implements a modified 3D bin packing approach that considers
    item priority, preferred zones, and accessibility to provide optimal placement
    recommendations.
    
    Args:
        db: Database session
        items: List of items to place
        containers: List of available containers
    
    Returns:
        Dict containing placement recommendations and any necessary rearrangements
    """
    # Sort items by priority (highest first) and size (largest first)
    sorted_items = sorted(items, key=lambda x: (-x.priority, -(x.width * x.height * x.depth)))
    
    # Group containers by zone
    containers_by_zone = {}
    for container in containers:
        if container.zone not in containers_by_zone:
            containers_by_zone[container.zone] = []
        containers_by_zone[container.zone].append(container)
    
    # Initialize result structures
    placements = []
    rearrangements = []
    
    # Place each item
    for item in sorted_items:
        placement = None
        
        # First try to place in preferred zone if specified
        if item.preferred_zone and item.preferred_zone in containers_by_zone:
            preferred_containers = containers_by_zone[item.preferred_zone]
            placement = _find_best_placement(db, item, preferred_containers)
        
        # If no placement found in preferred zone, try all containers
        if not placement:
            placement = _find_best_placement(db, item, containers)
        
        # If still no placement found, try rearrangement
        if not placement:
            rearrange_result = _find_rearrangement_opportunity(db, item, containers)
            if rearrange_result:
                container, position, steps = rearrange_result
                # Add rearrangement steps
                rearrangements.extend(steps)
                # Add the placement after rearrangement
                placements.append({
                    "item_id": item.id,
                    "container_id": container.id,
                    "position": {
                        "start_coordinates": {
                            "width": position[0],
                            "depth": position[1],
                            "height": position[2]
                        },
                        "end_coordinates": {
                            "width": position[0] + item.width,
                            "depth": position[1] + item.depth,
                            "height": position[2] + item.height
                        }
                    },
                    "orientation": 0  # Default orientation
                })
        elif placement:
            # Add successful placement
            container, position, orientation = placement
            width, height, depth = item.get_possible_orientations()[orientation]
            placements.append({
                "item_id": item.id,
                "container_id": container.id,
                "position": {
                    "start_coordinates": {
                        "width": position[0],
                        "depth": position[1],
                        "height": position[2]
                    },
                    "end_coordinates": {
                        "width": position[0] + width,
                        "depth": position[1] + depth,
                        "height": position[2] + height
                    }
                },
                "orientation": orientation
            })
    
    return {
        "placements": placements,
        "rearrangements": rearrangements
    }

def _find_best_placement(db: Session, item: Item, containers: List[Container]) -> Optional[Tuple[Container, Tuple[float, float, float], int]]:
    """
    Find the best placement for an item within the given containers.
    
    Args:
        db: Database session
        item: Item to place
        containers: List of containers to consider
    
    Returns:
        Tuple of (container, position, orientation) or None if no valid placement found
    """
    best_score = -1
    best_placement = None
    
    # Try each container
    for container in containers:
        # Get current positions in the container
        positions = crud.get_container_positions(db, container.id)
        
        # Create a 3D grid representation of the container
        occupied_space = _create_container_grid(container, positions)
        
        # Try all possible orientations
        for orientation_idx, dimensions in enumerate(item.get_possible_orientations()):
            width, height, depth = dimensions
            
            # Check if item fits in the container
            if width > container.width or height > container.height or depth > container.depth:
                continue
            
            # Try different positions in the container
            for x in range(int(container.width - width + 1)):
                for y in range(int(container.height - height + 1)):
                    for z in range(int(container.depth - depth + 1)):
                        position = (x, y, z)
                        
                        # Check if position is valid (no overlap with other items)
                        if is_valid_position(position, dimensions, occupied_space):
                            # Calculate score for this placement
                            score = _calculate_placement_score(item, container, position, dimensions)
                            
                            # Update best placement if this one is better
                            if score > best_score:
                                best_score = score
                                best_placement = (container, position, orientation_idx)
    
    return best_placement

def _create_container_grid(container: Container, positions: List[Position]) -> np.ndarray:
    """
    Create a 3D grid representation of the container with occupied spaces.
    
    Args:
        container: Container to represent
        positions: List of positions of items in the container
    
    Returns:
        3D numpy array where 1 represents occupied space and 0 represents free space
    """
    # Create a grid with dimensions slightly larger to handle rounding issues
    grid = np.zeros((
        int(container.width) + 1,
        int(container.height) + 1,
        int(container.depth) + 1
    ), dtype=np.int8)
    
    # Mark occupied spaces
    for position in positions:
        # Get the item
        item = crud.get_item(None, position.item_id)
        if not item:
            continue
        
        # Get dimensions based on orientation
        orientation = position.orientation
        orientations = item.get_possible_orientations()
        if 0 <= orientation < len(orientations):
            width, height, depth = orientations[orientation]
        else:
            width, height, depth = item.width, item.height, item.depth
        
        # Mark the space as occupied
        x1, y1, z1 = int(position.x), int(position.y), int(position.z)
        x2, y2, z2 = int(position.x + width), int(position.y + height), int(position.z + depth)
        
        # Ensure we stay within grid bounds
        x2 = min(x2, grid.shape[0])
        y2 = min(y2, grid.shape[1])
        z2 = min(z2, grid.shape[2])
        
        grid[x1:x2, y1:y2, z1:z2] = 1
    
    return grid

def _calculate_placement_score(item: Item, container: Container, position: Tuple[float, float, float], dimensions: Tuple[float, float, float]) -> float:
    """
    Calculate a score for a potential placement based on various factors.
    
    Args:
        item: Item being placed
        container: Container where the item is being placed
        position: Position (x, y, z) where the item is being placed
        dimensions: Dimensions (width, height, depth) of the item in this orientation
    
    Returns:
        Score for the placement (higher is better)
    """
    # Base score from item priority
    score = item.priority / 100.0  # Normalize to 0-1 range
    
    # Preferred zone bonus
    if item.preferred_zone and item.preferred_zone == container.zone:
        score += 0.5
    
    # Accessibility score - items closer to the open face are more accessible
    accessibility = calculate_accessibility(position, dimensions, container)
    score += accessibility * 0.3
    
    # Space utilization - prefer placements that use space efficiently
    # (This is a simplified metric - a real implementation would consider more factors)
    volume_used = dimensions[0] * dimensions[1] * dimensions[2]
    volume_score = min(volume_used / (container.width * container.height * container.depth) * 10, 0.2)
    score += volume_score
    
    return score

def _find_rearrangement_opportunity(db: Session, item: Item, containers: List[Container]) -> Optional[Tuple[Container, Tuple[float, float, float], List[Dict[str, Any]]]]:
    """
    Find a rearrangement opportunity to fit the item.
    
    This function looks for opportunities to rearrange existing items to make
    space for the new item, prioritizing moving lower priority items.
    
    Args:
        db: Database session
        item: Item to place
        containers: List of containers to consider
    
    Returns:
        Tuple of (container, position, rearrangement_steps) or None if no rearrangement possible
    """
    # This is a simplified implementation. A real implementation would consider:
    # - Which items to move (based on priority, size, accessibility)
    # - Where to move them (finding spaces in other containers)
    # - Minimizing the number of moves
    
    # Just for demonstration, return a simulated rearrangement
    # In a real implementation, this would be a complex algorithm
    
    # Look for a container with lower priority items that could be moved
    for container in containers:
        positions = crud.get_container_positions(db, container.id)
        if not positions:
            continue
        
        # Look for low priority items
        low_priority_positions = []
        for position in positions:
            p_item = crud.get_item(db, position.item_id)
            if p_item and p_item.priority < item.priority:
                low_priority_positions.append((position, p_item))
        
        # If we found low priority items, simulate moving one
        if low_priority_positions:
            # Sort by priority (lowest first)
            low_priority_positions.sort(key=lambda x: x[1].priority)
            
            # Take the lowest priority position
            position_to_move, item_to_move = low_priority_positions[0]
            
            # Find another container to move it to
            target_container = None
            for other_container in containers:
                if other_container.id != container.id:
                    # Check if item fits in this container
                    if (item_to_move.width <= other_container.width and
                        item_to_move.height <= other_container.height and
                        item_to_move.depth <= other_container.depth):
                        target_container = other_container
                        break
            
            if target_container:
                # Simulate rearrangement steps
                rearrangement_steps = [
                    {
                        "action": "move",
                        "item_id": item_to_move.id,
                        "from_container": container.id,
                        "from_position": {
                            "start_coordinates": {
                                "width": position_to_move.x,
                                "depth": position_to_move.z,
                                "height": position_to_move.y
                            },
                            "end_coordinates": {
                                "width": position_to_move.x + item_to_move.width,
                                "depth": position_to_move.z + item_to_move.depth,
                                "height": position_to_move.y + item_to_move.height
                            }
                        },
                        "to_container": target_container.id,
                        "to_position": {
                            "start_coordinates": {
                                "width": 0,
                                "depth": 0,
                                "height": 0
                            },
                            "end_coordinates": {
                                "width": item_to_move.width,
                                "depth": item_to_move.depth,
                                "height": item_to_move.height
                            }
                        }
                    }
                ]
                
                # Return the space that would be available after rearrangement
                return (container, (position_to_move.x, position_to_move.y, position_to_move.z), rearrangement_steps)
    
    return None
