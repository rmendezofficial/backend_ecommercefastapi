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
from models.orders import Orders, OrderItems, OrderStatus
from models.users import ShippingAddresses, Users
import pytz 
from sqlalchemy import update, select, delete, exists
from models.reviews import Reviews
from schemas.reviews import Review

router=APIRouter(prefix='/reviews')


@router.post('/add_review',tags=['reviews'])
async def add_review(
    request:Request,
    user: Annotated[User, Depends(get_current_active_user)],
    csrf_protect:Annotated[CsrfProtect, Depends()],
    x_csrf_token:Annotated[str,Header(...,description='"X-CSRF-Token')],
    session:SessionDB,
    review:Review
    )->JSONResponse:
    await csrf_protect.validate_csrf(request)
    product_db=session.query(Products).filter(Products.id==review.product_id).with_for_update().first()
    if not product_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='The product was not found.')
    existing_order=session.query(
            exists().where(
                Orders.user_id == user.id,
                Orders.status == 'delivered',
                OrderItems.order_id == Orders.id,
                OrderItems.product_id == review.product_id
            )
        ).scalar()
    if not existing_order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='You cannot add a review to this product because you have not made a delivered order for it.')
    try: #handle case where stars is null
        
        existing_review_db=session.query(Reviews).filter(Reviews.product_id==review.product_id, Reviews.user_id==user.id).first()
        if existing_review_db: #update the rating
            existing_review_db.review_text=review.review_text
            existing_review_db.edited=True
            
        else:
            new_review_db=Reviews(product_id=review.product_id, user_id=user.id, review_text=review.review_text, edited=False)
            session.add(new_review_db)
        session.commit()
        return JSONResponse(status_code=status.HTTP_201_CREATED,content={'message':'Review added to product successfully successfully.'})
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An error occurred while adding the review to the product.')
    
@router.delete('/remove_review/{product_id}', tags=['reviews'])
async def remove_review(
    request:Request,
    user: Annotated[User, Depends(get_current_active_user)],
    csrf_protect:Annotated[CsrfProtect, Depends()],
    x_csrf_token:Annotated[str,Header(...,description='"X-CSRF-Token')],
    session:SessionDB,
    product_id:int
    )->JSONResponse:
    await csrf_protect.validate_csrf(request)
    product_db=session.query(Products).filter(Products.id==product_id).with_for_update().first()
    if not product_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='The product was not found.')
    existing_order=session.query(
            exists().where(
                Orders.user_id == user.id,
                Orders.status == 'delivered',
                OrderItems.order_id == Orders.id,
                OrderItems.product_id == product_id
            )
        ).scalar()
    if not existing_order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='You cannot add a review to this product because you have not made a delivered order for it.')
    existing_review_db=session.query(Reviews).filter(Reviews.product_id==product_id, Reviews.user_id==user.id).first()
    if not existing_review_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='The review was not found.')
    try:
        session.delete(existing_review_db)
        session.commit()
        return JSONResponse(status_code=status.HTTP_200_OK, content={'message':'The review was successfully removed from the product.'})
        
    except SQLAlchemyError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An error occurred while removing the review from the product.')