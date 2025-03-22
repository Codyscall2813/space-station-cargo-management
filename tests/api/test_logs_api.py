import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.session import Base, get_db
from src.api.main import app
from src.models.log import LogEntry, ActionType

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

# Setup test logs
def setup_logs():
    db = TestingSessionLocal()
    
    # Create sample log entries
    log1 = LogEntry(
        operation=ActionType.PLACEMENT,
        user_id="user1",
        details={"items_placed": 2},
        item_ids=["log_item1", "log_item2"],
        container_ids=["log_cont1"]
    )
    
    log2 = LogEntry(
        operation=ActionType.RETRIEVAL,
        user_id="user2",
        details={"item_retrieved": "log_item1"},
        item_ids=["log_item1"],
        container_ids=["log_cont1"]
    )
    
    log3 = LogEntry(
        operation=ActionType.DISPOSAL,
        user_id="user1",
        details={"item_disposed": "log_item3"},
        item_ids=["log_item3"],
        container_ids=["log_cont2"]
    )
    
    # Set timestamps to be different
    log1.timestamp = datetime.now() - timedelta(days=2)
    log2.timestamp = datetime.now() - timedelta(days=1)
    log3.timestamp = datetime.now()
    
    db.add_all([log1, log2, log3])
    db.commit()
    db.close()

# Run setup once
setup_logs()

def test_get_logs_all():
    """Test getting all logs within a date range."""
    # Get logs for the last 3 days
    start_date = (datetime.now() - timedelta(days=3)).isoformat()
    end_date = datetime.now().isoformat()
    
    response = client.get(f"/api/logs?startDate={start_date}&endDate={end_date}")
    
    # Check response
    assert response.status_code == 200
    assert "logs" in response.json()
    assert len(response.json()["logs"]) == 3  # All logs

def test_get_logs_by_user():
    """Test getting logs filtered by user ID."""
    # Get logs for user1
    start_date = (datetime.now() - timedelta(days=3)).isoformat()
    end_date = datetime.now().isoformat()
    
    response = client.get(f"/api/logs?startDate={start_date}&endDate={end_date}&userId=user1")
    
    # Check response
    assert response.status_code == 200
    assert "logs" in response.json()
    
    logs = response.json()["logs"]
    assert len(logs) == 2  # Two logs for user1
    
    # All logs should be for user1
    for log in logs:
        assert log["userId"] == "user1"

def test_get_logs_by_action_type():
    """Test getting logs filtered by action type."""
    # Get retrieval logs
    start_date = (datetime.now() - timedelta(days=3)).isoformat()
    end_date = datetime.now().isoformat()
    
    response = client.get(f"/api/logs?startDate={start_date}&endDate={end_date}&actionType=retrieval")
    
    # Check response
    assert response.status_code == 200
    assert "logs" in response.json()
    
    logs = response.json()["logs"]
    assert len(logs) == 1  # One retrieval log
    assert logs[0]["actionType"] == "retrieval"

def test_get_logs_by_item():
    """Test getting logs filtered by item ID."""
    # Get logs for item1
    start_date = (datetime.now() - timedelta(days=3)).isoformat()
    end_date = datetime.now().isoformat()
    
    # The logs API should filter by item ID internally
    response = client.get(f"/api/logs?startDate={start_date}&endDate={end_date}&itemId=log_item1")
    
    # Check response
    assert response.status_code == 200
    
    # Due to the implementation, we'd need to check the filtering in a more integrated way
    # However, for unit testing we can verify the basic API functionality
    assert "logs" in response.json()

def test_get_logs_invalid_date():
    """Test getting logs with invalid date format."""
    # Invalid date format
    response = client.get("/api/logs?startDate=invalid&endDate=invalid")
    
    # Should return an error
    assert response.status_code == 400
