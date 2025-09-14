from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from ..database import Base

class Deck(Base):
    __tablename__ = "decks"

    id = Column(Integer, primary_key=True, index=True)
    prospect_id = Column(Integer, ForeignKey("prospects.id"), nullable=False)

    title = Column(String, nullable=False, default="OffDeal Pitch")
    slides_json = Column(Text, nullable=False)   # normalized slides as JSON string (schema order)
    pdf_path = Column(String, nullable=True)     # filled when you render a PDF
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    prospect = relationship("Prospect", back_populates="decks")
