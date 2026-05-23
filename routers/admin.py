from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db, User, Seller, Product, Ticket, Dispute, Review
from auth_utils import require_role
from typing import Optional

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/analytics")
def get_analytics(
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    total_users = db.query(User).filter(User.role != "admin").count()
    total_sellers = db.query(Seller).filter(Seller.verification_status == "verified").count()
    total_products = db.query(Product).filter(Product.status == "active").count()
    total_tickets = db.query(Ticket).count()
    completed_tickets = db.query(Ticket).filter(Ticket.status == "completed").count()
    open_disputes = db.query(Dispute).filter(Dispute.status.in_(["open", "under_review"])).count()
    pending_sellers = db.query(Seller).filter(Seller.verification_status == "pending").count()
    total_volume = db.query(Ticket).filter(Ticket.status == "completed").all()
    volume = sum(t.agreed_price for t in total_volume)
    return {
        "total_users": total_users,
        "total_sellers": total_sellers,
        "total_products": total_products,
        "total_tickets": total_tickets,
        "completed_tickets": completed_tickets,
        "open_disputes": open_disputes,
        "pending_sellers": pending_sellers,
        "total_volume": volume,
    }


@router.get("/sellers")
def list_sellers(
    status: Optional[str] = Query(None),
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    query = db.query(Seller)
    if status:
        query = query.filter(Seller.verification_status == status)
    sellers = query.order_by(Seller.created_at.desc()).all()
    result = []
    for s in sellers:
        user = db.query(User).filter(User.id == s.user_id).first()
        if user:
            result.append({
                "id": str(s.user_id),
                "seller_id": str(s.id),
                "name": user.name,
                "email": user.email,
                "shop_name": s.shop_name,
                "whatsapp": s.whatsapp,
                "description": s.description,
                "rating": s.rating,
                "total_reviews": s.total_reviews,
                "verification_status": s.verification_status,
                "is_active": user.is_active,
                "created_at": s.created_at,
                "bank_name": s.bank_name,
                "account_number": s.account_number,
                "account_name": s.account_name,
            })
    return result


@router.put("/sellers/{seller_user_id}/verify")
def verify_seller(
    seller_user_id: str,
    action: str = Query(...),
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    valid_actions = ["verified", "rejected", "suspended"]
    if action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Action must be one of {valid_actions}")
    seller = db.query(Seller).filter(Seller.user_id == seller_user_id).first()
    if not seller:
        raise HTTPException(status_code=404, detail="Seller not found")
    seller.verification_status = action
    if action == "suspended":
        user = db.query(User).filter(User.id == seller_user_id).first()
        if user:
            user.is_active = False
    elif action == "verified":
        user = db.query(User).filter(User.id == seller_user_id).first()
        if user:
            user.is_active = True
    db.commit()
    return {"message": f"Seller {action}"}


@router.get("/users")
def list_users(
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [{
        "id": str(u.id),
        "name": u.name,
        "email": u.email,
        "role": u.role,
        "is_active": u.is_active,
        "created_at": u.created_at,
    } for u in users]


@router.put("/users/{user_id}/toggle-active")
def toggle_user(
    user_id: str,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = not user.is_active
    db.commit()
    return {"message": "Updated", "is_active": user.is_active}
