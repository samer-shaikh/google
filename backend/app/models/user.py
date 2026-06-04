from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from sqlalchemy.orm import relationship
 
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)

    email = Column(String, unique=True)

    password_hash = Column(String, nullable=True)

    google_id = Column(String, nullable=True)

    name = Column(String)

    picture = Column(String)

    created_at = Column(DateTime,
                        default=datetime.utcnow)
    

    threads = relationship(
        "Thread",
        back_populates="user",
        cascade="all, delete"
    )