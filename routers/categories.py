from fastapi import APIRouter, Request, Depends, Header, HTTPException, status
from schemas.categories import CategoryInventoryParams
from models.categories import Categories
from typing import Annotated
from fastapi.responses import JSONResponse
from routers.users import is_admin
from fastapi_csrf_protect import CsrfProtect
from dependencies.database import SessionDB
from sqlalchemy.exc import SQLAlchemyError



router=APIRouter(prefix='/categories_admin')


@router.post('/get_categories_admins',tags=['categories_admins'])
async def get_categories_admins(
    request:Request,
    admin: Annotated[bool, Depends(is_admin)],
    csrf_protect:Annotated[CsrfProtect, Depends()],
    x_csrf_token:Annotated[str,Header(...,description='"X-CSRF-Token')],
    session:SessionDB,
    categories_params: CategoryInventoryParams,
    page:int|None=1,
    limit:int|None=10,
    )->JSONResponse:
    await csrf_protect.validate_csrf(request)
    if not admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail='Not enough permissions')
    try:
        query=session.query(Categories)
        
        categories_found=[]
     
        if categories_params.title:
            query=query.filter(Categories.title.ilike(f"%{categories_params.title}%"))
            
        
        offset=(page-1)*limit
        query=query.offset(offset).limit(limit)    
        
        categories=query.all()
        for category in categories:
            category_object={
                'id':category.id,
                'title':category.title
            }
            categories_found.append(category_object)
                
        return JSONResponse(status_code=status.HTTP_200_OK,content={'categories':categories_found, 'page':page,'limit':limit})
    except SQLAlchemyError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail='An error occurred while getting the categories.')
