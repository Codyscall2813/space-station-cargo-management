import pytest
import numpy as np
from unittest.mock import MagicMock
from src.algorithms.spatial import (
    is_valid_position,
    calculate_accessibility,
    check_collision,
    find_empty_space
)
from src.models.container import Container

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

def test_is_valid_position():
    """Test checking if a position is valid (no overlaps)."""
    # Create a simple 5x5x5 grid
    grid = np.zeros((5, 5, 5), dtype=np.int8)
    
    # Mark some space as occupied
    grid[1:3, 1:3, 1:3] = 1
    
    # Test valid positions
    assert is_valid_position((0, 0, 0), (1, 1, 1), grid) is True
    assert is_valid_position((3, 3, 3), (1, 1, 1), grid) is True
    
    # Test invalid positions (overlapping with occupied space)
    assert is_valid_position((1, 1, 1), (1, 1, 1), grid) is False
    assert is_valid_position((0, 0, 0), (2, 2, 2), grid) is False
    
    # Test positions that go out of bounds
    assert is_valid_position((4, 4, 4), (2, 2, 2), grid) is False

def test_calculate_accessibility(sample_container):
    """Test calculating accessibility score."""
    # Items at the front should have high accessibility
    assert calculate_accessibility((0, 0, 0), (10, 10, 10), sample_container) == 1.0
    
    # Items at the back should have low accessibility
    assert calculate_accessibility((0, 0, 80), (10, 10, 5), sample_container) < 0.1
    
    # Items in the middle should have medium accessibility
    mid_score = calculate_accessibility((0, 0, 40), (10, 10, 10), sample_container)
    assert 0.4 < mid_score < 0.6
    
    # Test with a zero-depth container (edge case)
    zero_depth_container = Container(
        id="zero",
        name="Zero Depth",
        zone="Test",
        width=100.0,
        height=100.0,
        depth=0.0,
        open_face="front"
    )
    assert calculate_accessibility((0, 0, 0), (10, 10, 10), zero_depth_container) == 1.0

def test_check_collision():
    """Test checking for collision between two items."""
    # Test non-overlapping items
    assert check_collision(
        (0, 0, 0), (10, 10, 10),
        (20, 20, 20), (10, 10, 10)
    ) is False
    
    # Test completely overlapping items
    assert check_collision(
        (5, 5, 5), (10, 10, 10),
        (5, 5, 5), (10, 10, 10)
    ) is True
    
    # Test partially overlapping items
    assert check_collision(
        (0, 0, 0), (15, 15, 15),
        (10, 10, 10), (15, 15, 15)
    ) is True
    
    # Test items that touch but don't overlap
    assert check_collision(
        (0, 0, 0), (10, 10, 10),
        (10, 0, 0), (10, 10, 10)
    ) is True
    
    # Test items overlapping in only one dimension
    assert check_collision(
        (0, 0, 0), (10, 10, 10),
        (5, 20, 20), (10, 10, 10)
    ) is False

def test_find_empty_space(sample_container):
    """Test finding empty spaces in a container."""
    # Create some sample positions
    positions = [
        {
            "position": {
                "startCoordinates": {"width": 0, "height": 0, "depth": 0},
                "endCoordinates": {"width": 50, "height": 100, "depth": 40}
            }
        },
        {
            "position": {
                "startCoordinates": {"width": 50, "height": 0, "depth": 0},
                "endCoordinates": {"width": 100, "height": 100, "depth": 40}
            }
        }
    ]
    
    # Find empty spaces for an item that fits in the remaining space
    spaces = find_empty_space(sample_container, positions, 20, 20, 20)
    
    # Should find at least one space
    assert len(spaces) > 0
    
    # All spaces should be valid (within container bounds)
    for space in spaces:
        x, y, z = space
        assert 0 <= x <= sample_container.width - 20
        assert 0 <= y <= sample_container.height - 20
        assert 0 <= z <= sample_container.depth - 20
    
    # Test with an item that's too big for any remaining space
    big_spaces = find_empty_space(sample_container, positions, 60, 150, 50)
    assert len(big_spaces) == 0
