from fastapi import APIRouter, Request, Depends, Header, HTTPException, status
from typing import Annotated
from fastapi.responses import JSONResponse
from routers.users import is_admin
from fastapi_csrf_protect import CsrfProtect
from dependencies.database import SessionDB
from models.orders import Orders
from sqlalchemy.exc import SQLAlchemyError
from schemas.orders import OrderStatusRequest

router=APIRouter(prefix='/orders_admin')

@router.patch('/update_order_status/{order_id}',tags=['orders_admin'])
async def update_order_status(
    request:Request,
    admin: Annotated[bool, Depends(is_admin)],
    csrf_protect:Annotated[CsrfProtect, Depends()],
    x_csrf_token:Annotated[str,Header(...,description='"X-CSRF-Token')],
    order_id:int,
    session:SessionDB,
    order_status:OrderStatusRequest
)->JSONResponse:
    await csrf_protect.validate_csrf(request)
    if not admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail='Not enough permissions')
    order_db=session.query(Orders).filter(Orders.id==order_id).first()
    if not order_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='The order does not exist')
    try:
        order_db.status=order_status
        session.commit()
        session.refresh(order_db)
        return JSONResponse(status_code=status.HTTP_200_OK, content={'message':f'Order status successfully updated to {order_db.status}'})
    except SQLAlchemyError as e:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f'An error occurred while updating the order: {e}')
        
        
    