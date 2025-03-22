from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import List

from src.db.session import get_db
from src.db import crud
from src.api import schemas
from src.algorithms import placement

router = APIRouter()

@router.post("/placement", response_model=schemas.PlacementResponse)
async def recommend_placement(
    request: schemas.PlacementRequest,
    db: Session = Depends(get_db)
):
    """
    Get optimal placement recommendations for multiple items.
    
    This endpoint analyzes available containers and computes the best placement
    locations for the specified items, considering priority, accessibility, and 
    space utilization.
    """
    try:
        # Ensure we have items and containers
        if not request.items or not request.containers:
            raise HTTPException(status_code=400, detail="Items and containers must be provided")
        
        # Store or update containers and items in the database
        containers = []
        for container_data in request.containers:
            # Check if container exists
            container = crud.get_container(db, container_data.containerId)
            if not container:
                container = crud.create_container(db, container_data.dict())
            containers.append(container)
        
        items = []
        for item_data in request.items:
            # Check if item exists
            item = crud.get_item(db, item_data.itemId)
            if not item:
                item = crud.create_item(db, item_data.dict())
            items.append(item)
        
        # Get the placement recommendations from the algorithm
        result = placement.optimize_placement(db, items, containers)
        
        # Convert the result to the API response format
        response = schemas.PlacementResponse(
            success=True,
            placements=[
                schemas.PlacementPositionResponse(
                    itemId=p["item_id"],
                    containerId=p["container_id"],
                    position=schemas.Position(
                        startCoordinates=schemas.Coordinates(
                            width=p["position"]["start_coordinates"]["width"],
                            depth=p["position"]["start_coordinates"]["depth"],
                            height=p["position"]["start_coordinates"]["height"]
                        ),
                        endCoordinates=schemas.Coordinates(
                            width=p["position"]["end_coordinates"]["width"],
                            depth=p["position"]["end_coordinates"]["depth"],
                            height=p["position"]["end_coordinates"]["height"]
                        )
                    )
                ) for p in result["placements"]
            ],
            rearrangements=[
                schemas.RearrangementStep(
                    step=i + 1,
                    action=r["action"],
                    itemId=r["item_id"],
                    fromContainer=r.get("from_container"),
                    fromPosition=schemas.Position(
                        startCoordinates=schemas.Coordinates(
                            width=r["from_position"]["start_coordinates"]["width"],
                            depth=r["from_position"]["start_coordinates"]["depth"],
                            height=r["from_position"]["start_coordinates"]["height"]
                        ),
                        endCoordinates=schemas.Coordinates(
                            width=r["from_position"]["end_coordinates"]["width"],
                            depth=r["from_position"]["end_coordinates"]["depth"],
                            height=r["from_position"]["end_coordinates"]["height"]
                        )
                    ) if r.get("from_position") else None,
                    toContainer=r.get("to_container"),
                    toPosition=schemas.Position(
                        startCoordinates=schemas.Coordinates(
                            width=r["to_position"]["start_coordinates"]["width"],
                            depth=r["to_position"]["start_coordinates"]["depth"],
                            height=r["to_position"]["start_coordinates"]["height"]
                        ),
                        endCoordinates=schemas.Coordinates(
                            width=r["to_position"]["end_coordinates"]["width"],
                            depth=r["to_position"]["end_coordinates"]["depth"],
                            height=r["to_position"]["end_coordinates"]["height"]
                        )
                    ) if r.get("to_position") else None
                ) for i, r in enumerate(result["rearrangements"])
            ]
        )
        
        # Log the placement operation
        crud.create_log_entry(
            db,
            operation=crud.ActionType.PLACEMENT,
            details={"placements": len(response.placements), "rearrangements": len(response.rearrangements)},
            item_ids=[item.id for item in items],
            container_ids=[container.id for container in containers]
        )
        
        return response
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Placement recommendation failed: {str(e)}")
