from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional, Tuple, Set
import numpy as np
import time
import heapq
import random
from src.models.container import Container
from src.models.item import Item
from src.models.position import Position
from src.db import crud
from src.algorithms.spatial import is_valid_position, calculate_accessibility, check_collision, find_empty_space, create_spatial_index, query_spatial_index

# Constants for rearrangement optimization
MAX_CANDIDATES = 10
MAX_ITERATIONS = 1000
INITIAL_TEMPERATURE = 100.0
COOLING_RATE = 0.95

def optimize_rearrangement(db: Session, container: Container, new_items: List[Item]) -> Dict[str, Any]:
    """
    Optimize the rearrangement of items in a container to accommodate new items.
    
    This function analyzes the current container state and generates a plan for
    rearranging existing items to create space for new items, prioritizing
    moving lower priority items.
    
    Args:
        db: Database session
        container: Container to reorganize
        new_items: New items to accommodate
    
    Returns:
        Dict containing rearrangement plan, including which items to move,
        the steps to follow, and the resulting space configuration
    """
    start_time = time.time()
    
    # Analyze current container state
    current_state = analyze_container_state(db, container)
    
    # Identify items that can be rearranged (low priority, rarely used, etc.)
    movable_items = identify_movable_items(db, container, new_items)
    
    if not movable_items:
        # No items can be moved, cannot accommodate new items
        return {
            "success": False,
            "reason": "No suitable items to move",
            "items_to_move": [],
            "rearrangement_steps": [],
            "resulting_space": 0,
            "new_item_placements": []
        }
    
    # Generate candidate rearrangement plans
    candidate_plans = []
    for i in range(min(MAX_CANDIDATES, len(movable_items) * 2)):
        # Create a new plan using simulated annealing or genetic algorithm
        plan = generate_rearrangement_plan(db, container, movable_items, new_items)
        if plan:
            candidate_plans.append(plan)
    
    # If no valid plans were generated, return failure
    if not candidate_plans:
        return {
            "success": False,
            "reason": "Unable to generate valid rearrangement plan",
            "items_to_move": [],
            "rearrangement_steps": [],
            "resulting_space": 0,
            "new_item_placements": []
        }
    
    # Score plans based on space utilization, movement count, priority preservation
    scored_plans = score_rearrangement_plans(candidate_plans)
    
    # Select the best plan
    best_plan = select_best_plan(scored_plans)
    
    # Generate movement steps for the best plan
    movement_steps = generate_movement_plan(best_plan)
    
    end_time = time.time()
    execution_time = end_time - start_time
    
    return {
        "success": True,
        "items_to_move": best_plan["items_to_move"],
        "rearrangement_steps": movement_steps,
        "resulting_space": best_plan["resulting_space"],
        "new_item_placements": best_plan["new_item_placements"],
        "execution_time": execution_time
    }

def analyze_container_state(db: Session, container: Container) -> Dict[str, Any]:
    """
    Analyze the current state of a container.
    
    This function examines the container's current occupancy, item distribution,
    and available space.
    
    Args:
        db: Database session
        container: Container to analyze
    
    Returns:
        Dict containing container analysis data
    """
    # Get current positions in the container
    positions = crud.get_container_positions(db, container.id)
    
    # Calculate total volume and used volume
    total_volume = container.volume()
    used_volume = 0
    
    item_positions = []
    for position in positions:
        item = crud.get_item(db, position.item_id)
        if not item:
            continue
        
        # Get dimensions based on orientation
        orientation = position.orientation
        orientations = item.get_possible_orientations()
        if 0 <= orientation < len(orientations):
            width, height, depth = orientations[orientation]
        else:
            width, height, depth = item.width, item.height, item.depth
        
        item_volume = width * height * depth
        used_volume += item_volume
        
        item_positions.append({
            "item": item,
            "position": position,
            "volume": item_volume,
            "dimensions": (width, height, depth)
        })
    
    # Calculate space utilization
    space_utilization = (used_volume / total_volume) if total_volume > 0 else 0
    
    # Find largest contiguous empty spaces
    empty_spaces = find_maximal_spaces(container, item_positions)
    
    # Calculate space fragmentation (0-1 where 0 is not fragmented)
    space_fragmentation = calculate_fragmentation(empty_spaces, total_volume - used_volume)
    
    return {
        "total_volume": total_volume,
        "used_volume": used_volume,
        "available_volume": total_volume - used_volume,
        "space_utilization": space_utilization,
        "item_count": len(item_positions),
        "item_positions": item_positions,
        "empty_spaces": empty_spaces,
        "space_fragmentation": space_fragmentation
    }

def identify_movable_items(db: Session, container: Container, new_items: List[Item]) -> List[Dict[str, Any]]:
    """
    Identify items that can be rearranged based on priority, visibility, and other factors.
    
    Args:
        db: Database session
        container: Container to analyze
        new_items: New items that need to be accommodated
    
    Returns:
        List of items that can be moved, with their positions and scores
    """
    # Get current positions in the container
    positions = crud.get_container_positions(db, container.id)
    
    # Calculate total volume needed for new items
    new_items_volume = sum(item.volume() for item in new_items)
    
    # Calculate the priorities of the new items
    new_items_avg_priority = sum(item.priority for item in new_items) / len(new_items) if new_items else 0
    
    # Identify potentially movable items
    movable_items = []
    for position in positions:
        item = crud.get_item(db, position.item_id)
        if not item:
            continue
        
        # Skip items with higher priority than the average of new items
        # unless we need a lot of space
        if item.priority > new_items_avg_priority and new_items_volume < container.volume() * 0.3:
            continue
        
        # Get dimensions based on orientation
        orientation = position.orientation
        orientations = item.get_possible_orientations()
        if 0 <= orientation < len(orientations):
            width, height, depth = orientations[orientation]
        else:
            width, height, depth = item.width, item.height, item.depth
        
        # Calculate a movability score (higher means easier to move)
        movability_score = calculate_movability_score(item, position, new_items_avg_priority)
        
        movable_items.append({
            "item": item,
            "position": position,
            "dimensions": (width, height, depth),
            "volume": width * height * depth,
            "movability_score": movability_score
        })
    
    # Sort by movability score (highest first)
    movable_items.sort(key=lambda x: x["movability_score"], reverse=True)
    
    # Limit the number of items to consider for performance
    return movable_items[:20]  # Consider up to 20 items for rearrangement

def calculate_movability_score(item: Item, position: Position, new_items_avg_priority: float) -> float:
    """
    Calculate a score for how movable an item is.
    
    Args:
        item: Item to evaluate
        position: Current position of the item
        new_items_avg_priority: Average priority of new items being placed
    
    Returns:
        Movability score (higher means easier to move)
    """
    # Base score from priority (lower priority items are more movable)
    priority_factor = 1.0 - (item.priority / 100)
    
    # Visibility factor (visible items are easier to move)
    visibility_factor = 1.0 if position.visible else 0.5
    
    # Volume factor (smaller items are easier to move)
    volume = item.volume()
    volume_factor = 1.0 - min(volume / 10000, 0.9)  # Normalize to 0.1-1.0 range
    
    # Priority difference with new items (greater difference means more movable)
    priority_diff_factor = min(max(0, (new_items_avg_priority - item.priority)) / 100, 1.0)
    
    # Calculate final score with weights
    score = (
        priority_factor * 0.4 +
        visibility_factor * 0.3 +
        volume_factor * 0.2 +
        priority_diff_factor * 0.1
    )
    
    return score

def find_maximal_spaces(container: Container, item_positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Identify maximal empty spaces in the container.
    
    This algorithm identifies corners where spaces can start and grows 
    them to find the maximum possible spaces.
    
    Args:
        container: Container to analyze
        item_positions: List of item positions with dimensions
    
    Returns:
        List of maximal empty spaces with their dimensions and positions
    """
    # Create a 3D grid representation of the container with occupied spaces
    grid_resolution = max(1, min(int(container.width / 20), int(container.height / 20), int(container.depth / 20)))
    
    grid_width = int(container.width / grid_resolution) + 1
    grid_height = int(container.height / grid_resolution) + 1
    grid_depth = int(container.depth / grid_resolution) + 1
    
    occupied_space = np.zeros((grid_width, grid_height, grid_depth), dtype=np.bool_)
    
    # Mark occupied spaces
    for item_pos in item_positions:
        position = item_pos["position"]
        dimensions = item_pos["dimensions"]
        
        x1 = max(0, int(position.x / grid_resolution))
        y1 = max(0, int(position.y / grid_resolution))
        z1 = max(0, int(position.z / grid_resolution))
        
        x2 = min(int((position.x + dimensions[0]) / grid_resolution) + 1, grid_width)
        y2 = min(int((position.y + dimensions[1]) / grid_resolution) + 1, grid_height)
        z2 = min(int((position.z + dimensions[2]) / grid_resolution) + 1, grid_depth)
        
        occupied_space[x1:x2, y1:y2, z1:z2] = True
    
    # Identify all corners (potential starting points for empty spaces)
    corners = identify_corners(occupied_space, grid_width, grid_height, grid_depth)
    
    # For each corner, grow the maximum possible space
    max_spaces = []
    for corner in corners:
        space = grow_maximal_space(corner, occupied_space, grid_width, grid_height, grid_depth)
        if space["volume"] > grid_resolution**3:  # Ignore trivially small spaces
            # Convert grid coordinates to real coordinates
            space["x"] = corner[0] * grid_resolution
            space["y"] = corner[1] * grid_resolution
            space["z"] = corner[2] * grid_resolution
            space["width"] = space["grid_width"] * grid_resolution
            space["height"] = space["grid_height"] * grid_resolution
            space["depth"] = space["grid_depth"] * grid_resolution
            max_spaces.append(space)
    
    # Merge overlapping spaces and eliminate redundant ones
    optimized_spaces = merge_and_optimize_spaces(max_spaces)
    
    return optimized_spaces

def identify_corners(occupied_space: np.ndarray, grid_width: int, grid_height: int, grid_depth: int) -> List[Tuple[int, int, int]]:
    """
    Identify corner points in the grid where empty spaces can start.
    
    Args:
        occupied_space: 3D grid of occupied spaces
        grid_width: Width of the grid
        grid_height: Height of the grid
        grid_depth: Depth of the grid
    
    Returns:
        List of corner coordinates (x, y, z)
    """
    corners = []
    
    # Check all grid points (naive approach for simplicity)
    for x in range(grid_width):
        for y in range(grid_height):
            for z in range(grid_depth):
                # Skip occupied cells
                if occupied_space[x, y, z]:
                    continue
                
                # Check if this is a corner (has an occupied neighbor)
                is_corner = False
                
                # Check the 6 face neighbors
                if (x > 0 and occupied_space[x-1, y, z]) or \
                   (x < grid_width-1 and occupied_space[x+1, y, z]) or \
                   (y > 0 and occupied_space[x, y-1, z]) or \
                   (y < grid_height-1 and occupied_space[x, y+1, z]) or \
                   (z > 0 and occupied_space[x, y, z-1]) or \
                   (z < grid_depth-1 and occupied_space[x, y, z+1]):
                    is_corner = True
                
                # Also consider cells at the boundaries as corners
                if x == 0 or x == grid_width-1 or \
                   y == 0 or y == grid_height-1 or \
                   z == 0 or z == grid_depth-1:
                    is_corner = True
                
                if is_corner:
                    corners.append((x, y, z))
    
    return corners

def grow_maximal_space(corner: Tuple[int, int, int], occupied_space: np.ndarray, grid_width: int, grid_height: int, grid_depth: int) -> Dict[str, Any]:
    """
    Grow a maximal empty space from a corner point.
    
    Args:
        corner: Starting corner coordinates (x, y, z)
        occupied_space: 3D grid of occupied spaces
        grid_width: Width of the grid
        grid_height: Height of the grid
        grid_depth: Depth of the grid
    
    Returns:
        Dict containing maximal space dimensions and volume
    """
    x, y, z = corner
    
    # Initialize maximal dimensions
    max_width = 0
    max_height = 0
    max_depth = 0
    
    # Try to grow in the x direction
    for dx in range(grid_width - x):
        if occupied_space[x + dx, y, z]:
            break
        max_width = dx + 1
    
    # Try to grow in the y direction
    for dy in range(grid_height - y):
        if occupied_space[x, y + dy, z]:
            break
        max_height = dy + 1
    
    # Try to grow in the z direction
    for dz in range(grid_depth - z):
        if occupied_space[x, y, z + dz]:
            break
        max_depth = dz + 1
    
    # Now grow in multiple dimensions simultaneously
    for dy in range(max_height):
        for dz in range(max_depth):
            for dx in range(max_width):
                if occupied_space[x + dx, y + dy, z + dz]:
                    max_width = dx
                    break
    
    for dx in range(max_width):
        for dz in range(max_depth):
            for dy in range(max_height):
                if occupied_space[x + dx, y + dy, z + dz]:
                    max_height = dy
                    break
    
    for dx in range(max_width):
        for dy in range(max_height):
            for dz in range(max_depth):
                if occupied_space[x + dx, y + dy, z + dz]:
                    max_depth = dz
                    break
    
    # Calculate volume
    volume = max_width * max_height * max_depth
    
    return {
        "grid_x": x,
        "grid_y": y,
        "grid_z": z,
        "grid_width": max_width,
        "grid_height": max_height,
        "grid_depth": max_depth,
        "volume": volume
    }

def merge_and_optimize_spaces(spaces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Merge overlapping spaces and eliminate redundant ones.
    
    Args:
        spaces: List of maximal empty spaces
    
    Returns:
        Optimized list of non-overlapping maximal spaces
    """
    # Sort spaces by volume (largest first)
    sorted_spaces = sorted(spaces, key=lambda s: s["volume"], reverse=True)
    
    # Keep track of covered space
    covered = set()
    optimized_spaces = []
    
    for space in sorted_spaces:
        # Check if this space is largely already covered by previous spaces
        x = space["x"]
        y = space["y"]
        z = space["z"]
        width = space["width"]
        height = space["height"]
        depth = space["depth"]
        
        total_cells = width * height * depth
        covered_cells = 0
        
        # Check how much of this space is already covered
        # Simplification: Just check a sample of points for performance
        sample_points = min(1000, total_cells)
        points_checked = 0
        
        for i in range(sample_points):
            # Generate a random point within the space
            px = x + (random.random() * width)
            py = y + (random.random() * height)
            pz = z + (random.random() * depth)
            
            point_key = (int(px), int(py), int(pz))
            if point_key in covered:
                covered_cells += 1
            
            points_checked += 1
        
        # If more than 70% is already covered, skip this space
        if points_checked > 0 and covered_cells / points_checked > 0.7:
            continue
        
        # Add this space to the optimized list
        optimized_spaces.append(space)
        
        # Mark all points in this space as covered
        for dx in range(int(width)):
            for dy in range(int(height)):
                for dz in range(int(depth)):
                    covered.add((int(x + dx), int(y + dy), int(z + dz)))
        
        # Limit the number of spaces for performance
        if len(optimized_spaces) >= 10:
            break
    
    return optimized_spaces

def calculate_fragmentation(empty_spaces: List[Dict[str, Any]], total_empty_volume: float) -> float:
    """
    Calculate the fragmentation level of empty space.
    
    Args:
        empty_spaces: List of empty spaces
        total_empty_volume: Total empty volume in the container
    
    Returns:
        Fragmentation level (0-1 where 0 is not fragmented)
    """
    if total_empty_volume <= 0:
        return 0.0
    
    # Calculate the volume of the largest empty space
    largest_space_volume = max(space["volume"] for space in empty_spaces) if empty_spaces else 0
    
    # Fragmentation is the complement of the ratio of largest space to total empty space
    fragmentation = 1.0 - (largest_space_volume / total_empty_volume)
    
    return fragmentation

def generate_rearrangement_plan(db: Session, container: Container, movable_items: List[Dict[str, Any]], new_items: List[Item]) -> Optional[Dict[str, Any]]:
    """
    Generate a candidate rearrangement plan using simulated annealing.
    
    Args:
        db: Database session
        container: Container to reorganize
        movable_items: Items that can be moved
        new_items: New items to accommodate
    
    Returns:
        Dict containing rearrangement plan or None if unsuccessful
    """
    # Use simulated annealing to find a good arrangement
    return simulated_annealing_rearrangement(db, container, movable_items, new_items)

def simulated_annealing_rearrangement(db: Session, container: Container, movable_items: List[Dict[str, Any]], new_items: List[Item], initial_temperature=INITIAL_TEMPERATURE, cooling_rate=COOLING_RATE, iterations=MAX_ITERATIONS) -> Optional[Dict[str, Any]]:
    """
    Use simulated annealing to find an optimal rearrangement plan.
    
    Args:
        db: Database session
        container: Container to reorganize
        movable_items: Items that can be moved
        new_items: New items to accommodate
        initial_temperature: Initial temperature for annealing
        cooling_rate: Cooling rate for temperature
        iterations: Maximum number of iterations
    
    Returns:
        Dict containing rearrangement plan or None if unsuccessful
    """
    # Create initial arrangement
    current_arrangement = create_initial_arrangement(container, movable_items, new_items)
    if not current_arrangement:
        return None
    
    current_score = score_arrangement(current_arrangement, new_items)
    best_arrangement = current_arrangement
    best_score = current_score
    
    temperature = initial_temperature
    
    for i in range(iterations):
        # Create a neighbor arrangement by making a small change
        neighbor = create_neighbor(container, current_arrangement, movable_items)
        if not neighbor:
            continue
        
        neighbor_score = score_arrangement(neighbor, new_items)
        
        # Decide whether to accept the new arrangement
        if should_accept(current_score, neighbor_score, temperature):
            current_arrangement = neighbor
            current_score = neighbor_score
            
            # Update best if improved
            if current_score > best_score:
                best_arrangement = current_arrangement
                best_score = current_score
        
        # Cool the temperature
        temperature *= cooling_rate
        
        # Early termination if we found a good enough solution
        if best_score > 0.9:
            break
    
    # If we didn't find a good enough solution, return None
    if best_score < 0.5:
        return None
    
    # Convert the best arrangement to a rearrangement plan
    return convert_to_rearrangement_plan(best_arrangement, new_items)

def create_initial_arrangement(container: Container, movable_items: List[Dict[str, Any]], new_items: List[Item]) -> Optional[Dict[str, Any]]:
    """
    Create an initial arrangement by selecting some items to move out.
    
    Args:
        container: Container to reorganize
        movable_items: Items that can be moved
        new_items: New items to accommodate
    
    Returns:
        Dict containing initial arrangement or None if unsuccessful
    """
    # Calculate total volume needed for new items
    new_items_volume = sum(item.volume() for item in new_items)
    
    # Sort movable items by movability score (highest first)
    sorted_items = sorted(movable_items, key=lambda x: x["movability_score"], reverse=True)
    
    # Select items to move until we have enough space
    items_to_move = []
    moved_volume = 0
    
    for item_data in sorted_items:
        items_to_move.append(item_data)
        moved_volume += item_data["volume"]
        
        # If we've freed enough space, stop
        if moved_volume >= new_items_volume * 1.2:  # Add 20% buffer
            break
    
    # If we couldn't free enough space, try adding more items
    if moved_volume < new_items_volume and len(items_to_move) < len(sorted_items):
        # Add more items
        for item_data in sorted_items[len(items_to_move):]:
            items_to_move.append(item_data)
            moved_volume += item_data["volume"]
            
            if moved_volume >= new_items_volume:
                break
    
    # If we still couldn't free enough space, return None
    if moved_volume < new_items_volume:
        return None
    
    # Create the initial arrangement
    initial_arrangement = {
        "container": container,
        "items_to_move": items_to_move,
        "moved_volume": moved_volume,
        "new_items": new_items,
        "new_items_volume": new_items_volume,
        "resulting_space": moved_volume - new_items_volume
    }
    
    return initial_arrangement

def create_neighbor(container: Container, current_arrangement: Dict[str, Any], all_movable_items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Create a neighboring arrangement by modifying the current one.
    
    Args:
        container: Container to reorganize
        current_arrangement: Current arrangement
        all_movable_items: All items that can be moved
    
    Returns:
        Dict containing neighboring arrangement or None if unsuccessful
    """
    # Clone the current arrangement
    neighbor = current_arrangement.copy()
    neighbor["items_to_move"] = current_arrangement["items_to_move"].copy()
    
    # Randomly choose an operation:
    # 1. Add an item to move
    # 2. Remove an item to move
    # 3. Swap an item to move with one not being moved
    
    operation = random.randint(1, 3)
    
    if operation == 1 and len(neighbor["items_to_move"]) < len(all_movable_items):
        # Add an item to move
        movable_not_selected = [item for item in all_movable_items if item not in neighbor["items_to_move"]]
        if movable_not_selected:
            item_to_add = random.choice(movable_not_selected)
            neighbor["items_to_move"].append(item_to_add)
            neighbor["moved_volume"] += item_to_add["volume"]
            neighbor["resulting_space"] = neighbor["moved_volume"] - neighbor["new_items_volume"]
    
    elif operation == 2 and len(neighbor["items_to_move"]) > 1:
        # Remove an item to move (ensure we keep at least one)
        item_to_remove = random.choice(neighbor["items_to_move"])
        neighbor["items_to_move"].remove(item_to_remove)
        neighbor["moved_volume"] -= item_to_remove["volume"]
        neighbor["resulting_space"] = neighbor["moved_volume"] - neighbor["new_items_volume"]
        
        # If this would result in insufficient space, don't make the change
        if neighbor["resulting_space"] < 0:
            return current_arrangement
    
    elif operation == 3:
        # Swap an item
        if len(neighbor["items_to_move"]) < len(all_movable_items):
            movable_not_selected = [item for item in all_movable_items if item not in neighbor["items_to_move"]]
            if movable_not_selected and neighbor["items_to_move"]:
                item_to_remove = random.choice(neighbor["items_to_move"])
                item_to_add = random.choice(movable_not_selected)
                
                neighbor["items_to_move"].remove(item_to_remove)
                neighbor["items_to_move"].append(item_to_add)
                
                neighbor["moved_volume"] = neighbor["moved_volume"] - item_to_remove["volume"] + item_to_add["volume"]
                neighbor["resulting_space"] = neighbor["moved_volume"] - neighbor["new_items_volume"]
                
                # If this would result in insufficient space, don't make the change
                if neighbor["resulting_space"] < 0:
                    return current_arrangement
    
    return neighbor

def score_arrangement(arrangement: Dict[str, Any], new_items: List[Item]) -> float:
    """
    Score an arrangement based on various factors.
    
    Args:
        arrangement: Arrangement to score
        new_items: New items to accommodate
    
    Returns:
        Score between 0 and 1 (higher is better)
    """
    # Check if the arrangement provides enough space
    if arrangement["resulting_space"] < 0:
        return 0.0
    
    # Base score from space efficiency (don't move much more than needed)
    space_efficiency = min(arrangement["new_items_volume"] / max(arrangement["moved_volume"], 1), 1.0)
    
    # Movement count factor (fewer movements are better)
    movement_count_factor = 1.0 - min(len(arrangement["items_to_move"]) / 20, 0.9)  # Max consider 20 items
    
    # Priority preservation (moving lower priority items is better)
    total_priority = sum(item_data["item"].priority for item_data in arrangement["items_to_move"])
    avg_priority = total_priority / len(arrangement["items_to_move"]) if arrangement["items_to_move"] else 0
    
    # Calculate priority score (higher if moving lower priority items)
    priority_score = 1.0 - (avg_priority / 100)
    
    # Final score with weights
    score = (
        space_efficiency * 0.4 +
        movement_count_factor * 0.3 +
        priority_score * 0.3
    )
    
    return score

def should_accept(current_score: float, neighbor_score: float, temperature: float) -> bool:
    """
    Decide whether to accept a new arrangement in simulated annealing.
    
    Args:
        current_score: Score of the current arrangement
        neighbor_score: Score of the neighbor arrangement
        temperature: Current temperature
    
    Returns:
        True if the new arrangement should be accepted, False otherwise
    """
    # If the new score is better, always accept
    if neighbor_score > current_score:
        return True
    
    # Otherwise, accept with a probability based on the score difference and temperature
    score_diff = neighbor_score - current_score
    acceptance_probability = np.exp(score_diff / temperature)
    
    return random.random() < acceptance_probability

def convert_to_rearrangement_plan(arrangement: Dict[str, Any], new_items: List[Item]) -> Dict[str, Any]:
    """
    Convert an arrangement to a rearrangement plan.
    
    Args:
        arrangement: Arrangement to convert
        new_items: New items to accommodate
    
    Returns:
        Dict containing rearrangement plan details
    """
    # Extract relevant details for the plan
    container = arrangement["container"]
    items_to_move = arrangement["items_to_move"]
    moved_volume = arrangement["moved_volume"]
    resulting_space = arrangement["resulting_space"]
    
    # Calculate potential new item placements (simplified)
    # In a real implementation, you would use the placement algorithm here
    new_item_placements = []
    for item in new_items:
        new_item_placements.append({
            "item_id": item.id,
            "container_id": container.id,
            "suggested_position": "Use placement algorithm for exact coordinates"
        })
    
    # Create the plan
    plan = {
        "container": container,
        "items_to_move": items_to_move,
        "moved_volume": moved_volume,
        "new_items": new_items,
        "new_items_volume": arrangement["new_items_volume"],
        "resulting_space": resulting_space,
        "new_item_placements": new_item_placements
    }
    
    return plan

def score_rearrangement_plans(plans: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Score multiple rearrangement plans.
    
    Args:
        plans: List of rearrangement plans
    
    Returns:
        Sorted list of plans with scores
    """
    # Calculate scores for each plan
    scored_plans = []
    for plan in plans:
        score = score_arrangement(plan, plan["new_items"])
        scored_plan = plan.copy()
        scored_plan["score"] = score
        scored_plans.append(scored_plan)
    
    # Sort by score (highest first)
    scored_plans.sort(key=lambda p: p["score"], reverse=True)
    
    return scored_plans

def select_best_plan(scored_plans: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Select the best rearrangement plan.
    
    Args:
        scored_plans: List of scored rearrangement plans
    
    Returns:
        The best plan
    """
    # Simple selection: choose the plan with the highest score
    return scored_plans[0] if scored_plans else None

def generate_movement_plan(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Generate a step-by-step movement plan for the rearrangement.
    
    Args:
        plan: Rearrangement plan
    
    Returns:
        List of movement steps
    """
    # Extract items to move
    items_to_move = plan["items_to_move"]
    
    # Sort items by dependency (items blocking others must be moved first)
    sorted_items = sort_by_dependency(items_to_move)
    
    # Generate step-by-step movement instructions
    steps = []
    for i, item_data in enumerate(sorted_items):
        item = item_data["item"]
        position = item_data["position"]
        
        # Add a step for this item
        steps.append({
            "step": i + 1,
            "action": "move",
            "item_id": item.id,
            "item_name": item.name,
            "from_container": position.container_id,
            "from_position": {
                "startCoordinates": {
                    "width": position.x,
                    "depth": position.z,
                    "height": position.y
                },
                "endCoordinates": {
                    "width": position.x + item_data["dimensions"][0],
                    "depth": position.z + item_data["dimensions"][2],
                    "height": position.y + item_data["dimensions"][1]
                }
            },
            "to_container": "temporary",  # In a real system, you would specify an actual target
            "to_position": {
                "startCoordinates": {
                    "width": 0,
                    "depth": 0,
                    "height": 0
                },
                "endCoordinates": {
                    "width": item_data["dimensions"][0],
                    "depth": item_data["dimensions"][2],
                    "height": item_data["dimensions"][1]
                }
            }
        })
    
    return steps

def sort_by_dependency(items_to_move: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sort items by dependency (items blocking others must be moved first).
    
    Args:
        items_to_move: Items to be moved
    
    Returns:
        Sorted list of items
    """
    # In a real implementation, you would build a dependency graph and use topological sort
    # For simplicity, just sort by z-coordinate (items closer to the open face first)
    return sorted(items_to_move, key=lambda x: x["position"].z)
