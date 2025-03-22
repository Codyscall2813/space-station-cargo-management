import pytest
from fastapi.testclient import TestClient
from datetime import datetime, date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.session import Base, get_db
from src.api.main import app
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

# Setup test data for simulation
def setup_simulation_data():
    db = TestingSessionLocal()
    
    # Create items with different properties for simulation
    
    # Regular item
    item1 = Item(
        id="sim_item1",
        name="Regular Item",
        width=10.0,
        height=20.0,
        depth=15.0,
        mass=5.0,
        priority=80,
        usage_limit=10,
        current_usage=5,
        status=ItemStatus.ACTIVE
    )
    
    # Item close to expiration
    tomorrow = date.today() + timedelta(days=1)
    item2 = Item(
        id="sim_item2",
        name="Expiring Item",
        width=15.0,
        height=25.0,
        depth=10.0,
        mass=8.0,
        priority=90,
        expiry_date=tomorrow,
        status=ItemStatus.ACTIVE
    )
    
    # Item almost depleted
    item3 = Item(
        id="sim_item3",
        name="Almost Depleted Item",
        width=20.0,
        height=15.0,
        depth=30.0,
        mass=12.0,
        priority=70,
        usage_limit=6,
        current_usage=5,
        status=ItemStatus.ACTIVE
    )
    
    db.add(item1)
    db.add(item2)
    db.add(item3)
    db.commit()
    db.close()

# Run setup once
setup_simulation_data()

def test_simulate_day_basic():
    """Test basic day simulation."""
    # Simulate one day with no items used
    response = client.post(
        "/api/simulate/day",
        json={
            "numOfDays": 1,
            "itemsToBeUsedPerDay": []
        }
    )
    
    # Check response
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "newDate" in response.json()
    assert "changes" in response.json()
    
    # No items should be used
    assert len(response.json()["changes"]["itemsUsed"]) == 0

def test_simulate_day_with_usage():
    """Test simulation with item usage."""
    # Simulate one day with item usage
    response = client.post(
        "/api/simulate/day",
        json={
            "numOfDays": 1,
            "itemsToBeUsedPerDay": [
                {"itemId": "sim_item1"},
                {"itemId": "sim_item3"}
            ]
        }
    )
    
    # Check response
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    # Check that items were used
    used_items = response.json()["changes"]["itemsUsed"]
    assert len(used_items) == 2
    
    # Item1 should have been used but not depleted
    item1_data = next(item for item in used_items if item["itemId"] == "sim_item1")
    assert item1_data["remainingUses"] == 4  # Was 5, used 1
    
    # Item3 should have been depleted (was at 5/6 usage)
    depleted_items = response.json()["changes"]["itemsDepletedToday"]
    assert len(depleted_items) == 1
    assert depleted_items[0]["itemId"] == "sim_item3"
    
    # Check database state
    db = TestingSessionLocal()
    item1 = db.query(Item).filter(Item.id == "sim_item1").first()
    item3 = db.query(Item).filter(Item.id == "sim_item3").first()
    
    assert item1.current_usage == 6  # Was 5, now 6
    assert item3.current_usage == 6  # Was 5, now 6 (max)
    assert item3.status == ItemStatus.DEPLETED  # Should be marked as depleted
    
    db.close()

def test_simulate_day_with_expiration():
    """Test simulation with item expiration."""
    # Simulate two days to trigger expiration
    response = client.post(
        "/api/simulate/day",
        json={
            "numOfDays": 2,
            "itemsToBeUsedPerDay": []
        }
    )
    
    # Check response
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    # Check that items expired
    expired_items = response.json()["changes"]["itemsExpired"]
    assert len(expired_items) == 1
    assert expired_items[0]["itemId"] == "sim_item2"
    
    # Check database state
    db = TestingSessionLocal()
    item2 = db.query(Item).filter(Item.id == "sim_item2").first()
    
    assert item2.status == ItemStatus.WASTE  # Should be marked as waste
    
    db.close()

def test_simulate_day_with_specific_date():
    """Test simulation to a specific date."""
    # Simulate to a specific date
    target_date = (date.today() + timedelta(days=5)).isoformat()
    response = client.post(
        "/api/simulate/day",
        json={
            "toTimestamp": target_date,
            "itemsToBeUsedPerDay": []
        }
    )
    
    # Check response
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["newDate"] == target_date
