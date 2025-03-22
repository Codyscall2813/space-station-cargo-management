from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, List

from src.db.session import get_db
from src.db import crud
from src.api import schemas

router = APIRouter()

@router.get("/logs", response_model=schemas.LogResponse)
async def get_logs(
    startDate: str = Query(..., description="Start date in ISO format"),
    endDate: str = Query(..., description="End date in ISO format"),
    itemId: Optional[str] = Query(None, description="Filter logs by item ID"),
    userId: Optional[str] = Query(None, description="Filter logs by user ID"),
    actionType: Optional[str] = Query(None, description="Filter logs by action type"),
    db: Session = Depends(get_db)
):
    """
    Get system logs with filtering.
    
    This endpoint retrieves logs based on various filters including date range,
    item ID, user ID, and action type.
    """
    try:
        # Parse dates
        start_date = None
        end_date = None
        try:
            start_date = datetime.fromisoformat(startDate)
            end_date = datetime.fromisoformat(endDate)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use ISO format: YYYY-MM-DDTHH:MM:SS")
        
        # Parse action type if provided
        operation = None
        if actionType:
            try:
                operation = crud.ActionType[actionType.upper()]
            except KeyError:
                valid_types = [t.name.lower() for t in crud.ActionType]
                raise HTTPException(
                    status_code=400, 
                    detail=f"Invalid action type. Valid types are: {', '.join(valid_types)}"
                )
        
        # Get logs with filters
        logs = crud.get_logs(
            db,
            start_date=start_date,
            end_date=end_date,
            user_id=userId,
            operation=operation
        )
        
        # Filter by item ID if provided
        if itemId:
            logs = [log for log in logs if log.item_ids and itemId in log.item_ids]
        
        # Format logs for response
        log_entries = []
        for log in logs:
            log_dict = log.to_dict()
            log_entries.append(schemas.LogEntry(
                timestamp=log_dict["timestamp"],
                userId=log_dict["userId"],
                actionType=log_dict["operation"],
                itemId=log_dict["itemIds"][0] if log_dict["itemIds"] else None,
                details=log_dict["details"]
            ))
        
        return schemas.LogResponse(logs=log_entries)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Log retrieval failed: {str(e)}")
