from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db, Ticket, User
from auth_utils import get_current_user, require_role
from datetime import datetime

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/{ticket_id}/confirm")
def confirm_payment(
    ticket_id: str,
    current_user: User = Depends(require_role("seller")),
    db: Session = Depends(get_db)
):
    """Seller manually confirms payment after customer sends proof via WhatsApp"""
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if str(ticket.seller_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not your ticket")
    if ticket.status != "pending_payment":
        raise HTTPException(status_code=400, detail="Ticket is not awaiting payment")

    ticket.status = "payment_confirmed"
    ticket.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Payment confirmed. Start processing the order."}
