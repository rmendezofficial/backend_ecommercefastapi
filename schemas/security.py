from pydantic import BaseModel
from config import CSRF_SECRET_KEY
from pydantic_settings import BaseSettings

class Token(BaseModel):
    access_token:str
    token_type:str
    
class TokenData(BaseModel):
    username:str|None=None
    
class CsrfSettings(BaseSettings):
    secret_key:str=CSRF_SECRET_KEY
    
