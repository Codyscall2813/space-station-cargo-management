import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from src.algorithms.placement import (
    optimize_placement,
    _find_best_placement,
    _create_container_grid,
    _calculate_placement_score,
    _find_rearrangement_opportunity
)
from src.models.container import Container
from src.models.item import Item
from src.models.position import Position

@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock()

@pytest.fixture
def sample_container():
    """Create a sample container for testing."""
    container = Container(
        id="cont1",
        name="Test Container",
        zone="TestZone",
        width=100.0,
        height=200.0,
        depth=85.0,
        open_face="front"
    )
    return container

@pytest.fixture
def sample_containers(sample_container):
    """Create a list of sample containers for testing."""
    container2 = Container(
        id="cont2",
        name="Test Container 2",
        zone="AnotherZone",
        width=120.0,
        height=180.0,
        depth=90.0,
        open_face="front"
    )
    return [sample_container, container2]

@pytest.fixture
def sample_item():
    """Create a sample item for testing."""
    item = Item(
        id="item1",
        name="Test Item",
        width=10.0,
        height=20.0,
        depth=15.0,
        mass=5.0,
        priority=80,
        preferred_zone="TestZone"
    )
    return item

@pytest.fixture
def sample_items(sample_item):
    """Create a list of sample items for testing."""
    item2 = Item(
        id="item2",
        name="Test Item 2",
        width=15.0,
        height=25.0,
        depth=10.0,
        mass=8.0,
        priority=90,
        preferred_zone="AnotherZone"
    )
    return [sample_item, item2]

@pytest.fixture
def sample_position(sample_item, sample_container):
    """Create a sample position for testing."""
    position = Position(
        id="pos1",
        item_id=sample_item.id,
        container_id=sample_container.id,
        x=0.0,
        y=0.0,
        z=0.0,
        orientation=0,
        visible=True
    )
    return position

def test_create_container_grid(sample_container, sample_position):
    """Test that the container grid is created correctly."""
    positions = [sample_position]
    
    # Mock the get_item function to return our sample item
    with patch('src.db.crud.get_item') as mock_get_item:
        # Create a mock item with the dimensions matching the sample_position
        mock_item = MagicMock()
        mock_item.width = 10.0
        mock_item.height = 20.0
        mock_item.depth = 15.0
        mock_item.get_possible_orientations.return_value = [
            (10.0, 20.0, 15.0),  # Original orientation
            (10.0, 15.0, 20.0),  # Rotated
            (20.0, 10.0, 15.0),  # Rotated
            (20.0, 15.0, 10.0),  # Rotated
            (15.0, 10.0, 20.0),  # Rotated
            (15.0, 20.0, 10.0),  # Rotated
        ]
        mock_get_item.return_value = mock_item
        
        grid = _create_container_grid(sample_container, positions)
        
        # Check that the grid has the right shape
        assert grid.shape == (101, 201, 86)  # +1 to handle rounding issues
        
        # Check that the position of the sample item is marked as occupied
        assert np.all(grid[0:10, 0:20, 0:15] == 1)
        
        # Check that the rest of the grid is empty
        assert np.all(grid[11:, :, :] == 0)
        assert np.all(grid[:, 21:, :] == 0)
        assert np.all(grid[:, :, 16:] == 0)

def test_calculate_placement_score(sample_item, sample_container):
    """Test that the placement score is calculated correctly."""
    position = (0.0, 0.0, 0.0)
    dimensions = (10.0, 20.0, 15.0)
    
    # Calculate score
    score = _calculate_placement_score(sample_item, sample_container, position, dimensions)
    
    # Score should be positive
    assert score > 0
    
    # Higher priority items should have higher scores
    high_priority_item = Item(
        id="item_high",
        name="High Priority Item",
        width=10.0,
        height=20.0,
        depth=15.0,
        mass=5.0,
        priority=100,  # Higher priority
        preferred_zone="TestZone"
    )
    
    high_score = _calculate_placement_score(high_priority_item, sample_container, position, dimensions)
    assert high_score > score
    
    # Items in their preferred zone should have higher scores
    not_preferred_item = Item(
        id="item_not_preferred",
        name="Item with Different Preferred Zone",
        width=10.0,
        height=20.0,
        depth=15.0,
        mass=5.0,
        priority=80,
        preferred_zone="OtherZone"  # Different from container's zone
    )
    
    not_preferred_score = _calculate_placement_score(not_preferred_item, sample_container, position, dimensions)
    assert score > not_preferred_score
    
    # Items closer to the open face should have higher scores
    back_position = (0.0, 0.0, 70.0)  # Far from open face
    back_score = _calculate_placement_score(sample_item, sample_container, back_position, dimensions)
    assert score > back_score

def test_find_best_placement(mock_db, sample_item, sample_containers):
    """Test finding the best placement for an item."""
    # Mock the get_container_positions function to return an empty list
    with patch('src.db.crud.get_container_positions') as mock_get_positions:
        mock_get_positions.return_value = []
        
        # Test with an item that fits in the container
        placement = _find_best_placement(mock_db, sample_item, sample_containers)
        
        # Should find a valid placement
        assert placement is not None
        assert len(placement) == 3
        
        container, position, orientation = placement
        assert container in sample_containers
        assert len(position) == 3  # (x, y, z)
        assert 0 <= orientation < 6  # 6 possible orientations
        
        # Test with an item that doesn't fit
        big_item = Item(
            id="big_item",
            name="Big Item",
            width=200.0,  # Bigger than any container
            height=300.0,
            depth=400.0,
            mass=100.0,
            priority=80
        )
        
        placement = _find_best_placement(mock_db, big_item, sample_containers)
        
        # Should not find a valid placement
        assert placement is None

@patch('src.algorithms.placement._find_best_placement')
@patch('src.algorithms.placement._find_rearrangement_opportunity')
def test_optimize_placement(mock_find_rearrangement, mock_find_best_placement, mock_db, sample_items, sample_containers):
    """Test the main placement optimization function."""
    # Set up the mocks
    mock_find_best_placement.side_effect = [
        (sample_containers[0], (0.0, 0.0, 0.0), 0),  # First item gets placed
        None  # Second item needs rearrangement
    ]
    
    mock_find_rearrangement.return_value = (
        sample_containers[1],
        (10.0, 10.0, 10.0),
        [{"action": "move", "item_id": "item3", "from_container": "cont1"}]
    )
    
    # Run the optimization
    result = optimize_placement(mock_db, sample_items, sample_containers)
    
    # Check the result structure
    assert "placements" in result
    assert "rearrangements" in result
    
    # Check that both items were placed
    assert len(result["placements"]) == 2
    
    # Verify the first placement
    placement1 = result["placements"][0]
    assert placement1["item_id"] == sample_items[0].id
    assert placement1["container_id"] == sample_containers[0].id
    
    # Verify the second placement (via rearrangement)
    placement2 = result["placements"][1]
    assert placement2["item_id"] == sample_items[1].id
    assert placement2["container_id"] == sample_containers[1].id
    
    # Check rearrangements
    assert len(result["rearrangements"]) == 1
    assert result["rearrangements"][0]["action"] == "move"
