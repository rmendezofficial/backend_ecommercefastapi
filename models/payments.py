from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text, Float, ForeignKey, Numeric, Enum
from sqlalchemy.sql import func
from database import Base
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum

class PaymentMethod(str, PyEnum):
    paypal='paypal'
    stripe='stripe'
    bank_transfer='bank_transfer'
    
class PaymentStatus(str, PyEnum):
    pending='pending'
    paid='paid'
    failed='failed'
    refunded='refunded'
    cancelled='cancelled'

class Payments(Base):
    __tablename__='payments'
    
    id=Column(Integer,primary_key=True,index=True)
    order_id=Column(Integer,ForeignKey('orders.id'),nullable=False)
    user_id=Column(Integer,ForeignKey('users.id'),nullable=False)
    payment_method=Column(Enum(PaymentMethod),nullable=False)
    status=Column(Enum(PaymentStatus),nullable=False)
    created_at=Column(DateTime,server_default=func.now())
    stripe_session_id=Column(String(200),nullable=False)
    stripe_customer_id=Column(String(200),nullable=False)
    currency=Column(String(200),nullable=False)
    tax_details=Column(Numeric(10,2),nullable=False)
    payment_intent_id=Column(String(200),nullable=False)
    charge_id=Column(String(200),nullable=False)
    receipt_url=Column(Text,nullable=False)

class CheckoutStatus(str, PyEnum):
    expired='expired'
    active='active'    
    cancelled='cancelled'

class CheckOutSessions(Base):
    __tablename__='checkoutsessions'
    
    id=Column(Integer, primary_key=True, index=True)
    user_id=Column(Integer,ForeignKey('users.id'),nullable=False)
    expires_at=Column(DateTime)
    status=Column(Enum(CheckoutStatus), nullable=False)
    session_id=Column(String(200),nullable=False)
    session_url=Column(Text,nullable=False)