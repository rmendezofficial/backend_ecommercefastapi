from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text, Float, ForeignKey, Numeric, Enum, CheckConstraint
from sqlalchemy.sql import func
from database import Base
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum

class ProductStatus(str,PyEnum):
    active='active'
    inactive='inactive'
    deleted='deleted'
    discontinued='discontinued'
 
class Products(Base):
    __tablename__='products'
    
    id=Column(Integer,primary_key=True,index=True)
    title=Column(String(200),unique=True, nullable=False) 
    description=Column(Text, nullable=False)
    price=Column(Numeric(10,2), nullable=False)
    stock=Column(Integer, nullable=False)
    category_id=Column(Integer,ForeignKey('categories.id'), nullable=False)
    discount_percentage=Column(Numeric(10,2),nullable=False)
    created_at=Column(DateTime, server_default=func.now())
    weight=Column(Float,nullable=True)
    height=Column(Float,nullable=True)
    length=Column(Float,nullable=True)
    width=Column(Float,nullable=True)
    status=Column(Enum(ProductStatus),default=ProductStatus.active,nullable=False)
    taxcode=Column(String(200),nullable=False)
    reserve_stock=Column(Integer, nullable=False)
    available_stock=Column(Integer, nullable=False)
    
    __table_args__ = (
        CheckConstraint('stock >= 0', name='check_stock_positive'),
        CheckConstraint('reserve_stock >= 0', name='check_reserve_stock_positive'),
        CheckConstraint('available_stock >= 0', name='check_available_stock_positive'),
        CheckConstraint('price >= 0', name='check_price_positive'),
        CheckConstraint('discount_percentage >= 0', name='check_discount_percentage_positive'),
    )
    
class product_images(Base):
    __tablename__='product_images'
    
    id=Column(Integer, primary_key=True, index=True)
    product_id=Column(Integer, ForeignKey('products.id'), nullable=False)
    image_url=Column(Text,nullable=False)
    is_main=Column(Boolean,nullable=False,default=False)
    
  