from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from database import get_db, Product, User, Seller
from auth_utils import get_current_user, require_role
from pydantic import BaseModel
from typing import Optional, List
import uuid, json, os
from datetime import datetime

router = APIRouter(prefix="/products", tags=["Products"])

UPLOAD_DIR = "uploads/products"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def product_to_dict(p: Product, db: Session):
    seller = db.query(User).filter(User.id == p.seller_id).first()
    seller_profile = db.query(Seller).filter(Seller.user_id == p.seller_id).first()
    return {
        "id": str(p.id),
        "title": p.title,
        "description": p.description,
        "price": p.price,
        "category": p.category,
        "images": json.loads(p.images) if p.images else [],
        "whatsapp": p.whatsapp,
        "status": p.status,
        "created_at": p.created_at,
        "seller": {
            "id": str(seller.id) if seller else None,
            "name": seller.name if seller else None,
            "shop_name": seller_profile.shop_name if seller_profile else None,
            "rating": seller_profile.rating if seller_profile else 0,
            "whatsapp": seller_profile.whatsapp if seller_profile else None,
        }
    }


# ── PUBLIC: Browse marketplace ──────────────────────────────────────────────

@router.get("/")
def list_products(
    category: Optional[str] = None,
    search: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    db: Session = Depends(get_db)
):
    q = db.query(Product).filter(Product.status == "active")
    if category:
        q = q.filter(Product.category.ilike(f"%{category}%"))
    if search:
        q = q.filter(Product.title.ilike(f"%{search}%"))
    if min_price is not None:
        q = q.filter(Product.price >= min_price)
    if max_price is not None:
        q = q.filter(Product.price <= max_price)
    products = q.order_by(Product.created_at.desc()).all()
    return [product_to_dict(p, db) for p in products]


@router.get("/{product_id}")
def get_product(product_id: str, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == product_id, Product.status == "active").first()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    return product_to_dict(p, db)


# ── SELLER: Manage own products ──────────────────────────────────────────────

@router.get("/seller/mine")
def my_products(
    current_user: User = Depends(require_role("seller", "admin")),
    db: Session = Depends(get_db)
):
    products = db.query(Product).filter(Product.seller_id == current_user.id).all()
    return [product_to_dict(p, db) for p in products]


@router.post("/", status_code=201)
async def create_product(
    title: str = Form(...),
    description: str = Form(""),
    price: float = Form(...),
    category: str = Form("General"),
    whatsapp: str = Form(...),
    images: List[UploadFile] = File(default=[]),
    current_user: User = Depends(require_role("seller")),
    db: Session = Depends(get_db)
):
    seller_profile = db.query(Seller).filter(Seller.user_id == current_user.id).first()
    if not seller_profile or seller_profile.verification_status != "verified":
        raise HTTPException(status_code=403, detail="Your seller account must be verified before listing products")

    image_urls = []
    for img in images:
        ext = img.filename.split(".")[-1]
        filename = f"{uuid.uuid4()}.{ext}"
        path = os.path.join(UPLOAD_DIR, filename)
        content = await img.read()
        with open(path, "wb") as f:
            f.write(content)
        image_urls.append(f"/uploads/products/{filename}")

    product = Product(
        id=uuid.uuid4(),
        seller_id=current_user.id,
        title=title,
        description=description,
        price=price,
        category=category,
        whatsapp=whatsapp,
        images=json.dumps(image_urls),
        status="active",
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product_to_dict(product, db)


@router.put("/{product_id}")
def update_product(
    product_id: str,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    price: Optional[float] = Form(None),
    category: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
    current_user: User = Depends(require_role("seller", "admin")),
    db: Session = Depends(get_db)
):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    if current_user.role == "seller" and str(p.seller_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not your product")

    if title: p.title = title
    if description: p.description = description
    if price: p.price = price
    if category: p.category = category
    if status and status in ["active", "inactive"]: p.status = status

    db.commit()
    return {"message": "Product updated"}


@router.delete("/{product_id}")
def delete_product(
    product_id: str,
    current_user: User = Depends(require_role("seller", "admin")),
    db: Session = Depends(get_db)
):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    if current_user.role == "seller" and str(p.seller_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not your product")
    p.status = "deleted"
    db.commit()
    return {"message": "Product deleted"}
