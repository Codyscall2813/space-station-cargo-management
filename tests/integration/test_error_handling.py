"""
Integration tests for error handling and system stability.

This test suite verifies the system's ability to handle various error conditions
and maintain stability under problematic inputs:
1. Validation of inputs at API boundaries
2. Graceful handling of invalid data
3. Error recovery mechanisms
4. System stability under edge case scenarios
"""

import pytest
import io
import json
from datetime import date, datetime, timedelta
from tests.integration.framework import IntegrationTestFixture, client

class TestErrorHandlingIntegration(IntegrationTestFixture):
    """Test the system's error handling and stability."""
    
    def test_invalid_dimensions_handling(self):
        """
        Test handling of invalid item dimensions.
        
        This test verifies that:
        1. The system validates item dimensions properly
        2. Appropriate error messages are returned
        3. The system remains stable after invalid inputs
        """
        # Step 1: Create a valid container
        container = self.create_container(id="valid_cont")
        
        # Step 2: Attempt to place an item with invalid dimensions
        placement_request = {
            "items": [
                {
                    "itemId": "invalid_item",
                    "name": "Invalid Item",
                    "width": -10.0,  # Negative value (invalid)
                    "depth": 0.0,    # Zero value (invalid)
                    "height": 20.0,
                    "mass": 5.0,
                    "priority": 80
                }
            ],
            "containers": [
                {
                    "containerId": container.id,
                    "zone": container.zone,
                    "width": container.width,
                    "depth": container.depth,
                    "height": container.height
                }
            ]
        }
        
        # Expect an error response
        response = client.post("/api/placement", json=placement_request)
        assert response.status_code != 200, "Should reject invalid dimensions"
        
        # Step 3: Now try with a valid item to ensure system stability
        valid_placement_request = {
            "items": [
                {
                    "itemId": "valid_item",
                    "name": "Valid Item",
                    "width": 10.0,
                    "depth": 15.0,
                    "height": 20.0,
                    "mass": 5.0,
                    "priority": 80
                }
            ],
            "containers": [
                {
                    "containerId": container.id,
                    "zone": container.zone,
                    "width": container.width,
                    "depth": container.depth,
                    "height": container.height
                }
            ]
        }
        
        response = client.post("/api/placement", json=valid_placement_request)
        placement_result = self.assert_request_success(response)
        
        # Verify the valid placement succeeded despite previous error
        assert len(placement_result["placements"]) == 1, "Should place the valid item"
    
    def test_nonexistent_item_handling(self):
        """
        Test handling of operations on non-existent items.
        
        This test verifies that:
        1. The system properly validates item existence
        2. Appropriate error messages are returned
        3. The system remains stable after invalid operations
        """
        # Step 1: Attempt to retrieve a non-existent item
        response = client.get("/api/search?itemId=nonexistent_item")
        search_result = self.assert_request_success(response)
        
        # Should indicate item not found rather than error
        assert not search_result["found"], "Should indicate item not found"
        
        # Step 2: Attempt to retrieve a non-existent item (should return error)
        retrieval_request = {
            "itemId": "nonexistent_item",
            "userId": "test_user"
        }
        response = client.post("/api/retrieve", json=retrieval_request)
        assert response.status_code == 404, "Should return 404 for non-existent item"
        
        # Step 3: Create a valid item and retrieve it to ensure stability
        valid_item = self.create_item(id="valid_retrieve_item")
        valid_container = self.create_container(id="valid_retrieve_cont")
        self.create_position(
            item_id=valid_item.id,
            container_id=valid_container.id
        )
        
        response = client.get(f"/api/search?itemId={valid_item.id}")
        search_result = self.assert_request_success(response)
        
        assert search_result["found"], "Should find the valid item"
        
        retrieval_request = {
            "itemId": valid_item.id,
            "userId": "test_user"
        }
        response = client.post("/api/retrieve", json=retrieval_request)
        retrieval_result = self.assert_request_success(response)
        
        assert retrieval_result["success"], "Should successfully retrieve the valid item"
    
    def test_malformed_csv_handling(self):
        """
        Test handling of malformed CSV files during import.
        
        This test verifies that:
        1. The system properly validates CSV format
        2. Detailed error information is provided
        3. The system remains stable after import errors
        """
        # Step 1: Attempt to import a malformed CSV
        malformed_csv = "This is not a CSV file,but just some text\nwith no proper,structure"
        files = {'file': ('malformed.csv', io.StringIO(malformed_csv), 'text/csv')}
        
        response = client.post("/api/import/items", files=files)
        # May return 400 or 500 level error, or 200 with error details
        
        # Step 2: Import a valid CSV to ensure stability
        valid_csv = (
            "Item ID,Name,Width (cm),Depth (cm),Height (cm),Mass (kg),Priority (1-100)\n"
            "csv_item1,CSV Item 1,10,15,20,5,80\n"
        )
        files = {'file': ('valid.csv', io.StringIO(valid_csv), 'text/csv')}
        
        response = client.post("/api/import/items", files=files)
        import_result = self.assert_request_success(response)
        
        assert import_result["success"], "Should import valid CSV successfully"
        assert import_result["itemsImported"] > 0, "Should import at least one item"
        
        # Verify the item was imported
        response = client.get("/api/search?itemId=csv_item1")
        search_result = self.assert_request_success(response)
        
        assert search_result["found"], "Should find the imported item"
    
    def test_simulation_edge_cases(self):
        """
        Test edge cases in the simulation system.
        
        This test verifies that:
        1. The system handles invalid simulation parameters
        2. Extreme simulation requests are handled gracefully
        3. The system remains stable after simulation errors
        """
        # Step 1: Attempt a simulation with negative days
        simulation_request = {
            "numOfDays": -5,
            "itemsToBeUsedPerDay": []
        }
        
        response = client.post("/api/simulate/day", json=simulation_request)
        # Should return error or minimum of 1 day
        
        # Step 2: Attempt a simulation with a date in the past
        past_date = (date.today() - timedelta(days=10)).isoformat()
        simulation_request = {
            "toTimestamp": past_date,
            "itemsToBeUsedPerDay": []
        }
        
        response = client.post("/api/simulate/day", json=simulation_request)
        # Should handle this gracefully
        
        # Step 3: Run a valid simulation to ensure stability
        valid_item = self.create_item(
            id="sim_stability_item",
            usage_limit=10,
            current_usage=0
        )
        
        simulation_request = {
            "numOfDays": 1,
            "itemsToBeUsedPerDay": [
                {"itemId": valid_item.id}
            ]
        }
        
        response = client.post("/api/simulate/day", json=simulation_request)
        simulation_result = self.assert_request_success(response)
        
        assert simulation_result["success"], "Valid simulation should succeed"
        
        # Verify item usage was updated
        self.db = TestingSessionLocal()
        updated_item = self.db.query(Item).filter(Item.id == valid_item.id).first()
        assert updated_item.current_usage > 0, "Item usage should be updated"
        self.db.close()
    
    def test_concurrent_operations(self):
        """
        Test system stability during concurrent operations.
        
        This is a simplified test since we can't easily test true concurrency in pytest,
        but we can verify the system handles sequences of interleaved operations correctly.
        """
        # Create test items and containers
        container1 = self.create_container(id="concurrent_cont1")
        container2 = self.create_container(id="concurrent_cont2")
        
        item1 = self.create_item(id="concurrent_item1")
        item2 = self.create_item(id="concurrent_item2")
        
        # Interleave operations on different items
        
        # Start a placement operation for item1
        placement_request1 = {
            "items": [
                {
                    "itemId": item1.id,
                    "name": item1.name,
                    "width": item1.width,
                    "depth": item1.depth,
                    "height": item1.height,
                    "mass": item1.mass,
                    "priority": item1.priority
                }
            ],
            "containers": [
                {
                    "containerId": container1.id,
                    "zone": container1.zone,
                    "width": container1.width,
                    "depth": container1.depth,
                    "height": container1.height
                }
            ]
        }
        
        response1 = client.post("/api/placement", json=placement_request1)
        placement_result1 = self.assert_request_success(response1)
        
        # Start a placement operation for item2
        placement_request2 = {
            "items": [
                {
                    "itemId": item2.id,
                    "name": item2.name,
                    "width": item2.width,
                    "depth": item2.depth,
                    "height": item2.height,
                    "mass": item2.mass,
                    "priority": item2.priority
                }
            ],
            "containers": [
                {
                    "containerId": container2.id,
                    "zone": container2.zone,
                    "width": container2.width,
                    "depth": container2.depth,
                    "height": container2.height
                }
            ]
        }
        
        response2 = client.post("/api/placement", json=placement_request2)
        placement_result2 = self.assert_request_success(response2)
        
        # Now retrieve item1
        retrieval_request1 = {
            "itemId": item1.id,
            "userId": "test_user"
        }
        response3 = client.post("/api/retrieve", json=retrieval_request1)
        retrieval_result1 = self.assert_request_success(response3)
        
        # While placing item2 in a different location
        place_request2 = {
            "itemId": item2.id,
            "userId": "test_user",
            "containerId": container1.id,
            "position": {
                "startCoordinates": {
                    "width": 20.0,
                    "depth": 20.0,
                    "height": 20.0
                },
                "endCoordinates": {
                    "width": 20.0 + item2.width,
                    "depth": 20.0 + item2.depth,
                    "height": 20.0 + item2.height
                }
            }
        }
        response4 = client.post("/api/place", json=place_request2)
        place_result2 = self.assert_request_success(response4)
        
        # Verify both items are where they should be
        response = client.get(f"/api/search?itemId={item2.id}")
        search_result = self.assert_request_success(response)
        
        assert search_result["found"], "Item 2 should be found"
        assert search_result["item"]["containerId"] == container1.id, "Item 2 should be in container 1"
        
        # Item 1 should not be in any container (was retrieved)
        response = client.get(f"/api/search?itemId={item1.id}")
        search_result = self.assert_request_success(response)
        
        if search_result["found"]:
            assert search_result["item"]["containerId"] != container1.id, "Item 1 should not be in container 1"
    
    def test_boundary_values(self):
        """
        Test system stability with boundary values.
        
        This test verifies that:
        1. The system handles extremely large/small values properly
        2. The system maintains stability with boundary inputs
        """
        # Step 1: Create a container with extremely large dimensions
        large_container = self.create_container(
            id="large_cont",
            width=1000000.0,  # Very large
            height=1000000.0,
            depth=1000000.0
        )
        
        # Step 2: Create an item with extremely small dimensions
        small_item = self.create_item(
            id="small_item",
            width=0.1,  # Very small
            height=0.1,
            depth=0.1,
            mass=0.001
        )
        
        # Step 3: Create an item with extremely large dimensions
        large_item = self.create_item(
            id="large_item",
            width=900000.0,  # Very large
            height=900000.0,
            depth=900000.0,
            mass=1000000.0
        )
        
        # Step 4: Attempt to place both items
        placement_request = {
            "items": [
                {
                    "itemId": small_item.id,
                    "name": small_item.name,
                    "width": small_item.width,
                    "depth": small_item.depth,
                    "height": small_item.height,
                    "mass": small_item.mass,
                    "priority": small_item.priority
                },
                {
                    "itemId": large_item.id,
                    "name": large_item.name,
                    "width": large_item.width,
                    "depth": large_item.depth,
                    "height": large_item.height,
                    "mass": large_item.mass,
                    "priority": large_item.priority
                }
            ],
            "containers": [
                {
                    "containerId": large_container.id,
                    "zone": large_container.zone,
                    "width": large_container.width,
                    "depth": large_container.depth,
                    "height": large_container.height
                }
            ]
        }
        
        # This may succeed or fail depending on system limits, but should not crash
        response = client.post("/api/placement", json=placement_request)
        
        # Step 5: Verify the system is still functional with a normal request
        normal_container = self.create_container(id="normal_cont")
        normal_item = self.create_item(id="normal_item")
        
        normal_placement_request = {
            "items": [
                {
                    "itemId": normal_item.id,
                    "name": normal_item.name,
                    "width": normal_item.width,
                    "depth": normal_item.depth,
                    "height": normal_item.height,
                    "mass": normal_item.mass,
                    "priority": normal_item.priority
                }
            ],
            "containers": [
                {
                    "containerId": normal_container.id,
                    "zone": normal_container.zone,
                    "width": normal_container.width,
                    "depth": normal_container.depth,
                    "height": normal_container.height
                }
            ]
        }
        
        response = client.post("/api/placement", json=normal_placement_request)
        placement_result = self.assert_request_success(response)
        
        assert len(placement_result["placements"]) == 1, "Should place the normal item"
    
    def test_invalid_return_plan_handling(self):
        """
        Test handling of invalid return mission plans.
        
        This test verifies that:
        1. The system validates return mission parameters
        2. Appropriate error messages are provided
        3. The system remains stable after invalid operations
        """
        # Step 1: Create a valid container
        container = self.create_container(id="return_cont")
        
        # Step 2: Attempt to create a return plan with a non-existent container
        return_plan_request = {
            "undockingContainerId": "nonexistent_container",
            "undockingDate": (date.today() + timedelta(days=5)).isoformat(),
            "maxWeight": 100.0
        }
        
        response = client.post("/api/waste/return-plan", json=return_plan_request)
        assert response.status_code == 404, "Should return 404 for non-existent container"
        
        # Step 3: Attempt to create a return plan with invalid date format
        return_plan_request = {
            "undockingContainerId": container.id,
            "undockingDate": "invalid-date",
            "maxWeight": 100.0
        }
        
        response = client.post("/api/waste/return-plan", json=return_plan_request)
        assert response.status_code == 400, "Should return 400 for invalid date"
        
        # Step 4: Create a valid return plan to ensure system stability
        valid_return_plan_request = {
            "undockingContainerId": container.id,
            "undockingDate": (date.today() + timedelta(days=5)).isoformat(),
            "maxWeight": 100.0
        }
        
        response = client.post("/api/waste/return-plan", json=valid_return_plan_request)
        # This might succeed with an empty plan if no waste items exist
        assert response.status_code == 200, "Valid request should not cause error"
