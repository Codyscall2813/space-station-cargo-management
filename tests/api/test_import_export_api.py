import pytest
import io
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

def test_import_items():
    """Test importing items from CSV."""
    # Create a sample CSV in memory
    csv_content = (
        "Item ID,Name,Width (cm),Depth (cm),Height (cm),Mass (kg),Priority (1-100),Expiry Date,Usage Limit,Preferred Zone\n"
        "imp_item1,Imported Item 1,10,15,20,5,80,2025-05-20,30,Zone A\n"
        "imp_item2,Imported Item 2,15,10,25,8,90,2025-06-15,20,Zone B\n"
    )
    
    files = {
        'file': ('items.csv', io.StringIO(csv_content), 'text/csv')
    }
    
    # Send request
    response = client.post("/api/import/items", files=files)
    
    # Check response
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["itemsImported"] == 2
    
    # Check that items were added to the database
    db = TestingSessionLocal()
    items = db.query(Item).filter(Item.id.in_(["imp_item1", "imp_item2"])).all()
    assert len(items) == 2
    db.close()

def test_import_containers():
    """Test importing containers from CSV."""
    # Create a sample CSV in memory
    csv_content = (
        "Container ID,Zone,Width(cm),Depth(cm),Height(cm),Open Face,Max Weight (kg)\n"
        "imp_cont1,Zone A,100,85,200,front,500\n"
        "imp_cont2,Zone B,150,90,180,front,600\n"
    )
    
    files = {
        'file': ('containers.csv', io.StringIO(csv_content), 'text/csv')
    }
    
    # Send request
    response = client.post("/api/import/containers", files=files)
    
    # Check response
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["containersImported"] == 2
    
    # Check that containers were added to the database
    db = TestingSessionLocal()
    containers = db.query(Container).filter(Container.id.in_(["imp_cont1", "imp_cont2"])).all()
    assert len(containers) == 2
    db.close()

def test_export_arrangement():
    """Test exporting the current arrangement."""
    # Setup some data to export
    db = TestingSessionLocal()
    
    container = Container(
        id="exp_cont1",
        name="Export Container",
        zone="Export Zone",
        width=100.0,
        height=200.0,
        depth=85.0,
        open_face="front"
    )
    
    item = Item(
        id="exp_item1",
        name="Export Item",
        width=10.0,
        height=20.0,
        depth=15.0,
        mass=5.0,
        priority=80
    )
    
    position = Position(
        id="exp_pos1",
        item_id="exp_item1",
        container_id="exp_cont1",
        x=0.0,
        y=0.0,
        z=0.0,
        orientation=0,
        visible=True
    )
    
    db.add_all([container, item, position])
    db.commit()
    db.close()
    
    # Send export request
    response = client.get("/api/export/arrangement")
    
    # Check response
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv"
    assert "attachment" in response.headers["content-disposition"]
    
    # Parse the CSV content
    csv_content = response.content.decode('utf-8')
    lines = csv_content.strip().split('\n')
    
    # Check CSV structure
    assert "Item ID" in lines[0]
    assert "Container ID" in lines[0]
    assert "Coordinates" in lines[0]
    
    # Should contain our export item
    for line in lines[1:]:
        if "exp_item1" in line and "exp_cont1" in line:
            # Found our item
            assert "(0.0,0.0,0.0)" in line  # Start coordinates
            break
    else:
        assert False, "Exported item not found in CSV"
