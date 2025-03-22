import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.session import Base, get_db
from src.api.main import app
from src.db import crud
from src.models.item import Item, ItemStatus
from src.models.container import Container
from src.models.position import Position

# Setup in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create test database tables
Base.metadata.create_all(bind=engine)

# Override the get_db dependency for testing
def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

# Setup test data
def setup_test_data():
    db = TestingSessionLocal()
    
    # Create test container
    container = Container(
        id="cont1",
        name="Test Container",
        zone="TestZone",
        width=100.0,
        height=200.0,
        depth=85.0,
        open_face="front"
    )
    db.add(container)
    
    # Create test item
    item = Item(
        id="item1",
        name="Test Item",
        width=10.0,
        height=20.0,
        depth=15.0,
        mass=5.0,
        priority=80,
        usage_limit=10,
        current_usage=5,
        status=ItemStatus.ACTIVE
    )
    db.add(item)
    
    # Create test position
    position = Position(
        id="pos1",
        item_id="item1",
        container_id="cont1",
        x=0.0,
        y=0.0,
        z=0.0,
        orientation=0,
        visible=True
    )
    db.add(position)
    
    db.commit()
    db.close()

# Run setup once
setup_test_data()

def test_search_api_by_id():
    """Test search API using item ID."""
    # Search by ID
    response = client.get("/api/search?itemId=item1")
    
    # Check response
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["found"] is True
    assert response.json()["item"]["itemId"] == "item1"
    assert response.json()["item"]["containerId"] == "cont1"
    assert "retrievalSteps" in response.json()

def test_search_api_by_name():
    """Test search API using item name."""
    # Search by name
    response = client.get("/api/search?itemName=Test%20Item")
    
    # Check response
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["found"] is True
    assert response.json()["item"]["itemId"] == "item1"

def test_search_api_not_found():
    """Test search API for an item that doesn't exist."""
    # Search for non-existent item
    response = client.get("/api/search?itemId=nonexistent")
    
    # Check response
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["found"] is False

def test_search_api_missing_parameters():
    """Test search API with missing parameters."""
    # No item ID or name provided
    response = client.get("/api/search")
    
    # Should return an error
    assert response.status_code == 400

def test_retrieve_api():
    """Test retrieve API."""
    # Retrieve item
    response = client.post(
        "/api/retrieve",
        json={
            "itemId": "item1",
            "userId": "user1",
            "timestamp": "2023-01-01T12:00:00"
        }
    )
    
    # Check response
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    # Check that usage count was incremented
    db = TestingSessionLocal()
    item = db.query(Item).filter(Item.id == "item1").first()
    assert item.current_usage == 6  # Was 5, now 6
    db.close()

def test_retrieve_api_nonexistent_item():
    """Test retrieve API with a non-existent item."""
    # Retrieve non-existent item
    response = client.post(
        "/api/retrieve",
        json={
            "itemId": "nonexistent",
            "userId": "user1"
        }
    )
    
    # Should return an error
    assert response.status_code == 404

def test_place_api():
    """Test place API."""
    # Place item
    response = client.post(
        "/api/place",
        json={
            "itemId": "item1",
            "userId": "user1",
            "timestamp": "2023-01-01T12:00:00",
            "containerId": "cont1",
            "position": {
                "startCoordinates": {
                    "width": 10.0,
                    "depth": 10.0,
                    "height": 10.0
                },
                "endCoordinates": {
                    "width": 20.0,
                    "depth": 25.0,
                    "height": 30.0
                }
            }
        }
    )
    
    # Check response
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    # Check that a new position was created
    db = TestingSessionLocal()
    positions = db.query(Position).filter(Position.item_id == "item1").all()
    assert len(positions) > 1  # Should have created a new position
    db.close()

def test_place_api_nonexistent_item():
    """Test place API with a non-existent item."""
    # Place non-existent item
    response = client.post(
        "/api/place",
        json={
            "itemId": "nonexistent",
            "userId": "user1",
            "containerId": "cont1",
            "position": {
                "startCoordinates": {
                    "width": 10.0,
                    "depth": 10.0,
                    "height": 10.0
                },
                "endCoordinates": {
                    "width": 20.0,
                    "depth": 25.0,
                    "height": 30.0
                }
            }
        }
    )
    
    # Should return an error
    assert response.status_code == 404

def test_place_api_nonexistent_container():
    """Test place API with a non-existent container."""
    # Place item in non-existent container
    response = client.post(
        "/api/place",
        json={
            "itemId": "item1",
            "userId": "user1",
            "containerId": "nonexistent",
            "position": {
                "startCoordinates": {
                    "width": 10.0,
                    "depth": 10.0,
                    "height": 10.0
                },
                "endCoordinates": {
                    "width": 20.0,
                    "depth": 25.0,
                    "height": 30.0
                }
            }
        }
    )
    
    # Should return an error
    assert response.status_code == 404
