from pydantic import BaseModel, constr, Field
from typing import Annotated
from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum

class ProductStatusCart(str,PyEnum):
    active='active'

class CartProduct(BaseModel):
    product_id:Annotated[int,Field(gt=0)]
    units:Annotated[int,Field(gt=0)]
    
class CartProductCheckout(BaseModel):
    cart_product_id:int
    id:int
    title:Annotated[str,constr(max_length=200)]
    description:str
    price:Annotated[Decimal, Field(gt=0)]
    stock:Annotated[int, Field(gt=0)]
    category:Annotated[str,constr(max_length=50)]
    discount_percentage:Annotated[Decimal, Field(ge=0)]
    status:ProductStatusCart
    units:Annotated[int, Field(gt=0)]
    taxcode:str
    
class CartProductsCheckout(BaseModel):
    products:list[CartProductCheckout]
        
    
    