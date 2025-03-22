import time
import functools
import threading
from typing import Dict, Any, Callable, List, Optional
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global cache for memoization
_memoization_cache = {}
_cache_lock = threading.RLock()

# Global cache for container state
_container_cache = {}
_container_cache_lock = threading.RLock()

def memoize(max_size: int = 100):
    """
    Memoization decorator for caching function results.
    
    Args:
        max_size: Maximum number of results to cache
    
    Returns:
        Decorated function with caching capability
    """
    def decorator(func):
        cache = {}
        cache_key_queue = []
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Create a cache key from the arguments
            key = (func.__name__, args, frozenset(kwargs.items()))
            
            with _cache_lock:
                if key in cache:
                    return cache[key]
                
                result = func(*args, **kwargs)
                
                # Add to cache
                cache[key] = result
                cache_key_queue.append(key)
                
                # Maintain maximum cache size
                if len(cache) > max_size:
                    oldest_key = cache_key_queue.pop(0)
                    if oldest_key in cache:
                        del cache[oldest_key]
                
                return result
        
        # Add functions to clear cache if needed
        wrapper.cache = cache
        wrapper.clear_cache = lambda: cache.clear()
        
        return wrapper
    
    return decorator

def performance_timer(func):
    """
    Decorator to measure and log function execution time.
    
    Args:
        func: Function to measure
    
    Returns:
        Decorated function with timing capability
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        
        execution_time = end_time - start_time
        logger.info(f"Function {func.__name__} executed in {execution_time:.4f} seconds")
        
        return result
    
    return wrapper

def get_cached_container_state(container_id: str, db_session) -> Optional[Dict[str, Any]]:
    """
    Get cached container state, or retrieve and cache it if not available.
    
    Args:
        container_id: ID of the container
        db_session: Database session
    
    Returns:
        Container state (positions and grid representation)
    """
    from src.db import crud
    from src.algorithms.placement import _create_container_grid
    
    with _container_cache_lock:
        # Check if cache is valid
        if container_id in _container_cache:
            cached_state = _container_cache[container_id]
            last_update_time = cached_state.get("last_update_time", 0)
            
            # If cache is recent enough (less than 5 seconds old), use it
            if time.time() - last_update_time < 5:
                return cached_state
        
        # Cache miss or expired, retrieve from database
        container = crud.get_container(db_session, container_id)
        if not container:
            return None
        
        positions = crud.get_container_positions(db_session, container_id)
        
        # Create grid representation
        container_grid = _create_container_grid(container, positions)
        
        # Create cache entry
        container_state = {
            "container": container,
            "positions": positions,
            "grid": container_grid,
            "last_update_time": time.time()
        }
        
        # Update cache
        _container_cache[container_id] = container_state
        
        return container_state

def invalidate_container_cache(container_id: str):
    """
    Invalidate the cache for a specific container.
    
    Args:
        container_id: ID of the container to invalidate
    """
    with _container_cache_lock:
        if container_id in _container_cache:
            del _container_cache[container_id]

def batch_database_operations(operations: List[Callable], db_session) -> List[Any]:
    """
    Execute multiple database operations in a single transaction for better performance.
    
    Args:
        operations: List of callables that perform database operations
        db_session: Database session
    
    Returns:
        List of results from each operation
    """
    results = []
    
    # Execute all operations in a single transaction
    try:
        for operation in operations:
            result = operation(db_session)
            results.append(result)
        
        db_session.commit()
    except Exception as e:
        db_session.rollback()
        logger.error(f"Batch database operation failed: {str(e)}")
        raise
    
    return results

# Database query optimization
def optimize_query(query):
    """
    Apply common optimizations to database queries.
    
    Args:
        query: SQLAlchemy query object
    
    Returns:
        Optimized query
    """
    # Add common optimizations like eager loading for frequent joins
    if hasattr(query, 'options'):
        from sqlalchemy.orm import joinedload
        
        # Determine which relationships to eager load based on the entity
        mapper = query._entity_zero().entity_zero.entity
        
        if hasattr(mapper, '__tablename__'):
            tablename = mapper.__tablename__
            
            if tablename == 'items':
                query = query.options(joinedload(mapper.positions))
            elif tablename == 'containers':
                query = query.options(joinedload(mapper.positions))
            elif tablename == 'positions':
                query = query.options(joinedload(mapper.item), joinedload(mapper.container))
    
    return query

# Optimize bulk database operations
class BulkOperationOptimizer:
    """Utility class for optimizing bulk database operations."""
    
    @staticmethod
    def bulk_create_positions(positions_data: List[Dict[str, Any]], db_session) -> List[str]:
        """
        Create multiple positions in bulk with a single transaction.
        
        Args:
            positions_data: List of position data dictionaries
            db_session: Database session
        
        Returns:
            List of created position IDs
        """
        from src.db import crud
        from src.models.position import Position
        import uuid
        
        position_ids = []
        positions = []
        
        for position_data in positions_data:
            # Generate an ID if not provided
            position_id = position_data.get("id", f"pos_{uuid.uuid4().hex[:8]}")
            position_ids.append(position_id)
            
            # Create the position object
            position = Position(
                id=position_id,
                item_id=position_data.get("itemId"),
                container_id=position_data.get("containerId"),
                x=position_data.get("position", {}).get("startCoordinates", {}).get("width", 0),
                y=position_data.get("position", {}).get("startCoordinates", {}).get("height", 0),
                z=position_data.get("position", {}).get("startCoordinates", {}).get("depth", 0),
                orientation=position_data.get("orientation", 0),
                visible=position_data.get("visible", False)
            )
            positions.append(position)
        
        # Bulk insert
        db_session.add_all(positions)
        db_session.commit()
        
        # Invalidate container caches
        container_ids = set(p.container_id for p in positions)
        for container_id in container_ids:
            invalidate_container_cache(container_id)
        
        return position_ids
    
    @staticmethod
    def bulk_delete_positions(position_ids: List[str], db_session) -> int:
        """
        Delete multiple positions in bulk with a single transaction.
        
        Args:
            position_ids: List of position IDs to delete
            db_session: Database session
        
        Returns:
            Number of deleted positions
        """
        from src.models.position import Position
        
        # Get container IDs for cache invalidation
        positions = db_session.query(Position).filter(Position.id.in_(position_ids)).all()
        container_ids = set(p.container_id for p in positions)
        
        # Execute bulk delete
        result = db_session.query(Position).filter(Position.id.in_(position_ids)).delete(synchronize_session=False)
        db_session.commit()
        
        # Invalidate container caches
        for container_id in container_ids:
            invalidate_container_cache(container_id)
        
        return result

# Thread pool for parallel processing
class AlgorithmThreadPool:
    """
    Thread pool for executing computationally intensive algorithms in parallel.
    """
    
    def __init__(self, max_workers: int = 4):
        """
        Initialize the thread pool.
        
        Args:
            max_workers: Maximum number of worker threads
        """
        self.max_workers = max_workers
        self._workers = []
        self._results = {}
        self._lock = threading.RLock()
        self._result_available = threading.Event()
    
    def submit(self, task_id: str, func: Callable, *args, **kwargs):
        """
        Submit a task to the thread pool.
        
        Args:
            task_id: Unique ID for the task
            func: Function to execute
            *args: Arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function
        """
        with self._lock:
            # Clean up finished workers
            self._workers = [w for w in self._workers if w.is_alive()]
            
            # Check if we need to wait for worker slots
            while len(self._workers) >= self.max_workers:
                self._lock.release()
                time.sleep(0.1)  # Short sleep to avoid CPU spinning
                self._lock.acquire()
                self._workers = [w for w in self._workers if w.is_alive()]
            
            # Create and start a new worker thread
            worker = threading.Thread(
                target=self._worker_function,
                args=(task_id, func, args, kwargs)
            )
            worker.daemon = True
            self._workers.append(worker)
            worker.start()
    
    def _worker_function(self, task_id: str, func: Callable, args, kwargs):
        """Worker thread function that executes the task."""
        try:
            result = func(*args, **kwargs)
            with self._lock:
                self._results[task_id] = {"status": "completed", "result": result}
        except Exception as e:
            with self._lock:
                self._results[task_id] = {"status": "error", "error": str(e)}
        
        self._result_available.set()
    
    def get_result(self, task_id: str, timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        Get the result of a task.
        
        Args:
            task_id: ID of the task
            timeout: Maximum time to wait for the result (None for no timeout)
        
        Returns:
            Task result with status
        """
        end_time = None if timeout is None else time.time() + timeout
        
        while True:
            with self._lock:
                if task_id in self._results:
                    return self._results.pop(task_id)
            
            if end_time is not None and time.time() >= end_time:
                return {"status": "timeout"}
            
            # Wait for any result to become available
            self._result_available.wait(timeout=0.1)
            self._result_available.clear()
    
    def shutdown(self, wait: bool = True):
        """
        Shutdown the thread pool.
        
        Args:
            wait: Whether to wait for all tasks to complete
        """
        if wait:
            for worker in self._workers:
                worker.join()
        
        self._workers = []
        self._results = {}

# Create a global thread pool instance
algorithm_thread_pool = AlgorithmThreadPool()

# Database connection pool optimization
def configure_db_pool(engine, pool_size=10, max_overflow=20, pool_timeout=30):
    """
    Configure the database connection pool for optimal performance.
    
    Args:
        engine: SQLAlchemy engine
        pool_size: Target size of the pool
        max_overflow: Maximum overflow size
        pool_timeout: Pool timeout in seconds
    """
    engine.pool._pool.setmaxbufsize(pool_size)
    engine.pool._pool.setmaxcached(pool_size)
    engine.pool._pool.setmaxshared(pool_size)
    engine.pool._pool.setmaxconnections(pool_size + max_overflow)
    engine.pool._pool.timeout = pool_timeout
