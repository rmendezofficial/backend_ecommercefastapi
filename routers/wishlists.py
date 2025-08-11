from fastapi import APIRouter, HTTPException,status, Request, Depends, Header
from fastapi.responses import JSONResponse
from typing import Annotated
from dependencies.database import SessionDB
from fastapi_csrf_protect import CsrfProtect
from routers.users import get_current_active_user, is_admin
from schemas.users import User
from models.products import Products, product_images
from sqlalchemy.exc import SQLAlchemyError
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta, timezone
from models.users import ShippingAddresses, Users
import pytz 
from sqlalchemy import update, select, delete, exists
from models.wishlists import Wishlist
from models.categories import Categories
from routers.products import get_stock, get_or_create_category

router=APIRouter(prefix='/wishlists')


@router.post('/add_wishlist',tags=['wishlists'])
async def add_wishlist(
    request:Request,
    user: Annotated[User, Depends(get_current_active_user)],
    csrf_protect:Annotated[CsrfProtect, Depends()],
    x_csrf_token:Annotated[str,Header(...,description='"X-CSRF-Token')],
    session:SessionDB,
    product_id:int,
    )->JSONResponse:
    await csrf_protect.validate_csrf(request)
    product_db=session.query(Products).filter(Products.id==product_id).first()
    if not product_db: 
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='The product was not found.')
    existing_wishlist_db=session.query(Wishlist).filter(Wishlist.product_id==product_id, Wishlist.user_id==user.id).first()
    if existing_wishlist_db:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='The product is already in your wishlist.')
    try: 
        new_wishlist_db=Wishlist(product_id=product_id, user_id=user.id)
        session.add(new_wishlist_db)
        session.commit()
        return JSONResponse(status_code=status.HTTP_201_CREATED,content={'message':'Product successfully added to your wishlist.'})
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An error occurred while adding the product to your wishlist.')
    
@router.delete('/delete_wishlist/{product_id}', tags=['wishlists'])
async def delete_wishlist(
    request:Request,
    user: Annotated[User, Depends(get_current_active_user)],
    csrf_protect:Annotated[CsrfProtect, Depends()],
    x_csrf_token:Annotated[str,Header(...,description='"X-CSRF-Token')],
    session:SessionDB,
    product_id:int,
)->JSONResponse: 
    await csrf_protect.validate_csrf(request)
    product_db=session.query(Products).filter(Products.id==product_id).first()
    if not product_db: 
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='The product was not found.')
    existing_wishlist_db=session.query(Wishlist).filter(Wishlist.product_id==product_id, Wishlist.user_id==user.id).first()
    if not existing_wishlist_db:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='The product is not in your wishlist.')
    try:
        session.delete(existing_wishlist_db)
        session.commit()
        return JSONResponse(status_code=status.HTTP_200_OK, content={'message':'Product successfully removed from your wishlist.'})
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An error occurred while removing the product from your wishlist.')
    
