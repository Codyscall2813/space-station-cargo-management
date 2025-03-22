import numpy as np
from typing import Tuple, List, Dict, Any
from src.models.container import Container

def is_valid_position(position: Tuple[float, float, float], dimensions: Tuple[float, float, float], occupied_space: np.ndarray) -> bool:
    """
    Check if a position is valid for placing an item (no overlap with existing items).
    
    Args:
        position: Position (x, y, z) for the item
        dimensions: Dimensions (width, height, depth) of the item
        occupied_space: 3D grid representing occupied spaces in the container
    
    Returns:
        True if the position is valid, False otherwise
    """
    x, y, z = position
    width, height, depth = dimensions
    
    # Calculate grid indices for the item
    x1, y1, z1 = int(x), int(y), int(z)
    x2, y2, z2 = int(x + width), int(y + height), int(z + depth)
    
    # Check bounds
    if (x2 >= occupied_space.shape[0] or y2 >= occupied_space.shape[1] or z2 >= occupied_space.shape[2]):
        return False
    
    # Check if any space is already occupied
    if np.any(occupied_space[x1:x2, y1:y2, z1:z2] > 0):
        return False
    
    return True

def calculate_accessibility(position: Tuple[float, float, float], dimensions: Tuple[float, float, float], container: Container) -> float:
    """
    Calculate the accessibility score for an item at the given position.
    
    Accessibility is higher for items closer to the open face of the container.
    
    Args:
        position: Position (x, y, z) of the item
        dimensions: Dimensions (width, height, depth) of the item
        container: Container object
    
    Returns:
        Accessibility score between 0 and 1 (higher is more accessible)
    """
    x, y, z = position
    width, height, depth = dimensions
    
    # For simplicity, assume the open face is at z=0
    # A real implementation would consider the actual open face direction
    
    # Calculate average z-distance from the open face
    z_distance = z + depth / 2
    
    # Normalize to [0, 1] range
    # Items at the open face (z=0) get a score of 1
    # Items at the back of the container get a score of 0
    if container.depth == 0:
        return 1.0
    
    accessibility = 1.0 - (z_distance / container.depth)
    return max(0.0, min(1.0, accessibility))

def check_collision(item1_pos: Tuple[float, float, float], item1_dim: Tuple[float, float, float],
                   item2_pos: Tuple[float, float, float], item2_dim: Tuple[float, float, float]) -> bool:
    """
    Check if two items collide in 3D space.
    
    Args:
        item1_pos: Position (x, y, z) of the first item
        item1_dim: Dimensions (width, height, depth) of the first item
        item2_pos: Position (x, y, z) of the second item
        item2_dim: Dimensions (width, height, depth) of the second item
    
    Returns:
        True if the items collide, False otherwise
    """
    x1, y1, z1 = item1_pos
    w1, h1, d1 = item1_dim
    
    x2, y2, z2 = item2_pos
    w2, h2, d2 = item2_dim
    
    # Check for overlap in each dimension
    x_overlap = (x1 < x2 + w2) and (x2 < x1 + w1)
    y_overlap = (y1 < y2 + h2) and (y2 < y1 + h1)
    z_overlap = (z1 < z2 + d2) and (z2 < z1 + d1)
    
    # Collision occurs if there's overlap in all dimensions
    return x_overlap and y_overlap and z_overlap

def find_empty_space(container: Container, positions: List[Dict[str, Any]], min_width: float, min_height: float, min_depth: float) -> List[Tuple[float, float, float]]:
    """
    Find empty spaces in the container that could fit an item of the given minimum dimensions.
    
    Args:
        container: Container object
        positions: List of item positions in the container
        min_width: Minimum width required
        min_height: Minimum height required
        min_depth: Minimum depth required
    
    Returns:
        List of potential positions (x, y, z) where an item could be placed
    """
    # This is a simplified implementation using a grid-based approach
    # A real implementation would use more sophisticated algorithms like Skyline, Extreme Point, etc.
    
    # Create a 3D grid representing the container
    grid_resolution = 1  # 1 cm grid
    grid_width = int(container.width / grid_resolution) + 1
    grid_height = int(container.height / grid_resolution) + 1
    grid_depth = int(container.depth / grid_resolution) + 1
    
    occupied_space = np.zeros((grid_width, grid_height, grid_depth), dtype=np.int8)
    
    # Mark occupied spaces
    for position in positions:
        x = position["position"]["startCoordinates"]["width"]
        y = position["position"]["startCoordinates"]["height"]
        z = position["position"]["startCoordinates"]["depth"]
        
        width = position["position"]["endCoordinates"]["width"] - x
        height = position["position"]["endCoordinates"]["height"] - y
        depth = position["position"]["endCoordinates"]["depth"] - z
        
        # Convert to grid coordinates
        x1, y1, z1 = int(x / grid_resolution), int(y / grid_resolution), int(z / grid_resolution)
        x2 = min(int((x + width) / grid_resolution) + 1, grid_width)
        y2 = min(int((y + height) / grid_resolution) + 1, grid_height)
        z2 = min(int((z + depth) / grid_resolution) + 1, grid_depth)
        
        occupied_space[x1:x2, y1:y2, z1:z2] = 1
    
    # Find potential positions for the item
    potential_positions = []
    
    # Required grid dimensions for the item
    req_grid_width = int(min_width / grid_resolution) + 1
    req_grid_height = int(min_height / grid_resolution) + 1
    req_grid_depth = int(min_depth / grid_resolution) + 1
    
    # Check each potential starting position
    for x in range(grid_width - req_grid_width + 1):
        for y in range(grid_height - req_grid_height + 1):
            for z in range(grid_depth - req_grid_depth + 1):
                # Check if the space is empty
                if not np.any(occupied_space[x:x+req_grid_width, y:y+req_grid_height, z:z+req_grid_depth]):
                    # Convert back to real coordinates
                    real_x = x * grid_resolution
                    real_y = y * grid_resolution
                    real_z = z * grid_resolution
                    potential_positions.append((real_x, real_y, real_z))
    
    return potential_positions
