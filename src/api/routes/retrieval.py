from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from src.db.session import get_db
from src.db import crud
from src.api import schemas
from src.algorithms import retrieval

router = APIRouter()

@router.get("/search", response_model=schemas.SearchResponse)
async def search_item(
    itemId: Optional[str] = Query(None),
    itemName: Optional[str] = Query(None),
    userId: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Search for items based on ID or name.
    
    This endpoint allows searching for items by their ID or name and returns
    the current position and retrieval steps if found.
    """
    try:
        # Either itemId or itemName must be provided
        if not itemId and not itemName:
            raise HTTPException(status_code=400, detail="Either itemId or itemName must be provided")
        
        # Find the item
        item = None
        if itemId:
            item = crud.get_item(db, itemId)
        elif itemName:
            item = crud.get_item_by_name(db, itemName)
        
        if not item:
            return schemas.SearchResponse(
                success=True,
                found=False
            )
        
        # Get the current position of the item
        position = crud.get_item_position(db, item.id)
        
        if not position:
            return schemas.SearchResponse(
                success=True,
                found=True,
                item={
                    "itemId": item.id,
                    "name": item.name,
                    "containerId": None,
                    "zone": None,
                    "position": None
                },
                retrievalSteps=[]
            )
        
        # Get container details
        container = crud.get_container(db, position.container_id)
        
        # Generate retrieval steps using the algorithm
        steps = retrieval.generate_retrieval_steps(db, item.id, position.container_id)
        
        # Format response
        item_response = {
            "itemId": item.id,
            "name": item.name,
            "containerId": position.container_id,
            "zone": container.zone if container else None,
            "position": position.to_dict()["position"]
        }
        
        retrieval_steps = [
            schemas.RetrievalStep(
                step=i + 1,
                action=step["action"],
                itemId=step["item_id"],
                itemName=step["item_name"]
            ) for i, step in enumerate(steps)
        ]
        
        # Log the search operation
        crud.create_log_entry(
            db,
            operation=crud.ActionType.RETRIEVAL,
            user_id=userId,
            details={"action": "search", "found": True},
            item_ids=[item.id]
        )
        
        return schemas.SearchResponse(
            success=True,
            found=True,
            item=item_response,
            retrievalSteps=retrieval_steps
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search operation failed: {str(e)}")

@router.post("/retrieve", response_model=schemas.RetrievalResponse)
async def retrieve_item(request: schemas.RetrievalRequest, db: Session = Depends(get_db)):
    """
    Execute a retrieval operation.
    
    This endpoint records that an item has been retrieved, incrementing its usage
    count and updating its status if it becomes depleted.
    """
    try:
        # Find the item
        item = crud.get_item(db, request.itemId)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        
        # Get current position
        position = crud.get_item_position(db, item.id)
        
        # Parse timestamp if provided, otherwise use current time
        timestamp = None
        if request.timestamp:
            try:
                timestamp = datetime.fromisoformat(request.timestamp)
            except ValueError:
                timestamp = datetime.now()
        else:
            timestamp = datetime.now()
        
        # Increment usage count
        depleted = item.increment_usage()
        
        # Update item and log retrieval
        db.commit()
        
        # If item became depleted, mark it as waste
        if depleted:
            crud.mark_item_as_waste(db, item.id, crud.WasteReason.DEPLETED)
            
        # Log the retrieval operation
        crud.create_log_entry(
            db,
            operation=crud.ActionType.RETRIEVAL,
            user_id=request.userId,
            details={
                "action": "retrieve",
                "timestamp": timestamp.isoformat(),
                "usage_count": item.current_usage,
                "depleted": depleted
            },
            item_ids=[item.id],
            container_ids=[position.container_id] if position else None
        )
        
        return schemas.RetrievalResponse(success=True)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Retrieval operation failed: {str(e)}")

@router.post("/place", response_model=schemas.PlaceResponse)
async def place_item(request: schemas.PlaceRequest, db: Session = Depends(get_db)):
    """
    Place an item in a specific container.
    
    This endpoint records that an item has been placed in a container at a specific
    position.
    """
    try:
        # Find the item
        item = crud.get_item(db, request.itemId)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        
        # Find the container
        container = crud.get_container(db, request.containerId)
        if not container:
            raise HTTPException(status_code=404, detail="Container not found")
        
        # Parse timestamp if provided, otherwise use current time
        timestamp = None
        if request.timestamp:
            try:
                timestamp = datetime.fromisoformat(request.timestamp)
            except ValueError:
                timestamp = datetime.now()
        else:
            timestamp = datetime.now()
        
        # Check if the item already has a position
        old_position = crud.get_item_position(db, item.id)
        
        # Prepare the position data
        position_data = {
            "itemId": item.id,
            "containerId": container.id,
            "position": {
                "startCoordinates": {
                    "width": request.position.startCoordinates.width,
                    "height": request.position.startCoordinates.height,
                    "depth": request.position.startCoordinates.depth
                }
            },
            "orientation": 0,  # Default orientation
            "visible": retrieval.is_visible(
                request.position.startCoordinates.width,
                request.position.startCoordinates.height,
                request.position.startCoordinates.depth,
                container
            )
        }
        
        # Create the new position
        new_position = crud.create_position(db, position_data)
        
        # Log the placement operation
        crud.create_log_entry(
            db,
            operation=crud.ActionType.PLACEMENT,
            user_id=request.userId,
            details={
                "action": "place",
                "timestamp": timestamp.isoformat(),
                "old_position": old_position.to_dict() if old_position else None,
                "new_position": new_position.to_dict()
            },
            item_ids=[item.id],
            container_ids=[container.id]
        )
        
        return schemas.PlaceResponse(success=True)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Placement operation failed: {str(e)}")
