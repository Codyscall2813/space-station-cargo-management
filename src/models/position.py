from sqlalchemy import Column, String, Float, Integer, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from src.db.session import Base

class Position(Base):
    """Model representing the position of an item in a container."""
    __tablename__ = "positions"

    id = Column(String, primary_key=True, index=True)
    item_id = Column(String, ForeignKey("items.id"), nullable=False)
    container_id = Column(String, ForeignKey("containers.id"), nullable=False)
    
    # Coordinates relative to container origin (bottom-left of open face)
    x = Column(Float, nullable=False)  # Width axis
    y = Column(Float, nullable=False)  # Height axis
    z = Column(Float, nullable=False)  # Depth axis
    
    # Item orientation (0-5) corresponding to the 6 possible orientations
    orientation = Column(Integer, nullable=False)
    
    # Whether the item is directly visible/accessible from the open face
    visible = Column(Boolean, default=False)
    
    # Timestamp for when this position was recorded
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    item = relationship("Item", back_populates="positions")
    container = relationship("Container", back_populates="positions")
    
    def to_dict(self):
        """Convert position object to dictionary."""
        # Get item dimensions based on orientation
        if self.item:
            orientations = self.item.get_possible_orientations()
            if 0 <= self.orientation < len(orientations):
                width, height, depth = orientations[self.orientation]
            else:
                width, height, depth = self.item.width, self.item.height, self.item.depth
        else:
            width, height, depth = 0, 0, 0
            
        return {
            "id": self.id,
            "itemId": self.item_id,
            "containerId": self.container_id,
            "position": {
                "startCoordinates": {
                    "width": self.x,
                    "height": self.y,
                    "depth": self.z
                },
                "endCoordinates": {
                    "width": self.x + width,
                    "height": self.y + height,
                    "depth": self.z + depth
                }
            },
            "orientation": self.orientation,
            "visible": self.visible,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }
