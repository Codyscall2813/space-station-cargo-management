from sqlalchemy import Column, String, Float, Enum
from sqlalchemy.orm import relationship
from src.db.session import Base
import enum

class OpenFace(enum.Enum):
    FRONT = "front"
    BACK = "back"
    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"

class Container(Base):
    """Model representing a storage container in the space station."""
    __tablename__ = "containers"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, index=True)
    zone = Column(String, index=True)
    width = Column(Float, nullable=False)  # Width - horizontal along open face
    depth = Column(Float, nullable=False)  # Depth - perpendicular to open face
    height = Column(Float, nullable=False)  # Height - vertical along open face
    open_face = Column(Enum(OpenFace), default=OpenFace.FRONT)
    max_weight = Column(Float, nullable=True)  # Optional weight constraint
    
    # Relationships
    positions = relationship("Position", back_populates="container", cascade="all, delete-orphan")
    
    def volume(self):
        """Calculate the total volume of the container."""
        return self.width * self.height * self.depth
    
    def to_dict(self):
        """Convert container object to dictionary."""
        return {
            "containerId": self.id,
            "name": self.name,
            "zone": self.zone,
            "width": self.width,
            "depth": self.depth,
            "height": self.height,
            "openFace": self.open_face.value if self.open_face else "front",
            "maxWeight": self.max_weight
        }
