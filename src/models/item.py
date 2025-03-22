from sqlalchemy import Column, String, Float, Integer, Date, Enum, ForeignKey
from sqlalchemy.orm import relationship
from datetime import date
import enum
from src.db.session import Base

class ItemStatus(enum.Enum):
    ACTIVE = "active"
    WASTE = "waste"
    DEPLETED = "depleted"

class Item(Base):
    """Model representing an item in the space station."""
    __tablename__ = "items"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, index=True)
    width = Column(Float, nullable=False)
    height = Column(Float, nullable=False)
    depth = Column(Float, nullable=False)
    mass = Column(Float, nullable=False)
    priority = Column(Integer, nullable=False)  # 1-100, higher means more important
    expiry_date = Column(Date, nullable=True)
    usage_limit = Column(Integer, nullable=True)
    current_usage = Column(Integer, default=0)
    preferred_zone = Column(String, nullable=True)
    status = Column(Enum(ItemStatus), default=ItemStatus.ACTIVE)
    
    # Relationships
    positions = relationship("Position", back_populates="item", cascade="all, delete-orphan")
    waste_info = relationship("WasteItem", back_populates="item", uselist=False, cascade="all, delete-orphan")
    
    def volume(self):
        """Calculate the volume of the item."""
        return self.width * self.height * self.depth
    
    def is_expired(self, current_date=None):
        """Check if the item is expired based on the current date."""
        if not self.expiry_date:
            return False
        if current_date is None:
            current_date = date.today()
        return current_date >= self.expiry_date
    
    def is_depleted(self):
        """Check if the item has reached its usage limit."""
        if not self.usage_limit:
            return False
        return self.current_usage >= self.usage_limit
    
    def increment_usage(self, amount=1):
        """Increment the usage count of the item."""
        if self.usage_limit:
            self.current_usage += amount
            if self.current_usage >= self.usage_limit:
                self.status = ItemStatus.DEPLETED
                return True
        return False
    
    def get_possible_orientations(self):
        """Generate all possible orientations of the item."""
        return [
            (self.width, self.height, self.depth),  # original orientation
            (self.width, self.depth, self.height),  # rotate 90° around x
            (self.height, self.width, self.depth),  # rotate 90° around y
            (self.height, self.depth, self.width),  # rotate 90° around x, then 90° around y
            (self.depth, self.width, self.height),  # rotate 90° around z
            (self.depth, self.height, self.width),  # rotate 90° around z, then 90° around x
        ]
    
    def to_dict(self):
        """Convert item object to dictionary."""
        return {
            "itemId": self.id,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "depth": self.depth,
            "mass": self.mass,
            "priority": self.priority,
            "expiryDate": self.expiry_date.isoformat() if self.expiry_date else None,
            "usageLimit": self.usage_limit,
            "currentUsage": self.current_usage,
            "preferredZone": self.preferred_zone,
            "status": self.status.value if self.status else "active"
        }
