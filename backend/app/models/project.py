from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.schema import ForeignKey
from sqlalchemy.orm import relationship
 
from app.database import Base

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    title = Column(String)
    description = Column(Text)

    user_id = Column(
        Integer,
        ForeignKey("users.id")
    )