from pydantic import BaseModel, constr, Field
from typing import Annotated
from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum

    

class CategoryInventoryParams(BaseModel):
    title:Annotated[str|None,constr(max_length=50)]=None
