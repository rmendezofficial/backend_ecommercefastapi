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
from models.payments import Payments, PaymentMethod, PaymentStatus

router=APIRouter(prefix='/payment')

stripe.api_key=STRIPE_SECRET_KEY

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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An error occurred while releasing the product')
    
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
        return JSONResponse(status_code=status.HTTP_200_OK,content={'url':stripe_session.url})
    except Exception as e:
        existing_reservation_created=session.query(Reservations).filter(Reservations.user_id==user.id).first()
        if existing_reservation_created:
            for cart_product in cart_products:
                delete_reservation(session, cart_product.product_id, cart_product.units, user.id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) 


def handle_checkout_success(stripe_session_data,session:SessionDB):
    customer_id = stripe_session_data.get("customer")
    user=session.query(Users).filter(Users.stripe_id==customer_id).first()
    user_id=user.id
    checkout_created_at = datetime.fromtimestamp(stripe_session_data['created'], tz=timezone.utc)
    reservations_db=session.query(Reservations).filter(Reservations.user_id==user_id).all()
    reservations_before_checkout=0
    for reservation in reservations_db:   
        reservation_created_at=reservation.expires_at-timedelta(minutes=CREATE_RESERVATION_EXPIRATION_TIME)
        if reservation_created_at<=checkout_created_at:
            reservations_before_checkout+=1
    if reservations_before_checkout==0:
        stripe.Refund.create(payment_intent=stripe_session_data['payment_intent'])
        print("Refunded because no reservations existed before checkout.")

        
    try:
        
        cart_products=session.query(Cart).filter(Cart.user_id==user_id).all()
        
        
        #create shipping address
        shipping_details=stripe_session_data['shipping_details']
        address=shipping_details['address']
        line2=is_line2(address)
        shipping_address_db=ShippingAddresses(user_id=user_id,address_line1=address['line1'],address_line2=line2,city=address['city'],state=address['state'],country=address['country'],zip_code=address['postal_code'])
        session.add(shipping_address_db)
        session.commit()
        session.refresh(shipping_address_db)
        #create order
        order_db=Orders(user_id=user_id, total_amount=stripe_session_data['amount_total'], status=OrderStatus.paid, shipping_address_id=shipping_address_db.id)
        session.add(order_db)
        session.commit()
        session.refresh(order_db)
        #create order items
        for cart_product_db in cart_products:
            product_db=session.query(Products).filter(Products.id==cart_product_db.product_id).first()
            order_item_db=OrderItems(order_id=order_db.id, units=cart_product_db.units, product_id=cart_product_db.product_id, price_at_purchase=product_db.price)
            session.add(order_item_db)
        #create payment
        payment_intent_id=stripe_session_data['payment_intent']
        payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        charge=payment_intent["charges"]["data"][0]    
        payment_db=Payments(order_id=order_db.id, user_id=user_id, payment_method=PaymentMethod.stripe, status=PaymentStatus.paid, stripe_session_id=stripe_session_data['id'], stripe_customer_id=customer_id, currency=stripe_session_data['currency'], tax_details=stripe_session_data['total_details'].get("amount_tax", 0), payment_intent_id=payment_intent_id, charge_id=charge['id'], receipt_url=charge['receipt_url'])
        session.add(payment_db)
        #delete cart products
        for cart_product in cart_products:
            session.delete(cart_product)
        #delete reservations 
        reservations_db=session.query(Reservations).filter(Reservations.user_id==user_id).all()
        for reservation_db in reservations_db:
            session.delete(reservation_db)
        print(f'stripe_session:{stripe_session_data}')
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        #create email for admin indicationg the payment was successful but there was an error creating the order, also delete cart from user, reservations from user, and create the order for the user
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='An error occurred while creating the order')
    

def handle_failed_payment(intent, session:SessionDB):
    # Log failure or notify user
    customer_id = intent.get("customer")
    user=session.query(Users).filter(Users.stripe_id==customer_id).first()
    user_id=user.id
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

    print(f'payload:{payload}')
    print(f'sig_header:{sig_header}')
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


