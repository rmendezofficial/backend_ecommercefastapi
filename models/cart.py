from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text, Float, ForeignKey, Numeric, Enum
from sqlalchemy.sql import func
from database import Base
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum



class Cart(Base):
    __tablename__='cart'
    
    id=Column(Integer,primary_key=True,index=True)
    product_id=Column(Integer,ForeignKey('products.id'),nullable=False)
    user_id=Column(Integer,ForeignKey('users.id'),nullable=False)
    units=Column(Integer, nullable=False)
    created_at=Column(DateTime,server_default=func.now())
    
class CartSnapshoots(Base):
    __tablename__='cartsnapshoots'
    
    id=Column(Integer,primary_key=True,index=True)
    product_id=Column(Integer,ForeignKey('products.id'),nullable=False)
    user_id=Column(Integer,ForeignKey('users.id'),nullable=False)
    units=Column(Integer, nullable=False)
    created_at=Column(DateTime,server_default=func.now())
    checkout_session_id=Column(Integer,ForeignKey('checkoutsessions.id'),nullable=False)
    price_at_purchase=Column(Numeric(10,2), nullable=False)
    