from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from database import get_db, Dispute, Ticket, User, Seller
from auth_utils import get_current_user, require_role
from pydantic import BaseModel
from typing import Optional
import uuid, json, os
from datetime import datetime

router = APIRouter(prefix="/disputes", tags=["Disputes"])

UPLOAD_DIR = "uploads/disputes"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def dispute_to_dict(d: Dispute, db: Session):
    ticket = db.query(Ticket).filter(Ticket.id == d.ticket_id).first()
    opener = db.query(User).filter(User.id == d.opened_by).first()
    return {
        "id": str(d.id),
        "ticket_id": str(d.ticket_id),
        "txn_id": ticket.txn_id if ticket else None,
        "opened_by": opener.name if opener else None,
        "description": d.description,
        "evidence_urls": json.loads(d.evidence_urls) if d.evidence_urls else [],
        "status": d.status,
        "admin_notes": d.admin_notes,
        "resolved_at": d.resolved_at,
        "created_at": d.created_at,
    }


@router.post("/{ticket_id}/open", status_code=201)
async def open_dispute(
    ticket_id: str,
    description: str = Form(...),
    evidence: list[UploadFile] = File(default=[]),
    current_user: User = Depends(require_role("customer")),
    db: Session = Depends(get_db)
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if str(ticket.customer_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not your ticket")
    if ticket.status == "completed":
        raise HTTPException(status_code=400, detail="Cannot dispute a completed ticket")

    existing = db.query(Dispute).filter(Dispute.ticket_id == ticket_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Dispute already exists for this ticket")

    evidence_urls = []
    for ev in evidence:
        ext = ev.filename.split(".")[-1]
        filename = f"{uuid.uuid4()}.{ext}"
        path = os.path.join(UPLOAD_DIR, filename)
        content = await ev.read()
        with open(path, "wb") as f:
            f.write(content)
        evidence_urls.append(f"/uploads/disputes/{filename}")

    dispute = Dispute(
        id=uuid.uuid4(),
        ticket_id=ticket_id,
        opened_by=current_user.id,
        description=description,
        evidence_urls=json.dumps(evidence_urls),
        status="open",
    )
    db.add(dispute)
    ticket.status = "disputed"
    db.commit()
    db.refresh(dispute)
    return dispute_to_dict(dispute, db)


@router.get("/customer/mine")
def my_disputes(
    current_user: User = Depends(require_role("customer")),
    db: Session = Depends(get_db)
):
    my_ticket_ids = [t.id for t in db.query(Ticket).filter(Ticket.customer_id == current_user.id).all()]
    disputes = db.query(Dispute).filter(Dispute.ticket_id.in_(my_ticket_ids)).all()
    return [dispute_to_dict(d, db) for d in disputes]


@router.get("/admin/all")
def all_disputes(
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    disputes = db.query(Dispute).order_by(Dispute.created_at.desc()).all()
    return [dispute_to_dict(d, db) for d in disputes]


class ResolveDisputeRequest(BaseModel):
    resolution: str  # resolved_refund | resolved_warning | resolved_closed
    admin_notes: str
    action: Optional[str] = None  # suspend_seller | warn_seller | nothing


@router.put("/{dispute_id}/resolve")
def resolve_dispute(
    dispute_id: str,
    payload: ResolveDisputeRequest,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    dispute = db.query(Dispute).filter(Dispute.id == dispute_id).first()
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")

    valid_resolutions = ["resolved_refund", "resolved_warning", "resolved_closed"]
    if payload.resolution not in valid_resolutions:
        raise HTTPException(status_code=400, detail=f"Resolution must be one of {valid_resolutions}")

    dispute.status = payload.resolution
    dispute.admin_notes = payload.admin_notes
    dispute.resolved_at = datetime.utcnow()

    ticket = db.query(Ticket).filter(Ticket.id == dispute.ticket_id).first()
    if ticket:
        ticket.status = "cancelled" if payload.resolution == "resolved_refund" else "completed"

    # Optional admin action on seller
    if payload.action == "suspend_seller" and ticket:
        seller_user = db.query(User).filter(User.id == ticket.seller_id).first()
        if seller_user:
            seller_user.is_active = False
            seller_profile = db.query(Seller).filter(Seller.user_id == ticket.seller_id).first()
            if seller_profile:
                seller_profile.verification_status = "suspended"

    db.commit()
    return {"message": "Dispute resolved", "dispute": dispute_to_dict(dispute, db)}
