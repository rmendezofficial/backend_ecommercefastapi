from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text, Float, ForeignKey, Numeric, Enum, CheckConstraint
from sqlalchemy.sql import func
from database import Base
from datetime import datetime

class Reservations(Base):
    __tablename__='reservations'
    
    id=Column(Integer, primary_key=True, index=True)
    product_id=Column(Integer, ForeignKey('products.id'), nullable=False)
    user_id=Column(Integer, ForeignKey('users.id'), nullable=False)
    units=Column(Integer,nullable=False)
    expires_at=Column(DateTime)
    status=Column(String(200),default='pending')
    checkout_session_id=Column(Text, nullable=False)