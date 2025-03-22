from sqlalchemy import Column, String, Float, Date, Enum, ForeignKey, Text
from sqlalchemy.orm import relationship
import enum
from src.db.session import Base

class MissionStatus(enum.Enum):
    PLANNED = "planned"
    LOADING = "loading"
    COMPLETE = "complete"

class WasteReason(enum.Enum):
    EXPIRED = "expired"
    DEPLETED = "depleted"
    DAMAGED = "damaged"
    OTHER = "other"

class ReturnMission(Base):
    """Model representing a cargo return mission."""
    __tablename__ = "return_missions"

    id = Column(String, primary_key=True, index=True)
    scheduled_date = Column(Date, nullable=False)
    max_weight = Column(Float, nullable=False)
    max_volume = Column(Float, nullable=False)
    current_weight = Column(Float, default=0)
    current_volume = Column(Float, default=0)
    status = Column(Enum(MissionStatus), default=MissionStatus.PLANNED)
    
    # Relationships
    waste_items = relationship("WasteItem", back_populates="return_mission")
    
    def to_dict(self):
        """Convert return mission to dictionary."""
        return {
            "id": self.id,
            "scheduledDate": self.scheduled_date.isoformat() if self.scheduled_date else None,
            "maxWeight": self.max_weight,
            "maxVolume": self.max_volume,
            "currentWeight": self.current_weight,
            "currentVolume": self.current_volume,
            "status": self.status.value if self.status else "planned",
            "wasteItems": [item.to_dict() for item in self.waste_items] if self.waste_items else []
        }

class WasteItem(Base):
    """Model representing an item marked as waste."""
    __tablename__ = "waste_items"

    id = Column(String, primary_key=True, index=True)
    item_id = Column(String, ForeignKey("items.id"), nullable=False)
    reason = Column(Enum(WasteReason), nullable=False)
    waste_date = Column(Date, nullable=False)
    return_mission_id = Column(String, ForeignKey("return_missions.id"), nullable=True)
    notes = Column(Text, nullable=True)
    
    # Relationships
    item = relationship("Item", back_populates="waste_info")
    return_mission = relationship("ReturnMission", back_populates="waste_items")
    
    def to_dict(self):
        """Convert waste item to dictionary."""
        return {
            "id": self.id,
            "itemId": self.item_id,
            "reason": self.reason.value if self.reason else None,
            "wasteDate": self.waste_date.isoformat() if self.waste_date else None,
            "returnMissionId": self.return_mission_id,
            "notes": self.notes
        }
