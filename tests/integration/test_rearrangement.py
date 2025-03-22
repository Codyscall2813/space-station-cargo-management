"""
Integration tests for container rearrangement and space optimization.

This test suite verifies the complex workflows involving rearrangement operations:
1. Placing items when space is constrained
2. Rearranging existing items to optimize space utilization
3. Moving items based on priority
4. Verifying placements after rearrangement
"""

import pytest
from datetime import date, timedelta
from tests.integration.framework import IntegrationTestFixture, client

class TestRearrangementIntegration(IntegrationTestFixture):
    """Test the rearrangement algorithms and space optimization integration."""
    
    def test_rearrangement_when_space_constrained(self):
        """
        Test the system's ability to rearrange items when space is constrained.
        
        This test verifies that:
        1. The system can place multiple items in a container
        2. When a high-priority item doesn't fit, the system correctly recommends rearrangement
        3. The rearrangement steps are valid and executable
        4. After rearrangement, the high-priority item can be placed
        """
        # Step 1: Create a container with limited space
        small_container = self.create_container(
            id="small_cont",
            name="Small Container",
            width=50.0,
            height=50.0,
            depth=50.0,
            zone="TestZone"
        )
        
        # Step 2: Create a low-priority item that will take up significant space
        low_priority_item = self.create_item(
            id="low_pri_item",
            name="Low Priority Item",
            width=30.0,
            height=30.0,
            depth=30.0,
            mass=10.0,
            priority=30,  # Low priority
            preferred_zone="TestZone"
        )
        
        # Step 3: Create a medium-priority item
        medium_priority_item = self.create_item(
            id="med_pri_item",
            name="Medium Priority Item",
            width=20.0,
            height=20.0, 
            depth=20.0,
            mass=5.0,
            priority=60,  # Medium priority
            preferred_zone="TestZone"
        )
        
        # Step 4: Create a high-priority item that will need space
        high_priority_item = self.create_item(
            id="high_pri_item",
            name="High Priority Item",
            width=40.0,
            height=40.0,
            depth=40.0,
            mass=20.0,
            priority=90,  # High priority
            preferred_zone="TestZone"
        )
        
        # Step 5: Place the low and medium priority items
        placement_request = {
            "items": [
                {
                    "itemId": low_priority_item.id,
                    "name": low_priority_item.name,
                    "width": low_priority_item.width,
                    "depth": low_priority_item.depth,
                    "height": low_priority_item.height,
                    "mass": low_priority_item.mass,
                    "priority": low_priority_item.priority,
                    "preferredZone": low_priority_item.preferred_zone
                },
                {
                    "itemId": medium_priority_item.id,
                    "name": medium_priority_item.name,
                    "width": medium_priority_item.width,
                    "depth": medium_priority_item.depth,
                    "height": medium_priority_item.height,
                    "mass": medium_priority_item.mass,
                    "priority": medium_priority_item.priority,
                    "preferredZone": medium_priority_item.preferred_zone
                }
            ],
            "containers": [
                {
                    "containerId": small_container.id,
                    "zone": small_container.zone,
                    "width": small_container.width,
                    "depth": small_container.depth,
                    "height": small_container.height
                }
            ]
        }
        
        response = client.post("/api/placement", json=placement_request)
        placement_result = self.assert_request_success(response)
        
        # Verify initial placement succeeded
        assert len(placement_result["placements"]) == 2, "Should place both initial items"
        
        # Step 6: Try to place the high priority item (should trigger rearrangement)
        placement_request = {
            "items": [
                {
                    "itemId": high_priority_item.id,
                    "name": high_priority_item.name,
                    "width": high_priority_item.width,
                    "depth": high_priority_item.depth,
                    "height": high_priority_item.height,
                    "mass": high_priority_item.mass,
                    "priority": high_priority_item.priority,
                    "preferredZone": high_priority_item.preferred_zone
                }
            ],
            "containers": [
                {
                    "containerId": small_container.id,
                    "zone": small_container.zone,
                    "width": small_container.width,
                    "depth": small_container.depth,
                    "height": small_container.height
                }
            ]
        }
        
        response = client.post("/api/placement", json=placement_request)
        rearrangement_result = self.assert_request_success(response)
        
        # Verify rearrangement was triggered
        assert len(rearrangement_result["rearrangements"]) > 0, "Should trigger rearrangement"
        assert len(rearrangement_result["placements"]) > 0, "Should place the high priority item"
        
        # Step 7: Verify the result through retrieval
        response = client.get(f"/api/search?itemId={high_priority_item.id}")
        search_result = self.assert_request_success(response)
        
        # High priority item should be found in the container
        assert search_result["found"], "High priority item should be placed"
        assert search_result["item"]["containerId"] == small_container.id, "Item should be in the container"
        
        # Verify low priority item was moved or removed to make space
        response = client.get(f"/api/search?itemId={low_priority_item.id}")
        low_pri_search = self.assert_request_success(response)
        
        # The container should not have both the high priority item and the low priority item
        # since they wouldn't fit together
        if low_pri_search["found"] and low_pri_search["item"]["containerId"] == small_container.id:
            # If the low priority item is still there, verify medium priority was moved
            response = client.get(f"/api/search?itemId={medium_priority_item.id}")
            med_pri_search = self.assert_request_success(response)
            
            assert not med_pri_search["found"] or med_pri_search["item"]["containerId"] != small_container.id, \
                "At least one of the lower priority items should have been moved"
    
    def test_priority_based_placement_with_multiple_containers(self):
        """
        Test placement optimization across multiple containers with priority considerations.
        
        This test verifies that:
        1. High priority items are placed in their preferred zones
        2. When space is constrained, lower priority items are moved to non-preferred zones
        3. The system optimizes placement across multiple containers
        """
        # Step 1: Create two containers in different zones
        zone_a_container = self.create_container(
            id="zone_a_cont",
            name="Zone A Container",
            width=60.0,
            height=60.0,
            depth=60.0,
            zone="ZoneA"
        )
        
        zone_b_container = self.create_container(
            id="zone_b_cont",
            name="Zone B Container",
            width=100.0,
            height=100.0,
            depth=100.0,
            zone="ZoneB"
        )
        
        # Step 2: Create items with different priorities and preferred zones
        # High priority item that prefers Zone A
        high_pri_a = self.create_item(
            id="high_pri_a",
            name="High Priority Zone A Item",
            width=40.0,
            height=40.0,
            depth=40.0,
            mass=15.0,
            priority=90,
            preferred_zone="ZoneA"
        )
        
        # High priority item that prefers Zone B
        high_pri_b = self.create_item(
            id="high_pri_b",
            name="High Priority Zone B Item",
            width=35.0,
            height=35.0,
            depth=35.0,
            mass=12.0,
            priority=85,
            preferred_zone="ZoneB"
        )
        
        # Medium priority items that prefer Zone A
        med_pri_a1 = self.create_item(
            id="med_pri_a1",
            name="Medium Priority Zone A Item 1",
            width=30.0,
            height=30.0,
            depth=30.0,
            mass=10.0,
            priority=60,
            preferred_zone="ZoneA"
        )
        
        med_pri_a2 = self.create_item(
            id="med_pri_a2",
            name="Medium Priority Zone A Item 2",
            width=25.0,
            height=25.0,
            depth=25.0,
            mass=8.0,
            priority=55,
            preferred_zone="ZoneA"
        )
        
        # Low priority item that prefers Zone A
        low_pri_a = self.create_item(
            id="low_pri_a",
            name="Low Priority Zone A Item",
            width=20.0,
            height=20.0,
            depth=20.0,
            mass=5.0,
            priority=30,
            preferred_zone="ZoneA"
        )
        
        # Step 3: Request placement for all items at once
        placement_request = {
            "items": [
                {
                    "itemId": high_pri_a.id,
                    "name": high_pri_a.name,
                    "width": high_pri_a.width,
                    "depth": high_pri_a.depth,
                    "height": high_pri_a.height,
                    "mass": high_pri_a.mass,
                    "priority": high_pri_a.priority,
                    "preferredZone": high_pri_a.preferred_zone
                },
                {
                    "itemId": high_pri_b.id,
                    "name": high_pri_b.name,
                    "width": high_pri_b.width,
                    "depth": high_pri_b.depth,
                    "height": high_pri_b.height,
                    "mass": high_pri_b.mass,
                    "priority": high_pri_b.priority,
                    "preferredZone": high_pri_b.preferred_zone
                },
                {
                    "itemId": med_pri_a1.id,
                    "name": med_pri_a1.name,
                    "width": med_pri_a1.width,
                    "depth": med_pri_a1.depth,
                    "height": med_pri_a1.height,
                    "mass": med_pri_a1.mass,
                    "priority": med_pri_a1.priority,
                    "preferredZone": med_pri_a1.preferred_zone
                },
                {
                    "itemId": med_pri_a2.id,
                    "name": med_pri_a2.name,
                    "width": med_pri_a2.width,
                    "depth": med_pri_a2.depth,
                    "height": med_pri_a2.height,
                    "mass": med_pri_a2.mass,
                    "priority": med_pri_a2.priority,
                    "preferredZone": med_pri_a2.preferred_zone
                },
                {
                    "itemId": low_pri_a.id,
                    "name": low_pri_a.name,
                    "width": low_pri_a.width,
                    "depth": low_pri_a.depth,
                    "height": low_pri_a.height,
                    "mass": low_pri_a.mass,
                    "priority": low_pri_a.priority,
                    "preferredZone": low_pri_a.preferred_zone
                }
            ],
            "containers": [
                {
                    "containerId": zone_a_container.id,
                    "zone": zone_a_container.zone,
                    "width": zone_a_container.width,
                    "depth": zone_a_container.depth,
                    "height": zone_a_container.height
                },
                {
                    "containerId": zone_b_container.id,
                    "zone": zone_b_container.zone,
                    "width": zone_b_container.width,
                    "depth": zone_b_container.depth,
                    "height": zone_b_container.height
                }
            ]
        }
        
        response = client.post("/api/placement", json=placement_request)
        placement_result = self.assert_request_success(response)
        
        # Verify all items were placed
        assert len(placement_result["placements"]) == 5, "All items should be placed"
        
        # Step 4: Verify placement priorities
        # Check where each item was placed
        item_placements = {}
        for placement in placement_result["placements"]:
            item_placements[placement["itemId"]] = placement["containerId"]
        
        # Verify high priority items are in their preferred zones
        assert item_placements[high_pri_a.id] == zone_a_container.id, "High priority Zone A item should be in Zone A"
        assert item_placements[high_pri_b.id] == zone_b_container.id, "High priority Zone B item should be in Zone B"
        
        # The Zone A container is too small for all Zone A items, so lower priority ones
        # should have been placed in Zone B
        zone_a_items = [id for id, container in item_placements.items() if container == zone_a_container.id]
        zone_b_items = [id for id, container in item_placements.items() if container == zone_b_container.id]
        
        # Zone A should have high priority items
        assert high_pri_a.id in zone_a_items, "High priority Zone A item should be in Zone A"
        
        # At least one of the lower priority Zone A items should be in Zone B
        assert any(item_id in zone_b_items for item_id in [med_pri_a1.id, med_pri_a2.id, low_pri_a.id]), \
            "At least one lower priority Zone A item should be in Zone B"
        
        # Confirm the placements through search
        for item_id, container_id in item_placements.items():
            response = client.get(f"/api/search?itemId={item_id}")
            search_result = self.assert_request_success(response)
            
            assert search_result["found"], f"Item {item_id} should be found"
            assert search_result["item"]["containerId"] == container_id, \
                f"Item {item_id} should be in container {container_id}"
    
    def test_step_by_step_rearrangement_execution(self):
        """
        Test executing the rearrangement plan steps one by one.
        
        This test verifies that:
        1. The system generates valid rearrangement steps
        2. Each step can be executed properly
        3. After execution, the container state is as expected
        4. Retrieval works correctly after rearrangement
        """
        # Step 1: Create a container with limited space
        container = self.create_container(
            id="rearrange_cont",
            width=50.0,
            height=50.0,
            depth=50.0
        )
        
        # Step 2: Create low and medium priority items
        low_item = self.create_item(
            id="low_item",
            name="Low Priority Item",
            width=30.0,
            height=20.0,
            depth=20.0,
            priority=30
        )
        
        med_item = self.create_item(
            id="med_item",
            name="Medium Priority Item",
            width=25.0,
            height=25.0,
            depth=25.0,
            priority=60
        )
        
        # Place these items in the container
        self.create_position(
            item_id=low_item.id,
            container_id=container.id,
            x=0.0,
            y=0.0,
            z=0.0
        )
        
        self.create_position(
            item_id=med_item.id,
            container_id=container.id,
            x=30.0,
            y=0.0,
            z=0.0
        )
        
        # Step 3: Create a large high priority item
        high_item = self.create_item(
            id="high_item",
            name="High Priority Item",
            width=40.0,
            height=40.0,
            depth=40.0,
            priority=90
        )
        
        # Step 4: Try to place the high priority item (should trigger rearrangement)
        placement_request = {
            "items": [
                {
                    "itemId": high_item.id,
                    "name": high_item.name,
                    "width": high_item.width,
                    "depth": high_item.depth,
                    "height": high_item.height,
                    "mass": high_item.mass,
                    "priority": high_item.priority
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
        
        response = client.post("/api/placement", json=placement_request)
        rearrangement_result = self.assert_request_success(response)
        
        # Verify rearrangement was triggered
        assert len(rearrangement_result["rearrangements"]) > 0, "Should trigger rearrangement"
        
        # Step 5: Execute the rearrangement steps one by one
        # This would typically be done through the UI or by an automated system
        for step in rearrangement_result["rearrangements"]:
            if step["action"] == "move":
                # Simulate moving an item by removing it from source and placing at destination
                # First "retrieve" it from the original position
                retrieve_request = {
                    "itemId": step["itemId"],
                    "userId": "test_user"
                }
                response = client.post("/api/retrieve", json=retrieve_request)
                self.assert_request_success(response)
                
                # Then "place" it at the new position
                place_request = {
                    "itemId": step["itemId"],
                    "userId": "test_user",
                    "containerId": step["toContainer"],
                    "position": step["toPosition"]
                }
                response = client.post("/api/place", json=place_request)
                self.assert_request_success(response)
        
        # Step 6: Execute the placement
        for placement in rearrangement_result["placements"]:
            place_request = {
                "itemId": placement["itemId"],
                "userId": "test_user",
                "containerId": placement["containerId"],
                "position": placement["position"]
            }
            response = client.post("/api/place", json=place_request)
            self.assert_request_success(response)
        
        # Step 7: Verify the final arrangement
        # The high priority item should be in the container
        response = client.get(f"/api/search?itemId={high_item.id}")
        search_result = self.assert_request_success(response)
        
        assert search_result["found"], "High priority item should be placed"
        assert search_result["item"]["containerId"] == container.id, "High priority item should be in the container"
        
        # At least one of the lower priority items should have been moved or removed
        at_least_one_moved = False
        
        for item_id in [low_item.id, med_item.id]:
            response = client.get(f"/api/search?itemId={item_id}")
            search_result = self.assert_request_success(response)
            
            if not search_result["found"] or search_result["item"]["containerId"] != container.id:
                at_least_one_moved = True
                break
        
        assert at_least_one_moved, "At least one lower priority item should have been moved"
