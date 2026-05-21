from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db, User, Seller, Product, Ticket, Dispute, Review
from auth_utils import require_role
from pydantic import BaseModel
from typing import Optional
import uuid

router = APIRouter(prefix="/admin", tags=["Admin"])


# ── USERS ────────────────────────────────────────────────────────────────────

@router.get("/users")
def list_users(
    role: Optional[str] = None,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    q = db.query(User)
    if role:
        q = q.filter(User.role == role)
    users = q.all()
    return [
        {
            "id": str(u.id),
            "name": u.name,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "created_at": u.created_at,
        }
        for u in users
    ]


@router.put("/users/{user_id}/toggle-active")
def toggle_user_active(
    user_id: str,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = not user.is_active
    db.commit()
    return {"message": f"User {'activated' if user.is_active else 'suspended'}", "is_active": user.is_active}


@router.put("/users/{user_id}/set-role")
def set_user_role(
    user_id: str,
    role: str,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    if role not in ["customer", "seller", "admin"]:
        raise HTTPException(status_code=400, detail="Invalid role")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = role
    db.commit()
    return {"message": f"Role updated to {role}"}


# ── SELLERS ──────────────────────────────────────────────────────────────────

@router.get("/sellers")
def list_sellers(
    status: Optional[str] = None,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    q = db.query(Seller)
    if status:
        q = q.filter(Seller.verification_status == status)
    sellers = q.all()
    result = []
    for s in sellers:
        user = db.query(User).filter(User.id == s.user_id).first()
        result.append({
            "id": str(s.id),
            "user_id": str(s.user_id),
            "name": user.name if user else None,
            "email": user.email if user else None,
            "shop_name": s.shop_name,
            "whatsapp": s.whatsapp,
            "verification_status": s.verification_status,
            "rating": s.rating,
            "total_reviews": s.total_reviews,
            "created_at": s.created_at,
        })
    return result


@router.put("/sellers/{seller_id}/verify")
def verify_seller(
    seller_id: str,
    action: str,  # verified | rejected | suspended
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    if action not in ["verified", "rejected", "suspended"]:
        raise HTTPException(status_code=400, detail="Action must be verified | rejected | suspended")
    seller = db.query(Seller).filter(Seller.id == seller_id).first()
    if not seller:
        raise HTTPException(status_code=404, detail="Seller not found")
    seller.verification_status = action

    # If verified, update user role to seller
    if action == "verified":
        user = db.query(User).filter(User.id == seller.user_id).first()
        if user:
            user.role = "seller"
    elif action == "suspended":
        user = db.query(User).filter(User.id == seller.user_id).first()
        if user:
            user.is_active = False

    db.commit()
    return {"message": f"Seller {action}"}


# ── ANALYTICS ────────────────────────────────────────────────────────────────

@router.get("/analytics")
def analytics(
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    total_users = db.query(func.count(User.id)).scalar()
    total_sellers = db.query(func.count(Seller.id)).filter(Seller.verification_status == "verified").scalar()
    pending_sellers = db.query(func.count(Seller.id)).filter(Seller.verification_status == "pending").scalar()
    total_products = db.query(func.count(Product.id)).filter(Product.status == "active").scalar()
    total_tickets = db.query(func.count(Ticket.id)).scalar()
    completed_tickets = db.query(func.count(Ticket.id)).filter(Ticket.status == "completed").scalar()
    open_disputes = db.query(func.count(Dispute.id)).filter(Dispute.status == "open").scalar()
    total_revenue = db.query(func.sum(Ticket.agreed_price)).filter(Ticket.status == "completed").scalar() or 0

    return {
        "total_users": total_users,
        "total_sellers": total_sellers,
        "pending_sellers": pending_sellers,
        "total_products": total_products,
        "total_tickets": total_tickets,
        "completed_tickets": completed_tickets,
        "open_disputes": open_disputes,
        "total_volume": total_revenue,
    }
