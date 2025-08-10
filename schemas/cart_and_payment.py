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
        
    
class CartSortBy(str,PyEnum):
    units_asc='units_asc'
    units_desc='units_desc'
    date_asc='date_asc'
    date_desc='date_desc'

class CartInventoryParams(BaseModel):
    product_id:int|None=None
    user_id:int|None=None
    min_units:int|None=None
    max_units:int|None=None
    date_before:datetime|None=None
    date_after:datetime|None=None
    sort_by:CartSortBy|None=None
    
        
class CartSnapshootSortBy(str,PyEnum):
    units_asc='units_asc'
    units_desc='units_desc'
    date_asc='date_asc'
    date_desc='date_desc'
    price_at_purchase_asc='price_at_purchase_asc'
    price_at_purchase_desc='price_at_purchase_desc'

class CartSnapshootInventoryParams(BaseModel):
    product_id:int|None=None
    user_id:int|None=None
    min_units:int|None=None
    max_units:int|None=None
    date_before:datetime|None=None
    date_after:datetime|None=None
    checkout_session_id:int|None=None
    min_price_at_purchase:float|None=None
    max_price_at_purchase:float|None=None
    sort_by:CartSnapshootSortBy|None=None