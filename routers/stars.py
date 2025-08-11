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
from models.stars import Stars
from schemas.stars import Star

router=APIRouter(prefix='/stars')


@router.post('/rate_stars',tags=['stars'])
async def rate_stars(
    request:Request,
    user: Annotated[User, Depends(get_current_active_user)],
    csrf_protect:Annotated[CsrfProtect, Depends()],
    x_csrf_token:Annotated[str,Header(...,description='"X-CSRF-Token')],
    session:SessionDB,
    star:Star
    )->JSONResponse:
    await csrf_protect.validate_csrf(request)
    product_db=session.query(Products).filter(Products.id==star.product_id).with_for_update().first()
    if not product_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='The product was not found.')
    existing_order=session.query(
            exists().where(
                Orders.user_id == user.id,
                Orders.status == 'delivered',
                OrderItems.order_id == Orders.id,
                OrderItems.product_id == star.product_id
            )
        ).scalar()
    if not existing_order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='You cannot rate this product because you have not made a delivered order for it.')
    try: #handle case where stars is null
        if product_db.average_stars==None:
            product_db.average_stars=0
            product_db.total_stars=0
            session.flush()
        
        existing_star_db=session.query(Stars).filter(Stars.product_id==star.product_id, Stars.user_id==user.id).first()
        if existing_star_db: #update the rating
            product_db.average_stars=((product_db.average_stars*product_db.total_stars)+(star.stars_number-existing_star_db.stars_number))/product_db.total_stars
            
            existing_star_db.stars_number=star.stars_number
        else:
            product_db.average_stars=((product_db.average_stars*product_db.total_stars)+star.stars_number)/(product_db.total_stars+1)
            product_db.total_stars+=1
            
            new_star_db=Stars(product_id=star.product_id, user_id=user.id, stars_number=star.stars_number)
            session.add(new_star_db)
        
        session.commit()
        return JSONResponse(status_code=status.HTTP_201_CREATED,content={'message':'Product rated successfully.'})
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An error occurred while adding the product to the cart')
    
    
    