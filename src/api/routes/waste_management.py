from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from src.db.session import get_db
from src.db import crud
from src.api import schemas
from src.models.item import ItemStatus
from src.algorithms import retrieval, return_planning

router = APIRouter()

@router.get("/identify", response_model=schemas.WasteIdentifyResponse)
async def identify_waste(db: Session = Depends(get_db)):
    """
    Identify items that are considered waste.
    
    This endpoint returns all items that are marked as waste due to expiry
    or depletion.
    """
    try:
        # Get all items with waste status
        waste_items = []
        all_items = crud.get_items(db)
        
        for item in all_items:
            if item.status in [ItemStatus.WASTE, ItemStatus.DEPLETED]:
                # Get the current position
                position = crud.get_item_position(db, item.id)
                container_id = position.container_id if position else None
                
                # Determine reason
                reason = "Expired" if item.is_expired() else "Out of Uses"
                
                waste_items.append({
                    "itemId": item.id,
                    "name": item.name,
                    "reason": reason,
                    "containerId": container_id,
                    "position": position.to_dict()["position"] if position else None
                })
        
        # Log the waste identification
        crud.create_log_entry(
            db,
            operation=crud.ActionType.DISPOSAL,
            details={"action": "identify", "waste_count": len(waste_items)},
            item_ids=[item["itemId"] for item in waste_items]
        )
        
        return schemas.WasteIdentifyResponse(
            success=True,
            wasteItems=[
                schemas.WasteItemResponse(
                    itemId=item["itemId"],
                    name=item["name"],
                    reason=item["reason"],
                    containerId=item["containerId"],
                    position=schemas.Position(
                        startCoordinates=schemas.Coordinates(
                            width=item["position"]["startCoordinates"]["width"],
                            depth=item["position"]["startCoordinates"]["depth"],
                            height=item["position"]["startCoordinates"]["height"]
                        ),
                        endCoordinates=schemas.Coordinates(
                            width=item["position"]["endCoordinates"]["width"],
                            depth=item["position"]["endCoordinates"]["depth"],
                            height=item["position"]["endCoordinates"]["height"]
                        )
                    ) if item["position"] else None
                ) for item in waste_items
            ]
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Waste identification failed: {str(e)}")

@router.post("/return-plan", response_model=schemas.ReturnPlanResponse)
async def generate_return_plan(
    request: schemas.ReturnPlanRequest,
    db: Session = Depends(get_db)
):
    """
    Generate a plan for returning waste items.
    
    This endpoint creates a plan for moving waste items to the undocking container
    while respecting weight and volume constraints.
    """
    try:
        # Verify undocking container exists
        undocking_container = crud.get_container(db, request.undockingContainerId)
        if not undocking_container:
            raise HTTPException(status_code=404, detail="Undocking container not found")
        
        # Parse undocking date
        undocking_date = None
        try:
            undocking_date = datetime.fromisoformat(request.undockingDate).date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid undocking date format")
        
        # Create or get return mission
        mission = crud.create_return_mission(db, {
            "id": f"mission_{datetime.now().strftime('%Y%m%d')}_{undocking_container.id}",
            "scheduledDate": request.undockingDate,
            "maxWeight": request.maxWeight,
            "maxVolume": undocking_container.volume()
        })
        
        # Generate return plan using algorithm
        return_plan_result = return_planning.generate_return_plan(db, mission.id, undocking_container.id, request.maxWeight)
        
        # Format response
        response = schemas.ReturnPlanResponse(
            success=return_plan_result["success"],
            returnPlan=[
                schemas.ReturnPlanStep(
                    step=i + 1,
                    itemId=step["item_id"],
                    itemName=step["item_name"],
                    fromContainer=step["from_container"],
                    toContainer=step["to_container"]
                ) for i, step in enumerate(return_plan_result["return_plan"])
            ],
            retrievalSteps=[
                schemas.RetrievalStep(
                    step=i + 1,
                    action=step["action"],
                    itemId=step["item_id"],
                    itemName=step["item_name"]
                ) for i, step in enumerate(return_plan_result["retrieval_steps"])
            ],
            returnManifest=schemas.ReturnManifest(
                undockingContainerId=undocking_container.id,
                undockingDate=undocking_date.isoformat(),
                returnItems=[
                    schemas.ReturnManifestItem(
                        itemId=item["item_id"],
                        name=item["name"],
                        reason=item["reason"]
                    ) for item in return_plan_result["return_manifest"]["return_items"]
                ],
                totalVolume=return_plan_result["return_manifest"]["total_volume"],
                totalWeight=return_plan_result["return_manifest"]["total_weight"]
            )
        )
        
        # Log the return plan generation
        crud.create_log_entry(
            db,
            operation=crud.ActionType.DISPOSAL,
            details={
                "action": "return_plan",
                "mission_id": mission.id,
                "undocking_container": undocking_container.id,
                "undocking_date": undocking_date.isoformat(),
                "items_count": len(response.returnManifest.returnItems)
            },
            item_ids=[item.itemId for item in response.returnManifest.returnItems],
            container_ids=[undocking_container.id]
        )
        
        return response
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Return plan generation failed: {str(e)}")

@router.post("/complete-undocking", response_model=schemas.UndockingResponse)
async def complete_undocking(
    request: schemas.UndockingRequest,
    db: Session = Depends(get_db)
):
    """
    Complete the undocking process.
    
    This endpoint removes all waste items from the system that are in the
    undocking container.
    """
    try:
        # Verify container exists
        container = crud.get_container(db, request.undockingContainerId)
        if not container:
            raise HTTPException(status_code=404, detail="Undocking container not found")
        
        # Parse timestamp if provided, otherwise use current time
        timestamp = None
        if request.timestamp:
            try:
                timestamp = datetime.fromisoformat(request.timestamp)
            except ValueError:
                timestamp = datetime.now()
        else:
            timestamp = datetime.now()
        
        # Get all positions in this container
        positions = crud.get_container_positions(db, container.id)
        
        # Get the item IDs and clear their positions
        item_ids = []
        for position in positions:
            item_ids.append(position.item_id)
            crud.delete_position(db, position.id)
        
        # Update return mission status if found
        missions = crud.get_active_return_missions(db)
        for mission in missions:
            if any(item_id in [waste_item.item_id for waste_item in mission.waste_items] for item_id in item_ids):
                mission.status = crud.MissionStatus.COMPLETE
        
        # Commit changes
        db.commit()
        
        # Log the undocking completion
        crud.create_log_entry(
            db,
            operation=crud.ActionType.DISPOSAL,
            details={
                "action": "complete_undocking",
                "container_id": container.id,
                "timestamp": timestamp.isoformat(),
                "items_removed": len(item_ids)
            },
            item_ids=item_ids,
            container_ids=[container.id]
        )
        
        return schemas.UndockingResponse(
            success=True,
            itemsRemoved=len(item_ids)
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Undocking completion failed: {str(e)}")
