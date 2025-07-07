from enum import Enum as PyEnum 
from pydantic import BaseModel

class OrderStatus(str, PyEnum):
    shipped = "shipped"
    delivered = "delivered"
    cancelled = "cancelled"
    refunded='refunded'
    returned='returned'
    
class OrderStatusRequest(BaseModel):
    order_status:OrderStatus