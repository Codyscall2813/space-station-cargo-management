import pytest
import networkx as nx
from unittest.mock import MagicMock, patch
from src.algorithms.retrieval import (
    generate_retrieval_steps,
    is_visible,
    build_dependency_graph,
    find_items_to_move
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
def sample_items():
    """Create sample items for testing."""
    item1 = Item(
        id="item1",
        name="Test Item 1",
        width=10.0,
        height=20.0,
        depth=15.0,
        mass=5.0,
        priority=80
    )
    item2 = Item(
        id="item2",
        name="Test Item 2",
        width=15.0,
        height=25.0,
        depth=10.0,
        mass=8.0,
        priority=90
    )
    item3 = Item(
        id="item3",
        name="Test Item 3",
        width=20.0,
        height=15.0,
        depth=30.0,
        mass=12.0,
        priority=70
    )
    return [item1, item2, item3]

@pytest.fixture
def sample_positions(sample_items):
    """Create sample positions for testing."""
    # Item 1 is at the front (visible)
    pos1 = Position(
        id="pos1",
        item_id="item1",
        container_id="cont1",
        x=0.0,
        y=0.0,
        z=0.0,  # At the front
        orientation=0,
        visible=True
    )
    
    # Item 2 is behind item 1
    pos2 = Position(
        id="pos2",
        item_id="item2",
        container_id="cont1",
        x=5.0,
        y=5.0,
        z=20.0,  # Behind item 1
        orientation=0,
        visible=False
    )
    
    # Item 3 is at a different location but still visible
    pos3 = Position(
        id="pos3",
        item_id="item3",
        container_id="cont1",
        x=50.0,
        y=50.0,
        z=0.0,  # At the front
        orientation=0,
        visible=True
    )
    
    return [pos1, pos2, pos3]

def test_is_visible():
    """Test the visibility determination function."""
    container = Container(
        id="cont1",
        name="Test Container",
        zone="TestZone",
        width=100.0,
        height=200.0,
        depth=85.0,
        open_face="front"
    )
    
    # Items at z=0 should be visible
    assert is_visible(0.0, 0.0, 0.0, container) is True
    assert is_visible(50.0, 100.0, 0.0, container) is True
    
    # Items not at z=0 should not be visible
    assert is_visible(0.0, 0.0, 10.0, container) is False
    assert is_visible(50.0, 100.0, 5.0, container) is False

def test_build_dependency_graph(mock_db, sample_positions, sample_container):
    """Test building the dependency graph."""
    with patch('src.db.crud.get_item') as mock_get_item:
        # Mock the get_item function to return appropriate items
        def mock_get_item_side_effect(db, item_id):
            if item_id == "item1":
                item = MagicMock()
                item.width = 10.0
                item.height = 20.0
                item.depth = 15.0
                item.get_possible_orientations.return_value = [(10.0, 20.0, 15.0)]
                return item
            elif item_id == "item2":
                item = MagicMock()
                item.width = 15.0
                item.height = 25.0
                item.depth = 10.0
                item.get_possible_orientations.return_value = [(15.0, 25.0, 10.0)]
                return item
            elif item_id == "item3":
                item = MagicMock()
                item.width = 20.0
                item.height = 15.0
                item.depth = 30.0
                item.get_possible_orientations.return_value = [(20.0, 15.0, 30.0)]
                return item
            return None
        
        mock_get_item.side_effect = mock_get_item_side_effect
        
        # Build the graph
        graph = build_dependency_graph(mock_db, sample_positions, sample_container)
        
        # Check that all items are in the graph
        assert len(graph.nodes) == 3
        assert "item1" in graph.nodes
        assert "item2" in graph.nodes
        assert "item3" in graph.nodes
        
        # Since item1 is in front of item2, there should be an edge from item1 to item2
        assert graph.has_edge("item1", "item2")
        
        # There should be no other edges
        assert len(graph.edges) == 1

def test_find_items_to_move():
    """Test finding items that need to be moved."""
    # Create a simple dependency graph
    # item1 blocks item2, item3 blocks item4
    graph = nx.DiGraph()
    graph.add_nodes_from(["item1", "item2", "item3", "item4"])
    graph.add_edges_from([("item1", "item2"), ("item3", "item4")])
    
    # To retrieve item2, we should move item1
    items_to_move = find_items_to_move(graph, "item2")
    assert items_to_move == ["item1"]
    
    # To retrieve item4, we should move item3
    items_to_move = find_items_to_move(graph, "item4")
    assert items_to_move == ["item3"]
    
    # To retrieve item1 or item3, we don't need to move anything
    assert find_items_to_move(graph, "item1") == []
    assert find_items_to_move(graph, "item3") == []

@patch('src.algorithms.retrieval.build_dependency_graph')
@patch('src.algorithms.retrieval.find_items_to_move')
@patch('src.db.crud.get_item')
@patch('src.db.crud.get_container')
@patch('src.db.crud.get_container_positions')
def test_generate_retrieval_steps(
    mock_get_positions, mock_get_container, mock_get_item, 
    mock_find_items, mock_build_graph, mock_db
):
    """Test generating retrieval steps."""
    # Setup mocks
    mock_item = MagicMock()
    mock_item.id = "item2"
    mock_item.name = "Test Item 2"
    mock_get_item.return_value = mock_item
    
    mock_container = MagicMock()
    mock_container.id = "cont1"
    mock_get_container.return_value = mock_container
    
    mock_position = MagicMock()
    mock_position.item_id = "item2"
    mock_position.x = 5.0
    mock_position.y = 5.0
    mock_position.z = 20.0
    mock_position.visible = False
    mock_get_positions.return_value = [mock_position]
    
    mock_graph = MagicMock()
    mock_build_graph.return_value = mock_graph
    
    # Mock that item1 needs to be moved to get to item2
    mock_find_items.return_value = ["item1"]
    
    # Call the function
    steps = generate_retrieval_steps(mock_db, "item2", "cont1")
    
    # Check that the steps are correct
    assert len(steps) == 4
    
    # Step 1: Remove item1
    assert steps[0]["action"] == "remove"
    assert steps[0]["item_id"] == "item1"
    
    # Step 2: Set aside item1
    assert steps[1]["action"] == "setAside"
    assert steps[1]["item_id"] == "item1"
    
    # Step 3: Retrieve target item2
    assert steps[2]["action"] == "retrieve"
    assert steps[2]["item_id"] == "item2"
    
    # Step 4: Place back item1
    assert steps[3]["action"] == "placeBack"
    assert steps[3]["item_id"] == "item1"
    
    # Test with a visible item (no items to move)
    mock_position.visible = True
    mock_find_items.return_value = []
    
    steps = generate_retrieval_steps(mock_db, "item2", "cont1")
    
    # Should only have one step to retrieve the item
    assert len(steps) == 1
    assert steps[0]["action"] == "retrieve"
    assert steps[0]["item_id"] == "item2"
