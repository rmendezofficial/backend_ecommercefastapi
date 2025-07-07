from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text, Float, ForeignKey, Numeric, Enum
from sqlalchemy.sql import func
from database import Base
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum

class EmailStatus(str, PyEnum):
    pending='pending'
    sent='sent'
    failed='failed'
    unsubscribed='unsubscribed'
    
class EmailType(str, PyEnum):
    transactional='transactional'   
    promotional='promotional'
    account='account'
    feedback='feedback'
    system='system'
    
class Emails(Base):
    __tablename__='emails'
    
    id=Column(Integer,primary_key=True,index=True)
    user_id=Column(Integer,ForeignKey('users.id'),nullable=False)
    type=Column(Enum(EmailType),nullable=False)
    status=Column(Enum(EmailStatus),default=EmailStatus.pending,nullable=False)
    created_at=Column(DateTime,server_default=func.now())

    
    
    


