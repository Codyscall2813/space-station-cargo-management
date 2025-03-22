import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.session import Base, get_db
from src.api.main import app

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

def test_placement_api_valid_request():
    """Test placement API with valid data."""
    # Prepare test data
    test_data = {
        "items": [
            {
                "itemId": "item1",
                "name": "Test Item 1",
                "width": 10.0,
                "depth": 15.0,
                "height": 20.0,
                "mass": 5.0,
                "priority": 80,
                "preferredZone": "TestZone"
            }
        ],
        "containers": [
            {
                "containerId": "cont1",
                "zone": "TestZone",
                "width": 100.0,
                "depth": 85.0,
                "height": 200.0
            }
        ]
    }
    
    # Send request
    response = client.post("/api/placement", json=test_data)
    
    # Check response
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "placements" in response.json()
    assert "rearrangements" in response.json()
    
    # Check placement content
    placements = response.json()["placements"]
    assert len(placements) == 1
    assert placements[0]["itemId"] == "item1"
    assert placements[0]["containerId"] == "cont1"
    assert "position" in placements[0]

def test_placement_api_invalid_request():
    """Test placement API with invalid data."""
    # Missing required fields
    invalid_data = {
        "items": [
            {
                "itemId": "item1",
                "name": "Test Item 1"
                # Missing dimensions
            }
        ],
        "containers": [
            {
                "containerId": "cont1",
                "zone": "TestZone",
                "width": 100.0,
                "depth": 85.0,
                "height": 200.0
            }
        ]
    }
    
    # Send request
    response = client.post("/api/placement", json=invalid_data)
    
    # Should return an error
    assert response.status_code != 200

def test_placement_api_no_containers():
    """Test placement API with no containers."""
    # No containers provided
    no_containers_data = {
        "items": [
            {
                "itemId": "item1",
                "name": "Test Item 1",
                "width": 10.0,
                "depth": 15.0,
                "height": 20.0,
                "mass": 5.0,
                "priority": 80
            }
        ],
        "containers": []
    }
    
    # Send request
    response = client.post("/api/placement", json=no_containers_data)
    
    # Should return an error
    assert response.status_code == 400

def test_placement_api_no_items():
    """Test placement API with no items."""
    # No items provided
    no_items_data = {
        "items": [],
        "containers": [
            {
                "containerId": "cont1",
                "zone": "TestZone",
                "width": 100.0,
                "depth": 85.0,
                "height": 200.0
            }
        ]
    }
    
    # Send request
    response = client.post("/api/placement", json=no_items_data)
    
    # Should return an error
    assert response.status_code == 400
