from pydantic import BaseModel, constr, Field
from typing import Annotated,List
from decimal import Decimal
from models.products import ProductStatus
from enum import Enum as PyEnum
from datetime import datetime

    
class Star(BaseModel):
    product_id:int
    stars_number:Annotated[int,Field(ge=1,le=5)]