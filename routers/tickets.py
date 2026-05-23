from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db, Ticket, Product, User, Seller
from auth_utils import get_current_user, require_role
from pydantic import BaseModel
from typing import Optional
import uuid, random, string
from datetime import datetime

router = APIRouter(prefix="/tickets", tags=["Tickets"])


def generate_txn_id():
    chars = string.ascii_uppercase + string.digits
    suffix = ''.join(random.choices(chars, k=8))
    return f"TXN-{suffix}"


def ticket_to_dict(t: Ticket, db: Session):
    product = db.query(Product).filter(Product.id == t.product_id).first()
    seller = db.query(User).filter(User.id == t.seller_id).first()
    seller_profile = db.query(Seller).filter(Seller.user_id == t.seller_id).first()
    customer = db.query(User).filter(User.id == t.customer_id).first() if t.customer_id else None
    return {
        "id": str(t.id),
        "txn_id": t.txn_id,
        "status": t.status,
        "agreed_price": t.agreed_price,
        "customer_reference": t.customer_reference,
        "tracking_info": t.tracking_info,
        "notes": t.notes,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
        "product": {
            "id": str(product.id) if product else None,
            "title": product.title if product else None,
            "price": product.price if product else None,
        },
        "seller": {
            "id": str(seller.id) if seller else None,
            "name": seller.name if seller else None,
            "email": seller.email if seller else None,
            "whatsapp": seller_profile.whatsapp if seller_profile else None,
            "shop_name": seller_profile.shop_name if seller_profile else None,
        },
        "customer": {
            "id": str(customer.id) if customer else None,
            "name": customer.name if customer else None,
        } if customer else None,
    }


class CreateTicketRequest(BaseModel):
    product_id: str
    agreed_price: float
    customer_reference: str
    notes: Optional[str] = None


@router.post("/", status_code=201)
def create_ticket(
    payload: CreateTicketRequest,
    current_user: User = Depends(require_role("seller")),
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(
        Product.id == payload.product_id,
        Product.seller_id == current_user.id
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found or not yours")

    txn_id = generate_txn_id()
    while db.query(Ticket).filter(Ticket.txn_id == txn_id).first():
        txn_id = generate_txn_id()

    ticket = Ticket(
        id=uuid.uuid4(),
        txn_id=txn_id,
        seller_id=current_user.id,
        product_id=payload.product_id,
        agreed_price=payload.agreed_price,
        customer_reference=payload.customer_reference,
        notes=payload.notes,
        status="pending_payment",
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket_to_dict(ticket, db)


@router.get("/lookup/{txn_id}")
def lookup_ticket(
    txn_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    ticket = db.query(Ticket).filter(Ticket.txn_id == txn_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket_to_dict(ticket, db)


@router.post("/claim/{txn_id}")
def claim_ticket(
    txn_id: str,
    current_user: User = Depends(require_role("customer")),
    db: Session = Depends(get_db)
):
    ticket = db.query(Ticket).filter(Ticket.txn_id == txn_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.customer_id:
        raise HTTPException(status_code=400, detail="Ticket already claimed")
    ticket.customer_id = current_user.id
    db.commit()
    return ticket_to_dict(ticket, db)


@router.get("/customer/mine")
def my_customer_tickets(
    current_user: User = Depends(require_role("customer")),
    db: Session = Depends(get_db)
):
    tickets = db.query(Ticket).filter(Ticket.customer_id == current_user.id).order_by(Ticket.created_at.desc()).all()
    return [ticket_to_dict(t, db) for t in tickets]


@router.get("/seller/mine")
def my_seller_tickets(
    current_user: User = Depends(require_role("seller")),
    db: Session = Depends(get_db)
):
    tickets = db.query(Ticket).filter(Ticket.seller_id == current_user.id).order_by(Ticket.created_at.desc()).all()
    return [ticket_to_dict(t, db) for t in tickets]


class UpdateStatusRequest(BaseModel):
    status: str
    tracking_info: Optional[str] = None


SELLER_ALLOWED_STATUSES = ["processing", "shipped", "arrived"]


@router.put("/{ticket_id}/status")
def update_ticket_status(
    ticket_id: str,
    payload: UpdateStatusRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if current_user.role == "seller":
        if str(ticket.seller_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="Not your ticket")
        if payload.status not in SELLER_ALLOWED_STATUSES + ["payment_confirmed"]:
            raise HTTPException(status_code=400, detail=f"Seller can only set: {SELLER_ALLOWED_STATUSES + ['payment_confirmed']}")

    elif current_user.role == "customer":
        if str(ticket.customer_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="Not your ticket")
        if payload.status != "delivered":
            raise HTTPException(status_code=400, detail="Customer can only confirm delivery")
        if ticket.status != "arrived":
            raise HTTPException(status_code=400, detail="Item must be marked arrived before confirming delivery")
        payload.status = "completed"

    elif current_user.role == "admin":
        pass

    ticket.status = payload.status
    if payload.tracking_info:
        ticket.tracking_info = payload.tracking_info
    ticket.updated_at = datetime.utcnow()
    db.commit()
    return ticket_to_dict(ticket, db)


@router.get("/admin/all")
def all_tickets(
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    tickets = db.query(Ticket).order_by(Ticket.created_at.desc()).all()
    return [ticket_to_dict(t, db) for t in tickets]


@router.get("/{ticket_id}")
def get_ticket(
    ticket_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if current_user.role == "customer" and str(ticket.customer_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")
    if current_user.role == "seller" and str(ticket.seller_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    return ticket_to_dict(ticket, db)
