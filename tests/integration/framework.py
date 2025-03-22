"""
Integration Test Framework for Space Station Cargo Management System.

This module provides the base infrastructure for running integration tests
that verify the correct operation of multiple system components working together.
"""

import pytest
import json
import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.session import Base, get_db
from src.api.main import app
from src.models.container import Container
from src.models.item import Item, ItemStatus
from src.models.position import Position
from src.models.log import LogEntry, ActionType
from src.models.return_mission import ReturnMission, WasteItem, WasteReason, MissionStatus

# Setup in-memory database for testing
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in TEST_DATABASE_URL else {},
    poolclass=StaticPool if "sqlite" in TEST_DATABASE_URL else None
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Override the get_db dependency for testing
def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

# Create a test client
test_client = TestClient(app)

class IntegrationTestFixture:
    """Base class for integration test fixtures."""
    
    @classmethod
    def setup_class(cls):
        """Set up the database tables."""
        Base.metadata.create_all(bind=engine)
    
    @classmethod
    def teardown_class(cls):
        """Drop all tables after tests."""
        Base.metadata.drop_all(bind=engine)
    
    def setup_method(self):
        """Set up before each test."""
        # Create a database session
        self.db = TestingSessionLocal()
        
        # Clear any existing data to ensure test isolation
        self._clear_database()
        
        # Set up any common test data
        self._setup_common_data()
        
        # Commit and close the session
        self.db.commit()
        self.db.close()
    
    def teardown_method(self):
        """Clean up after each test."""
        # Ensure the db session is closed
        if hasattr(self, 'db') and self.db:
            self.db.close()
    
    def _clear_database(self):
        """Clear all data from the database."""
        # Delete rows from all tables - order matters due to foreign keys
        self.db.query(WasteItem).delete()
        self.db.query(ReturnMission).delete()
        self.db.query(Position).delete()
        self.db.query(LogEntry).delete()
        self.db.query(Item).delete()
        self.db.query(Container).delete()
        self.db.commit()
    
    def _setup_common_data(self):
        """Set up common test data used across tests."""
        # Override in subclasses
        pass

    def create_container(self, **kwargs):
        """Create a container with the given attributes."""
        container_id = kwargs.get('id', f"cont_{len(self.db.query(Container).all()) + 1}")
        container = Container(
            id=container_id,
            name=kwargs.get('name', f"Container {container_id}"),
            zone=kwargs.get('zone', "TestZone"),
            width=kwargs.get('width', 100.0),
            height=kwargs.get('height', 200.0),
            depth=kwargs.get('depth', 85.0),
            open_face=kwargs.get('open_face', "front"),
            max_weight=kwargs.get('max_weight', None)
        )
        self.db.add(container)
        self.db.commit()
        self.db.refresh(container)
        return container

    def create_item(self, **kwargs):
        """Create an item with the given attributes."""
        item_id = kwargs.get('id', f"item_{len(self.db.query(Item).all()) + 1}")
        item = Item(
            id=item_id,
            name=kwargs.get('name', f"Item {item_id}"),
            width=kwargs.get('width', 10.0),
            height=kwargs.get('height', 20.0),
            depth=kwargs.get('depth', 15.0),
            mass=kwargs.get('mass', 5.0),
            priority=kwargs.get('priority', 80),
            expiry_date=kwargs.get('expiry_date', None),
            usage_limit=kwargs.get('usage_limit', None),
            current_usage=kwargs.get('current_usage', 0),
            preferred_zone=kwargs.get('preferred_zone', None),
            status=kwargs.get('status', ItemStatus.ACTIVE)
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def create_position(self, **kwargs):
        """Create a position for an item in a container."""
        position_id = kwargs.get('id', f"pos_{len(self.db.query(Position).all()) + 1}")
        position = Position(
            id=position_id,
            item_id=kwargs.get('item_id'),
            container_id=kwargs.get('container_id'),
            x=kwargs.get('x', 0.0),
            y=kwargs.get('y', 0.0),
            z=kwargs.get('z', 0.0),
            orientation=kwargs.get('orientation', 0),
            visible=kwargs.get('visible', True)
        )
        self.db.add(position)
        self.db.commit()
        self.db.refresh(position)
        return position
    
    def create_test_scenario(self, scenario_name):
        """
        Create a predefined test scenario.
        
        Args:
            scenario_name: Name of the scenario to create
            
        Returns:
            Dict with scenario objects
        """
        if scenario_name == "basic_container_with_items":
            container = self.create_container(id="cont1", zone="TestZone")
            
            item1 = self.create_item(id="item1", preferred_zone="TestZone", priority=80)
            item2 = self.create_item(id="item2", preferred_zone="TestZone", priority=90)
            item3 = self.create_item(id="item3", preferred_zone="OtherZone", priority=70)
            
            pos1 = self.create_position(item_id="item1", container_id="cont1", x=0.0, y=0.0, z=0.0)
            pos2 = self.create_position(item_id="item2", container_id="cont1", x=20.0, y=0.0, z=0.0)
            
            return {
                "container": container,
                "items": [item1, item2, item3],
                "positions": [pos1, pos2]
            }
        elif scenario_name == "waste_management":
            # Create containers
            storage = self.create_container(id="storage", zone="Storage")
            undocking = self.create_container(id="undocking", zone="Airlock")
            
            # Create items (waste and regular)
            expired = self.create_item(id="expired", status=ItemStatus.WASTE)
            depleted = self.create_item(id="depleted", status=ItemStatus.DEPLETED)
            regular = self.create_item(id="regular", status=ItemStatus.ACTIVE)
            
            # Create positions
            pos1 = self.create_position(item_id="expired", container_id="storage")
            pos2 = self.create_position(item_id="depleted", container_id="storage")
            pos3 = self.create_position(item_id="regular", container_id="storage")
            
            # Create waste records
            waste1 = WasteItem(
                id="waste1",
                item_id="expired",
                reason=WasteReason.EXPIRED,
                waste_date=None
            )
            waste2 = WasteItem(
                id="waste2",
                item_id="depleted",
                reason=WasteReason.DEPLETED,
                waste_date=None
            )
            
            self.db.add_all([waste1, waste2])
            self.db.commit()
            
            return {
                "containers": [storage, undocking],
                "items": [expired, depleted, regular],
                "positions": [pos1, pos2, pos3],
                "waste_records": [waste1, waste2]
            }
        else:
            raise ValueError(f"Unknown scenario: {scenario_name}")

    def assert_request_success(self, response, message=None):
        """Assert that an API request was successful."""
        assert response.status_code == 200, f"Request failed with status {response.status_code}: {response.text}"
        response_json = response.json()
        assert response_json.get("success", False), f"Request returned success=False: {message or response_json}"
        return response_json

    def api_get(self, endpoint, **kwargs):
        """Make a GET request to the API."""
        return test_client.get(endpoint, **kwargs)

    def api_post(self, endpoint, json_data=None, **kwargs):
        """Make a POST request to the API."""
        return test_client.post(endpoint, json=json_data, **kwargs)

# Export test client for direct usage
client = test_client
