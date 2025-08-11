from pydantic import BaseModel, constr, Field
from typing import Annotated,List
from decimal import Decimal
from models.products import ProductStatus
from enum import Enum as PyEnum
from datetime import datetime

    
class Review(BaseModel):
    product_id:int
    review_text:Annotated[str, constr(min_length=1, max_length=1000)]