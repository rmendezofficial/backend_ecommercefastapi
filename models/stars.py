from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text, Float, ForeignKey, Numeric, Enum, CheckConstraint
from sqlalchemy.sql import func
from database import Base
from sqlalchemy.orm import relationship
import enum

class Stars(Base):
    __tablename__='stars'
    
    id=Column(Integer,primary_key=True,index=True)
    product_id=Column(Integer,ForeignKey('products.id'),nullable=False)
    user_id=Column(Integer,ForeignKey('users.id'),nullable=False)
    stars_number=Column(Integer, nullable=False)
    created_at=Column(DateTime,server_default=func.now())
    
    
    __table_args__ = (
        CheckConstraint('stars_number >= 0', name='check_stars_greater_than_or_equal_to_0'), #0 is for not rated
        CheckConstraint('stars_number <= 5', name='check_stars_less_than_or_equal_to_5')
    )