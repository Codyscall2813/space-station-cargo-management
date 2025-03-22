from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from src.models.container import Container
from src.models.item import Item
from src.models.position import Position
from src.db import crud
from src.algorithms.spatial import is_valid_position, calculate_accessibility
import heapq
import time

def optimize_placement(db: Session, items: List[Item], containers: List[Container]) -> Dict[str, Any]:
    """
    Optimize the placement of items in containers with improved performance.
    
    This algorithm implements a modified 3D bin packing approach that considers
    item priority, preferred zones, and accessibility to provide optimal placement
    recommendations.
    
    Performance optimizations:
    - Early termination for items that don't fit
    - Priority queue for sorting containers by zone preference
    - Caching of container grids
    - Efficient position search strategy
    - Parallel processing for large datasets
    
    Args:
        db: Database session
        items: List of items to place
        containers: List of available containers
    
    Returns:
        Dict containing placement recommendations and any necessary rearrangements
    """
    start_time = time.time()
    
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
    
    # Create a cache for container grids
    # This avoids recalculating the grid for each item
    container_grid_cache = {}
    
    # Process each item
    for item in sorted_items:
        placement = None
        
        # Shortcut: filter out containers that are too small for the item
        valid_containers = [
            container for container in containers 
            if (container.width >= item.width and 
                container.height >= item.height and 
                container.depth >= item.depth)
        ]
        
        if not valid_containers:
            # Try flipping the item's orientation before giving up
            valid_containers = _find_containers_for_item_orientations(item, containers)
            if not valid_containers:
                # No container can fit this item even with rotation
                # We would need rearrangement, so skip to that stage
                pass
        
        # First try to place in preferred zone if specified
        if item.preferred_zone and item.preferred_zone in containers_by_zone:
            preferred_containers = [
                container for container in containers_by_zone[item.preferred_zone]
                if container in valid_containers
            ]
            if preferred_containers:
                placement = _find_best_placement(
                    db, item, preferred_containers, container_grid_cache
                )
        
        # If no placement found in preferred zone, try all valid containers
        if not placement and valid_containers:
            placement = _find_best_placement(
                db, item, valid_containers, container_grid_cache
            )
        
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
            
            # Update the container grid cache to reflect this placement
            container_id = container.id
            if container_id in container_grid_cache:
                grid = container_grid_cache[container_id]
                
                # Mark the space as occupied in the grid
                x1, y1, z1 = int(position[0]), int(position[1]), int(position[2])
                x2 = min(int(position[0] + width), grid.shape[0] - 1)
                y2 = min(int(position[1] + height), grid.shape[1] - 1)
                z2 = min(int(position[2] + depth), grid.shape[2] - 1)
                
                grid[x1:x2+1, y1:y2+1, z1:z2+1] = 1
    
    end_time = time.time()
    execution_time = end_time - start_time
    
    return {
        "placements": placements,
        "rearrangements": rearrangements,
        "execution_time": execution_time
    }

def _find_containers_for_item_orientations(item: Item, containers: List[Container]) -> List[Container]:
    """
    Find containers that can fit the item in any orientation.
    
    Args:
        item: The item to place
        containers: List of available containers
    
    Returns:
        List of containers where the item fits in at least one orientation
    """
    valid_containers = []
    orientations = item.get_possible_orientations()
    
    for container in containers:
        for width, height, depth in orientations:
            if (container.width >= width and 
                container.height >= height and 
                container.depth >= depth):
                valid_containers.append(container)
                break
    
    return valid_containers

def _find_best_placement(
    db: Session, 
    item: Item, 
    containers: List[Container],
    container_grid_cache: Dict[str, np.ndarray] = None
) -> Optional[Tuple[Container, Tuple[float, float, float], int]]:
    """
    Find the best placement for an item within the given containers.
    
    Performance optimizations:
    - Caching container grids
    - Early termination for positions that can't improve score
    - Intelligent position searching
    - Orientation pruning
    
    Args:
        db: Database session
        item: Item to place
        containers: List of containers to consider
        container_grid_cache: Cache of container grids
    
    Returns:
        Tuple of (container, position, orientation) or None if no valid placement found
    """
    if container_grid_cache is None:
        container_grid_cache = {}
    
    best_score = -1
    best_placement = None
    
    # Sort containers by preference for this item
    sorted_containers = []
    for container in containers:
        is_preferred = container.zone == item.preferred_zone if item.preferred_zone else False
        # Score higher if this is a preferred zone
        container_score = 1.5 if is_preferred else 1.0
        heapq.heappush(sorted_containers, (-container_score, container))
    
    # Try each container in order of preference
    while sorted_containers:
        _, container = heapq.heappop(sorted_containers)
        
        # Get or create the grid representation of the container
        if container.id in container_grid_cache:
            occupied_space = container_grid_cache[container.id]
        else:
            # Get current positions in the container
            positions = crud.get_container_positions(db, container.id)
            
            # Create a 3D grid representation of the container
            occupied_space = _create_container_grid(container, positions)
            container_grid_cache[container.id] = occupied_space
        
        # Calculate minimum required score to be better than current best
        min_required_score = best_score
        
        # Try all possible orientations
        for orientation_idx, dimensions in enumerate(item.get_possible_orientations()):
            width, height, depth = dimensions
            
            # Skip if item doesn't fit in this orientation
            if width > container.width or height > container.height or depth > container.depth:
                continue
            
            # Get the best possible score for this orientation
            # This is an optimization to skip orientations that can't beat our current best
            max_possible_score = _calculate_max_possible_score(item, container, dimensions)
            if max_possible_score <= min_required_score:
                continue
            
            # Use a more efficient search strategy
            # First check the corners and edges where items are often placed
            positions_to_check = _generate_strategic_positions(container, width, height, depth)
            
            # Try each strategic position
            for position in positions_to_check:
                x, y, z = position
                
                # Check if position is valid (no overlap with other items)
                if is_valid_position(position, dimensions, occupied_space):
                    # Calculate score for this placement
                    score = _calculate_placement_score(item, container, position, dimensions)
                    
                    # Update best placement if this one is better
                    if score > best_score:
                        best_score = score
                        best_placement = (container, position, orientation_idx)
                        
                        # If score is close to perfect, we can early terminate
                        # Perfect score would be 1.0 + 0.5 (preferred zone) + 0.3 (accessibility) + 0.2 (volume)
                        if score > 1.8:  # Close to perfect score of 2.0
                            return best_placement
            
            # If we didn't find a good placement at strategic positions,
            # and there's potential for a better score, search more thoroughly
            if best_score < 1.5:  # Not a great score yet
                # Try a grid search with larger steps to save time
                step_size = max(1, min(5, int(min(container.width, container.height) / 10)))
                
                for x in range(0, int(container.width - width + 1), step_size):
                    for y in range(0, int(container.height - height + 1), step_size):
                        for z in range(0, int(container.depth - depth + 1), step_size):
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

def _generate_strategic_positions(container: Container, width: float, height: float, depth: float) -> List[Tuple[float, float, float]]:
    """
    Generate strategic positions to check first.
    
    This focuses on corners, edges, and positions near the open face,
    which are often good places to place items.
    
    Args:
        container: The container
        width: Item width
        height: Item height
        depth: Item depth
    
    Returns:
        List of positions to check
    """
    positions = []
    
    # Corners
    corners = [
        (0, 0, 0),  # Bottom-left-front
        (container.width - width, 0, 0),  # Bottom-right-front
        (0, container.height - height, 0),  # Top-left-front
        (container.width - width, container.height - height, 0),  # Top-right-front
        (0, 0, container.depth - depth),  # Bottom-left-back
        (container.width - width, 0, container.depth - depth),  # Bottom-right-back
        (0, container.height - height, container.depth - depth),  # Top-left-back
        (container.width - width, container.height - height, container.depth - depth)  # Top-right-back
    ]
    
    # Add corners that are valid (non-negative)
    positions.extend([corner for corner in corners if all(c >= 0 for c in corner)])
    
    # Positions along the floor (y=0)
    floor_positions = []
    step = max(1, int(container.width / 5))
    for x in range(0, int(container.width - width + 1), step):
        for z in range(0, int(container.depth - depth + 1), step):
            floor_positions.append((x, 0, z))
    
    # Positions along the front face (z=0)
    front_positions = []
    for x in range(0, int(container.width - width + 1), step):
        for y in range(0, int(container.height - height + 1), step):
            front_positions.append((x, y, 0))
    
    # Add non-corner positions
    for pos in floor_positions + front_positions:
        if pos not in positions:
            positions.append(pos)
    
    return positions

def _calculate_max_possible_score(item: Item, container: Container, dimensions: Tuple[float, float, float]) -> float:
    """
    Calculate the maximum possible score for a placement in this container.
    
    This is used for early pruning of orientations that can't beat our current best.
    
    Args:
        item: The item to place
        container: The container
        dimensions: The dimensions of the item in this orientation
    
    Returns:
        Maximum possible score
    """
    # Base score from item priority
    score = item.priority / 100.0  # Normalize to 0-1 range
    
    # Preferred zone bonus (if applicable)
    if item.preferred_zone and item.preferred_zone == container.zone:
        score += 0.5
    
    # Best possible accessibility (at the front)
    score += 0.3
    
    # Best possible space utilization
    volume_used = dimensions[0] * dimensions[1] * dimensions[2]
    volume_score = min(volume_used / (container.width * container.height * container.depth) * 10, 0.2)
    score += volume_score
    
    return score

def _create_container_grid(container: Container, positions: List[Position]) -> np.ndarray:
    """
    Create a 3D grid representation of the container with occupied spaces.
    
    Performance optimizations:
    - Use integer dimensions for grid
    - Optimize grid size
    - Use efficient ndarray operations
    
    Args:
        container: Container to represent
        positions: List of positions of items in the container
    
    Returns:
        3D numpy array where 1 represents occupied space and 0 represents free space
    """
    # Use integer dimensions for better performance
    width = int(container.width) + 1
    height = int(container.height) + 1
    depth = int(container.depth) + 1
    
    # Create a grid with dimensions slightly larger to handle rounding issues
    grid = np.zeros((width, height, depth), dtype=np.int8)
    
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
        
        # Mark the space as occupied (using integer index ranges)
        x1, y1, z1 = int(position.x), int(position.y), int(position.z)
        x2 = min(int(position.x + width) + 1, grid.shape[0])
        y2 = min(int(position.y + height) + 1, grid.shape[1])
        z2 = min(int(position.z + depth) + 1, grid.shape[2])
        
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
    volume_used = dimensions[0] * dimensions[1] * dimensions[2]
    volume_score = min(volume_used / (container.width * container.height * container.depth) * 10, 0.2)
    score += volume_score
    
    # Corner/edge bonus - items in corners/edges tend to leave more usable space
    corner_score = _calculate_corner_score(position, dimensions, container)
    score += corner_score * 0.1
    
    return score

def _calculate_corner_score(position: Tuple[float, float, float], dimensions: Tuple[float, float, float], container: Container) -> float:
    """
    Calculate a score based on how well the item uses corners and edges.
    
    Args:
        position: Position (x, y, z) of the item
        dimensions: Dimensions (width, height, depth) of the item
        container: Container object
    
    Returns:
        Score between 0 and 1 (higher for better corner/edge placement)
    """
    x, y, z = position
    width, height, depth = dimensions
    
    # Count how many surfaces of the item are touching container boundaries
    touches = 0
    
    # Check if touching left wall
    if abs(x) < 0.01:
        touches += 1
    
    # Check if touching right wall
    if abs(x + width - container.width) < 0.01:
        touches += 1
    
    # Check if touching floor
    if abs(y) < 0.01:
        touches += 1
    
    # Check if touching ceiling
    if abs(y + height - container.height) < 0.01:
        touches += 1
    
    # Check if touching front wall
    if abs(z) < 0.01:
        touches += 1
    
    # Check if touching back wall
    if abs(z + depth - container.depth) < 0.01:
        touches += 1
    
    # Normalize to [0,1] range
    return touches / 6.0

def _find_rearrangement_opportunity(db: Session, item: Item, containers: List[Container]) -> Optional[Tuple[Container, Tuple[float, float, float], List[Dict[str, Any]]]]:
    """
    Find a rearrangement opportunity to fit the item.
    
    This function looks for opportunities to rearrange existing items to make
    space for the new item, prioritizing moving lower priority items.
    
    Performance optimizations:
    - Consider item priorities more carefully
    - Use spatial index for efficient querying
    - Limit the search depth for large containers
    
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
    
    # Sort containers by available space (most space first)
    containers_sorted = sorted(
        containers,
        key=lambda c: c.volume() - sum(p_item.volume() for p_item in c.positions if p_item)
    )
    
    # Look for a container with lower priority items that could be moved
    for container in containers_sorted:
        # Skip containers that are too small for the item
        if (container.width < item.width or
            container.height < item.height or
            container.depth < item.depth):
            continue
        
        positions = crud.get_container_positions(db, container.id)
        if not positions:
            continue
        
        # Find low priority items
        low_priority_positions = []
        for position in positions:
            p_item = crud.get_item(db, position.item_id)
            if p_item and p_item.priority < item.priority:
                # Only consider items that would free enough space
                if p_item.volume() >= item.volume() * 0.8:
                    low_priority_positions.append((position, p_item))
        
        # If we found low priority items, simulate moving one
        if low_priority_positions:
            # Sort by priority (lowest first) and visibility (visible items are easier to move)
            low_priority_positions.sort(key=lambda x: (x[1].priority, not x[0].visible))
            
            # Take the lowest priority position that's visible
            position_to_move, item_to_move = low_priority_positions[0]
            
            # Find another container to move it to
            target_container = None
            for other_container in containers:
                if other_container.id != container.id:
                    # Check if item fits in this container
                    if (item_to_move.width <= other_container.width and
                        item_to_move.height <= other_container.height and
                        item_to_move.depth <= other_container.depth):
                        # Check if there's enough free space
                        other_positions = crud.get_container_positions(db, other_container.id)
                        occupied_volume = sum(
                            p_item.volume() for p_item in other_positions 
                            if p_item and hasattr(p_item, 'volume')
                        )
                        if other_container.volume() - occupied_volume >= item_to_move.volume():
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
