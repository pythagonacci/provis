from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
from ..database import Base

class Prospect(Base):
    __tablename__ = "prospects"

    id = Column(Integer, primary_key=True, index=True)

    # Core identity
    company_name = Column(String, nullable=False)
    contact_name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)

    # Context for personalization
    industry = Column(String, nullable=True)
    revenue_range = Column(String, nullable=True)
    location = Column(String, nullable=True)
    sale_motivation = Column(Text, nullable=True)
    signals = Column(Text, nullable=True)   # short notes like "owner retiring"
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships (filled in later by related models)
    decks = relationship("Deck", back_populates="prospect", cascade="all, delete-orphan")
    emails = relationship("Email", back_populates="prospect", cascade="all, delete-orphan")

    