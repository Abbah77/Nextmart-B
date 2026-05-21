from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from database import get_db, User, Seller
from auth_utils import hash_password, verify_password, create_access_token, get_current_user
import uuid

router = APIRouter(prefix="/auth", tags=["Auth"])


class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = "customer"  # customer or seller
    whatsapp: str = None
    shop_name: str = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str
    name: str
    user_id: str


@router.post("/signup", status_code=201)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    if payload.role not in ["customer", "seller"]:
        raise HTTPException(status_code=400, detail="Role must be customer or seller")

    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        id=uuid.uuid4(),
        name=payload.name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.flush()

    if payload.role == "seller":
        if not payload.whatsapp:
            raise HTTPException(status_code=400, detail="WhatsApp number required for sellers")
        seller = Seller(
            id=uuid.uuid4(),
            user_id=user.id,
            whatsapp=payload.whatsapp,
            shop_name=payload.shop_name or payload.name,
            verification_status="pending",
        )
        db.add(seller)

    db.commit()
    db.refresh(user)
    return {"message": "Account created successfully", "role": user.role}


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account suspended")

    token = create_access_token({"sub": str(user.id), "role": user.role})
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "name": user.name,
        "user_id": str(user.id),
    }


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role,
        "created_at": current_user.created_at,
    }
