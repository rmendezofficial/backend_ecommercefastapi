from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text, Float, ForeignKey, Numeric, Enum
from sqlalchemy.sql import func
from database import Base
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum

class NotificationType(str, PyEnum):
    order_confirmation = "order_confirmation"
    shipping_update = "shipping_update"
    payment_received = "payment_received"
    promotion = "promotion"
    account_alert = "account_alert"
    review_request = "review_request"
    cart_reminder = "cart_reminder"    

class Notifications(Base):
    __tablename__='notifications'
    
    id=Column(Integer, primary_key=True, index=True)
    user_id=Column(Integer,ForeignKey('users.id'),nullable=False)
    message=Column(Text,nullable=False)
    type=Column(Enum(NotificationType),nullable=False)
    created_at=Column(DateTime,server_default=func.now())
    
    