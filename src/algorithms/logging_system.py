from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional, Union, Set
from datetime import datetime, date, timedelta
import json
import uuid
import threading
import time

from src.models.log import LogEntry, ActionType
from src.db import crud

# Thread-safe buffer for asynchronous logging
class LogBuffer:
    """A thread-safe buffer for asynchronous logging."""
    
    def __init__(self, max_size: int = 100, flush_interval: int = 5):
        """
        Initialize the log buffer.
        
        Args:
            max_size: Maximum number of entries before automatic flush
            flush_interval: Time in seconds between automatic flushes
        """
        self.buffer = []
        self.lock = threading.Lock()
        self.max_size = max_size
        self.flush_interval = flush_interval
        self.session_factory = None
        self.is_running = False
        self.flush_thread = None
        
    def start(self, session_factory) -> None:
        """
        Start the buffer's background flushing thread.
        
        Args:
            session_factory: Factory function to create database sessions
        """
        self.session_factory = session_factory
        self.is_running = True
        self.flush_thread = threading.Thread(target=self._background_flush)
        self.flush_thread.daemon = True
        self.flush_thread.start()
    
    def stop(self) -> None:
        """Stop the buffer's background flushing thread."""
        self.is_running = False
        if self.flush_thread:
            self.flush_thread.join(timeout=self.flush_interval * 2)
    
    def write(self, log_entry: Dict[str, Any]) -> None:
        """
        Write a log entry to the buffer.
        
        Args:
            log_entry: Log entry to buffer
        """
        with self.lock:
            self.buffer.append(log_entry)
            
            # If buffer exceeds max size, schedule a flush
            if len(self.buffer) >= self.max_size:
                self.flush()
    
    def flush(self) -> None:
        """Flush buffered log entries to the database."""
        with self.lock:
            if not self.buffer:
                return
            
            buffer_copy = self.buffer.copy()
            self.buffer = []
        
        # Write to database outside the lock
        if buffer_copy and self.session_factory:
            try:
                session = self.session_factory()
                try:
                    for entry in buffer_copy:
                        db_entry = LogEntry(
                            operation=entry.get("operation"),
                            user_id=entry.get("user_id"),
                            details=entry.get("details"),
                            item_ids=entry.get("item_ids"),
                            container_ids=entry.get("container_ids")
                        )
                        session.add(db_entry)
                    session.commit()
                finally:
                    session.close()
            except Exception as e:
                # In case of error, try to recover the entries
                with self.lock:
                    self.buffer = buffer_copy + self.buffer
                print(f"Error flushing log buffer: {str(e)}")
    
    def _background_flush(self) -> None:
        """Background thread that periodically flushes the buffer."""
        while self.is_running:
            time.sleep(self.flush_interval)
            try:
                self.flush()
            except Exception as e:
                print(f"Error in background flush: {str(e)}")


# Global log buffer instance
log_buffer = LogBuffer()


def initialize_logging(session_factory) -> None:
    """
    Initialize the logging system.
    
    Args:
        session_factory: Factory function to create database sessions
    """
    log_buffer.start(session_factory)


def shutdown_logging() -> None:
    """Shutdown the logging system cleanly."""
    log_buffer.flush()
    log_buffer.stop()


def log_operation(
    db: Session,
    operation: ActionType, 
    user_id: Optional[str] = None, 
    details: Optional[Dict[str, Any]] = None, 
    item_ids: Optional[List[str]] = None, 
    container_ids: Optional[List[str]] = None,
    is_critical: bool = False
) -> str:
    """
    Log an operation to the system.
    
    Args:
        db: Database session
        operation: Type of operation
        user_id: ID of the user performing the operation
        details: Additional details about the operation
        item_ids: IDs of items affected by the operation
        container_ids: IDs of containers affected by the operation
        is_critical: Whether this is a critical operation requiring immediate persistence
    
    Returns:
        ID of the created log entry
    """
    log_entry = {
        "operation": operation,
        "user_id": user_id or "system",
        "details": details or {},
        "item_ids": item_ids or [],
        "container_ids": container_ids or [],
        "timestamp": datetime.now()
    }
    
    if is_critical:
        # For critical operations, write directly to database
        db_entry = LogEntry(
            operation=log_entry["operation"],
            user_id=log_entry["user_id"],
            details=log_entry["details"],
            item_ids=log_entry["item_ids"],
            container_ids=log_entry["container_ids"]
        )
        db.add(db_entry)
        db.commit()
        db.refresh(db_entry)
        return db_entry.id
    else:
        # For non-critical operations, use the buffer
        log_buffer.write(log_entry)
        # Return a placeholder ID
        return f"buffered_{uuid.uuid4().hex}"


def query_logs(
    db: Session,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    user_id: Optional[str] = None,
    operation: Optional[ActionType] = None,
    item_id: Optional[str] = None,
    container_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    include_details: bool = True
) -> Dict[str, Any]:
    """
    Query logs with various filters.
    
    Args:
        db: Database session
        start_date: Start date for log entries
        end_date: End date for log entries
        user_id: Filter by user ID
        operation: Filter by operation type
        item_id: Filter by item ID
        container_id: Filter by container ID
        limit: Maximum number of entries to return
        offset: Offset for pagination
        include_details: Whether to include detailed fields
    
    Returns:
        Dict containing query results
    """
    # First, ensure the buffer is flushed to get the latest logs
    log_buffer.flush()
    
    # Build the query
    query = db.query(LogEntry)
    
    # Apply filters
    if start_date:
        query = query.filter(LogEntry.timestamp >= start_date)
    
    if end_date:
        query = query.filter(LogEntry.timestamp <= end_date)
    
    if user_id:
        query = query.filter(LogEntry.user_id == user_id)
    
    if operation:
        query = query.filter(LogEntry.operation == operation)
    
    # Apply item_id filter if provided
    if item_id:
        # This is a more complex filter since item_ids is a JSON array
        query = query.filter(LogEntry.item_ids.contains([item_id]))
    
    # Apply container_id filter if provided
    if container_id:
        query = query.filter(LogEntry.container_ids.contains([container_id]))
    
    # Get total count for pagination
    total_count = query.count()
    
    # Apply sorting, pagination
    query = query.order_by(LogEntry.timestamp.desc())
    query = query.offset(offset).limit(limit)
    
    # Execute query
    log_entries = query.all()
    
    # Format results
    formatted_logs = [
        format_log_entry(entry, include_details)
        for entry in log_entries
    ]
    
    return {
        "logs": formatted_logs,
        "total": total_count,
        "limit": limit,
        "offset": offset
    }


def format_log_entry(log_entry: LogEntry, include_details: bool = True) -> Dict[str, Any]:
    """
    Format a log entry for API response.
    
    Args:
        log_entry: Log entry to format
        include_details: Whether to include detailed fields
    
    Returns:
        Dict with formatted log entry
    """
    formatted = {
        "id": log_entry.id,
        "timestamp": log_entry.timestamp.isoformat(),
        "operation": log_entry.operation.value if log_entry.operation else None,
        "userId": log_entry.user_id
    }
    
    # Include item_id if available (first one for simplicity)
    if log_entry.item_ids and len(log_entry.item_ids) > 0:
        formatted["itemId"] = log_entry.item_ids[0]
    
    # Include details if requested
    if include_details:
        formatted["details"] = log_entry.details
        formatted["itemIds"] = log_entry.item_ids
        formatted["containerIds"] = log_entry.container_ids
    
    return formatted


def get_log_statistics(
    db: Session,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Generate statistics from log entries.
    
    Args:
        db: Database session
        start_date: Start date for log entries
        end_date: End date for log entries
    
    Returns:
        Dict containing various log statistics
    """
    # Ensure buffer is flushed
    log_buffer.flush()
    
    # Set default date range if not specified
    if not end_date:
        end_date = datetime.now()
    
    if not start_date:
        start_date = end_date - timedelta(days=30)  # Last 30 days by default
    
    # Build base query
    query = db.query(LogEntry).filter(
        LogEntry.timestamp >= start_date,
        LogEntry.timestamp <= end_date
    )
    
    # Get total count
    total_entries = query.count()
    
    # Get operation type counts
    operation_counts = {}
    for operation_type in ActionType:
        count = db.query(LogEntry).filter(
            LogEntry.timestamp >= start_date,
            LogEntry.timestamp <= end_date,
            LogEntry.operation == operation_type
        ).count()
        operation_counts[operation_type.value] = count
    
    # Get unique users
    unique_users = db.query(LogEntry.user_id).filter(
        LogEntry.timestamp >= start_date,
        LogEntry.timestamp <= end_date
    ).distinct().count()
    
    # Get user activity
    user_query = db.query(
        LogEntry.user_id, 
        db.func.count(LogEntry.id).label('count')
    ).filter(
        LogEntry.timestamp >= start_date,
        LogEntry.timestamp <= end_date
    ).group_by(LogEntry.user_id).order_by(db.text('count DESC')).limit(10)
    
    user_activity = [
        {"userId": row.user_id, "count": row.count}
        for row in user_query
    ]
    
    # Get most active items
    item_activity = {}
    
    # This is more complex due to the JSON array storage
    # We'll use a manual approach for demonstration
    logs_with_items = db.query(LogEntry).filter(
        LogEntry.timestamp >= start_date,
        LogEntry.timestamp <= end_date,
        LogEntry.item_ids.isnot(None)
    ).all()
    
    item_counts = {}
    for log in logs_with_items:
        if log.item_ids:
            for item_id in log.item_ids:
                item_counts[item_id] = item_counts.get(item_id, 0) + 1
    
    # Sort and limit to top 10
    top_items = sorted(item_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    item_activity = [{"itemId": item_id, "count": count} for item_id, count in top_items]
    
    return {
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        },
        "total_entries": total_entries,
        "operations": operation_counts,
        "unique_users": unique_users,
        "user_activity": user_activity,
        "item_activity": item_activity
    }


def analyze_operation_trends(
    db: Session,
    operation_type: Optional[ActionType] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    interval: str = "day"  # "hour", "day", "week", "month"
) -> Dict[str, Any]:
    """
    Analyze operation trends over time.
    
    Args:
        db: Database session
        operation_type: Type of operation to analyze (None for all)
        start_date: Start date for analysis
        end_date: End date for analysis
        interval: Time interval for grouping ("hour", "day", "week", "month")
    
    Returns:
        Dict containing trend analysis
    """
    # Ensure buffer is flushed
    log_buffer.flush()
    
    # Set default date range if not specified
    if not end_date:
        end_date = datetime.now()
    
    if not start_date:
        # Default range depends on interval
        if interval == "hour":
            start_date = end_date - timedelta(days=1)  # Last 24 hours
        elif interval == "day":
            start_date = end_date - timedelta(days=30)  # Last 30 days
        elif interval == "week":
            start_date = end_date - timedelta(weeks=12)  # Last 12 weeks
        elif interval == "month":
            start_date = end_date - timedelta(days=365)  # Last 12 months
        else:
            start_date = end_date - timedelta(days=30)  # Default to 30 days
    
    # Build base query
    query = db.query(LogEntry).filter(
        LogEntry.timestamp >= start_date,
        LogEntry.timestamp <= end_date
    )
    
    # Apply operation filter if specified
    if operation_type:
        query = query.filter(LogEntry.operation == operation_type)
    
    # Get all matching logs
    logs = query.all()
    
    # Group by time interval
    time_groups = {}
    
    for log in logs:
        # Get the interval key
        if interval == "hour":
            key = log.timestamp.strftime("%Y-%m-%d %H:00")
        elif interval == "day":
            key = log.timestamp.strftime("%Y-%m-%d")
        elif interval == "week":
            # ISO week format: YYYY-WW
            key = f"{log.timestamp.isocalendar()[0]}-W{log.timestamp.isocalendar()[1]:02d}"
        elif interval == "month":
            key = log.timestamp.strftime("%Y-%m")
        else:
            key = log.timestamp.strftime("%Y-%m-%d")  # Default to day
        
        # Increment count
        if key in time_groups:
            time_groups[key] += 1
        else:
            time_groups[key] = 1
    
    # Convert to sorted list for output
    time_series = [
        {"interval": key, "count": count}
        for key, count in sorted(time_groups.items())
    ]
    
    # Calculate summary statistics
    total_count = sum(time_groups.values())
    avg_per_interval = total_count / len(time_groups) if time_groups else 0
    max_interval = max(time_groups.values()) if time_groups else 0
    min_interval = min(time_groups.values()) if time_groups else 0
    
    return {
        "operation_type": operation_type.value if operation_type else "all",
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "interval": interval
        },
        "total_count": total_count,
        "avg_per_interval": avg_per_interval,
        "max_interval": max_interval,
        "min_interval": min_interval,
        "time_series": time_series
    }


def get_item_history(
    db: Session,
    item_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    include_details: bool = True
) -> Dict[str, Any]:
    """
    Get the history of operations for a specific item.
    
    Args:
        db: Database session
        item_id: ID of the item
        start_date: Start date for log entries
        end_date: End date for log entries
        include_details: Whether to include detailed fields
    
    Returns:
        Dict containing item history
    """
    # Ensure buffer is flushed
    log_buffer.flush()
    
    # Get item details
    item = crud.get_item(db, item_id)
    if not item:
        return {
            "success": False,
            "reason": "Item not found",
            "logs": []
        }
    
    # Build query
    query = db.query(LogEntry).filter(LogEntry.item_ids.contains([item_id]))
    
    # Apply date filters if specified
    if start_date:
        query = query.filter(LogEntry.timestamp >= start_date)
    
    if end_date:
        query = query.filter(LogEntry.timestamp <= end_date)
    
    # Execute query
    logs = query.order_by(LogEntry.timestamp.desc()).all()
    
    # Format logs
    formatted_logs = [
        format_log_entry(log, include_details)
        for log in logs
    ]
    
    return {
        "success": True,
        "item": {
            "id": item.id,
            "name": item.name,
            "status": item.status.value if item.status else None
        },
        "logs": formatted_logs,
        "total": len(formatted_logs)
    }


def get_container_history(
    db: Session,
    container_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    include_details: bool = True
) -> Dict[str, Any]:
    """
    Get the history of operations for a specific container.
    
    Args:
        db: Database session
        container_id: ID of the container
        start_date: Start date for log entries
        end_date: End date for log entries
        include_details: Whether to include detailed fields
    
    Returns:
        Dict containing container history
    """
    # Ensure buffer is flushed
    log_buffer.flush()
    
    # Get container details
    container = crud.get_container(db, container_id)
    if not container:
        return {
            "success": False,
            "reason": "Container not found",
            "logs": []
        }
    
    # Build query
    query = db.query(LogEntry).filter(LogEntry.container_ids.contains([container_id]))
    
    # Apply date filters if specified
    if start_date:
        query = query.filter(LogEntry.timestamp >= start_date)
    
    if end_date:
        query = query.filter(LogEntry.timestamp <= end_date)
    
    # Execute query
    logs = query.order_by(LogEntry.timestamp.desc()).all()
    
    # Format logs
    formatted_logs = [
        format_log_entry(log, include_details)
        for log in logs
    ]
    
    return {
        "success": True,
        "container": {
            "id": container.id,
            "name": container.name,
            "zone": container.zone
        },
        "logs": formatted_logs,
        "total": len(formatted_logs)
    }
