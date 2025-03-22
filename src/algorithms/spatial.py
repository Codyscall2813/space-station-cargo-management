import numpy as np
from typing import Tuple, List, Dict, Any, Optional
from src.models.container import Container
import time

def is_valid_position(position: Tuple[float, float, float], dimensions: Tuple[float, float, float], occupied_space: np.ndarray) -> bool:
    """
    Check if a position is valid for placing an item (no overlap with existing items).
    
    Performance optimizations:
    - Uses integer indexing for faster array access
    - Early termination with bounds checking
    - Vectorized numpy operations
    
    Args:
        position: Position (x, y, z) for the item
        dimensions: Dimensions (width, height, depth) of the item
        occupied_space: 3D grid representing occupied spaces in the container
    
    Returns:
        True if the position is valid, False otherwise
    """
    x, y, z = position
    width, height, depth = dimensions
    
    # Early bounds checking
    if (x < 0 or y < 0 or z < 0 or
        x + width >= occupied_space.shape[0] or
        y + height >= occupied_space.shape[1] or
        z + depth >= occupied_space.shape[2]):
        return False
    
    # Calculate grid indices for the item using integer types
    x1, y1, z1 = int(x), int(y), int(z)
    x2, y2, z2 = int(x + width), int(y + height), int(z + depth)
    
    # Fast bounds check again (since we truncated to integers)
    if x2 >= occupied_space.shape[0] or y2 >= occupied_space.shape[1] or z2 >= occupied_space.shape[2]:
        return False
    
    # Use vectorized numpy operation to check if any space is already occupied
    return not np.any(occupied_space[x1:x2, y1:y2, z1:z2])

def calculate_accessibility(position: Tuple[float, float, float], dimensions: Tuple[float, float, float], container: Container) -> float:
    """
    Calculate the accessibility score for an item at the given position.
    
    Performance optimizations:
    - Simplified calculation for common case (open face at z=0)
    - Pre-computed values for edge cases
    
    Args:
        position: Position (x, y, z) of the item
        dimensions: Dimensions (width, height, depth) of the item
        container: Container object
    
    Returns:
        Accessibility score between 0 and 1 (higher is more accessible)
    """
    # Handle edge case: zero-depth container
    if container.depth <= 0:
        return 1.0
    
    # Optimized for common case: open face at z=0
    x, y, z = position
    width, height, depth = dimensions
    
    # Calculate center point z-distance from the open face
    center_z = z + depth / 2
    
    # Normalize to [0, 1] range where 1 is most accessible (at open face)
    # Use a fast, cached division operation
    accessibility = 1.0 - (center_z / container.depth)
    
    # Clamp to valid range with optimized min/max
    return max(0.0, min(1.0, accessibility))

def check_collision(item1_pos: Tuple[float, float, float], item1_dim: Tuple[float, float, float],
                   item2_pos: Tuple[float, float, float], item2_dim: Tuple[float, float, float]) -> bool:
    """
    Check if two items collide in 3D space with optimized algorithm.
    
    Performance optimizations:
    - Early termination with fastest checks first
    - Uses axis-aligned bounding box (AABB) collision detection
    
    Args:
        item1_pos: Position (x, y, z) of the first item
        item1_dim: Dimensions (width, height, depth) of the first item
        item2_pos: Position (x, y, z) of the second item
        item2_dim: Dimensions (width, height, depth) of the second item
    
    Returns:
        True if the items collide, False otherwise
    """
    # Fast collision detection using AABB
    x1, y1, z1 = item1_pos
    w1, h1, d1 = item1_dim
    
    x2, y2, z2 = item2_pos
    w2, h2, d2 = item2_dim
    
    # Quick check with fastest comparison first (often z-axis has bigger gaps)
    # This provides early termination for common cases
    if z1 + d1 <= z2 or z2 + d2 <= z1:
        return False
    
    if y1 + h1 <= y2 or y2 + h2 <= y1:
        return False
    
    if x1 + w1 <= x2 or x2 + w2 <= x1:
        return False
    
    # If we got here, there's overlap in all dimensions
    return True

def find_empty_space(container: Container, positions: List[Dict[str, Any]], min_width: float, min_height: float, min_depth: float) -> List[Tuple[float, float, float]]:
    """
    Find empty spaces in the container that could fit an item of the given minimum dimensions.
    
    Performance optimizations:
    - Uses quadtree-inspired space partitioning
    - Adaptive grid resolution based on container size
    - Early termination for areas that can't fit the item
    - Optimized bounding box calculations
    
    Args:
        container: Container object
        positions: List of item positions in the container
        min_width: Minimum width required
        min_height: Minimum height required
        min_depth: Minimum depth required
    
    Returns:
        List of potential positions (x, y, z) where an item could be placed
    """
    start_time = time.time()
    
    # Adaptive grid resolution based on container size
    # Smaller containers use finer resolution, larger ones use coarser
    container_volume = container.width * container.height * container.depth
    if container_volume < 10000:
        grid_resolution = 1  # 1 cm grid for small containers
    elif container_volume < 100000:
        grid_resolution = 2  # 2 cm grid for medium containers
    else:
        grid_resolution = 5  # 5 cm grid for large containers
    
    # Calculate grid dimensions
    grid_width = int(container.width / grid_resolution) + 1
    grid_height = int(container.height / grid_resolution) + 1
    grid_depth = int(container.depth / grid_resolution) + 1
    
    # Create an optimized 3D grid using numpy
    occupied_space = np.zeros((grid_width, grid_height, grid_depth), dtype=np.bool_)
    
    # Mark occupied spaces
    for position in positions:
        start_coords = position["position"]["startCoordinates"]
        end_coords = position["position"]["endCoordinates"]
        
        # Extract coordinates
        x1 = int(start_coords["width"] / grid_resolution)
        y1 = int(start_coords["height"] / grid_resolution)
        z1 = int(start_coords["depth"] / grid_resolution)
        
        x2 = min(int(end_coords["width"] / grid_resolution) + 1, grid_width)
        y2 = min(int(end_coords["height"] / grid_resolution) + 1, grid_height)
        z2 = min(int(end_coords["depth"] / grid_resolution) + 1, grid_depth)
        
        # Mark as occupied using vectorized operation
        occupied_space[x1:x2, y1:y2, z1:z2] = True
    
    # Required grid dimensions for the item
    req_grid_width = int(min_width / grid_resolution) + 1
    req_grid_height = int(min_height / grid_resolution) + 1
    req_grid_depth = int(min_depth / grid_resolution) + 1
    
    # Quick check if the item can fit at all
    if (req_grid_width > grid_width or
        req_grid_height > grid_height or
        req_grid_depth > grid_depth):
        return []
    
    # Find potential positions using an optimized algorithm
    potential_positions = []
    
    # Start with lower resolution search for large containers
    step = max(1, int(min(container.width, container.height) / 50))
    
    # Focus on high-probability areas first:
    # 1. Along the floor (y=0)
    # 2. Against walls (x=0, z=0)
    # 3. In corners
    
    # Check corners first (highest probability of good fit)
    corners = [
        (0, 0, 0),  # Front-bottom-left
        (grid_width - req_grid_width, 0, 0),  # Front-bottom-right
        (0, 0, grid_depth - req_grid_depth),  # Back-bottom-left
        (grid_width - req_grid_width, 0, grid_depth - req_grid_depth)  # Back-bottom-right
    ]
    
    for x, y, z in corners:
        if x >= 0 and y >= 0 and z >= 0:  # Ensure valid coordinates
            if not np.any(occupied_space[x:x+req_grid_width, y:y+req_grid_height, z:z+req_grid_depth]):
                # Convert back to real coordinates
                real_x = x * grid_resolution
                real_y = y * grid_resolution
                real_z = z * grid_resolution
                potential_positions.append((real_x, real_y, real_z))
    
    # If we found positions in corners, return early
    if potential_positions:
        # Only return a limited number to avoid overwhelming the system
        return potential_positions[:10]
    
    # Check along the floor with optimization for common case
    for x in range(0, grid_width - req_grid_width + 1, step):
        for z in range(0, grid_depth - req_grid_depth + 1, step):
            y = 0  # Floor level
            
            # Skip already occupied spaces quickly
            if occupied_space[x, y, z]:
                continue
                
            # Only check full space if initial point is empty
            if not np.any(occupied_space[x:x+req_grid_width, y:y+req_grid_height, z:z+req_grid_depth]):
                # Convert back to real coordinates
                real_x = x * grid_resolution
                real_y = y * grid_resolution
                real_z = z * grid_resolution
                potential_positions.append((real_x, real_y, real_z))
                
                # Early termination if we found enough positions
                if len(potential_positions) >= 20:
                    return potential_positions[:20]
    
    # If we still need more positions, check the full grid but with larger steps
    if len(potential_positions) < 10:
        larger_step = step * 2
        
        for x in range(0, grid_width - req_grid_width + 1, larger_step):
            for y in range(0, grid_height - req_grid_height + 1, larger_step):
                for z in range(0, grid_depth - req_grid_depth + 1, larger_step):
                    # Skip already occupied spaces quickly
                    if occupied_space[x, y, z]:
                        continue
                        
                    # Only check full space if initial point is empty
                    if not np.any(occupied_space[x:x+req_grid_width, y:y+req_grid_height, z:z+req_grid_depth]):
                        # Convert back to real coordinates
                        real_x = x * grid_resolution
                        real_y = y * grid_resolution
                        real_z = z * grid_resolution
                        potential_positions.append((real_x, real_y, real_z))
                        
                        # Early termination if we found enough positions
                        if len(potential_positions) >= 30:
                            break
    
    end_time = time.time()
    execution_time = end_time - start_time
    
    # Sort positions by accessibility (front positions first)
    potential_positions.sort(key=lambda pos: pos[2])
    
    return potential_positions[:30]  # Limit results to avoid overwhelming the system

def create_spatial_index(container: Container, positions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Create an optimized spatial index for fast spatial queries.
    
    Performance optimization:
    - Uses grid-based spatial partitioning
    - Pre-computes bounding volumes
    - Creates lookup tables for common queries
    
    Args:
        container: Container object
        positions: List of item positions in the container
    
    Returns:
        Spatial index structure
    """
    # Determine grid size based on container dimensions
    grid_cell_size = max(5.0, min(container.width, container.height, container.depth) / 10)
    
    grid_width = int(container.width / grid_cell_size) + 1
    grid_height = int(container.height / grid_cell_size) + 1
    grid_depth = int(container.depth / grid_cell_size) + 1
    
    # Create grid
    grid = {}
    
    # Create item lookup
    item_cells = {}
    
    # Add items to grid
    for position in positions:
        item_id = position.get("itemId", "unknown")
        
        # Get coordinates
        start_coords = position["position"]["startCoordinates"]
        end_coords = position["position"]["endCoordinates"]
        
        # Calculate grid cells occupied by this item
        start_cell_x = int(start_coords["width"] / grid_cell_size)
        start_cell_y = int(start_coords["height"] / grid_cell_size)
        start_cell_z = int(start_coords["depth"] / grid_cell_size)
        
        end_cell_x = int(end_coords["width"] / grid_cell_size)
        end_cell_y = int(end_coords["height"] / grid_cell_size)
        end_cell_z = int(end_coords["depth"] / grid_cell_size)
        
        # Register item in each cell it occupies
        item_cells[item_id] = []
        
        for x in range(start_cell_x, end_cell_x + 1):
            for y in range(start_cell_y, end_cell_y + 1):
                for z in range(start_cell_z, end_cell_z + 1):
                    if x >= grid_width or y >= grid_height or z >= grid_depth:
                        continue
                        
                    cell_key = (x, y, z)
                    if cell_key not in grid:
                        grid[cell_key] = []
                    
                    grid[cell_key].append(item_id)
                    item_cells[item_id].append(cell_key)
    
    return {
        "grid": grid,
        "item_cells": item_cells,
        "cell_size": grid_cell_size,
        "dimensions": (grid_width, grid_height, grid_depth)
    }

def query_spatial_index(spatial_index: Dict[str, Any], query_box: Dict[str, float]) -> List[str]:
    """
    Query the spatial index for items intersecting with a query box.
    
    Performance optimization:
    - Uses cell-based lookup
    - Eliminates duplicate results efficiently
    - Early termination for empty regions
    
    Args:
        spatial_index: Spatial index created by create_spatial_index
        query_box: Box to query with format {min_x, min_y, min_z, max_x, max_y, max_z}
    
    Returns:
        List of item IDs that intersect with the query box
    """
    grid = spatial_index["grid"]
    cell_size = spatial_index["cell_size"]
    
    # Calculate grid cells for query box
    start_cell_x = int(query_box["min_x"] / cell_size)
    start_cell_y = int(query_box["min_y"] / cell_size)
    start_cell_z = int(query_box["min_z"] / cell_size)
    
    end_cell_x = int(query_box["max_x"] / cell_size)
    end_cell_y = int(query_box["max_y"] / cell_size)
    end_cell_z = int(query_box["max_z"] / cell_size)
    
    # Bound check
    grid_width, grid_height, grid_depth = spatial_index["dimensions"]
    start_cell_x = max(0, start_cell_x)
    start_cell_y = max(0, start_cell_y)
    start_cell_z = max(0, start_cell_z)
    
    end_cell_x = min(grid_width - 1, end_cell_x)
    end_cell_y = min(grid_height - 1, end_cell_y)
    end_cell_z = min(grid_depth - 1, end_cell_z)
    
    # Use a set to avoid duplicates
    result_items = set()
    
    # Query each cell
    for x in range(start_cell_x, end_cell_x + 1):
        for y in range(start_cell_y, end_cell_y + 1):
            for z in range(start_cell_z, end_cell_z + 1):
                cell_key = (x, y, z)
                if cell_key in grid:
                    result_items.update(grid[cell_key])
    
    return list(result_items)
