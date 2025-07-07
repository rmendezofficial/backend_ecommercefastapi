from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text, Float, ForeignKey, Numeric, Enum, CheckConstraint
from sqlalchemy.sql import func
from database import Base
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum

class Categories(Base):
    __tablename__='categories'
    
    id=Column(Integer,primary_key=True,index=True)
    title=Column(String(50),unique=True, nullable=False)
    
    