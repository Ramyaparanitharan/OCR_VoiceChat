from sqlalchemy import Column, Integer, Text
from database import Base

class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    
    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text)
    embedding = Column(Text)  # store JSON string for now
