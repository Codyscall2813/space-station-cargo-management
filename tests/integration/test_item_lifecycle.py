"""
Integration tests for the complete item lifecycle workflow.

This test suite verifies the end-to-end functionality of items through their
complete lifecycle:
1. Import items and containers
2. Optimize item placement
3. Search and retrieve items
4. Track usage and expiration
5. Identify waste items
6. Plan waste return
7. Complete undocking
"""

import pytest
import io
from datetime import date, datetime, timedelta
from tests.integration.framework import IntegrationTestFixture, client

class TestItemLifecycleIntegration(IntegrationTestFixture):
    """Test the complete lifecycle of items in the system."""
    
    def test_complete_item_lifecycle(self):
        """
        Test a complete item lifecycle from import to disposal.
        
        This test verifies the integration between multiple system components:
        - Import/Export API
        - Placement Algorithm
        - Retrieval Algorithm
        - Simulation Engine
        - Waste Management
        - Return Planning
        
        The test creates a realistic scenario with multiple items and containers,
        then exercises the full workflow that would occur in the real system.
        """
        # Step 1: Import containers
        containers_csv = (
            "Container ID,Zone,Width(cm),Depth(cm),Height(cm),Open Face,Max Weight (kg)\n"
            "storage1,Storage,100,85,200,front,500\n"
            "storage2,Storage,120,90,180,front,600\n"
            "return1,Airlock,150,100,200,front,1000\n"
        )
        
        files = {'file': ('containers.csv', io.StringIO(containers_csv), 'text/csv')}
        response = client.post("/api/import/containers", files=files)
        self.assert_request_success(response)
        
        # Step 2: Import items with different properties
        items_csv = (
            "Item ID,Name,Width (cm),Depth (cm),Height (cm),Mass (kg),Priority (1-100),Expiry Date,Usage Limit,Preferred Zone\n"
            "food1,Food Package,20,15,10,2,80,{expiry1},5,Storage\n"
            "food2,Food Package,20,15,10,2,80,{expiry2},5,Storage\n"
            "tool1,Tool Kit,30,25,15,10,90,,10,Storage\n"
            "equip1,Equipment,40,35,20,15,70,,3,Storage\n"
        ).format(
            expiry1=(date.today() + timedelta(days=5)).isoformat(),
            expiry2=(date.today() - timedelta(days=1)).isoformat()  # Already expired
        )
        
        files = {'file': ('items.csv', io.StringIO(items_csv), 'text/csv')}
        response = client.post("/api/import/items", files=files)
        self.assert_request_success(response)
        
        # Step 3: Get placement recommendations
        placement_request = {
            "items": [
                {
                    "itemId": "food1",
                    "name": "Food Package",
                    "width": 20,
                    "depth": 15,
                    "height": 10,
                    "mass": 2,
                    "priority": 80,
                    "expiryDate": (date.today() + timedelta(days=5)).isoformat(),
                    "usageLimit": 5,
                    "preferredZone": "Storage"
                },
                {
                    "itemId": "food2",
                    "name": "Food Package",
                    "width": 20,
                    "depth": 15,
                    "height": 10,
                    "mass": 2,
                    "priority": 80,
                    "expiryDate": (date.today() - timedelta(days=1)).isoformat(),
                    "usageLimit": 5,
                    "preferredZone": "Storage"
                },
                {
                    "itemId": "tool1",
                    "name": "Tool Kit",
                    "width": 30,
                    "depth": 25,
                    "height": 15,
                    "mass": 10,
                    "priority": 90,
                    "usageLimit": 10,
                    "preferredZone": "Storage"
                },
                {
                    "itemId": "equip1",
                    "name": "Equipment",
                    "width": 40,
                    "depth": 35,
                    "height": 20,
                    "mass": 15,
                    "priority": 70,
                    "usageLimit": 3,
                    "preferredZone": "Storage"
                }
            ],
            "containers": [
                {
                    "containerId": "storage1",
                    "zone": "Storage",
                    "width": 100,
                    "depth": 85,
                    "height": 200
                },
                {
                    "containerId": "storage2",
                    "zone": "Storage",
                    "width": 120,
                    "depth": 90,
                    "height": 180
                },
                {
                    "containerId": "return1",
                    "zone": "Airlock",
                    "width": 150,
                    "depth": 100,
                    "height": 200
                }
            ]
        }
        
        response = client.post("/api/placement", json=placement_request)
        placement_result = self.assert_request_success(response)
        
        # Verify placement results
        assert len(placement_result["placements"]) == 4, "All items should have been placed"
        
        # Step 4: Check the expired item with waste management
        response = client.get("/api/waste/identify")
        waste_result = self.assert_request_success(response)
        
        # Verify that food2 is identified as waste (expired)
        assert len(waste_result["wasteItems"]) >= 1, "Should identify at least one waste item"
        waste_item_ids = [item["itemId"] for item in waste_result["wasteItems"]]
        assert "food2" in waste_item_ids, "food2 should be identified as waste"
        
        # Step 5: Retrieve and use the food1 item
        response = client.get("/api/search?itemId=food1")
        search_result = self.assert_request_success(response)
        assert search_result["found"], "Should find food1"
        
        # Retrieve the item
        retrieval_request = {
            "itemId": "food1",
            "userId": "astronaut1",
            "timestamp": datetime.now().isoformat()
        }
        response = client.post("/api/retrieve", json=retrieval_request)
        self.assert_request_success(response)
        
        # Step 6: Use the tool1 until it's depleted
        # First, find the item
        response = client.get("/api/search?itemId=tool1")
        search_result = self.assert_request_success(response)
        assert search_result["found"], "Should find tool1"
        
        # Use the tool multiple times until depleted
        for i in range(10):  # Usage limit is 10
            retrieval_request = {
                "itemId": "tool1",
                "userId": "astronaut1",
                "timestamp": datetime.now().isoformat()
            }
            response = client.post("/api/retrieve", json=retrieval_request)
            self.assert_request_success(response)
        
        # Step 7: Check for waste items again (should include the depleted tool)
        response = client.get("/api/waste/identify")
        waste_result = self.assert_request_success(response)
        
        # Verify both food2 (expired) and tool1 (depleted) are identified as waste
        assert len(waste_result["wasteItems"]) >= 2, "Should identify at least two waste items"
        waste_item_ids = [item["itemId"] for item in waste_result["wasteItems"]]
        assert "food2" in waste_item_ids, "food2 should be identified as waste"
        assert "tool1" in waste_item_ids, "tool1 should be identified as waste"
        
        # Step 8: Generate a return plan for waste items
        return_plan_request = {
            "undockingContainerId": "return1",
            "undockingDate": (date.today() + timedelta(days=5)).isoformat(),
            "maxWeight": 100.0
        }
        response = client.post("/api/waste/return-plan", json=return_plan_request)
        return_plan = self.assert_request_success(response)
        
        # Verify return plan includes the waste items
        return_items = [item["itemId"] for item in return_plan["returnManifest"]["returnItems"]]
        assert "food2" in return_items, "food2 should be in return manifest"
        assert "tool1" in return_items, "tool1 should be in return manifest"
        
        # Step 9: Complete the undocking process
        undocking_request = {
            "undockingContainerId": "return1",
            "timestamp": datetime.now().isoformat()
        }
        response = client.post("/api/waste/complete-undocking", json=undocking_request)
        undocking_result = self.assert_request_success(response)
        
        # Verify undocking removed the items
        assert undocking_result["itemsRemoved"] >= 2, "Should remove at least the waste items"
        
        # Step 10: Verify through export that items are in the correct state
        response = client.get("/api/export/arrangement")
        assert response.status_code == 200, "Export should succeed"
        
        # Parse the CSV to verify items
        csv_content = response.content.decode('utf-8')
        csv_lines = csv_content.strip().split('\n')
        
        # Check that food1 is still in storage but food2 and tool1 are gone
        stored_items = []
        for line in csv_lines[1:]:  # Skip header
            if line:
                item_id = line.split(',')[0]
                stored_items.append(item_id)
        
        assert "food1" in stored_items, "food1 should still be in storage"
        assert "food2" not in stored_items, "food2 should be gone (undocked)"
        assert "tool1" not in stored_items, "tool1 should be gone (undocked)"
        assert "equip1" in stored_items, "equip1 should still be in storage"
        
    def test_simulation_with_item_lifecycle(self):
        """
        Test the simulation engine with item lifecycle changes.
        
        This test verifies that time simulation correctly:
        - Advances date
        - Tracks item usage
        - Identifies expired items
        - Handles item depletion
        """
        # Step 1: Import containers
        containers_csv = "Container ID,Zone,Width(cm),Depth(cm),Height(cm)\nstorageA,Storage,100,85,200\n"
        files = {'file': ('containers.csv', io.StringIO(containers_csv), 'text/csv')}
        response = client.post("/api/import/containers", files=files)
        self.assert_request_success(response)
        
        # Step 2: Import items with different properties
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        items_csv = (
            "Item ID,Name,Width (cm),Depth (cm),Height (cm),Mass (kg),Priority (1-100),Expiry Date,Usage Limit\n"
            "simFood,Sim Food,20,15,10,2,80,{tomorrow},5\n"
            "simTool,Sim Tool,30,25,15,10,90,,2\n"
        ).format(tomorrow=tomorrow)
        
        files = {'file': ('items.csv', io.StringIO(items_csv), 'text/csv')}
        response = client.post("/api/import/items", files=files)
        self.assert_request_success(response)
        
        # Step 3: Place items in the container
        placement_request = {
            "items": [
                {
                    "itemId": "simFood",
                    "name": "Sim Food",
                    "width": 20,
                    "depth": 15,
                    "height": 10,
                    "mass": 2,
                    "priority": 80,
                    "expiryDate": tomorrow,
                    "usageLimit": 5
                },
                {
                    "itemId": "simTool",
                    "name": "Sim Tool",
                    "width": 30,
                    "depth": 25,
                    "height": 15,
                    "mass": 10,
                    "priority": 90,
                    "usageLimit": 2
                }
            ],
            "containers": [
                {
                    "containerId": "storageA",
                    "zone": "Storage",
                    "width": 100,
                    "depth": 85,
                    "height": 200
                }
            ]
        }
        
        response = client.post("/api/placement", json=placement_request)
        self.assert_request_success(response)
        
        # Step 4: Use the tool once
        retrieval_request = {
            "itemId": "simTool",
            "userId": "astronaut1"
        }
        response = client.post("/api/retrieve", json=retrieval_request)
        self.assert_request_success(response)
        
        # Step 5: Simulate advancing time by 2 days with tool usage
        simulation_request = {
            "numOfDays": 2,
            "itemsToBeUsedPerDay": [
                {"itemId": "simTool"}
            ]
        }
        response = client.post("/api/simulate/day", json=simulation_request)
        simulation_result = self.assert_request_success(response)
        
        # Check simulation results
        assert len(simulation_result["changes"]["itemsExpired"]) >= 1, "simFood should have expired"
        assert len(simulation_result["changes"]["itemsDepletedToday"]) >= 1, "simTool should be depleted"
        
        # Step 6: Verify items are correctly marked as waste
        response = client.get("/api/waste/identify")
        waste_result = self.assert_request_success(response)
        
        # Both items should be waste now
        waste_items = waste_result["wasteItems"]
        waste_item_ids = [item["itemId"] for item in waste_items]
        
        assert len(waste_items) >= 2, "Should identify both items as waste"
        assert "simFood" in waste_item_ids, "simFood should be waste (expired)"
        assert "simTool" in waste_item_ids, "simTool should be waste (depleted)"
        
        # Verify the reasons are correct
        for item in waste_items:
            if item["itemId"] == "simFood":
                assert item["reason"] == "Expired", "simFood should be expired"
            elif item["itemId"] == "simTool":
                assert item["reason"] == "Out of Uses", "simTool should be depleted"
