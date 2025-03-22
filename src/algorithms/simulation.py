from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, date, timedelta
import json
import uuid

from src.models.item import Item, ItemStatus
from src.models.container import Container
from src.models.position import Position
from src.models.return_mission import ReturnMission, WasteItem, WasteReason, MissionStatus
from src.algorithms.waste_management import identify_waste_items, mark_as_waste
from src.db import crud


class SimulationEngine:
    """
    Engine for simulating time-based operations in the space station.
    
    This class provides functionality for time advancement, scheduled event
    processing, and state management for the simulation.
    """
    
    def __init__(self, db: Session):
        """
        Initialize the simulation engine.
        
        Args:
            db: Database session
        """
        self.db = db
        self.current_date = self._get_or_initialize_date()
        self.is_simulating = False
        self.event_queue = []
        self._load_scheduled_events()
    
    def _get_or_initialize_date(self) -> date:
        """
        Get the current simulation date from the database or initialize it.
        
        Returns:
            Current simulation date
        """
        # Check if we have a simulation state record
        simulation_state = self.db.query(SimulationState).first()
        
        if not simulation_state:
            # Initialize with today's date
            simulation_state = SimulationState(
                id="simulation_state",
                current_date=date.today(),
                last_checkpoint=datetime.now(),
                is_simulating=False
            )
            self.db.add(simulation_state)
            self.db.commit()
        
        return simulation_state.current_date
    
    def _load_scheduled_events(self) -> None:
        """
        Load scheduled events from the database.
        """
        # Get events scheduled for the future
        events = self.db.query(ScheduledEvent).filter(
            ScheduledEvent.event_date >= self.current_date,
            ScheduledEvent.processed == False
        ).order_by(ScheduledEvent.event_date).all()
        
        self.event_queue = events
    
    def advance_time(self, days: int = 1, items_to_use: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Advance the simulation time by a specified number of days.
        
        Args:
            days: Number of days to advance
            items_to_use: List of items to use each day
        
        Returns:
            Dict containing the results of the time advancement
        """
        if days < 1:
            return {
                "success": False,
                "reason": "Days must be at least 1",
                "new_date": self.current_date.isoformat()
            }
        
        # Set simulation state
        self.is_simulating = True
        self._update_simulation_state(is_simulating=True)
        
        # Calculate target date
        start_date = self.current_date
        target_date = start_date + timedelta(days=days)
        
        try:
            # Process events day by day
            items_used = []
            items_expired = []
            items_depleted = []
            days_processed = 0
            
            for day_offset in range(days):
                current_sim_date = start_date + timedelta(days=day_offset)
                next_sim_date = current_sim_date + timedelta(days=1)
                
                # Process scheduled events for this day
                day_events = self._process_events_for_date(current_sim_date)
                
                # Process item usage for this day
                if items_to_use:
                    day_items_used, day_items_depleted = self._process_item_usage(items_to_use)
                    items_used.extend(day_items_used)
                    items_depleted.extend(day_items_depleted)
                
                # Update simulation date
                self.current_date = next_sim_date
                self._update_simulation_state(current_date=next_sim_date)
                
                days_processed += 1
            
            # After time advancement, check for expirations
            newly_expired_items = identify_waste_items(self.db, self.current_date)
            items_expired.extend(newly_expired_items)
            
            # Create a checkpoint of the system state
            self._create_checkpoint(f"Auto checkpoint after {days} days advancement")
            
            # Update simulation state
            self.is_simulating = False
            self._update_simulation_state(is_simulating=False)
            
            return {
                "success": True,
                "new_date": self.current_date.isoformat(),
                "days_processed": days_processed,
                "items_used": [self._format_item_usage(item) for item in items_used],
                "items_expired": [self._format_item_base(item) for item in items_expired],
                "items_depleted": [self._format_item_base(item) for item in items_depleted]
            }
        
        except Exception as e:
            # In case of error, restore the original date
            self.current_date = start_date
            self._update_simulation_state(current_date=start_date, is_simulating=False)
            
            return {
                "success": False,
                "reason": str(e),
                "new_date": start_date.isoformat()
            }
    
    def advance_to_date(self, target_date: date, items_to_use: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Advance the simulation time to a specific date.
        
        Args:
            target_date: Target date to advance to
            items_to_use: List of items to use each day
        
        Returns:
            Dict containing the results of the time advancement
        """
        if target_date <= self.current_date:
            return {
                "success": False,
                "reason": "Target date must be in the future",
                "new_date": self.current_date.isoformat()
            }
        
        days_difference = (target_date - self.current_date).days
        return self.advance_time(days_difference, items_to_use)
    
    def _process_events_for_date(self, event_date: date) -> List[Dict[str, Any]]:
        """
        Process all scheduled events for a specific date.
        
        Args:
            event_date: Date to process events for
        
        Returns:
            List of processed events
        """
        # Find events scheduled for this date
        events = self.db.query(ScheduledEvent).filter(
            ScheduledEvent.event_date == event_date,
            ScheduledEvent.processed == False
        ).all()
        
        processed_events = []
        
        for event in events:
            # Process the event based on its type
            result = self._process_event(event)
            
            # Mark event as processed
            event.processed = True
            self.db.commit()
            
            processed_events.append({
                "event_id": event.id,
                "event_type": event.event_type,
                "result": result
            })
        
        return processed_events
    
    def _process_event(self, event: 'ScheduledEvent') -> Dict[str, Any]:
        """
        Process a specific scheduled event.
        
        Args:
            event: Event to process
        
        Returns:
            Dict containing the result of processing
        """
        try:
            # Parse event details
            details = event.details if event.details else {}
            
            # Process based on event type
            if event.event_type == EventType.ITEM_EXPIRY:
                # Mark item as expired waste
                item_id = details.get("item_id")
                if item_id:
                    item = crud.get_item(self.db, item_id)
                    if item and item.status == ItemStatus.ACTIVE:
                        mark_as_waste(self.db, item_id, WasteReason.EXPIRED)
                        return {"success": True, "item_id": item_id}
            
            elif event.event_type == EventType.RETURN_MISSION:
                # Process return mission event
                mission_id = details.get("mission_id")
                if mission_id:
                    mission = crud.get_return_mission(self.db, mission_id)
                    if mission:
                        mission.status = MissionStatus.LOADING
                        self.db.commit()
                        return {"success": True, "mission_id": mission_id}
            
            elif event.event_type == EventType.MAINTENANCE:
                # Log maintenance event (no actual effect)
                return {"success": True, "maintenance_type": details.get("maintenance_type")}
            
            # Unknown event type
            return {"success": False, "reason": "Unknown event type"}
        
        except Exception as e:
            return {"success": False, "reason": str(e)}
    
    def _process_item_usage(self, items_to_use: List[Dict[str, Any]]) -> Tuple[List[Item], List[Item]]:
        """
        Process usage of specified items.
        
        Args:
            items_to_use: List of items to use
        
        Returns:
            Tuple of (used items, depleted items)
        """
        used_items = []
        depleted_items = []
        
        for item_data in items_to_use:
            item = None
            
            # Find the item by ID or name
            if "itemId" in item_data and item_data["itemId"]:
                item = crud.get_item(self.db, item_data["itemId"])
            elif "name" in item_data and item_data["name"]:
                item = crud.get_item_by_name(self.db, item_data["name"])
            
            if item and item.status == ItemStatus.ACTIVE:
                # Increment usage
                depleted = item.increment_usage()
                used_items.append(item)
                
                # If item became depleted, mark it as waste
                if depleted:
                    mark_as_waste(self.db, item.id, WasteReason.DEPLETED)
                    depleted_items.append(item)
        
        self.db.commit()
        return used_items, depleted_items
    
    def _format_item_usage(self, item: Item) -> Dict[str, Any]:
        """
        Format an item with usage details for the API response.
        
        Args:
            item: Item to format
        
        Returns:
            Dict with formatted item data
        """
        return {
            "itemId": item.id,
            "name": item.name,
            "remainingUses": item.usage_limit - item.current_usage if item.usage_limit else None
        }
    
    def _format_item_base(self, item: Item) -> Dict[str, Any]:
        """
        Format an item with basic details for the API response.
        
        Args:
            item: Item to format
        
        Returns:
            Dict with formatted item data
        """
        return {
            "itemId": item.id,
            "name": item.name
        }
    
    def _update_simulation_state(self, current_date: Optional[date] = None, is_simulating: Optional[bool] = None) -> None:
        """
        Update the simulation state in the database.
        
        Args:
            current_date: Current simulation date
            is_simulating: Whether simulation is in progress
        """
        simulation_state = self.db.query(SimulationState).first()
        
        if not simulation_state:
            # Create a new state record
            simulation_state = SimulationState(
                id="simulation_state",
                current_date=current_date or self.current_date,
                last_checkpoint=datetime.now(),
                is_simulating=is_simulating if is_simulating is not None else self.is_simulating
            )
            self.db.add(simulation_state)
        else:
            # Update existing state
            if current_date:
                simulation_state.current_date = current_date
            if is_simulating is not None:
                simulation_state.is_simulating = is_simulating
        
        self.db.commit()
    
    def schedule_event(self, event_type: 'EventType', event_date: date, details: Optional[Dict[str, Any]] = None) -> 'ScheduledEvent':
        """
        Schedule a new event.
        
        Args:
            event_type: Type of event
            event_date: Date when the event should occur
            details: Additional details for the event
        
        Returns:
            Newly created ScheduledEvent
        """
        event = ScheduledEvent(
            id=f"event_{uuid.uuid4().hex}",
            event_type=event_type,
            event_date=event_date,
            details=details,
            processed=False
        )
        
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        
        # Add to event queue if in the future
        if event_date >= self.current_date:
            self.event_queue.append(event)
            # Sort the queue by date
            self.event_queue.sort(key=lambda e: e.event_date)
        
        return event
    
    def get_scheduled_events(self, start_date: Optional[date] = None, end_date: Optional[date] = None) -> List['ScheduledEvent']:
        """
        Get scheduled events within a date range.
        
        Args:
            start_date: Start date for the range
            end_date: End date for the range
        
        Returns:
            List of scheduled events
        """
        query = self.db.query(ScheduledEvent).filter(ScheduledEvent.processed == False)
        
        if start_date:
            query = query.filter(ScheduledEvent.event_date >= start_date)
        else:
            query = query.filter(ScheduledEvent.event_date >= self.current_date)
        
        if end_date:
            query = query.filter(ScheduledEvent.event_date <= end_date)
        
        return query.order_by(ScheduledEvent.event_date).all()
    
    def _create_checkpoint(self, label: str) -> 'SystemCheckpoint':
        """
        Create a checkpoint of the current system state.
        
        Args:
            label: Label for the checkpoint
        
        Returns:
            Newly created SystemCheckpoint
        """
        # Capture the current state
        current_state = {
            "date": self.current_date.isoformat(),
            "timestamp": datetime.now().isoformat()
        }
        
        checkpoint = SystemCheckpoint(
            id=f"checkpoint_{uuid.uuid4().hex}",
            created_at=datetime.now(),
            label=label,
            state=current_state
        )
        
        self.db.add(checkpoint)
        self.db.commit()
        self.db.refresh(checkpoint)
        
        # Update simulation state with last checkpoint
        simulation_state = self.db.query(SimulationState).first()
        if simulation_state:
            simulation_state.last_checkpoint = checkpoint.created_at
            self.db.commit()
        
        return checkpoint
    
    def create_checkpoint(self, label: str) -> Dict[str, Any]:
        """
        Create a checkpoint of the current system state (public method).
        
        Args:
            label: Label for the checkpoint
        
        Returns:
            Dict with checkpoint details
        """
        checkpoint = self._create_checkpoint(label)
        
        return {
            "success": True,
            "checkpoint_id": checkpoint.id,
            "created_at": checkpoint.created_at.isoformat(),
            "label": checkpoint.label
        }
    
    def restore_checkpoint(self, checkpoint_id: str) -> Dict[str, Any]:
        """
        Restore the system to a previous checkpoint.
        
        Args:
            checkpoint_id: ID of the checkpoint to restore
        
        Returns:
            Dict with restoration result
        """
        # Get the checkpoint
        checkpoint = self.db.query(SystemCheckpoint).filter(SystemCheckpoint.id == checkpoint_id).first()
        
        if not checkpoint:
            return {
                "success": False,
                "reason": "Checkpoint not found"
            }
        
        try:
            # Get the state from the checkpoint
            state = checkpoint.state
            
            # Restore the date
            if "date" in state:
                restored_date = date.fromisoformat(state["date"])
                self.current_date = restored_date
                self._update_simulation_state(current_date=restored_date)
            
            # Reload scheduled events
            self._load_scheduled_events()
            
            return {
                "success": True,
                "checkpoint_id": checkpoint_id,
                "restored_date": self.current_date.isoformat()
            }
        
        except Exception as e:
            return {
                "success": False,
                "reason": f"Restoration failed: {str(e)}"
            }
    
    def get_checkpoints(self) -> List['SystemCheckpoint']:
        """
        Get all available system checkpoints.
        
        Returns:
            List of SystemCheckpoint objects
        """
        return self.db.query(SystemCheckpoint).order_by(SystemCheckpoint.created_at.desc()).all()
    
    def get_simulation_state(self) -> Dict[str, Any]:
        """
        Get the current simulation state.
        
        Returns:
            Dict with simulation state
        """
        simulation_state = self.db.query(SimulationState).first()
        
        if not simulation_state:
            return {
                "current_date": date.today().isoformat(),
                "is_simulating": False,
                "last_checkpoint": None
            }
        
        return {
            "current_date": simulation_state.current_date.isoformat(),
            "is_simulating": simulation_state.is_simulating,
            "last_checkpoint": simulation_state.last_checkpoint.isoformat() if simulation_state.last_checkpoint else None
        }


# Enums and models for simulation functionality

class EventType:
    """Enum for scheduled event types."""
    ITEM_EXPIRY = "item_expiry"
    RETURN_MISSION = "return_mission"
    MAINTENANCE = "maintenance"
    CUSTOM = "custom"


from sqlalchemy import Column, String, Date, DateTime, Boolean, JSON, Integer, ForeignKey
from sqlalchemy.sql import func
from src.db.session import Base

class SimulationState(Base):
    """Model representing the current state of the simulation."""
    __tablename__ = "simulation_state"
    
    id = Column(String, primary_key=True)
    current_date = Column(Date, nullable=False)
    last_checkpoint = Column(DateTime(timezone=True))
    is_simulating = Column(Boolean, default=False)
    details = Column(JSON, nullable=True)


class ScheduledEvent(Base):
    """Model representing a scheduled event in the simulation."""
    __tablename__ = "scheduled_events"
    
    id = Column(String, primary_key=True)
    event_type = Column(String, nullable=False)
    event_date = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    details = Column(JSON, nullable=True)
    processed = Column(Boolean, default=False)


class SystemCheckpoint(Base):
    """Model representing a checkpoint of the system state."""
    __tablename__ = "system_checkpoints"
    
    id = Column(String, primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    label = Column(String, nullable=True)
    state = Column(JSON, nullable=False)


# Utility functions for the simulation module

def create_simulation_engine(db: Session) -> SimulationEngine:
    """
    Create and initialize a simulation engine.
    
    Args:
        db: Database session
    
    Returns:
        Initialized SimulationEngine
    """
    return SimulationEngine(db)


def advance_time(db: Session, days: int = 1, items_to_use: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Advance the simulation time by a specified number of days.
    
    Args:
        db: Database session
        days: Number of days to advance
        items_to_use: List of items to use each day
    
    Returns:
        Dict containing the results of the time advancement
    """
    engine = create_simulation_engine(db)
    return engine.advance_time(days, items_to_use)


def advance_to_date(db: Session, target_date: date, items_to_use: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Advance the simulation time to a specific date.
    
    Args:
        db: Database session
        target_date: Target date to advance to
        items_to_use: List of items to use each day
    
    Returns:
        Dict containing the results of the time advancement
    """
    engine = create_simulation_engine(db)
    return engine.advance_to_date(target_date, items_to_use)


def schedule_event(db: Session, event_type: str, event_date: date, details: Optional[Dict[str, Any]] = None) -> ScheduledEvent:
    """
    Schedule a new event.
    
    Args:
        db: Database session
        event_type: Type of event
        event_date: Date when the event should occur
        details: Additional details for the event
    
    Returns:
        Newly created ScheduledEvent
    """
    engine = create_simulation_engine(db)
    return engine.schedule_event(event_type, event_date, details)


def get_scheduled_events(db: Session, start_date: Optional[date] = None, end_date: Optional[date] = None) -> List[Dict[str, Any]]:
    """
    Get scheduled events within a date range.
    
    Args:
        db: Database session
        start_date: Start date for the range
        end_date: End date for the range
    
    Returns:
        List of scheduled events
    """
    engine = create_simulation_engine(db)
    events = engine.get_scheduled_events(start_date, end_date)
    
    # Format for API
    return [
        {
            "id": event.id,
            "event_type": event.event_type,
            "event_date": event.event_date.isoformat(),
            "created_at": event.created_at.isoformat(),
            "details": event.details
        }
        for event in events
    ]


def create_checkpoint(db: Session, label: str) -> Dict[str, Any]:
    """
    Create a checkpoint of the current system state.
    
    Args:
        db: Database session
        label: Label for the checkpoint
    
    Returns:
        Dict with checkpoint details
    """
    engine = create_simulation_engine(db)
    return engine.create_checkpoint(label)


def restore_checkpoint(db: Session, checkpoint_id: str) -> Dict[str, Any]:
    """
    Restore the system to a previous checkpoint.
    
    Args:
        db: Database session
        checkpoint_id: ID of the checkpoint to restore
    
    Returns:
        Dict with restoration result
    """
    engine = create_simulation_engine(db)
    return engine.restore_checkpoint(checkpoint_id)


def get_checkpoints(db: Session) -> List[Dict[str, Any]]:
    """
    Get all available system checkpoints.
    
    Args:
        db: Database session
    
    Returns:
        List of checkpoints
    """
    engine = create_simulation_engine(db)
    checkpoints = engine.get_checkpoints()
    
    # Format for API
    return [
        {
            "id": checkpoint.id,
            "created_at": checkpoint.created_at.isoformat(),
            "label": checkpoint.label
        }
        for checkpoint in checkpoints
    ]


def get_simulation_state(db: Session) -> Dict[str, Any]:
    """
    Get the current simulation state.
    
    Args:
        db: Database session
    
    Returns:
        Dict with simulation state
    """
    engine = create_simulation_engine(db)
    return engine.get_simulation_state()
