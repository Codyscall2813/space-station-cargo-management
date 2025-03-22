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
from src.models.return_mission import ReturnMission, WasteItem, WasteReason, MissionStatus

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

# Setup test data for waste management
def setup_waste_data():
    db = TestingSessionLocal()
    
    # Create containers
    container1 = Container(
        id="waste_cont1",
        name="Storage Container",
        zone="Storage",
        width=100.0,
        height=200.0,
        depth=85.0,
        open_face="front"
    )
    
    container2 = Container(
        id="waste_cont2",
        name="Undocking Container",
        zone="Airlock",
        width=150.0,
        height=180.0,
        depth=90.0,
        open_face="front"
    )
    
    # Create items in different states
    
    # Expired item
    expired_item = Item(
        id="waste_item1",
        name="Expired Food",
        width=10.0,
        height=20.0,
        depth=15.0,
        mass=5.0,
        priority=80,
        expiry_date=date.today() - timedelta(days=5),
        status=ItemStatus.WASTE
    )
    
    # Depleted item
    depleted_item = Item(
        id="waste_item2",
        name="Depleted Supply",
        width=15.0,
        height=25.0,
        depth=10.0,
        mass=8.0,
        priority=90,
        usage_limit=10,
        current_usage=10,
        status=ItemStatus.DEPLETED
    )
    
    # Regular item (not waste)
    regular_item = Item(
        id="reg_item1",
        name="Regular Item",
        width=20.0,
        height=15.0,
        depth=30.0,
        mass=12.0,
        priority=70,
        status=ItemStatus.ACTIVE
    )
    
    # Positions for items
    position1 = Position(
        id="waste_pos1",
        item_id="waste_item1",
        container_id="waste_cont1",
        x=0.0,
        y=0.0,
        z=0.0,
        orientation=0,
        visible=True
    )
    
    position2 = Position(
        id="waste_pos2",
        item_id="waste_item2",
        container_id="waste_cont1",
        x=20.0,
        y=0.0,
        z=0.0,
        orientation=0,
        visible=True
    )
    
    position3 = Position(
        id="reg_pos1",
        item_id="reg_item1",
        container_id="waste_cont1",
        x=40.0,
        y=0.0,
        z=0.0,
        orientation=0,
        visible=True
    )
    
    # Create waste records
    waste1 = WasteItem(
        id="waste_record1",
        item_id="waste_item1",
        reason=WasteReason.EXPIRED,
        waste_date=date.today() - timedelta(days=5)
    )
    
    waste2 = WasteItem(
        id="waste_record2",
        item_id="waste_item2",
        reason=WasteReason.DEPLETED,
        waste_date=date.today() - timedelta(days=2)
    )
    
    db.add_all([
        container1, container2,
        expired_item, depleted_item, regular_item,
        position1, position2, position3,
        waste1, waste2
    ])
    db.commit()
    db.close()

# Run setup once
setup_waste_data()

def test_identify_waste():
    """Test waste identification API."""
    response = client.get("/api/waste/identify")
    
    # Check response
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    # Should identify both waste items
    waste_items = response.json()["wasteItems"]
    assert len(waste_items) == 2
    
    # Check waste item details
    waste_ids = [item["itemId"] for item in waste_items]
    assert "waste_item1" in waste_ids
    assert "waste_item2" in waste_ids
    
    # Check reasons
    for item in waste_items:
        if item["itemId"] == "waste_item1":
            assert item["reason"] == "Expired"
        elif item["itemId"] == "waste_item2":
            assert item["reason"] == "Out of Uses"

def test_return_plan_generation():
    """Test return plan generation API."""
    response = client.post(
        "/api/waste/return-plan",
        json={
            "undockingContainerId": "waste_cont2",
            "undockingDate": (date.today() + timedelta(days=7)).isoformat(),
            "maxWeight": 50.0
        }
    )
    
    # Check response
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    # Check return plan components
    assert "returnPlan" in response.json()
    assert "retrievalSteps" in response.json()
    assert "returnManifest" in response.json()
    
    # Check manifest
    manifest = response.json()["returnManifest"]
    assert manifest["undockingContainerId"] == "waste_cont2"
    assert len(manifest["returnItems"]) == 2  # Both waste items
    
    # Check return plan
    return_plan = response.json()["returnPlan"]
    assert len(return_plan) == 2  # Both waste items
    
    # All items should be moved to the undocking container
    for step in return_plan:
        assert step["toContainer"] == "waste_cont2"

def test_complete_undocking():
    """Test undocking completion API."""
    # First create a return mission and assign waste items to it
    db = TestingSessionLocal()
    
    mission = ReturnMission(
        id="test_mission",
        scheduled_date=date.today() + timedelta(days=7),
        max_weight=50.0,
        max_volume=10000.0,
        current_weight=13.0,  # Sum of waste item weights
        current_volume=5000.0,
        status=MissionStatus.LOADING
    )
    db.add(mission)
    
    # Assign waste items to mission
    waste1 = db.query(WasteItem).filter(WasteItem.id == "waste_record1").first()
    waste2 = db.query(WasteItem).filter(WasteItem.id == "waste_record2").first()
    
    waste1.return_mission_id = "test_mission"
    waste2.return_mission_id = "test_mission"
    
    # Move items to undocking container
    pos1 = db.query(Position).filter(Position.item_id == "waste_item1").first()
    pos2 = db.query(Position).filter(Position.item_id == "waste_item2").first()
    
    pos1.container_id = "waste_cont2"
    pos2.container_id = "waste_cont2"
    
    db.commit()
    db.close()
    
    # Now test the undocking completion
    response = client.post(
        "/api/waste/complete-undocking",
        json={
            "undockingContainerId": "waste_cont2",
            "timestamp": datetime.now().isoformat()
        }
    )
    
    # Check response
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["itemsRemoved"] == 2
    
    # Check that positions were removed
    db = TestingSessionLocal()
    positions = db.query(Position).filter(
        Position.container_id == "waste_cont2"
    ).all()
    assert len(positions) == 0
    
    # Check that mission was marked as complete
    mission = db.query(ReturnMission).filter(
        ReturnMission.id == "test_mission"
    ).first()
    assert mission.status == MissionStatus.COMPLETE
    
    db.close()
