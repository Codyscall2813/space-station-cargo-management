from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import csv
import io
from datetime import datetime
from typing import List, Dict, Any, Optional

from src.db.session import get_db
from src.db import crud
from src.api import schemas

router = APIRouter()

@router.post("/import/items", response_model=schemas.ImportResponse)
async def import_items(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Import items from a CSV file.
    
    This endpoint allows bulk import of items using a CSV file.
    """
    try:
        # Check file type
        if not file.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail="File must be a CSV")
        
        # Read and parse CSV file
        content = await file.read()
        csv_text = content.decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(csv_text))
        
        imported_count = 0
        errors = []
        item_ids = []
        
        for row_idx, row in enumerate(csv_reader, start=2):  # Start from 2 to account for header row
            try:
                # Required fields validation
                required_fields = ['Item ID', 'Name', 'Width (cm)', 'Depth (cm)', 'Height (cm)', 'Mass (kg)', 'Priority (1-100)']
                for field in required_fields:
                    if field not in row or not row[field]:
                        raise ValueError(f"Missing required field: {field}")
                
                # Parse expiry date if provided
                expiry_date = None
                if 'Expiry Date' in row and row['Expiry Date'] and row['Expiry Date'].lower() != 'n/a':
                    try:
                        expiry_date = datetime.fromisoformat(row['Expiry Date']).date().isoformat()
                    except ValueError:
                        raise ValueError(f"Invalid expiry date format: {row['Expiry Date']}")
                
                # Create item data
                item_data = {
                    "itemId": row['Item ID'],
                    "name": row['Name'],
                    "width": float(row['Width (cm)']),
                    "depth": float(row['Depth (cm)']),
                    "height": float(row['Height (cm)']),
                    "mass": float(row['Mass (kg)']),
                    "priority": int(row['Priority (1-100)']),
                    "expiryDate": expiry_date,
                    "usageLimit": int(row['Usage Limit']) if 'Usage Limit' in row and row['Usage Limit'] and row['Usage Limit'].lower() != 'n/a' else None,
                    "preferredZone": row['Preferred Zone'] if 'Preferred Zone' in row else None
                }
                
                # Check if item already exists
                existing_item = crud.get_item(db, item_data["itemId"])
                if existing_item:
                    # Update existing item
                    crud.update_item(db, existing_item.id, item_data)
                else:
                    # Create new item
                    item = crud.create_item(db, item_data)
                    item_ids.append(item.id)
                
                imported_count += 1
                
            except Exception as e:
                errors.append({
                    "row": row_idx,
                    "message": str(e)
                })
        
        # Log the import operation
        crud.create_log_entry(
            db,
            operation=crud.ActionType.IMPORT,
            details={
                "file_name": file.filename,
                "items_imported": imported_count,
                "errors": len(errors)
            },
            item_ids=item_ids
        )
        
        return schemas.ImportResponse(
            success=True,
            itemsImported=imported_count,
            errors=errors if errors else None
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Item import failed: {str(e)}")

@router.post("/import/containers", response_model=schemas.ImportResponse)
async def import_containers(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Import containers from a CSV file.
    
    This endpoint allows bulk import of containers using a CSV file.
    """
    try:
        # Check file type
        if not file.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail="File must be a CSV")
        
        # Read and parse CSV file
        content = await file.read()
        csv_text = content.decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(csv_text))
        
        imported_count = 0
        errors = []
        container_ids = []
        
        for row_idx, row in enumerate(csv_reader, start=2):  # Start from 2 to account for header row
            try:
                # Required fields validation
                required_fields = ['Container ID', 'Zone', 'Width(cm)', 'Depth(cm)', 'Height(cm)']
                for field in required_fields:
                    if field not in row or not row[field]:
                        raise ValueError(f"Missing required field: {field}")
                
                # Create container data
                container_data = {
                    "containerId": row['Container ID'],
                    "zone": row['Zone'],
                    "width": float(row['Width(cm)']),
                    "depth": float(row['Depth(cm)']),
                    "height": float(row['Height(cm)']),
                    "openFace": row['Open Face'] if 'Open Face' in row and row['Open Face'] else "front",
                    "maxWeight": float(row['Max Weight (kg)']) if 'Max Weight (kg)' in row and row['Max Weight (kg)'] else None
                }
                
                # Check if container already exists
                existing_container = crud.get_container(db, container_data["containerId"])
                if not existing_container:
                    # Create new container
                    container = crud.create_container(db, container_data)
                    container_ids.append(container.id)
                    imported_count += 1
                
            except Exception as e:
                errors.append({
                    "row": row_idx,
                    "message": str(e)
                })
        
        # Log the import operation
        crud.create_log_entry(
            db,
            operation=crud.ActionType.IMPORT,
            details={
                "file_name": file.filename,
                "containers_imported": imported_count,
                "errors": len(errors)
            },
            container_ids=container_ids
        )
        
        return schemas.ImportResponse(
            success=True,
            containersImported=imported_count,
            errors=errors if errors else None
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Container import failed: {str(e)}")

@router.get("/export/arrangement")
async def export_arrangement(db: Session = Depends(get_db)):
    """
    Export the current arrangement to a CSV file.
    
    This endpoint exports the current arrangement of items in containers
    to a CSV file.
    """
    try:
        # Get all positions
        items = crud.get_items(db)
        
        # Create CSV content
        output = io.StringIO()
        csv_writer = csv.writer(output)
        
        # Write header
        csv_writer.writerow(['Item ID', 'Container ID', 'Coordinates (W1,D1,H1),(W2,D2,H2)'])
        
        # Write data rows
        for item in items:
            position = crud.get_item_position(db, item.id)
            if position:
                start_coords = f"({position.x},{position.y},{position.z})"
                
                # Calculate end coordinates based on orientation
                orientations = item.get_possible_orientations()
                if 0 <= position.orientation < len(orientations):
                    width, height, depth = orientations[position.orientation]
                else:
                    width, height, depth = item.width, item.height, item.depth
                
                end_coords = f"({position.x + width},{position.y + height},{position.z + depth})"
                
                csv_writer.writerow([
                    item.id,
                    position.container_id,
                    f"{start_coords},{end_coords}"
                ])
        
        # Prepare response
        output.seek(0)
        
        # Log the export operation
        crud.create_log_entry(
            db,
            operation=crud.ActionType.EXPORT,
            details={
                "export_type": "arrangement",
                "item_count": len(items)
            }
        )
        
        return StreamingResponse(
            io.StringIO(output.getvalue()),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=arrangement_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            }
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
