from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta
from typing import List, Optional

from src.db.session import get_db
from src.db import crud
from src.api import schemas
from src.models.item import ItemStatus
from src.models.return_mission import WasteReason

router = APIRouter()

@router.post("/simulate/day", response_model=schemas.SimulationResponse)
async def simulate_day(
    request: schemas.SimulationRequest,
    db: Session = Depends(get_db)
):
    """
    Simulate the passage of time.
    
    This endpoint simulates the passage of a specified number of days, updating
    expiry dates and usage counts for items.
    """
    try:
        # Determine simulation parameters
        num_days = request.numOfDays or 1
        target_date = None
        
        if request.toTimestamp:
            try:
                target_date = datetime.fromisoformat(request.toTimestamp).date()
                # Calculate days based on target date
                current_date = date.today()
                num_days = (target_date - current_date).days
                if num_days < 1:
                    num_days = 1  # Ensure at least one day is simulated
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid timestamp format")
        else:
            target_date = date.today() + timedelta(days=num_days)
        
        # Process items to be used each day
        items_used = []
        items_expired = []
        items_depleted = []
        
        # Find items to be used
        for item_request in request.itemsToBeUsedPerDay:
            item = None
            if item_request.itemId:
                item = crud.get_item(db, item_request.itemId)
            elif item_request.name:
                item = crud.get_item_by_name(db, item_request.name)
            
            if item and item.status == ItemStatus.ACTIVE:
                # Increment usage for each day of simulation
                for day in range(num_days):
                    depleted = item.increment_usage()
                    if depleted:
                        # If item became depleted, mark it as waste
                        crud.mark_item_as_waste(db, item.id, WasteReason.DEPLETED)
                        items_depleted.append(item)
                        break
                
                # Add to used items list
                items_used.append({
                    "itemId": item.id,
                    "name": item.name,
                    "remainingUses": item.usage_limit - item.current_usage if item.usage_limit else None
                })
        
        # Check for items that expire during the simulation period
        simulation_date = date.today() + timedelta(days=num_days)
        all_items = crud.get_active_items(db)
        
        for item in all_items:
            if item.expiry_date and item.expiry_date <= simulation_date and item.status == ItemStatus.ACTIVE:
                # Mark as expired waste
                crud.mark_item_as_waste(db, item.id, WasteReason.EXPIRED)
                items_expired.append({
                    "itemId": item.id,
                    "name": item.name
                })
        
        # Commit all changes
        db.commit()
        
        # Log the simulation
        crud.create_log_entry(
            db,
            operation=crud.ActionType.SIMULATION,
            details={
                "days_simulated": num_days,
                "final_date": simulation_date.isoformat(),
                "items_used_count": len(items_used),
                "items_expired_count": len(items_expired),
                "items_depleted_count": len(items_depleted)
            }
        )
        
        # Format response
        response = schemas.SimulationResponse(
            success=True,
            newDate=simulation_date.isoformat(),
            changes=schemas.SimulationChanges(
                itemsUsed=[
                    schemas.SimulationItemResponse(
                        itemId=item["itemId"],
                        name=item["name"],
                        remainingUses=item["remainingUses"]
                    ) for item in items_used
                ],
                itemsExpired=[
                    schemas.SimulationItemResponse(
                        itemId=item["itemId"],
                        name=item["name"]
                    ) for item in items_expired
                ],
                itemsDepletedToday=[
                    schemas.SimulationItemResponse(
                        itemId=item.id,
                        name=item.name
                    ) for item in items_depleted
                ]
            )
        )
        
        return response
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Simulation failed: {str(e)}")
