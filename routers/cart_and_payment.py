from fastapi import APIRouter, HTTPException,status, Request, Depends, Header
from fastapi.responses import JSONResponse
import stripe.error
from config import STRIPE_SECRET_KEY, SUCCESS_URL, CANCEL_URL,STRIPE_WEBHOOK_SECRET, CREATE_RESERVATION_EXPIRATION_TIME, CHECKOUT_PAYMENT_EXPIRATION_TIME
import stripe
from typing import Annotated
from dependencies.database import SessionDB
from fastapi_csrf_protect import CsrfProtect
from routers.users import get_current_active_user
from schemas.users import User
from schemas.cart_and_payment import CartProduct, CartProductsCheckout
from models.products import Products, product_images
from models.categories import Categories
from models.cart import Cart
from routers.products import get_stock
from sqlalchemy.exc import SQLAlchemyError
from decimal import Decimal, ROUND_HALF_UP
from models.reservations import Reservations
from datetime import datetime, timedelta, timezone
from models.orders import Orders, OrderItems, OrderStatus
from models.users import ShippingAddresses, Users
from models.payments import Payments, PaymentMethod, PaymentStatus, CheckOutSessions
from models.refunds import Refunds
import pytz 

router=APIRouter(prefix='/payment')

utc=pytz.UTC
stripe.api_key=STRIPE_SECRET_KEY

def create_checkout_session_row(session:SessionDB, user_id:int, stripe_session_id:str, stripe_session_url:str):
    try:
        checkout_session_db=CheckOutSessions(user_id=user_id, status='active', session_id=stripe_session_id, session_url=stripe_session_url)
        session.add(checkout_session_db)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An error occured while creating checkout sessions.')
    
def create_refund(session:SessionDB, user_id:int, payment_intent_id:str, checkout_session_id:int):
    try:
        refund_db=Refunds(user_id=user_id, payment_intent_id=payment_intent_id, checkout_session_id=checkout_session_id)
        session.add(refund_db)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An error occured while creating the refund petition.')
        

def create_reservation(session:SessionDB, product_id:int,units:int, user_id:int):
    existing_product=session.query(Products).filter(Products.id==product_id).first()
    if not existing_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='The product does not exist')
    existing_reservation_db=session.query(Reservations).filter(Reservations.user_id==user_id, Reservations.product_id==product_id, Reservations.status=='pending').first()
    if existing_reservation_db:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='A reservation was already created. Try again later')
    try:
        if existing_product.available_stock>=units:
            existing_product.reserve_stock+=units
            existing_product.available_stock-=units
            
            now=datetime.now(timezone.utc)
            expiration=now+timedelta(minutes=CREATE_RESERVATION_EXPIRATION_TIME)
            
            reservation_db=Reservations(product_id=existing_product.id, user_id=user_id, units=units, expires_at=expiration, status='pending')
            session.add(reservation_db)
            session.commit()
            
            return True
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Not enough stock')
            
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An error occurred while reserving the product')

def delete_reservation(session:SessionDB, product_id:int, units: int, user_id:int):
    existing_product=session.query(Products).filter(Products.id==product_id).first()
    if not existing_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='The product does not exist')
    existing_reservation_db=session.query(Reservations).filter(Reservations.user_id==user_id, Reservations.product_id==product_id, Reservations.status=='pending').first()
    if not existing_reservation_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='The reservation does not exist')
    try:
        existing_product.reserve_stock-=units
        existing_product.available_stock+=units
        
        session.delete(existing_reservation_db)
        session.commit()
        return True
            
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An error occurred while releasing the product.')

def expire_checkout_sessions(session:SessionDB, user_id:int):
    existing_checkout_sessions=session.query(CheckOutSessions).filter(CheckOutSessions.user_id==user_id).all()
    try:
        for checkout_session in existing_checkout_sessions:
            checkout_session.status='expired'
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An error occured while expiring checkout sessions.')
    
def is_line2(stripe_session_data):
    line2=stripe_session_data['line2']
    if line2:
        return line2
    return None

@router.get('/get_cart_products',tags=['cart'])
async def get_cart(
    request:Request,
    user: Annotated[User, Depends(get_current_active_user)],
    csrf_protect:Annotated[CsrfProtect, Depends()],
    x_csrf_token:Annotated[str,Header(...,description='"X-CSRF-Token')],
    session:SessionDB
)->JSONResponse:
    await csrf_protect.validate_csrf(request)
    try:
        cart_products_db=session.query(Cart).filter(Cart.user_id==user.id).all()
        cart_products=[]
        for cart_product_db in cart_products_db:
            product_db=session.query(Products).filter(Products.id==cart_product_db.product_id).first()
            category_db=session.query(Categories).filter(Categories.id==product_db.category_id).first()
            product_images_db=session.query(product_images).filter(product_images.product_id==product_db.id).all()
            product_images_list=[]
            for product_image_db in product_images_db:
                image_response={
                    'id':product_image_db.id,
                    'image_url':product_image_db.image_url,
                    'is_main':product_image_db.is_main,
                    'product_id':product_image_db.product_id
                }
                product_images_list.append(image_response)
            product_response={
                'cart_product_id':cart_product_db.id,
                'id':product_db.id,
                'title':product_db.title,
                'description':product_db.description,
                'price':str(product_db.price) if product_db.price is not None else None,
                'stock':get_stock(product_db),
                'category':category_db.title,
                'discount_percentage':str(product_db.discount_percentage) if product_db.discount_percentage is not None else None,
                'status':product_db.status,
                'images':product_images_list,
                'units':cart_product_db.units
            }
            cart_products.append(product_response)
        return JSONResponse(status_code=status.HTTP_200_OK, content={'products_cart':cart_products})
    except Exception as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An error occurred while getting the products')

@router.post('/add_cart_product',tags=['cart'])
async def add_cart_product(
    request:Request,
    user: Annotated[User, Depends(get_current_active_user)],
    csrf_protect:Annotated[CsrfProtect, Depends()],
    x_csrf_token:Annotated[str,Header(...,description='"X-CSRF-Token')],
    session:SessionDB,
    cart_product:CartProduct
    )->JSONResponse:
    await csrf_protect.validate_csrf(request)
    existing_product=session.query(Products).filter(Products.id==cart_product.product_id, Products.status!='deleted').first()
    existing_reservations=session.query(Reservations).filter(Reservations.user_id==user.id).first()
    if existing_reservations:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='You cannot add products from the cart if you recently started a checkout')
    if not existing_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='The product does not exist')
    existing_cart_product=session.query(Cart).filter(Cart.product_id==cart_product.product_id,Cart.user_id==user.id).first()
    if existing_cart_product:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='The product is already in the cart')
    if cart_product.units>existing_product.available_stock:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Not enough stock')
    if cart_product.units<=0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Units must be equal or greather than 1')
    try:
        cart_product_db=Cart(product_id=cart_product.product_id, user_id=user.id,units=cart_product.units)
        session.add(cart_product_db)
        session.commit()
        return JSONResponse(status_code=status.HTTP_200_OK, content={'message':'Product successfully added to the cart'})
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An error occurred while adding the product to the cart')
    
#delete product and send the list of products from cart to create checkout session
@router.delete('/delete_cart_product/{cart_product_id}',tags=['cart'])
async def delete_product(
    request:Request,
    user: Annotated[User, Depends(get_current_active_user)],
    csrf_protect:Annotated[CsrfProtect, Depends()],
    x_csrf_token:Annotated[str,Header(...,description='"X-CSRF-Token')],
    cart_product_id:int,
    session:SessionDB
    )->JSONResponse:    
    await csrf_protect.validate_csrf(request)
    existing_cart_product=session.query(Cart).filter(Cart.id==cart_product_id).first()
    existing_reservations=session.query(Reservations).filter(Reservations.user_id==user.id).first()
    if existing_reservations:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='You cannot delete products from the cart if you recently started a checkout')
    if not existing_cart_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail='Product is not in the cart')
    
    try:
        session.delete(existing_cart_product)
        session.commit()
        return JSONResponse(status_code=status.HTTP_200_OK, content={'message':'Product successfully removed from cart'})
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while removing the product from the cart.")
  

@router.post('/delete_reservations',tags=['payment'])
async def delete_reservations(
    request:Request,
    user: Annotated[User, Depends(get_current_active_user)],
    csrf_protect:Annotated[CsrfProtect, Depends()],
    x_csrf_token:Annotated[str,Header(...,description='"X-CSRF-Token')],
    session:SessionDB
):
    await csrf_protect.validate_csrf(request)
    try:
        expire_checkout_sessions(session, user.id)
        reservations_db=session.query(Reservations).filter(Reservations.user_id==user.id).all()
        for reservation in reservations_db:
            session.delete(reservation)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An error occurred while deleting reservations') 


@router.post('/create_checkout_session',tags=['payment'])
async def create_checkout_session(
    request:Request,
    user: Annotated[User, Depends(get_current_active_user)],
    csrf_protect:Annotated[CsrfProtect, Depends()],
    x_csrf_token:Annotated[str,Header(...,description='"X-CSRF-Token')],
    session:SessionDB,
):
    await csrf_protect.validate_csrf(request)
    cart_products=session.query(Cart).filter(Cart.user_id==user.id).all()
    if len(cart_products)<=0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='The cart is empty')
    existing_reservation=session.query(Reservations).filter(Reservations.user_id==user.id).first()
    if existing_reservation:
        raise HTTPException(status_code=409, detail="You already have a checkout in progress or you recently had one. Try again later")
    try:
        line_items_list=[]
        for cart_product in cart_products:
            product_db=session.query(Products).filter(Products.id==cart_product.product_id).first()
            if not product_db:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='The product does not exist')
            category_db=session.query(Categories).filter(Categories.id==product_db.category_id).first()
            if not category_db:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='The category does not exist')
            if product_db.price<=0:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='The price of the product cannot be 0')
            if cart_product.units<=0:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='The units of the product cannot be 0')
            create_reservation(session,product_db.id, cart_product.units, user.id)
            price = Decimal(str(product_db.price))
            discount_pct = Decimal(str(product_db.discount_percentage))

            discounted_price=(price*(Decimal("100")-discount_pct))/Decimal('100')
    
            discount_amount_cents = (discounted_price*100)
            discount_amount_cents = discount_amount_cents.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            discount_amount_cents = int(discount_amount_cents)
            
            product={
                'price_data':{
                    'currency':'usd',
                    'unit_amount':discount_amount_cents,
                    'tax_behavior':'exclusive',
                    'product_data':
                        {
                            'tax_code':product_db.taxcode,
                            'name':product_db.title,
                            'metadata':{'category':category_db.title}
                        }
                },
                'quantity':cart_product.units
            }
            line_items_list.append(product)
        
        stripe_session=stripe.checkout.Session.create(
            payment_method_types=['card'],
            mode='payment',
            line_items=line_items_list,
            shipping_address_collection={"allowed_countries": ["US"]},
            customer=f'{user.stripe_id}',
            customer_update={"shipping": "auto"},
            success_url=SUCCESS_URL,
            cancel_url=CANCEL_URL,
            automatic_tax={'enabled':True},
            expires_at=int((datetime.now(timezone.utc)+timedelta(minutes=CHECKOUT_PAYMENT_EXPIRATION_TIME)).timestamp())
        )
        create_checkout_session_row(session, user.id, stripe_session.id, stripe_session.url)
        return JSONResponse(status_code=status.HTTP_200_OK,content={'url':stripe_session.url})
    except Exception as e:
        expire_checkout_sessions(session, user.id)
        existing_reservation_created=session.query(Reservations).filter(Reservations.user_id==user.id).first()
        if existing_reservation_created:
            for cart_product in cart_products:
                delete_reservation(session, cart_product.product_id, cart_product.units, user.id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) 


def handle_checkout_success(stripe_session_data,session:SessionDB):
    customer_id = stripe_session_data.get("customer")
    user=session.query(Users).filter(Users.stripe_id==customer_id).first()
    user_id=user.id
    linked_checkout_session=session.query(CheckOutSessions).filter(CheckOutSessions.session_id==stripe_session_data['id']).first()
    payment_intent = stripe.PaymentIntent.retrieve(stripe_session_data['payment_intent'])
    if linked_checkout_session.status!='active' and payment_intent['amount_received'] > payment_intent["charges"]["data"][0]["refunds"]["data"]:
        #create refund request
        create_refund(session,user_id, payment_intent, linked_checkout_session.id)
        print(f'A refund petition was created')
        return
       
    reservations_db=session.query(Reservations).filter(Reservations.user_id==user_id).all()
    
    

def handle_failed_payment(intent, session:SessionDB):
    # Log failure or notify user
    customer_id = intent.get("customer")
    user=session.query(Users).filter(Users.stripe_id==customer_id).first()
    user_id=user.id
    expire_checkout_sessions(session, user_id)
    try:
        reservations_db=session.query(Reservations).filter(Reservations.user_id==user_id).all()
        for reservation_db in reservations_db:
            session.delete(reservation_db)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An error occurred while deleting the reservations')
    
def handle_expired_payment(intent, session:SessionDB):
    # Log failure or notify user
    customer_id = intent.get("customer")
    user=session.query(Users).filter(Users.stripe_id==customer_id).first()
    user_id=user.id
    expire_checkout_sessions(session, user_id)
    try:
        reservations_db=session.query(Reservations).filter(Reservations.user_id==user_id).all()
        for reservation_db in reservations_db:
            session.delete(reservation_db)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An error occurred while deleting the reservations')
    

@router.post("/webhook/stripe", status_code=200,tags=['payment'])
async def stripe_webhook(
    request:Request,
    session:SessionDB
    ):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid payload {e}")
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid signature {e}")

    # Handle specific event types
    if event['type'] == 'checkout.session.completed':
        stripe_session_data = event['data']['object']
        handle_checkout_success(stripe_session_data,session)

    elif event['type'] == 'payment_intent.payment_failed':
        intent = event['data']['object']
        handle_failed_payment(intent,session)
    
    elif event['type'] == 'payment_intent.expired':
        intent = event['data']['object']
        handle_expired_payment(intent,session)
        
    return {"status": "success"}


