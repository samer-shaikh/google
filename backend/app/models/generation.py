from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class Generation(Base):
    __tablename__ = "generations"

    id = Column(Integer, primary_key=True)

    thread_id = Column(
        Integer,
        ForeignKey("threads.id")
    )

    prompt = Column(Text)

    result = Column(Text)

    status = Column(String)

    thread = relationship(
        "Thread",
        back_populates="generations"
    )