from pydantic import BaseModel, constr, Field
from typing import Annotated,List
from decimal import Decimal
from models.products import ProductStatus
from enum import Enum as PyEnum
from datetime import datetime

class ProductImages(BaseModel):
    image_url:str
    is_main:bool|None=False

class Product(BaseModel):
    title:Annotated[str,constr(max_length=200)]
    description:str
    price:Annotated[Decimal, Field(gt=0)]
    stock:Annotated[int, Field(ge=0)]
    category:Annotated[str,constr(max_length=50)]
    discount_percentage:Annotated[Decimal, Field(ge=0)]
    weight:Annotated[float|None, Field(ge=0)]=None
    height:Annotated[float|None, Field(ge=0)]=None
    length:Annotated[float|None, Field(ge=0)]=None
    width:Annotated[float|None, Field(ge=0)]=None
    images:List[ProductImages]
    status:ProductStatus
    taxcode:str
    
class ProductUser(BaseModel):
    id:int
    title:Annotated[str,constr(max_length=200)]
    description:str
    price:Annotated[Decimal, Field(gt=0)]
    is_there_stock:bool
    category:Annotated[str,constr(max_length=50)]
    discount_percentage:Annotated[Decimal, Field(ge=0)]
    weight:Annotated[float|None, Field(ge=0)]=None
    height:Annotated[float|None, Field(ge=0)]=None
    length:Annotated[float|None, Field(ge=0)]=None
    width:Annotated[float|None, Field(ge=0)]=None
    images:List[ProductImages]
    status:ProductStatus





class ProductUpdate(BaseModel):
    title:Annotated[str|None,constr(max_length=200)]=None
    description:str|None=None
    price:Annotated[Decimal|None, Field(ge=0)]=None
    stock:int|None=None    
    category:Annotated[str|None,constr(max_length=50)]=None
    discount_percentage:Annotated[Decimal|None, Field(ge=0)]=None
    weight:Annotated[float|None, Field(ge=0)]=None
    height:Annotated[float|None, Field(ge=0)]=None
    length:Annotated[float|None, Field(ge=0)]=None
    width:Annotated[float|None, Field(ge=0)]=None
    images:List[ProductImages]|None=None
    status:ProductStatus|None=None
    taxcode:str|None=None



class ProductsSortBy(str,PyEnum):
    price_asc='price_asc'
    price_desc='price_desc'
    stock_asc='stock_asc'
    stock_desc='stock_desc'
    discount_percentage_asc='discount_percentage_asc'
    discount_percentage_desc='discount_percentage_desc'
    date_asc='date_asc'
    date_desc='date_desc'
    weight_asc='weight_asc'
    weight_desc='weight_desc'
    height_asc='height_asc'
    height_desc='height_desc'
    length_asc='length_asc'
    length_desc='length_desc'
    width_asc='width_asc'
    width_desc='width_desc'

class ProductsInventoryParams(BaseModel):
    query_title:Annotated[str|None,constr(max_length=200)]=None
    category:str|None=None
    status:ProductStatus|None=None
    taxcode:str|None=None
    min_price:float|None=None
    max_price:float|None=None
    min_stock:float|None=None
    max_stock:float|None=None
    min_discount_percentage:float|None=None
    max_discount_percentage:float|None=None
    date_before:datetime|None=None
    date_after:datetime|None=None
    min_weight:float|None=None
    max_weight:float|None=None
    min_height:float|None=None
    max_height:float|None=None
    min_length:float|None=None
    max_length:float|None=None
    min_width:float|None=None
    max_width:float|None=None
    sort_by:ProductsSortBy|None=None
    
    
    
class ProductsSortByUser(str,PyEnum):
    price_asc='price_asc'
    price_desc='price_desc'
    discount_percentage_asc='discount_percentage_asc'
    discount_percentage_desc='discount_percentage_desc'
    weight_asc='weight_asc'
    weight_desc='weight_desc'
    height_asc='height_asc'
    height_desc='height_desc'
    length_asc='length_asc'
    length_desc='length_desc'
    width_asc='width_asc'
    width_desc='width_desc'

class ProductsSearchUser(BaseModel):
    query_title:Annotated[str|None,constr(max_length=200)]=None
    category:str|None=None
    status:ProductStatus|None=None
    min_price:float|None=None
    max_price:float|None=None
    min_discount_percentage:float|None=None
    max_discount_percentage:float|None=None
    min_weight:float|None=None
    max_weight:float|None=None
    min_height:float|None=None
    max_height:float|None=None
    min_length:float|None=None
    max_length:float|None=None
    min_width:float|None=None
    max_width:float|None=None
    sort_by:ProductsSortByUser|None=None
    
    
    
    
    
    




