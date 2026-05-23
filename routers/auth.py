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
    role: str = "customer"
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


class UpdateProfileRequest(BaseModel):
    name: str = None
    shop_name: str = None
    description: str = None
    whatsapp: str = None
    bank_name: str = None
    account_number: str = None
    account_name: str = None
    opay_number: str = None
    palmpay_number: str = None


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
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = {
        "id": str(current_user.id),
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role,
        "created_at": current_user.created_at,
    }
    if current_user.role == "seller":
        sp = db.query(Seller).filter(Seller.user_id == current_user.id).first()
        if sp:
            data["seller"] = {
                "shop_name": sp.shop_name,
                "description": sp.description,
                "whatsapp": sp.whatsapp,
                "rating": sp.rating,
                "total_reviews": sp.total_reviews,
                "verification_status": sp.verification_status,
                "bank_name": sp.bank_name,
                "account_number": sp.account_number,
                "account_name": sp.account_name,
                "opay_number": sp.opay_number,
                "palmpay_number": sp.palmpay_number,
            }
    return data


@router.put("/profile")
def update_profile(
    payload: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if payload.name:
        current_user.name = payload.name

    if current_user.role == "seller":
        sp = db.query(Seller).filter(Seller.user_id == current_user.id).first()
        if sp:
            if payload.shop_name is not None: sp.shop_name = payload.shop_name
            if payload.description is not None: sp.description = payload.description
            if payload.whatsapp is not None: sp.whatsapp = payload.whatsapp
            if payload.bank_name is not None: sp.bank_name = payload.bank_name
            if payload.account_number is not None: sp.account_number = payload.account_number
            if payload.account_name is not None: sp.account_name = payload.account_name
            if payload.opay_number is not None: sp.opay_number = payload.opay_number
            if payload.palmpay_number is not None: sp.palmpay_number = payload.palmpay_number

    db.commit()
    return {"message": "Profile updated successfully"}


@router.get("/seller/{seller_id}/payment-info")
def get_seller_payment_info(seller_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get seller payment details for customer to pay — only accessible by authenticated users"""
    sp = db.query(Seller).filter(Seller.user_id == seller_id).first()
    if not sp:
        raise HTTPException(status_code=404, detail="Seller not found")
    return {
        "shop_name": sp.shop_name,
        "whatsapp": sp.whatsapp,
        "bank_name": sp.bank_name,
        "account_number": sp.account_number,
        "account_name": sp.account_name,
        "opay_number": sp.opay_number,
        "palmpay_number": sp.palmpay_number,
    }
