from sqlalchemy import Column, String, DateTime, JSON, Enum, Integer
from sqlalchemy.sql import func
import enum
from src.db.session import Base

class ActionType(enum.Enum):
    PLACEMENT = "placement"
    RETRIEVAL = "retrieval"
    REARRANGEMENT = "rearrangement"
    DISPOSAL = "disposal"
    SIMULATION = "simulation"
    IMPORT = "import"
    EXPORT = "export"

class LogEntry(Base):
    """Model representing a log entry for system operations."""
    __tablename__ = "log_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    operation = Column(Enum(ActionType), nullable=False)
    user_id = Column(String, nullable=True)
    details = Column(JSON, nullable=True)  # Flexible JSON field for operation-specific data
    item_ids = Column(JSON, nullable=True)  # Array of affected item IDs
    container_ids = Column(JSON, nullable=True)  # Array of affected container IDs
    
    def to_dict(self):
        """Convert log entry to dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "operation": self.operation.value if self.operation else None,
            "userId": self.user_id,
            "details": self.details,
            "itemIds": self.item_ids,
            "containerIds": self.container_ids
        }
