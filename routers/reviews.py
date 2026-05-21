from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db, Review, Ticket, User, Seller
from auth_utils import require_role
from pydantic import BaseModel
from typing import Optional
import uuid

router = APIRouter(prefix="/reviews", tags=["Reviews"])


class ReviewRequest(BaseModel):
    ticket_id: str
    rating: int  # 1-5
    comment: Optional[str] = None


@router.post("/", status_code=201)
def leave_review(
    payload: ReviewRequest,
    current_user: User = Depends(require_role("customer")),
    db: Session = Depends(get_db)
):
    if payload.rating < 1 or payload.rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be 1-5")

    ticket = db.query(Ticket).filter(
        Ticket.id == payload.ticket_id,
        Ticket.customer_id == current_user.id,
        Ticket.status == "completed"
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Completed ticket not found")

    existing = db.query(Review).filter(Review.ticket_id == payload.ticket_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already reviewed this order")

    review = Review(
        id=uuid.uuid4(),
        ticket_id=payload.ticket_id,
        customer_id=current_user.id,
        seller_id=ticket.seller_id,
        rating=payload.rating,
        comment=payload.comment,
    )
    db.add(review)

    # Update seller rating
    seller_profile = db.query(Seller).filter(Seller.user_id == ticket.seller_id).first()
    if seller_profile:
        all_reviews = db.query(Review).filter(Review.seller_id == ticket.seller_id).all()
        total = sum(r.rating for r in all_reviews) + payload.rating
        count = len(all_reviews) + 1
        seller_profile.rating = round(total / count, 2)
        seller_profile.total_reviews = count

    db.commit()
    return {"message": "Review submitted", "rating": payload.rating}


@router.get("/seller/{seller_id}")
def seller_reviews(seller_id: str, db: Session = Depends(get_db)):
    reviews = db.query(Review).filter(Review.seller_id == seller_id).all()
    result = []
    for r in reviews:
        customer = db.query(User).filter(User.id == r.customer_id).first()
        result.append({
            "id": str(r.id),
            "rating": r.rating,
            "comment": r.comment,
            "customer_name": customer.name if customer else "Anonymous",
            "created_at": r.created_at,
        })
    return result
