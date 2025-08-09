from fastapi import FastAPI, Request, Response, HTTPException, status
from routers import users, products,cart_and_payment, orders
from contextlib import asynccontextmanager
from database import engine, Base, SessionLocal
from fastapi.middleware.cors import CORSMiddleware
#from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from models.users import Users
from routers.users import get_password_hash, process_phone_number
from config import FIRST_ADMIN_PASSWORD, FIRST_ADMIN_EMAIL, FIRST_ADMIN_PHONE_NUMBER, FIRST_ADMIN_PHONE_NUMBER_REGION, RELEASE_EXPIRED_RESERVATIONS_TIME, ORIGIN_1, ORIGIN_2, ALLOWED_HOST_1, ALLOWED_HOST_2, CHECKOUT_SESSION_EXPIRATION_TIME
from fastapi_csrf_protect import CsrfProtect
from schemas.security import CsrfSettings
from fastapi_csrf_protect.exceptions import CsrfProtectError
from fastapi.responses import JSONResponse
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from models.reservations import Reservations
from models.products import Products
from models.payments import CheckOutSessions
from routers.cart_and_payment import delete_reservation
from sqlalchemy.exc import SQLAlchemyError


origins = [
    ORIGIN_1,
    ORIGIN_2, 
]

'''def release_expired_checkout_sessions(): #set them to expired rather than deleting and delete the cart snapshoots associated with expired checkout sessions, and do the reconcilliation process as well, also do not delete nor set to expire if there are transactions ongoing
    db=SessionLocal()
    now=datetime.now(timezone.utc)
    try:
        expired_checkout_sessions=db.query(CheckOutSessions).filter(CheckOutSessions.expires_at<now).all()
        for expired in expired_checkout_sessions:
            db.delete(expired)
        db.commit()
        db.close()
        print('All checkout sessions were deleted')
    except SQLAlchemyError as e:
        db.rollback()
        print(f'An error occurred while deleting the checkout sessions {e}')

scheduler = BackgroundScheduler()
scheduler.add_job(release_expired_checkout_sessions, 'interval', minutes=CHECKOUT_SESSION_EXPIRATION_TIME)
'''

@asynccontextmanager
async def lifespan(app:FastAPI):
    Base.metadata.create_all(bind=engine)
    
    session=SessionLocal()
    existing_admin=session.query(Users).filter(Users.role=='admin').first()
    if not existing_admin:
        phone_number=process_phone_number(FIRST_ADMIN_PHONE_NUMBER, FIRST_ADMIN_PHONE_NUMBER_REGION)
        password_hashed=get_password_hash(FIRST_ADMIN_PASSWORD)
        first_admin=Users(username='first_admin', email=FIRST_ADMIN_EMAIL, hashed_password=password_hashed,name='first_admin',lastname='first_admin',disabled=False, verified=True,role='admin',stripe_id='No id', phone_number=phone_number)
        session.add(first_admin)
        session.commit()
        session.refresh(first_admin)  
    else:
        session.close()
    #scheduler.start()
    yield
    #scheduler.shutdown()

app=FastAPI(lifespan=lifespan)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)

    # Set security headers manually
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer-when-downgrade"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"], 
)

#app.add_middleware(HTTPSRedirectMiddleware)

#app.add_middleware(TrustedHostMiddleware,
#    allowed_hosts=[ALLOWED_HOST_1, ALLOWED_HOST_2],)

#class CSPMiddleware(BaseHTTPMiddleware):
#    async def dispatch(self, request: Request, call_next):
#        response = await call_next(request)
#        response.headers["Content-Security-Policy"] = (
#            "default-src 'self'; "
#            "script-src 'self' https://cdn.jsdelivr.net; "
#            "style-src 'self' https://cdn.jsdelivr.net; "
#            "img-src 'self' data:; "
#            "font-src 'self' https://fonts.gstatic.com; "
#            "object-src 'none';"
#        )
#        return response
    
#class HSTSMiddleware(BaseHTTPMiddleware):
#    async def dispatch(self, request: Request, call_next):
#        response = await call_next(request)
#        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
#        return response

#app.add_middleware(HSTSMiddleware)

#app.add_middleware(CSPMiddleware)

#CSRF TOKEN LOGIC
@CsrfProtect.load_config
def get_csrf_config():
    return CsrfSettings()

@app.exception_handler(CsrfProtectError)
def csrf_protect_exception_handler(request: Request, exc: CsrfProtectError):
  return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


app.include_router(users.router)
app.include_router(products.router)
app.include_router(cart_and_payment.router)
app.include_router(orders.router)



