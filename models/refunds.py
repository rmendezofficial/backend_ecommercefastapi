from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text, Float, ForeignKey, Numeric, Enum, CheckConstraint
from sqlalchemy.sql import func
from database import Base
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum

class RefundStatus(str,PyEnum):
    pending = "pending"
    pending_accidental = "pending_accidental"
    cancelled = "cancelled"
    failed = "failed"
    refunded = "refunded"
    returned = "returned"

class Refunds(Base):
    __tablename__='refunds'
    
    id=Column(Integer,primary_key=True,index=True)
    user_id=Column(Integer,ForeignKey('users.id'),nullable=False)
    payment_intent_id=Column(Text, nullable=False)
    created_at=Column(DateTime,server_default=func.now())
    checkout_session_id=Column(Integer,ForeignKey('checkoutsessions.id'),nullable=False)
    status=Column(Enum(RefundStatus), default=RefundStatus.pending_accidental, nullable=False)