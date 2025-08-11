from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text, Float, ForeignKey, Numeric, Enum
from sqlalchemy.sql import func
from database import Base
from sqlalchemy.orm import relationship
import enum

class Reviews(Base):
    __tablename__='reviews'
    
    id=Column(Integer,primary_key=True,index=True)
    product_id=Column(Integer,ForeignKey('products.id'),nullable=False)
    user_id=Column(Integer,ForeignKey('users.id'),nullable=False)
    review_text=Column(Text, nullable=False)
    created_at=Column(DateTime,server_default=func.now())
    edited=Column(Boolean, nullable=False)