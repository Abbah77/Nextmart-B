from sqlalchemy import create_engine, Column, String, Float, Integer, Boolean, DateTime, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── MODELS ───────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(SAEnum("customer", "seller", "admin", name="user_role"), default="customer")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    seller_profile = relationship("Seller", back_populates="user", uselist=False)
    products = relationship("Product", back_populates="seller_user")
    customer_tickets = relationship("Ticket", foreign_keys="Ticket.customer_id", back_populates="customer")
    seller_tickets = relationship("Ticket", foreign_keys="Ticket.seller_id", back_populates="seller")


class Seller(Base):
    __tablename__ = "sellers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True)
    whatsapp = Column(String(30), nullable=False)
    shop_name = Column(String(100))
    description = Column(Text)
    verification_status = Column(SAEnum("pending", "verified", "rejected", "suspended", name="seller_status"), default="pending")
    rating = Column(Float, default=0.0)
    total_reviews = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Payment account details (new)
    bank_name = Column(String(100))
    account_number = Column(String(30))
    account_name = Column(String(100))
    opay_number = Column(String(30))
    palmpay_number = Column(String(30))

    user = relationship("User", back_populates="seller_profile")


class Product(Base):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    title = Column(String(200), nullable=False)
    description = Column(Text)
    price = Column(Float, nullable=False)
    category = Column(String(100))
    images = Column(Text)  # JSON array of image URLs
    whatsapp = Column(String(30))
    status = Column(SAEnum("active", "inactive", "deleted", name="product_status"), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)

    seller_user = relationship("User", back_populates="products")
    tickets = relationship("Ticket", back_populates="product")


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    txn_id = Column(String(20), unique=True, nullable=False)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    customer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"))
    agreed_price = Column(Float, nullable=False)
    customer_reference = Column(String(200))
    notes = Column(Text)
    status = Column(
        SAEnum(
            "pending_payment", "payment_confirmed",
            "processing", "shipped", "arrived", "completed",
            "disputed", "cancelled",
            name="ticket_status"
        ),
        default="pending_payment"
    )
    tracking_info = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    seller = relationship("User", foreign_keys=[seller_id], back_populates="seller_tickets")
    customer = relationship("User", foreign_keys=[customer_id], back_populates="customer_tickets")
    product = relationship("Product", back_populates="tickets")
    dispute = relationship("Dispute", back_populates="ticket", uselist=False)


class Dispute(Base):
    __tablename__ = "disputes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), unique=True)
    opened_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    description = Column(Text, nullable=False)
    evidence_urls = Column(Text)  # JSON array
    status = Column(SAEnum("open", "under_review", "resolved_refund", "resolved_warning", "resolved_closed", name="dispute_status"), default="open")
    admin_notes = Column(Text)
    resolution_action = Column(String(50))  # warn_seller, suspend_seller, nothing
    resolved_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    ticket = relationship("Ticket", back_populates="dispute")


class Review(Base):
    __tablename__ = "reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"))
    customer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    seller_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    rating = Column(Integer, nullable=False)  # 1-5
    comment = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
