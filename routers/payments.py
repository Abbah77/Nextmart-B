from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from database import get_db, Ticket, User
from auth_utils import get_current_user, require_role
import uuid, os
from datetime import datetime

router = APIRouter(prefix="/payments", tags=["Payments"])

UPLOAD_DIR = "uploads/payments"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/{ticket_id}/upload-proof")
async def upload_payment_proof(
    ticket_id: str,
    proof: UploadFile = File(...),
    current_user: User = Depends(require_role("customer")),
    db: Session = Depends(get_db)
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if str(ticket.customer_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not your ticket")
    if ticket.status not in ["pending_payment", "payment_uploaded"]:
        raise HTTPException(status_code=400, detail="Payment already confirmed or ticket closed")

    ext = proof.filename.split(".")[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    path = os.path.join(UPLOAD_DIR, filename)
    content = await proof.read()
    with open(path, "wb") as f:
        f.write(content)

    ticket.payment_proof_url = f"/uploads/payments/{filename}"
    ticket.status = "payment_uploaded"
    ticket.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Payment proof uploaded", "proof_url": ticket.payment_proof_url}


@router.post("/{ticket_id}/confirm")
def confirm_payment(
    ticket_id: str,
    current_user: User = Depends(require_role("seller")),
    db: Session = Depends(get_db)
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if str(ticket.seller_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not your ticket")
    if ticket.status != "payment_uploaded":
        raise HTTPException(status_code=400, detail="No payment proof uploaded yet")

    ticket.status = "payment_confirmed"
    ticket.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Payment confirmed. Start processing the order."}


@router.post("/{ticket_id}/reject-proof")
def reject_payment_proof(
    ticket_id: str,
    current_user: User = Depends(require_role("seller")),
    db: Session = Depends(get_db)
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if str(ticket.seller_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not your ticket")

    ticket.payment_proof_url = None
    ticket.status = "pending_payment"
    ticket.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Payment proof rejected. Customer must re-upload."}
