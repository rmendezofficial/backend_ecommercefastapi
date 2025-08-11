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

def in_wishlist(session:SessionDB, user_id:int, product_id:int):
    wishlist_product_db=session.query(Wishlist).filter(Wishlist.product_id==product_id, Wishlist.user_id==user_id).first()
    if wishlist_product_db:
        return True
    return False

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
    
@router.get('/get_my_wishlist/', tags=['wishlists'])
async def get_my_wishlist(
    request:Request,
    user: Annotated[User, Depends(get_current_active_user)],
    session:SessionDB,
    page:int|None=1,
    limit:int|None=10
)->JSONResponse:
    try:
        products_found=[]
        
        offset=(page-1)*limit
        wishlist_products_db=session.query(Wishlist).filter(Wishlist.user_id==user.id).offset(offset).limit(limit).all()
        for wishlist_product in wishlist_products_db:
            product_db=session.query(Products).filter(Products.id==wishlist_product.product_id).first()
            is_stock=get_stock(product_db)
            product_category_db=session.query(Categories).filter(Categories.id==product_db.category_id).first()
            product_images_db=session.query(product_images).filter(product_images.product_id==product_db.id).all()
            product_images_list=[]
            for image_db in product_images_db:
                image_db_dict={
                    'id':image_db.id,
                    'product_id':image_db.product_id,
                    'image_url':image_db.image_url,
                    'is_main':image_db.is_main
                }
                product_images_list.append(image_db_dict)
            product_response={
                'id':product_db.id,
                'title':product_db.title,
                'description':product_db.description,
                'price':str(product_db.price) if product_db.price is not None else None,
                'is_there_stock':is_stock,
                'category':product_category_db.title,
                'discount_percentage':str(product_db.discount_percentage) if product_db.price is not None else None,
                'weight':float(product_db.weight) if product_db.price is not None else None,
                'height':float(product_db.height) if product_db.price is not None else None,
                'length':float(product_db.length) if product_db.price is not None else None,
                'width':float(product_db.width) if product_db.price is not None else None,
                'status':product_db.status,
                'images':product_images_list,
                'average_stars':product_db.average_stars,
                'total_stars':product_db.total_stars
            }
            products_found.append(product_response)
        return JSONResponse(status_code=status.HTTP_200_OK, content={'message':'Products from wishlist successfully found', 'products':products_found})
            
    except SQLAlchemyError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An error occurred when getting the products from your wishlist.')