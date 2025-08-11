from fastapi import APIRouter, Depends, Request, HTTPException, status, Response
from fastapi_csrf_protect import CsrfProtect
from fastapi_csrf_protect.exceptions import CsrfProtectError
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from typing import Annotated
from sqlalchemy.orm import Session
from dependencies.database import SessionDB
from datetime import datetime, timedelta, timezone
from config import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, REFRESH_TOKEN_EXPIRE_DAYS, SECRET_KEY, STRIPE_SECRET_KEY
from schemas.users import UserSignUp,User,UserDB
from schemas.security import Token,TokenData,CsrfSettings
from fastapi.responses import JSONResponse
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from models.users import Users
import stripe
import phonenumbers
from phonenumbers.phonenumberutil import NumberParseException
from models.orders import Orders

router=APIRouter(prefix='/users')

#OAUTH2
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme=OAuth2PasswordBearer(tokenUrl='token')
access_token_expires=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
refresh_token_expires=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

#STRIPE
stripe.api_key=STRIPE_SECRET_KEY



#METHODS
def get_password_hash(password:str):
    return pwd_context.hash(password)

def get_user(session: SessionDB, username:str):
    user=session.query(Users).filter(Users.username==username.lower()).first()
    if user:
        user_dict={
            'id':user.id,
            'username':user.username,
            'email':user.email,
            'hashed_password':user.hashed_password,
            'name':user.name,
            'lastname':user.lastname,
            'verified':user.verified,
            'disabled':user.disabled,
            'role':user.role,
            'stripe_id':user.stripe_id,
            'phone_number':user.phone_number
            
        }
        return UserDB(**user_dict)

def verify_password(password, hashed_password):
    return pwd_context.verify(password, hashed_password) 

def authenticate_user(session:SessionDB,username:str, password:str):
    user=get_user(session,username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

def create_access_token(data:dict, expires_delta:timedelta|None=None):
    to_encode=data.copy()
    if expires_delta:
        expire=datetime.now(timezone.utc)+expires_delta
    else:
        expire=datetime.now(timezone.utc)+timedelta(minutes=15)
    to_encode.update({'exp':expire})
    encode_jwt=jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encode_jwt

async def get_current_user(request:Request, session:SessionDB):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = request.cookies.get("access_token")
    if not token:
        raise credentials_exception
    try:
        payload=jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username=payload.get('sub')
        if username is None:
            raise credentials_exception
        token_data=TokenData(username=username)
    except ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired",headers={"WWW-Authenticate": "Bearer"})
    except InvalidTokenError:
        raise credentials_exception
    user=get_user(session, username=token_data.username)
    if user is None:
        raise credentials_exception
    user_without_password=User(id=user.id,username=user.username, email=user.email, disabled=user.disabled,name=user.name,lastname=user.lastname,verified=user.verified,role=user.role,stripe_id=user.stripe_id, phone_number=user.phone_number)
    return user_without_password

async def get_current_user_custom(request:Request, session:SessionDB): #same but without raising exceptions if no user found, for get products
    token = request.cookies.get("access_token")
    if not token:
        return False
    try:
        payload=jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username=payload.get('sub')
        if username is None:
            return False
        token_data=TokenData(username=username)
    except ExpiredSignatureError:
        return False
    except InvalidTokenError:
        return False
    user=get_user(session, username=token_data.username)
    if user is None:
        return False
    user_without_password=User(id=user.id,username=user.username, email=user.email, disabled=user.disabled,name=user.name,lastname=user.lastname,verified=user.verified,role=user.role,stripe_id=user.stripe_id, phone_number=user.phone_number)
    return user_without_password

async def get_current_active_user(current_user:Annotated[User,Depends(get_current_user)]):
    #if current_user.verified==True: #set to false in production
    #    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail='Please verify your email')
    if current_user.disabled==True:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail='Inactive user')
    return current_user

async def get_current_active_user_custom(current_user:Annotated[User,Depends(get_current_user_custom)]):
    if current_user:
        #if current_user.verified==True: #set to false in production
            #return False
        if current_user.disabled==True:
            return False
        return current_user
    return False

async def is_admin(active_current_user:Annotated[User, Depends(get_current_active_user)]):
    return active_current_user.role=='admin'
        
        
        
def process_phone_number(raw_number: str, region: str = "US") -> str:
    try:
        # Parse the number
        parsed_number = phonenumbers.parse(raw_number, region)

        # Check if the number is valid
        if not phonenumbers.is_valid_number(parsed_number):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid number')

        # Format in E.164 for database storage
        return phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)

    except NumberParseException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'Invalid phone number format, {e}')






#ROUTES
@router.post('/token',tags=['Users'])
async def login(form_data:Annotated[OAuth2PasswordRequestForm, Depends()], session:SessionDB, csrf_protect: Annotated[CsrfProtect, Depends()])->JSONResponse:
    user=authenticate_user(session,form_data.username.lower(), form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token=create_access_token(data={'sub':user.username}, expires_delta=access_token_expires)
    refresh_token=create_access_token(data={'sub':user.username}, expires_delta=refresh_token_expires)
    csrf_token, signed_token=csrf_protect.generate_csrf_tokens()
    
    response=JSONResponse(content={'message':'Login successful', 'csrf_token':csrf_token})
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=1800,
        path="/"
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=604800,
        path="/"
    )
    
    csrf_protect.set_csrf_cookie(csrf_signed_token=signed_token,response=response)
    return response

@router.post("/refresh-token",tags=['Users'])
def refresh_token(request: Request, response: Response, session:SessionDB):
    old_refresh_token = request.cookies.get("refresh_token")
    
    if not old_refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")
    
    try:
        payload = jwt.decode(old_refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
        user_db=session.query(Users).filter(Users.username==username).first()
        if user_db is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
        if user_db.disabled==True:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail='Invalid refresh token') 
    except ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")
    except InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    
    # Generate new access token
    new_access_token = create_access_token(
        data={"sub": username},
        expires_delta=access_token_expires
    )
    
    # OPTIONAL: Generate a new refresh token
    new_refresh_token = create_access_token(
        data={"sub": username},
        expires_delta=refresh_token_expires
    )
    
    # Set cookies
    response.set_cookie(
        key="access_token",
        value=new_access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=1800,
        path="/"
    )
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
        path="/"
    )
    
    return {"message": "Token refreshed"}


@router.get('/me',tags=['Users'])
def get_me(session:SessionDB, current_user:Annotated[User,Depends(get_current_active_user)])->User:
    return current_user

@router.post('/logout',tags=['Users']) #check it when hosting a real server, for it needs https to send and delete the cookies
def logout(request:Request,response:Response)->JSONResponse:
    print(request.headers)
    response.delete_cookie(key='access_token',path='/',secure=True,samesite='lax')
    response.delete_cookie(key='refresh_token',path='/',secure=True,samesite='lax')
    response.delete_cookie(key='fastapi-csrf-token',path='/',secure=True,samesite='lax')
    return JSONResponse(content={'message':'Logged out successfully'})

@router.post('/signup',tags=['Users'])
def signup(user:UserSignUp, session:SessionDB)->User:
    user.email=user.email.lower()
    user.username=user.username.lower()
    existing_user_username=session.query(Users).filter(Users.username==user.username).first()
    if existing_user_username:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='User with this username already exists'
        )
    existing_user_email=session.query(Users).filter(Users.email==user.email).first()
    if existing_user_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='User with this email already exists'
        )
    try:
        customer=stripe.Customer.create(
            email=user.email,name=f'{user.name} {user.lastname}'
        )
        phone_number=process_phone_number(user.phone_number, user.phone_number_region)
        hashed_password=get_password_hash(user.password)
        user_db=Users(username=user.username, email=user.email, hashed_password=hashed_password,name=user.name,lastname=user.lastname,stripe_id=customer['id'], phone_number=phone_number)
        session.add(user_db)
        session.commit()
        session.refresh(user_db)
        user_returned=User(id=user_db.id, username=user_db.username, email=user_db.email, name=user_db.name, lastname=user_db.lastname, disabled=user_db.disabled, verified=user_db.verified, role=user_db.role, stripe_id=user_db.stripe_id, phone_number=user_db.phone_number)
        return user_returned
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f'An error ocurred while creating the user. {e}')
