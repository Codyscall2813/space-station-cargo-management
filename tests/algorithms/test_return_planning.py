import pytest
from unittest.mock import MagicMock, patch
from src.algorithms.return_planning import (
    generate_return_plan,
    knapsack_selection
)
from src.models.item import Item, ItemStatus
from src.models.return_mission import ReturnMission, WasteReason

@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock()

@pytest.fixture
def sample_items():
    """Create sample items for testing."""
    item1 = Item(
        id="item1",
        name="Waste Item 1",
        width=10.0,
        height=20.0,
        depth=15.0,
        mass=5.0,
        priority=80,
        status=ItemStatus.WASTE
    )
    item2 = Item(
        id="item2",
        name="Waste Item 2",
        width=15.0,
        height=25.0,
        depth=10.0,
        mass=10.0,
        priority=60,
        status=ItemStatus.DEPLETED
    )
    item3 = Item(
        id="item3",
        name="Waste Item 3",
        width=20.0,
        height=15.0,
        depth=30.0,
        mass=15.0,
        priority=90,
        status=ItemStatus.WASTE
    )
    
    # Add volume method
    for item in [item1, item2, item3]:
        item.volume = lambda: item.width * item.height * item.depth
    
    return [item1, item2, item3]

def test_knapsack_selection(sample_items):
    """Test the knapsack selection algorithm for return missions."""
    # Test with enough capacity for all items
    selected, total_weight, total_volume = knapsack_selection(
        sample_items, 100.0, 10000.0
    )
    
    # Should select all items
    assert len(selected) == 3
    assert total_weight == 30.0  # Sum of all item weights
    
    # Test with limited weight
    selected, total_weight, total_volume = knapsack_selection(
        sample_items, 15.0, 10000.0
    )
    
    # Should select items to maximize priority within weight limit
    assert len(selected) < 3
    assert total_weight <= 15.0
    
    # Check that higher priority items are selected first
    selected_ids = [item.id for item in selected]
    if "item3" not in selected_ids:
        # If the highest priority item (item3) is not selected,
        # it must be because it's too heavy on its own
        assert sample_items[2].mass > 15.0
    
    # Test with limited volume
    selected, total_weight, total_volume = knapsack_selection(
        sample_items, 100.0, 5000.0
    )
    
    # Should select items to maximize priority within volume limit
    assert len(selected) < 3
    assert total_volume <= 5000.0

@patch('src.db.crud.get_return_mission')
@patch('src.db.crud.get_container')
@patch('src.db.crud.get_items')
@patch('src.db.crud.get_item_position')
@patch('src.db.crud.assign_waste_to_mission')
@patch('src.algorithms.retrieval.generate_retrieval_steps')
def test_generate_return_plan(
    mock_retrieval, mock_assign, mock_get_position, 
    mock_get_items, mock_get_container, mock_get_mission, mock_db
):
    """Test generating a return plan."""
    # Setup mocks
    mock_mission = MagicMock()
    mock_mission.id = "mission1"
    mock_get_mission.return_value = mock_mission
    
    mock_container = MagicMock()
    mock_container.id = "cont1"
    mock_container.volume.return_value = 10000.0
    mock_get_container.return_value = mock_container
    
    # Create waste items
    waste_item1 = MagicMock()
    waste_item1.id = "waste1"
    waste_item1.name = "Waste Item 1"
    waste_item1.status = ItemStatus.WASTE
    waste_item1.mass = 5.0
    waste_item1.priority = 80
    waste_item1.is_expired.return_value = True
    waste_item1.waste_info = None
    waste_item1.volume.return_value = 1000.0
    
    waste_item2 = MagicMock()
    waste_item2.id = "waste2"
    waste_item2.name = "Waste Item 2"
    waste_item2.status = ItemStatus.DEPLETED
    waste_item2.mass = 10.0
    waste_item2.priority = 60
    waste_item2.is_expired.return_value = False
    waste_item2.waste_info = None
    waste_item2.volume.return_value = 2000.0
    
    mock_get_items.return_value = [waste_item1, waste_item2]
    
    # Mock positions
    position1 = MagicMock()
    position1.container_id = "cont2"
    position1.visible = True
    
    position2 = MagicMock()
    position2.container_id = "cont3"
    position2.visible = False
    
    mock_get_position.side_effect = [position1, position2]
    
    # Mock retrieval steps for the second item (not visible)
    mock_retrieval.return_value = [
        {"action": "remove", "item_id": "item1", "item_name": "Blocking Item"}
    ]
    
    # Generate the return plan
    result = generate_return_plan(mock_db, "mission1", "cont1", 20.0)
    
    # Check the result structure
    assert "success" in result
    assert result["success"] is True
    assert "return_plan" in result
    assert "retrieval_steps" in result
    assert "return_manifest" in result
    
    # Check the return plan content
    assert len(result["return_plan"]) == 2  # Both items should be in the plan
    
    # Check that retrieval steps are included for the non-visible item
    assert len(result["retrieval_steps"]) > 0
    
    # Check the manifest
    manifest = result["return_manifest"]
    assert len(manifest["return_items"]) == 2
    assert manifest["total_weight"] == 15.0  # Sum of both item weights
    assert manifest["total_volume"] == 3000.0  # Sum of both item volumes
