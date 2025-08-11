from fastapi import APIRouter, Depends, Request, Header, HTTPException,status
from fastapi.responses import JSONResponse
from typing import Annotated
from routers.users import is_admin, get_current_active_user_custom, get_current_active_user
from fastapi_csrf_protect import CsrfProtect
from fastapi_csrf_protect.exceptions import CsrfProtectError
from models.products import Products, product_images
from models.categories import Categories
from schemas.products import Product, ProductImages, ProductUser, ProductUpdate, ProductsInventoryParams, ProductsSortBy, ProductsSortByUser,ProductsSearchUser
from dependencies.database import SessionDB
from sqlalchemy.exc import SQLAlchemyError
from models.reservations import Reservations
from models.wishlists import Wishlist
from schemas.users import User


router=APIRouter(prefix='/products')

def in_wishlist(session:SessionDB, user_id:int, product_id:int):
    wishlist_product_db=session.query(Wishlist).filter(Wishlist.product_id==product_id, Wishlist.user_id==user_id).first()
    if wishlist_product_db:
        return True
    return False

def get_or_create_category(session:SessionDB, category_name:str):
    try:
        existing_category=session.query(Categories).filter(Categories.title==category_name).first()
        if existing_category:
            return existing_category.id
        category_db=Categories(title=category_name)
        session.add(category_db)
        session.commit()
        session.refresh(category_db)
        return category_db.id
    except SQLAlchemyError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail='An error occurred while getting the category')

def get_stock(product_db):
    try:
        return product_db.available_stock>0
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An error occurred while getting the stock')

#ADMINS
@router.post('/create_product',tags=['products_admins'])
async def create_product(
    request:Request,
    admin: Annotated[bool, Depends(is_admin)],
    csrf_protect:Annotated[CsrfProtect, Depends()],
    x_csrf_token:Annotated[str,Header(...,description='"X-CSRF-Token')],
    product:Product,
    session:SessionDB
    )->JSONResponse:
    await csrf_protect.validate_csrf(request)
    if not admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail='Not enough permissions')
    existing_product=session.query(Products).filter(Products.title==product.title).first()
    if existing_product:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,detail='Product with this title already exists')
    counter=0
    for image in product.images:
        if image.is_main==True:
            counter+=1
    if counter!=1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail='Only one image can be the main')
    try:
        
        category_id=get_or_create_category(session, product.category)
        
        product_db=Products(title=product.title,description=product.description,price=product.price,stock=product.stock,category_id=category_id,discount_percentage=product.discount_percentage,weight=product.weight,height=product.height,length=product.length,width=product.width,status='active',taxcode=product.taxcode,reserve_stock=0,available_stock=product.stock, average_stars=0, total_stars=0)
        session.add(product_db)
        session.commit()
        session.refresh(product_db)
        for image in product.images:
            image_db=product_images(image_url=image.image_url,is_main=image.is_main,product_id=product_db.id)
            session.add(image_db)
        session.commit()
        return JSONResponse(status_code=status.HTTP_201_CREATED,content={'message':'Product created'})
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while saving the product.")
    
@router.patch('/update_product/{product_id}',tags=['products_admins'])
async def update_product(
    request:Request,
    admin: Annotated[bool, Depends(is_admin)],
    csrf_protect:Annotated[CsrfProtect, Depends()],
    x_csrf_token:Annotated[str,Header(...,description='"X-CSRF-Token')],
    product_id:int,
    product:ProductUpdate,
    session:SessionDB
)->JSONResponse:
    await csrf_protect.validate_csrf(request)
    if not admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail='Not enough permissions')
    existing_product=session.query(Products).filter(Products.id==product_id).first()
    if not existing_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail='Product does not exist')
    #existing_reservation=session.query(Reservations).filter(Reservations.product_id==product_id).first()
    #if existing_reservation:
    #    raise HTTPException(status_code=status.HTTP_409_CONFLICT,detail='Product cannot be modified because there are reservations of the product')
    try: 
        product_dict=product.model_dump(exclude_unset=True)
        
        
        
        for key, value in product_dict.items():   
            if key=='images':
                counter=0
                for product_image in product_dict['images']:
                    if product_image['is_main']==True:
                        counter+=1
                if counter!=1:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail='Only one image can be the main')
                existing_images=session.query(product_images).filter(product_images.product_id==product_id).all()
                for image in existing_images:
                    session.delete(image)
                for product_image in product_dict['images']:
                    new_image=product_images(product_id=product_id,image_url=product_image['image_url'],is_main=product_image['is_main'])
                    session.add(new_image)
                    
            elif key=='category':
                    category_id=get_or_create_category(session,value)
                    setattr(existing_product,'category_id',category_id)         
            elif key=='stock':
                    existing_product.stock+=value
                    existing_product.available_stock+=value
            else:
                    setattr(existing_product, key, value)
        session.commit()
        session.refresh(existing_product)
        existing_images_final=session.query(product_images).filter(product_images.product_id==product_id).all()
        existing_images_list=[]
        for existing_image in existing_images_final:
            image_dict={'image_id':existing_image.id,'image_url':existing_image.image_url,'is_main':existing_image.is_main}
            existing_images_list.append(image_dict)
        existing_product_category=session.query(Categories).filter(Categories.id==existing_product.category_id).first()
        product_updated={
            'id':existing_product.id,
            'title':existing_product.title,
            'description':existing_product.description,
            'price':str(existing_product.price),
            'stock':existing_product.stock,
            'reserve_stock': existing_product.reserve_stock,
            'available_stock':existing_product.available_stock,
            'category':existing_product_category.title,
            'discount_percentage':str(existing_product.discount_percentage),
            'created_at':existing_product.created_at.isoformat(),
            'weight':float(existing_product.weight) if existing_product.weight is not None else None,
            'height':float(existing_product.height) if existing_product.height is not None else None,
            'length':float(existing_product.length) if existing_product.length is not None else None,
            'width':float(existing_product.width) if existing_product.width is not None else None,
            'images':existing_images_list,
            'status':existing_product.status,
            'taxcode':existing_product.taxcode,
            'average_stars':existing_product.average_stars,
            'total_stars':existing_product.total_stars
            
        }
        return JSONResponse(status_code=status.HTTP_200_OK,content={'message':'Product successfully updated', 'updated_product':product_updated})
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while updating the product.")
    
@router.delete('/delete_product/{product_id}',tags=['products_admins'])
async def delete_product(
    request:Request,
    admin: Annotated[bool, Depends(is_admin)],
    csrf_protect:Annotated[CsrfProtect, Depends()],
    x_csrf_token:Annotated[str,Header(...,description='"X-CSRF-Token')],
    product_id:int,
    session:SessionDB
    )->JSONResponse:    
    await csrf_protect.validate_csrf(request)
    if not admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail='Not enough permissions')
    existing_product=session.query(Products).filter(Products.id==product_id).first()
    if not existing_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail='Product does not exist')
    #existing_reservation=session.query(Reservations).filter(Reservations.product_id==product_id).first()
    #if existing_reservation:
    #    raise HTTPException(status_code=status.HTTP_409_CONFLICT,detail='Product cannot be modified because there are reservations of the product')
    try:
        existing_product.status='deleted'
        session.commit()
        return JSONResponse(status_code=status.HTTP_200_OK, content={'message':'Product successfully deleted'})
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while deleting the product.")
  
      
@router.post('/get_products_admins',tags=['products_admins'])
async def get_products_admins(
    request:Request,
    admin: Annotated[bool, Depends(is_admin)],
    csrf_protect:Annotated[CsrfProtect, Depends()],
    x_csrf_token:Annotated[str,Header(...,description='"X-CSRF-Token')],
    session:SessionDB,
    products_params: ProductsInventoryParams,
    page:int|None=1,
    limit:int|None=10,
    )->JSONResponse:
    await csrf_protect.validate_csrf(request)
    if not admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail='Not enough permissions')
    try:
        query=session.query(Products)
        
        products_found=[]
        
        if products_params.query_title:
            query=query.filter(Products.title.ilike(f"%{products_params.query_title}%"))
            
        if products_params.category:
            category=session.query(Categories).filter(Categories.title==products_params.category).first()
            if not category:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='The category does not exist')
            query=query.filter(Products.category_id==category.id)
                
        
        if products_params.status:
            query=query.filter(Products.status==products_params.status)
            
        if products_params.taxcode:
            query=query.filter(Products.taxcode==products_params.taxcode)
            
        if products_params.min_price is not None:
            query=query.filter(Products.price>=products_params.min_price)
            
        if products_params.max_price is not None:
            query=query.filter(Products.price<=products_params.max_price)
        
        if products_params.min_stock is not None:
            query=query.filter(Products.stock>=products_params.min_stock)
            
        if products_params.max_stock is not None:
            query=query.filter(Products.stock<=products_params.max_stock)
            
        if products_params.min_discount_percentage is not None:
            query=query.filter(Products.discount_percentage>=products_params.min_discount_percentage)
            
        if products_params.max_discount_percentage is not None:
            query=query.filter(Products.discount_percentage<=products_params.max_discount_percentage)
            
        if products_params.date_after is not None:
            query=query.filter(Products.created_at>=products_params.date_after)
            
        if products_params.date_before is not None:
            query=query.filter(Products.created_at<=products_params.date_before)
            
        if products_params.min_weight is not None:
            query=query.filter(Products.weight>=products_params.min_weight)
            
        if products_params.max_weight is not None:
            query=query.filter(Products.weight<=products_params.max_weight)
            
        if products_params.min_height is not None:
            query=query.filter(Products.height>=products_params.min_height)
            
        if products_params.max_height is not None:
            query=query.filter(Products.height<=products_params.max_height)
            
        if products_params.min_length is not None:
            query=query.filter(Products.length>=products_params.min_length)
            
        if products_params.max_length is not None:
            query=query.filter(Products.length<=products_params.max_length)
            
        if products_params.min_width is not None:
            query=query.filter(Products.width>=products_params.min_width)
            
        if products_params.max_width is not None:
            query=query.filter(Products.width<=products_params.max_width)
            
        if products_params.min_average_stars is not None:
            query=query.filter(Products.average_stars>=products_params.min_average_stars)
            
        if products_params.max_average_stars is not None:
            query=query.filter(Products.average_stars<=products_params.max_average_stars)
            
        if products_params.min_total_stars is not None:
            query=query.filter(Products.total_stars>=products_params.min_total_stars)
            
        if products_params.max_total_stars is not None:
            query=query.filter(Products.total_stars<=products_params.max_total_stars)
            
        if products_params.sort_by==ProductsSortBy.price_asc:
            query=query.order_by(Products.price.asc())
            
        elif products_params.sort_by==ProductsSortBy.price_desc:
            query=query.order_by(Products.price.desc())
            
        elif products_params.sort_by==ProductsSortBy.stock_asc:
            query=query.order_by(Products.stock.asc())
            
        elif products_params.sort_by==ProductsSortBy.stock_desc:
            query=query.order_by(Products.stock.desc())
            
        elif products_params.sort_by==ProductsSortBy.discount_percentage_asc:
            query=query.order_by(Products.discount_percentage.asc())
            
        elif products_params.sort_by==ProductsSortBy.discount_percentage_desc:
            query=query.order_by(Products.discount_percentage.desc())
        
        elif products_params.sort_by==ProductsSortBy.date_asc:
            query=query.order_by(Products.created_at.asc())
            
        elif products_params.sort_by==ProductsSortBy.date_desc:
            query=query.order_by(Products.created_at.desc())  
        
        elif products_params.sort_by==ProductsSortBy.weight_asc:
            query=query.order_by(Products.weight.asc())
            
        elif products_params.sort_by==ProductsSortBy.weight_desc:
            query=query.order_by(Products.weight.desc())  
            
        elif products_params.sort_by==ProductsSortBy.height_asc:
            query=query.order_by(Products.height.asc())
            
        elif products_params.sort_by==ProductsSortBy.height_desc:
            query=query.order_by(Products.height.desc())  
            
        elif products_params.sort_by==ProductsSortBy.length_asc:
            query=query.order_by(Products.length.asc())
            
        elif products_params.sort_by==ProductsSortBy.length_desc:
            query=query.order_by(Products.length.desc())
            
        elif products_params.sort_by==ProductsSortBy.width_asc:
            query=query.order_by(Products.width.asc())
            
        elif products_params.sort_by==ProductsSortBy.width_desc:
            query=query.order_by(Products.width.desc())
            
        elif products_params.sort_by==ProductsSortBy.average_stars_asc:
            query=query.order_by(Products.average_stars.asc())
            
        elif products_params.sort_by==ProductsSortBy.average_stars_desc:
            query=query.order_by(Products.average_stars.desc())
            
        elif products_params.sort_by==ProductsSortBy.total_stars_asc:
            query=query.order_by(Products.total_stars.asc())
            
        elif products_params.sort_by==ProductsSortBy.total_stars_desc:
            query=query.order_by(Products.total_stars.desc())
            
        offset=(page-1)*limit
        query=query.offset(offset).limit(limit)    
        
        products=query.all()
        
        for product in products:
            
                category_db=session.query(Categories).filter(Categories.id==product.category_id).first()
            
                product_found={
                    'id':product.id,
                    'title':product.title,
                    'description':product.description,
                    'price':str(product.price) if product.price is not None else None,
                    'stock':product.stock,
                    'reserve_stock': product.reserve_stock,
                    'available_stock':product.available_stock,
                    'category':category_db.title,
                    'discount_percentage':str(product.discount_percentage) if product.discount_percentage is not None else None,
                    'created_at':product.created_at.isoformat(),
                    'weight':float(product.weight) if product.weight is not None else None,
                    'height':float(product.height) if product.height is not None else None,
                    'length':float(product.length) if product.length is not None else None,
                    'width':float(product.width) if product.width is not None else None,
                    'status':product.status,
                    'taxcode':product.taxcode,
                    'average_stars':product.average_stars,
                    'total_stars':product.total_stars
                    }
                products_found.append(product_found)
                
        return JSONResponse(status_code=status.HTTP_200_OK,content={'products':products_found, 'page':page,'limit':limit})
    except SQLAlchemyError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail='An error occurred while getting the products.')
        
#admin 
#get product(with images and everything about the product)
@router.get('/get_product_admins/{product_id}',tags=['products_admins'])
async def get_product_admins(
    request:Request,
    admin: Annotated[bool, Depends(is_admin)],
    csrf_protect:Annotated[CsrfProtect, Depends()],
    x_csrf_token:Annotated[str,Header(...,description='"X-CSRF-Token')],
    session:SessionDB,
    product_id:int
    )->JSONResponse:
    await csrf_protect.validate_csrf(request)
    if not admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail='Not enough permissions')
    existing_product=session.query(Products).filter(Products.id==product_id).first()
    if not existing_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail='Product does not exist')
    try:
        product_db=session.query(Products).filter(Products.id==product_id).first()
        product_category_db=session.query(Categories).filter(Categories.id==product_db.category_id).first()
        product_images_db=session.query(product_images).filter(product_images.product_id==product_id).all()
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
            'stock':product_db.stock,
            'category':product_category_db.title,
            'discount_percentage':str(product_db.discount_percentage) if product_db.price is not None else None,
            'created_at':product_db.created_at.isoformat(),
            'weight':float(product_db.weight) if product_db.price is not None else None,
            'height':float(product_db.height) if product_db.price is not None else None,
            'length':float(product_db.length) if product_db.price is not None else None,
            'width':float(product_db.width) if product_db.price is not None else None,
            'status':product_db.status,
            'images':product_images_list,
            'taxcode':product_db.taxcode,
            'average_stars':product_db.average_stars,
            'total_stars':product_db.total_stars
        }
        return JSONResponse(status_code=status.HTTP_200_OK, content={'product':product_response})
    except SQLAlchemyError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An error occurred while getting the product')






#USERS 
@router.get('/get_products',tags=['products'])
async def get_products(
    request:Request,
    session:SessionDB,
    page:int|None=1,
    limit:int|None=10,
    )->JSONResponse:
    try:
        offset=(page-1)*limit
        products_db=session.query(Products).filter(Products.status!='deleted').order_by(Products.created_at.desc()).offset(offset).limit(limit).all()
        products_response=[]
        for product_db in products_db:
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
            products_response.append(product_response)
                
        return JSONResponse(status_code=status.HTTP_200_OK, content={'products':products_response})
    except SQLAlchemyError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An error ocurred while getting the products')

@router.get('/get_product/{product_id}',tags=['products'])
async def get_product(
    user:Annotated[User, Depends(get_current_active_user_custom)],
    request:Request,
    session:SessionDB,
    product_id:int
    )->JSONResponse:
    existing_product=session.query(Products).filter(Products.id==product_id,Products.status!='deleted').first()
    if not existing_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail='Product does not exist')
    try:
        product_in_wishlist=None
        if user:
            product_in_wishlist=in_wishlist(session, user.id, product_id)
        
        is_stock=get_stock(existing_product)
        product_category_db=session.query(Categories).filter(Categories.id==existing_product.category_id).first()
        product_images_db=session.query(product_images).filter(product_images.product_id==product_id).all()
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
            'id':existing_product.id,
            'title':existing_product.title,
            'description':existing_product.description,
            'price':str(existing_product.price) if existing_product.price is not None else None,
            'is_there_stock':is_stock,
            'category':product_category_db.title,
            'discount_percentage':str(existing_product.discount_percentage) if existing_product.price is not None else None,
            'weight':float(existing_product.weight) if existing_product.price is not None else None,
            'height':float(existing_product.height) if existing_product.price is not None else None,
            'length':float(existing_product.length) if existing_product.price is not None else None,
            'width':float(existing_product.width) if existing_product.price is not None else None,
            'status':existing_product.status,
            'images':product_images_list,
            'average_stars':existing_product.average_stars,
            'total_stars':existing_product.total_stars,
            'in_wishlist':product_in_wishlist
        }
        return JSONResponse(status_code=status.HTTP_200_OK, content={'product':product_response})
    except SQLAlchemyError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An error occurred while getting the product')

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


@router.post('/get_products_search',tags=['products'])
async def get_products_search(
    request:Request,
    session:SessionDB,
    products_params: ProductsSearchUser,
    page:int|None=1,
    limit:int|None=10,
    )->JSONResponse:
    try:
        query=session.query(Products)
        
        products_found=[]
        
        if products_params.query_title:
            query=query.filter(Products.title.ilike(f"%{products_params.query_title}%"))
            
        if products_params.category:
            category=session.query(Categories).filter(Categories.title==products_params.category).first()
            if not category:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='The category does not exist')
            query=query.filter(Products.category_id==category.id)
            
        if products_params.status:
            if products_params.status=='deleted':
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='The status does not exist')
            query=query.filter(Products.status==products_params.status)
        query=query.filter(Products.status!='deleted')
            
        if products_params.min_price is not None:
            query=query.filter(Products.price>=products_params.min_price)
            
        if products_params.max_price is not None:
            query=query.filter(Products.price<=products_params.max_price)
        
        if products_params.min_discount_percentage is not None:
            query=query.filter(Products.discount_percentage>=products_params.min_discount_percentage)
            
        if products_params.max_discount_percentage is not None:
            query=query.filter(Products.discount_percentage<=products_params.max_discount_percentage)
            
        if products_params.min_weight is not None:
            query=query.filter(Products.weight>=products_params.min_weight)
            
        if products_params.max_weight is not None:
            query=query.filter(Products.weight<=products_params.max_weight)
            
        if products_params.min_height is not None:
            query=query.filter(Products.height>=products_params.min_height)
            
        if products_params.max_height is not None:
            query=query.filter(Products.height<=products_params.max_height)
            
        if products_params.min_length is not None:
            query=query.filter(Products.length>=products_params.min_length)
            
        if products_params.max_length is not None:
            query=query.filter(Products.length<=products_params.max_length)
            
        if products_params.min_width is not None:
            query=query.filter(Products.width>=products_params.min_width)
            
        if products_params.max_width is not None:
            query=query.filter(Products.width<=products_params.max_width)
            
        if products_params.min_average_stars is not None:
            query=query.filter(Products.average_stars>=products_params.min_average_stars)
            
        if products_params.max_average_stars is not None:
            query=query.filter(Products.average_stars<=products_params.max_average_stars)
        
        if products_params.min_total_stars is not None:
            query=query.filter(Products.total_stars>=products_params.min_total_stars)
            
        if products_params.max_total_stars is not None:
            query=query.filter(Products.total_stars<=products_params.max_total_stars)    
            
        if products_params.sort_by==ProductsSortBy.price_asc:
            query=query.order_by(Products.price.asc())
            
        elif products_params.sort_by==ProductsSortBy.price_desc:
            query=query.order_by(Products.price.desc())
            
        elif products_params.sort_by==ProductsSortBy.discount_percentage_asc:
            query=query.order_by(Products.discount_percentage.asc())
            
        elif products_params.sort_by==ProductsSortBy.discount_percentage_desc:
            query=query.order_by(Products.discount_percentage.desc())
        
        elif products_params.sort_by==ProductsSortBy.weight_asc:
            query=query.order_by(Products.weight.asc())
            
        elif products_params.sort_by==ProductsSortBy.weight_desc:
            query=query.order_by(Products.weight.desc())  
            
        elif products_params.sort_by==ProductsSortBy.height_asc:
            query=query.order_by(Products.height.asc())
            
        elif products_params.sort_by==ProductsSortBy.height_desc:
            query=query.order_by(Products.height.desc())  
            
        elif products_params.sort_by==ProductsSortBy.length_asc:
            query=query.order_by(Products.length.asc())
            
        elif products_params.sort_by==ProductsSortBy.length_desc:
            query=query.order_by(Products.length.desc())
            
        elif products_params.sort_by==ProductsSortBy.width_asc:
            query=query.order_by(Products.width.asc())
            
        elif products_params.sort_by==ProductsSortBy.width_desc:
            query=query.order_by(Products.width.desc())
            
        elif products_params.sort_by==ProductsSortBy.average_stars_asc:
            query=query.order_by(Products.average_stars.asc())
            
        elif products_params.sort_by==ProductsSortBy.average_stars_desc:
            query=query.order_by(Products.average_stars.desc())
            
        elif products_params.sort_by==ProductsSortBy.total_stars_asc:
            query=query.order_by(Products.total_stars.asc())
            
        elif products_params.sort_by==ProductsSortBy.total_stars_desc:
            query=query.order_by(Products.total_stars.desc())
            
        
        
        offset=(page-1)*limit
        query=query.offset(offset).limit(limit)    
        
        products=query.all()
        
        for product in products:
            
                category_db=session.query(Categories).filter(Categories.id==product.category_id).first()
                is_stock=get_stock(product)
                product_images_db=session.query(product_images).filter(product_images.product_id==product.id).all()
                product_images_list=[]
                for image_db in product_images_db:
                    image_db_dict={
                        'id':image_db.id,
                        'product_id':image_db.product_id,
                        'image_url':image_db.image_url,
                        'is_main':image_db.is_main
                    }
                    product_images_list.append(image_db_dict)
            
                product_found={
                    'id':product.id,
                    'title':product.title,
                    'description':product.description,
                    'price':str(product.price) if product.price is not None else None,
                    'stock':is_stock,
                    'category':category_db.title,
                    'discount_percentage':str(product.discount_percentage) if product.discount_percentage is not None else None,
                    'weight':float(product.weight) if product.weight is not None else None,
                    'height':float(product.height) if product.height is not None else None,
                    'length':float(product.length) if product.length is not None else None,
                    'width':float(product.width) if product.width is not None else None,
                    'status':product.status,
                    'images':product_images_list,
                    'average_stars':product.average_stars,
                    'total_stars':product.total_stars
                    }
                products_found.append(product_found)
                
        return JSONResponse(status_code=status.HTTP_200_OK,content={'products':products_found, 'page':page,'limit':limit})
    except SQLAlchemyError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail='An error occurred while getting the products.')
        