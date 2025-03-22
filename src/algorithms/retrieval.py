from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional, Tuple, Set
import networkx as nx
from src.models.container import Container
from src.models.item import Item
from src.models.position import Position
from src.db import crud

def generate_retrieval_steps(db: Session, item_id: str, container_id: str) -> List[Dict[str, Any]]:
    """
    Generate steps for retrieving an item from a container.
    
    This algorithm uses a dependency graph to determine which items need to be
    moved to access the target item, and then generates a step-by-step retrieval plan.
    
    Args:
        db: Database session
        item_id: ID of the item to retrieve
        container_id: ID of the container containing the item
    
    Returns:
        List of retrieval steps with actions
    """
    # Get item and container
    item = crud.get_item(db, item_id)
    container = crud.get_container(db, container_id)
    
    if not item or not container:
        return []
    
    # Get the position of the target item
    target_position = None
    positions = crud.get_container_positions(db, container_id)
    for position in positions:
        if position.item_id == item_id:
            target_position = position
            break
    
    if not target_position:
        return []
    
    # Check if the item is directly visible
    if is_visible(target_position.x, target_position.y, target_position.z, container):
        return [{
            "action": "retrieve",
            "item_id": item_id,
            "item_name": item.name
        }]
    
    # Build dependency graph
    dependency_graph = build_dependency_graph(db, positions, container)
    
    # Find the items that need to be moved
    items_to_move = find_items_to_move(dependency_graph, item_id)
    
    # Generate retrieval steps
    retrieval_steps = []
    
    # First, remove the items blocking access
    for blocking_item_id in items_to_move:
        blocking_item = crud.get_item(db, blocking_item_id)
        if not blocking_item:
            continue
        
        retrieval_steps.append({
            "action": "remove",
            "item_id": blocking_item_id,
            "item_name": blocking_item.name
        })
        
        retrieval_steps.append({
            "action": "setAside",
            "item_id": blocking_item_id,
            "item_name": blocking_item.name
        })
    
    # Then retrieve the target item
    retrieval_steps.append({
        "action": "retrieve",
        "item_id": item_id,
        "item_name": item.name
    })
    
    # Finally, put back the items in reverse order
    for blocking_item_id in reversed(items_to_move):
        blocking_item = crud.get_item(db, blocking_item_id)
        if not blocking_item:
            continue
        
        retrieval_steps.append({
            "action": "placeBack",
            "item_id": blocking_item_id,
            "item_name": blocking_item.name
        })
    
    return retrieval_steps

def is_visible(x: float, y: float, z: float, container: Container) -> bool:
    """
    Determine if an item at the given position is visible from the open face.
    
    Args:
        x: X-coordinate of the item
        y: Y-coordinate of the item
        z: Z-coordinate of the item
        container: Container object
    
    Returns:
        True if the item is visible, False otherwise
    """
    # In a real implementation, this would consider the open face direction
    # and check if there are any items blocking the path to the open face.
    # For simplicity, we'll assume the open face is the front (z=0) and an
    # item is visible if it's at the front of the container
    
    # For now, approximate visibility by checking z-distance from open face
    # If it's at z=0, it's directly visible
    return z == 0

def build_dependency_graph(db: Session, positions: List[Position], container: Container) -> nx.DiGraph:
    """
    Build a dependency graph for items in the container.
    
    This graph represents the "must move A to access B" relationships between items.
    
    Args:
        db: Database session
        positions: List of item positions in the container
        container: Container object
    
    Returns:
        Directed graph where edges point from an item to the items it blocks
    """
    # Create a directed graph
    G = nx.DiGraph()
    
    # Add all items as nodes
    for position in positions:
        G.add_node(position.item_id)
    
    # Add edges for dependencies
    for pos1 in positions:
        item1 = crud.get_item(db, pos1.item_id)
        if not item1:
            continue
        
        # Get item1 dimensions based on orientation
        orientation1 = pos1.orientation
        orientations1 = item1.get_possible_orientations()
        if 0 <= orientation1 < len(orientations1):
            width1, height1, depth1 = orientations1[orientation1]
        else:
            width1, height1, depth1 = item1.width, item1.height, item1.depth
        
        # Calculate item1 coordinates
        x1_min, y1_min, z1_min = pos1.x, pos1.y, pos1.z
        x1_max = x1_min + width1
        y1_max = y1_min + height1
        z1_max = z1_min + depth1
        
        for pos2 in positions:
            if pos1.item_id == pos2.item_id:
                continue
            
            item2 = crud.get_item(db, pos2.item_id)
            if not item2:
                continue
            
            # Get item2 dimensions based on orientation
            orientation2 = pos2.orientation
            orientations2 = item2.get_possible_orientations()
            if 0 <= orientation2 < len(orientations2):
                width2, height2, depth2 = orientations2[orientation2]
            else:
                width2, height2, depth2 = item2.width, item2.height, item2.depth
            
            # Calculate item2 coordinates
            x2_min, y2_min, z2_min = pos2.x, pos2.y, pos2.z
            x2_max = x2_min + width2
            y2_max = y2_min + height2
            z2_max = z2_min + depth2
            
            # Check if item1 is in front of item2
            # (assuming the open face is at z=0)
            if (z1_min < z2_min and
                x1_min < x2_max and x2_min < x1_max and
                y1_min < y2_max and y2_min < y1_max):
                # item1 blocks access to item2
                G.add_edge(pos1.item_id, pos2.item_id)
    
    return G

def find_items_to_move(dependency_graph: nx.DiGraph, target_item_id: str) -> List[str]:
    """
    Find the items that need to be moved to access the target item.
    
    Args:
        dependency_graph: Dependency graph of items in the container
        target_item_id: ID of the item to retrieve
    
    Returns:
        List of item IDs that need to be moved, in the order they should be moved
    """
    # Find all items that block access to the target
    blocking_items = set()
    
    # Use BFS to find all items that need to be moved
    queue = [target_item_id]
    visited = set(queue)
    
    while queue:
        item_id = queue.pop(0)
        
        # Find all items that block this item
        for blocker_id in dependency_graph.predecessors(item_id):
            if blocker_id not in visited:
                blocking_items.add(blocker_id)
                queue.append(blocker_id)
                visited.add(blocker_id)
    
    # Order the blocking items by their dependencies
    # Items that block other blocking items should be moved first
    
    # Create a subgraph of just the blocking items
    subgraph = dependency_graph.subgraph(blocking_items)
    
    # Perform a topological sort to determine the order
    try:
        # A topological sort gives us an order where a node comes before all nodes it points to
        move_order = list(nx.topological_sort(subgraph))
        # Reverse the order because we want to move items that don't block others first
        move_order.reverse()
    except nx.NetworkXUnfeasible:
        # If there's a cycle, fall back to a simpler approach
        move_order = list(blocking_items)
    
    return move_order
