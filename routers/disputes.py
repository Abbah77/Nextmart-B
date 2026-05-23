from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from database import get_db, Dispute, Ticket, User, Seller
from auth_utils import get_current_user, require_role
from pydantic import BaseModel
from typing import Optional
import uuid, json, os
from datetime import datetime
from PIL import Image
import io

router = APIRouter(prefix="/disputes", tags=["Disputes"])

UPLOAD_DIR = "uploads/disputes"
os.makedirs(UPLOAD_DIR, exist_ok=True)

MAX_IMG_SIDE = 1200  # px
JPEG_QUALITY = 78


def compress_image(content: bytes, filename: str) -> bytes:
    """Compress image to reduce storage size while keeping decent quality"""
    try:
        img = Image.open(io.BytesIO(content))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        # Resize if larger than max side
        w, h = img.size
        if max(w, h) > MAX_IMG_SIDE:
            ratio = MAX_IMG_SIDE / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return buf.getvalue()
    except Exception:
        return content  # fallback: return original


def dispute_to_dict(d: Dispute, db: Session):
    ticket = db.query(Ticket).filter(Ticket.id == d.ticket_id).first()
    opener = db.query(User).filter(User.id == d.opened_by).first()
    seller_info = None
    if ticket:
        seller = db.query(User).filter(User.id == ticket.seller_id).first()
        seller_profile = db.query(Seller).filter(Seller.user_id == ticket.seller_id).first()
        if seller:
            seller_info = {
                "id": str(seller.id),
                "name": seller.name,
                "email": seller.email,
                "shop_name": seller_profile.shop_name if seller_profile else None,
                "whatsapp": seller_profile.whatsapp if seller_profile else None,
            }
    return {
        "id": str(d.id),
        "ticket_id": str(d.ticket_id),
        "txn_id": ticket.txn_id if ticket else None,
        "agreed_price": ticket.agreed_price if ticket else None,
        "product_title": ticket.product.title if ticket and ticket.product else None,
        "opened_by": opener.name if opener else None,
        "opened_by_id": str(d.opened_by),
        "description": d.description,
        "evidence_urls": json.loads(d.evidence_urls) if d.evidence_urls else [],
        "status": d.status,
        "admin_notes": d.admin_notes,
        "resolution_action": d.resolution_action,
        "resolved_at": d.resolved_at,
        "created_at": d.created_at,
        "seller": seller_info,
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
        content = await ev.read()
        # Compress images
        if ev.content_type and ev.content_type.startswith("image/"):
            content = compress_image(content, ev.filename)
            filename = f"{uuid.uuid4()}.jpg"
        else:
            ext = ev.filename.split(".")[-1] if "." in ev.filename else "bin"
            filename = f"{uuid.uuid4()}.{ext}"
        path = os.path.join(UPLOAD_DIR, filename)
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


@router.put("/{dispute_id}/mark-reviewing")
def mark_under_review(
    dispute_id: str,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    dispute = db.query(Dispute).filter(Dispute.id == dispute_id).first()
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")
    dispute.status = "under_review"
    db.commit()
    return {"message": "Marked as under review"}


class ResolveDisputeRequest(BaseModel):
    resolution: str  # resolved_refund | resolved_warning | resolved_closed
    admin_notes: str
    action: Optional[str] = "nothing"  # suspend_seller | warn_seller | nothing


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
    dispute.resolution_action = payload.action
    dispute.resolved_at = datetime.utcnow()

    ticket = db.query(Ticket).filter(Ticket.id == dispute.ticket_id).first()
    if ticket:
        ticket.status = "cancelled" if payload.resolution == "resolved_refund" else "completed"

    # Admin action on seller
    if payload.action == "suspend_seller" and ticket:
        seller_user = db.query(User).filter(User.id == ticket.seller_id).first()
        if seller_user:
            seller_user.is_active = False
            seller_profile = db.query(Seller).filter(Seller.user_id == ticket.seller_id).first()
            if seller_profile:
                seller_profile.verification_status = "suspended"

    # Clean up evidence files after resolution
    try:
        if dispute.evidence_urls:
            urls = json.loads(dispute.evidence_urls)
            for url in urls:
                path = url.lstrip("/")
                if os.path.exists(path):
                    os.remove(path)
        dispute.evidence_urls = json.dumps([])
    except Exception:
        pass

    db.commit()
    return {"message": "Dispute resolved", "dispute": dispute_to_dict(dispute, db)}
