from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text, Float, ForeignKey, Numeric, Enum
from sqlalchemy.sql import func
from database import Base
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum

class OrderStatus(str,PyEnum):
    pending = "pending"
    paid = "paid"
    processing = "processing"
    shipped = "shipped"
    delivered = "delivered"
    cancelled = "cancelled"
    failed = "failed"
    refunded = "refunded"
    returned = "returned"

class Orders(Base):
    __tablename__='orders'
    
    id=Column(Integer,primary_key=True,index=True)
    user_id=Column(Integer,ForeignKey('users.id'),nullable=False)
    total_amount=Column(Numeric(10,2),nullable=False)
    created_at=Column(DateTime,server_default=func.now())
    status=Column(Enum(OrderStatus), default=OrderStatus.pending,index=True, nullable=False)
    shipping_addresses_id=Column(Integer,ForeignKey('shipping_addresses.id'),nullable=False)
    stripe_session_id=Column(String(200),nullable=False)
    stripe_customer_id=Column(String(200),nullable=False)
    currency=Column(String(200),nullable=False)
    tax_details=Column(Numeric(10,2),nullable=False)
    payment_intent_id=Column(String(200),nullable=False)
    charge_id=Column(String(200),nullable=False)
    receipt_url=Column(Text,nullable=False)
    
class OrderItems(Base):
    __tablename__='order_items'
    
    id=Column(Integer,primary_key=True, index=True)
    order_id=Column(Integer,ForeignKey('orders.id'),nullable=False)
    product_id=Column(Integer,ForeignKey('products.id'),nullable=False)
    units=Column(Integer, nullable=False)
    price_at_purchase=Column(Numeric(10,2),nullable=False)
    
  

   