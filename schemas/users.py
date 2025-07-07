from pydantic import BaseModel, EmailStr, constr, field_validator
from typing import Annotated
import re

class UserSignUp(BaseModel):
    username:Annotated[str, constr(min_length=3, max_length=50)]
    password:Annotated[str,constr(min_length=8,max_length=200)]
    email:Annotated[EmailStr, constr(min_length=3,max_length=100)]
    name:Annotated[str,constr(min_length=2,max_length=50)]
    lastname:Annotated[str,constr(min_length=2,max_length=50)]
    phone_number:Annotated[str,constr(min_length=2, max_length=30)]
    phone_number_region:Annotated[str,constr(min_length=2, max_length=30)]
    
    
class User(BaseModel):
    id:int
    username:Annotated[str, constr(min_length=3, max_length=50)]
    email:Annotated[EmailStr, constr(min_length=3,max_length=100)]
    name:Annotated[str,constr(min_length=2,max_length=50)]
    lastname:Annotated[str,constr(min_length=2,max_length=50)]
    disabled:bool|None=False
    verified:bool|None=False
    role:str|None='user'
    stripe_id:str
    phone_number:Annotated[str,constr(min_length=2, max_length=30)]
    
class UserDB(User):
    hashed_password:str
    
    
@field_validator('password')
def password_complexity(cls, v):
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        return v

    
