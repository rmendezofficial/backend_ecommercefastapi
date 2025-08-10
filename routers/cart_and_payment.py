from fastapi import APIRouter, HTTPException,status, Request, Depends, Header
from fastapi.responses import JSONResponse
import stripe.error
from config import STRIPE_SECRET_KEY, SUCCESS_URL, CANCEL_URL,STRIPE_WEBHOOK_SECRET, CREATE_RESERVATION_EXPIRATION_TIME, CHECKOUT_PAYMENT_EXPIRATION_TIME
import stripe
from typing import Annotated
from dependencies.database import SessionDB
from fastapi_csrf_protect import CsrfProtect
from routers.users import get_current_active_user, is_admin
from schemas.users import User
from schemas.cart_and_payment import CartProduct, CartProductsCheckout, CartSortBy, CartInventoryParams, CartSnapshootInventoryParams, CartSnapshootSortBy
from models.products import Products, product_images
from models.categories import Categories
from models.cart import Cart, CartSnapshoots
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
from sqlalchemy import update, select, delete

router=APIRouter(prefix='/payment')

utc=pytz.UTC
stripe.api_key=STRIPE_SECRET_KEY

def create_cart_snapshoot(session:SessionDB, product_id:int, user_id:int, units:int, checkout_session_id:int):
    product_db=session.query(Products).filter(Products.id==product_id).first()
    cart_snapshoot_db=CartSnapshoots(product_id=product_id, user_id=user_id, units=units, checkout_session_id=checkout_session_id, price_at_purchase=product_db.price)
    session.add(cart_snapshoot_db)
    
def create_checkout_session_row(session:SessionDB, user_id:int, stripe_session_id:str, stripe_session_url:str):
    checkout_session_db=CheckOutSessions(user_id=user_id, status='active', session_id=stripe_session_id, session_url=stripe_session_url)
    session.add(checkout_session_db)
    session.flush()
    return checkout_session_db
    
def create_refund(session:SessionDB, user_id:int, payment_intent_id:str, checkout_session_id:int, order_id:int):
    
    refund_db=Refunds(user_id=user_id, payment_intent_id=payment_intent_id, checkout_session_id=checkout_session_id, order_id=order_id)
    session.add(refund_db)
        

def create_reservations(session:SessionDB, cart_products:list, user_id:int, checkout_session_id:int):
    if len(cart_products)<=0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='There are no products in the cart')
    for cart_product in cart_products:  
        existing_product_db=session.query(Products).filter(Products.id==cart_product.product_id).first()
        if not existing_product_db:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='The product does not exist')
        existing_reservation_db=session.query(Reservations).filter(Reservations.user_id==user_id, Reservations.product_id==cart_product.product_id, Reservations.status=='pending', Reservations.checkout_session_id==checkout_session_id).first()
        if existing_reservation_db:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='A reservation was already created. Try again later')
    
        result = session.query(Products).filter(
            Products.id == cart_product.product_id,
            Products.available_stock >= cart_product.units
        ).update(
            {
                Products.reserve_stock: Products.reserve_stock + cart_product.units,
                Products.available_stock: Products.available_stock - cart_product.units
            },
            synchronize_session=False  # Important for a reliable atomic update
        )
        
        if result == 0:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f'Not enough stock for product ID: {cart_product.product_id}')
        
        now = datetime.now(timezone.utc)
        expiration = now + timedelta(minutes=CREATE_RESERVATION_EXPIRATION_TIME)
        reservation_db = Reservations(
            product_id=cart_product.product_id, 
            user_id=user_id, 
            units=cart_product.units, 
            expires_at=expiration, 
            status='pending', 
            checkout_session_id=checkout_session_id
        )
        session.add(reservation_db)
            
    
            
         
def delete_reservation(session: SessionDB, product_id: int, units: int, user_id: int, checkout_session_id: int):
    # Atomic update: only subtract if reservation exists
    updated_rows = session.query(Products).filter(
        Products.id == product_id,
        session.query(Reservations.id).filter(
            Reservations.user_id == user_id,
            Reservations.product_id == product_id,
            Reservations.status == 'pending',
            Reservations.checkout_session_id == checkout_session_id
        ).exists()
    ).update(
        {
            Products.reserve_stock: Products.reserve_stock - units,
            Products.available_stock: Products.available_stock + units
        },
        synchronize_session=False
    )

    if updated_rows == 0:
        # No reservation found, nothing to do
        return

    # Delete reservation in the same transaction
    session.query(Reservations).filter(
        Reservations.user_id == user_id,
        Reservations.product_id == product_id,
        Reservations.status == 'pending',
        Reservations.checkout_session_id == checkout_session_id
    ).delete(synchronize_session=False)

         
def expire_checkout_session(session:SessionDB, user_id:int, checkout_session_id:int):
    session.query(CheckOutSessions).filter(
        CheckOutSessions.user_id == user_id, 
        CheckOutSessions.id == checkout_session_id
    ).update({'status': 'expired'}, synchronize_session=False)
    

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
        reservations_with_products = session.query(
            Reservations,
            Products
        ).join(
            Products,
            Reservations.product_id == Products.id
        ).filter(
            Reservations.user_id == user.id
        ).with_for_update().all()

        if not reservations_with_products:
            return

        for reservation, product in reservations_with_products:
            product.reserve_stock -= reservation.units
            product.available_stock += reservation.units

        session.query(Reservations).filter(
            Reservations.user_id == user.id
        ).delete(synchronize_session=False)

        session.query(CheckOutSessions).filter(
            CheckOutSessions.user_id == user.id,
            CheckOutSessions.status == 'active'
        ).update({'status': 'expired'}, synchronize_session=False)

        session.commit()

    except SQLAlchemyError as e:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f'An error occurred while deleting reservations: {e}')


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
        
        checkout_session_db=create_checkout_session_row(session, user.id, stripe_session.id, stripe_session.url)
        create_reservations(session, cart_products, user.id, checkout_session_db.id)
        
        #create the cart for each of the products of the cart with the checkout session id. 
        for cart_product in cart_products:
            create_cart_snapshoot(session,cart_product.product_id, user.id, cart_product.units, checkout_session_db.id)
        session.commit()
        return JSONResponse(status_code=status.HTTP_200_OK,content={'url':stripe_session.url})
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) 

#shipping address, order, order items, payment , modify the stock, delete products from cart(if linked checkout active), refund and oversold if needed, release reservations and set expired

def handle_checkout_success(stripe_session_data,session:SessionDB):
    customer_id = stripe_session_data.get("customer")
    user=session.query(Users).filter(Users.stripe_id==customer_id).first()
    user_id=user.id
    linked_checkout_session=session.query(CheckOutSessions).filter(CheckOutSessions.session_id==stripe_session_data['id']).first()
    payment_intent = stripe.PaymentIntent.retrieve(stripe_session_data['payment_intent'])
    existing_order = session.query(Orders).filter(Orders.checkout_session_id == linked_checkout_session.id).first()
    if existing_order:
        print("Webhook received for an already processed checkout session. Ignoring.")
        return
    try:
        #create shipping address
        address=stripe_session_data['customer_details']['address']
        shipping_address_db=ShippingAddresses(user_id=user_id, address_line1=address['line1'], address_line2=address['line2'], city=address['city'], state=address['state'], country=address['country'], zip_code=address['postal_code'])
        session.add(shipping_address_db)
        session.flush()
        #create order
        order_db=Orders(user_id=user_id, total_amount=stripe_session_data['amount_total'], shipping_addresses_id=shipping_address_db.id, checkout_session_id=linked_checkout_session.id)
        session.add(order_db)
        session.flush()
        #create order items
        cart_products_snapshoot_db=session.query(CartSnapshoots).filter(CartSnapshoots.user_id==user_id, CartSnapshoots.checkout_session_id==linked_checkout_session.id).all()
        for cart_product_snapshoot in cart_products_snapshoot_db:
            #use the cart snapshoots associated with the checkout session linked
            order_product_db=OrderItems(order_id=order_db.id, product_id=cart_product_snapshoot.product_id, units=cart_product_snapshoot.units, price_at_purchase=cart_product_snapshoot.price_at_purchase)
            session.add(order_product_db)
        #create payment
        payment_db = session.query(Payments).filter(Payments.payment_intent_id == payment_intent['id']).first()
        if payment_db:
            payment_db.order_id=order_db.id
            payment_db.user_id=user_id
            payment_db.payment_method=PaymentMethod.stripe
            payment_db.status=PaymentStatus.paid
            payment_db.stripe_session_id=stripe_session_data['id']
            payment_db.stripe_customer_id=customer_id
            payment_db.currency=stripe_session_data['currency']
            payment_db.tax_details=stripe_session_data['total_details'].get("amount_tax", 0)
            payment_db.payment_intent_id=payment_intent['id']
        else:    
            payment_db=Payments(order_id=order_db.id, user_id=user_id, payment_method=PaymentMethod.stripe, status=PaymentStatus.paid, stripe_session_id=stripe_session_data['id'], stripe_customer_id=customer_id, currency=stripe_session_data['currency'], tax_details=stripe_session_data['total_details'].get("amount_tax", 0), payment_intent_id=payment_intent['id']) 
            session.add(payment_db)
        print(f'PAYMENT_DB_:{payment_db.user_id}')
        print(f'PAYMENT_DB_:{payment_db.payment_method}')
        print(f'PAYMENT_DB_:{payment_db.status}')
        print(f'PAYMENT_DB_:{payment_db.created_at}')
        print(f'PAYMENT_DB_:{payment_db.stripe_session_id}')
        print(f'PAYMENT_DB_:{payment_db.stripe_customer_id}')
        print(f'PAYMENT_DB_:{payment_db.currency}')
        print(f'PAYMENT_DB_:{payment_db.tax_details}')
        print(f'PAYMENT_DB_:{payment_db.payment_intent_id}')
        print(f'PAYMENT_DB_:{payment_db.charge_id}')
        print(f'PAYMENT_DB_:{payment_db.receipt_url}')
        #modify stock and release reservations
        for product in cart_products_snapshoot_db:
            delete_reservation(session, product.product_id, product.units, user_id, linked_checkout_session.id) 
            session.query(Products).filter(Products.id == product.product_id).update({Products.stock: Products.stock - product.units, Products.available_stock: Products.available_stock - product.units},synchronize_session=False)
        #refund and if oversold and expired session
        if linked_checkout_session.status!='active': 
            order_db.oversold=True
            #create refund request
            create_refund(session,user_id, payment_intent['id'], linked_checkout_session.id, order_db.id)
            print(f'A refund petition was created')
        else:
            #delete cart products if checkout is active
            cart_products=session.query(Cart).filter(Cart.user_id==user_id).all()
            for cart_product in cart_products:
                session.delete(cart_product)
        linked_checkout_session.status='expired'
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        print(f'An error occured while handling the checkout success: {e}')
        
        
def handle_charge_succeess(charge_data,session:SessionDB):
    payment_intent_id = charge_data['payment_intent']
    payment_db = session.query(Payments).filter(Payments.payment_intent_id == payment_intent_id).first()
    try:
        if payment_db:
            payment_db.charge_id=charge_data['id']
            payment_db.receipt_url=charge_data['receipt_url']
            session.commit()
        else:
            payment_db=Payments(charge_id=charge_data['id'], receipt_url=charge_data['receipt_url']) 
            session.add(payment_db)
            session.commit()
        print(f'PAYMENT_DB_CHARGE:{payment_db.user_id}')
        print(f'PAYMENT_DB_CHARGE:{payment_db.payment_method}')
        print(f'PAYMENT_DB_CHARGE:{payment_db.status}')
        print(f'PAYMENT_DB_CHARGE:{payment_db.created_at}')
        print(f'PAYMENT_DB_CHARGE:{payment_db.stripe_session_id}')
        print(f'PAYMENT_DB_CHARGE:{payment_db.stripe_customer_id}')
        print(f'PAYMENT_DB_CHARGE:{payment_db.currency}')
        print(f'PAYMENT_DB_CHARGE:{payment_db.tax_details}')
        print(f'PAYMENT_DB_CHARGE:{payment_db.payment_intent_id}')
        print(f'PAYMENT_DB_CHARGE:{payment_db.charge_id}')
        print(f'PAYMENT_DB_CHARGE:{payment_db.receipt_url}')
    except SQLAlchemyError as e:
        session.rollback()
        print(f'An error occured while handling the charge success: {e}')
    
       
    
    

def handle_failed_payment(intent, session:SessionDB, stripe_session_data):
    # Log failure or notify user
    customer_id = intent.get("customer")
    user=session.query(Users).filter(Users.stripe_id==customer_id).first()
    user_id=user.id
    linked_checkout_session=session.query(CheckOutSessions).filter(CheckOutSessions.session_id==stripe_session_data['id']).first()
    try:
        expire_checkout_session(session, user_id, linked_checkout_session.id)
        reservations_db=session.query(Reservations).filter(Reservations.user_id==user_id, Reservations.checkout_session_id==linked_checkout_session.id).all()
        for reservation_db in reservations_db:
            delete_reservation(session, reservation_db.product_id, reservation_db.units, user_id, linked_checkout_session.id)
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        print(f'An error occured while handling the checkout failure: {e}')
    
    
def handle_expired_payment(intent, session:SessionDB, stripe_session_data):
    # Log failure or notify user
    customer_id = intent.get("customer")
    user=session.query(Users).filter(Users.stripe_id==customer_id).first()
    user_id=user.id
    linked_checkout_session=session.query(CheckOutSessions).filter(CheckOutSessions.session_id==stripe_session_data['id']).first()
    try:
        expire_checkout_session(session, user_id, linked_checkout_session.id)
        reservations_db=session.query(Reservations).filter(Reservations.user_id==user_id, Reservations.checkout_session_id==linked_checkout_session.id).all()
        for reservation_db in reservations_db:
            delete_reservation(session, reservation_db.product_id, reservation_db.units, user_id, linked_checkout_session.id)
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        print(f'An error occured while handling the checkout failure: {e}')
    
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
        
    elif event['type'] == 'charge.succeeded':
        # This is the new block for a successful charge
        charge_data = event['data']['object']
        handle_charge_succeess(charge_data, session)

    elif event['type'] == 'payment_intent.payment_failed':
        intent = event['data']['object']
        checkout_sessions = stripe.checkout.Session.list(payment_intent=intent["id"])
        if checkout_sessions.data:
            stripe_session_data = checkout_sessions.data[0]
            handle_failed_payment(intent,session, stripe_session_data)
    
    elif event['type'] == 'payment_intent.expired':
        intent = event['data']['object']
        checkout_sessions = stripe.checkout.Session.list(payment_intent=intent["id"])
        if checkout_sessions.data:
            stripe_session_data = checkout_sessions.data[0]
            handle_expired_payment(intent,session, stripe_session_data)
        
    return {"status": "success"}








#Cart admins

@router.post('/get_carts_admins',tags=['carts_admins'])
async def get_carts_admins(
    request:Request,
    admin: Annotated[bool, Depends(is_admin)],
    csrf_protect:Annotated[CsrfProtect, Depends()],
    x_csrf_token:Annotated[str,Header(...,description='"X-CSRF-Token')],
    session:SessionDB,
    carts_params: CartInventoryParams,
    page:int|None=1,
    limit:int|None=10,
    )->JSONResponse:
    await csrf_protect.validate_csrf(request)
    if not admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail='Not enough permissions')
    try:
        query=session.query(Cart)
        
        carts_found=[]
     
        if carts_params.product_id:
            query=query.filter(Cart.product_id==carts_params.product_id)
            
        if carts_params.user_id:
            query=query.filter(Cart.user_id==carts_params.user_id)
                
        
        if carts_params.min_units is not None:
            query=query.filter(Cart.units>=carts_params.min_units)
            
        if carts_params.max_units is not None:
            query=query.filter(Cart.units<=carts_params.max_units)
            
   
        if carts_params.date_after is not None:
            query=query.filter(Cart.created_at>=carts_params.date_after)
            
        if carts_params.date_before is not None:
            query=query.filter(Cart.created_at<=carts_params.date_before)
            
            
           
        if carts_params.sort_by==CartSortBy.units_asc:
            query=query.order_by(Cart.units.asc())
            
        elif carts_params.sort_by==CartSortBy.units_desc:
            query=query.order_by(Cart.units.desc())
            
        elif carts_params.sort_by==CartSortBy.date_asc:
            query=query.order_by(Cart.created_at.asc())
            
        elif carts_params.sort_by==CartSortBy.date_desc:
            query=query.order_by(Cart.created_at.desc())  
        
        offset=(page-1)*limit
        query=query.offset(offset).limit(limit)    
        
        carts=query.all()
        for cart in carts:
            cart_object={
                'id':cart.id,
                'product_id':cart.product_id,
                'user_id':cart.user_id,
                'units':cart.units,
                'created_at':cart.created_at.isoformat()
            }
            carts_found.append(cart_object)
                
        return JSONResponse(status_code=status.HTTP_200_OK,content={'carts':carts_found, 'page':page,'limit':limit})
    except SQLAlchemyError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail='An error occurred while getting the carts.')



@router.post('/get_cart_snapshoots_admins',tags=['cart_snapshoots_admins'])
async def get_cart_snapshoots_admins(
    request:Request,
    admin: Annotated[bool, Depends(is_admin)],
    csrf_protect:Annotated[CsrfProtect, Depends()],
    x_csrf_token:Annotated[str,Header(...,description='"X-CSRF-Token')],
    session:SessionDB,
    cart_snapshoots_params: CartSnapshootInventoryParams,
    page:int|None=1,
    limit:int|None=10,
    )->JSONResponse:
    await csrf_protect.validate_csrf(request)
    if not admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail='Not enough permissions')
    try:
        query=session.query(CartSnapshoots)
        
        cart_snapshoots_found=[]
     
        if cart_snapshoots_params.product_id:
            query=query.filter(CartSnapshoots.product_id==cart_snapshoots_params.product_id)
            
        if cart_snapshoots_params.user_id:
            query=query.filter(CartSnapshoots.user_id==cart_snapshoots_params.user_id)
                
        
        if cart_snapshoots_params.min_units is not None:
            query=query.filter(CartSnapshoots.units>=cart_snapshoots_params.min_units)
            
        if cart_snapshoots_params.max_units is not None:
            query=query.filter(CartSnapshoots.units<=cart_snapshoots_params.max_units)
            
   
        if cart_snapshoots_params.date_after is not None:
            query=query.filter(CartSnapshoots.created_at>=cart_snapshoots_params.date_after)
            
        if cart_snapshoots_params.date_before is not None:
            query=query.filter(CartSnapshoots.created_at<=cart_snapshoots_params.date_before)
            
        if cart_snapshoots_params.checkout_session_id:
            query=query.filter(CartSnapshoots.checkout_session_id==cart_snapshoots_params.checkout_session_id)
        
        if cart_snapshoots_params.min_price_at_purchase is not None:
            query=query.filter(CartSnapshoots.price_at_purchase>=cart_snapshoots_params.min_price_at_purchase)
            
        if cart_snapshoots_params.max_price_at_purchase is not None:
            query=query.filter(CartSnapshoots.price_at_purchase<=cart_snapshoots_params.max_price_at_purchase)
            
            
           
        if cart_snapshoots_params.sort_by==CartSnapshootSortBy.units_asc:
            query=query.order_by(CartSnapshoots.units.asc())
            
        elif cart_snapshoots_params.sort_by==CartSnapshootSortBy.units_desc:
            query=query.order_by(CartSnapshoots.units.desc())
            
        elif cart_snapshoots_params.sort_by==CartSnapshootSortBy.date_asc:
            query=query.order_by(CartSnapshoots.created_at.asc())
            
        elif cart_snapshoots_params.sort_by==CartSnapshootSortBy.date_desc:
            query=query.order_by(CartSnapshoots.created_at.desc()) 
            
        elif cart_snapshoots_params.sort_by==CartSnapshootSortBy.price_at_purchase_asc:
            query=query.order_by(CartSnapshoots.price_at_purchase.asc()) 
        
        elif cart_snapshoots_params.sort_by==CartSnapshootSortBy.price_at_purchase_desc:
            query=query.order_by(CartSnapshoots.price_at_purchase.desc())  
        
        offset=(page-1)*limit
        query=query.offset(offset).limit(limit)    
        
        cart_snapshoots=query.all()
        for cart_snapshoot in cart_snapshoots:
            cart_snapshoot_object={
                'id':cart_snapshoot.id,
                'product_id':cart_snapshoot.product_id,
                'user_id':cart_snapshoot.user_id,
                'units':cart_snapshoot.units,
                'created_at':cart_snapshoot.created_at.isoformat(),
                'checkout_session_id':cart_snapshoot.checkout_session_id,
                'price_at_purchase':str(cart_snapshoot.price_at_purchase) if cart_snapshoot.price_at_purchase is not None else None
                
            }
            cart_snapshoots_found.append(cart_snapshoot_object)
                
        return JSONResponse(status_code=status.HTTP_200_OK,content={'carts':cart_snapshoots_found, 'page':page,'limit':limit})
    except SQLAlchemyError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail='An error occurred while getting the carts.')
