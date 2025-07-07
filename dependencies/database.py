from database import SessionLocal
from fastapi import Depends
from typing import Annotated
from sqlalchemy.orm import Session

def get_db():
    db=SessionLocal()
    try:
        yield db
    finally:
        db.close()
        
#DATABASE
SessionDB=Annotated[Session, Depends(get_db)]