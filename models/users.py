from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text, Float, ForeignKey, Numeric
from sqlalchemy.sql import func
from database import Base
from sqlalchemy.orm import relationship

class Users(Base):
    __tablename__='users'
    
    id=Column(Integer, primary_key=True, index=True)
    username=Column(String(50), unique=True, nullable=False)
    hashed_password=Column(String(200),nullable=False)
    email=Column(String(100), unique=True, nullable=False)
    name=Column(String(50), nullable=False)
    lastname=Column(String(50),nullable=False)
    disabled=Column(Boolean,default=False, nullable=False)
    verified=Column(Boolean, default=False,nullable=False)
    role=Column(String(20),default='user',nullable=False)
    stripe_id=Column(String(200),nullable=False)
    phone_number=Column(String(30), nullable=False)
    
class ShippingAddresses(Base):
    __tablename__='shipping_addresses'
    
    id=Column(Integer, primary_key=True, index=True)
    user_id=Column(Integer, ForeignKey('users.id'),nullable=False)
    address_line1=Column(String(200),nullable=False)
    address_line2=Column(String(200),nullable=True)
    city=Column(String(50),nullable=False)
    state=Column(String(50),nullable=False)
    country=Column(String(50),nullable=False)
    zip_code=Column(String(50),nullable=False)
    
    
    
    
    

    
    