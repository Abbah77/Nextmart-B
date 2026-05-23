from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from database import get_db, Product, User, Seller
from auth_utils import get_current_user, require_role
from typing import Optional
import uuid, json, os
from PIL import Image
import io

router = APIRouter(prefix="/products", tags=["Products"])

UPLOAD_DIR = "uploads/products"
os.makedirs(UPLOAD_DIR, exist_ok=True)

MAX_IMG_SIDE = 1000
JPEG_QUALITY = 80


def compress_image(content: bytes) -> bytes:
    try:
        img = Image.open(io.BytesIO(content))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > MAX_IMG_SIDE:
            ratio = MAX_IMG_SIDE / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return buf.getvalue()
    except Exception:
        return content


def product_to_dict(p: Product, db: Session):
    seller_user = db.query(User).filter(User.id == p.seller_id).first()
    seller_profile = db.query(Seller).filter(Seller.user_id == p.seller_id).first()
    return {
        "id": str(p.id),
        "title": p.title,
        "description": p.description,
        "price": p.price,
        "category": p.category,
        "whatsapp": p.whatsapp,
        "images": json.loads(p.images) if p.images else [],
        "status": p.status,
        "created_at": p.created_at,
        "seller": {
            "id": str(seller_user.id) if seller_user else None,
            "name": seller_user.name if seller_user else None,
            "shop_name": seller_profile.shop_name if seller_profile else None,
            "rating": seller_profile.rating if seller_profile else 0.0,
            "total_reviews": seller_profile.total_reviews if seller_profile else 0,
            "whatsapp": seller_profile.whatsapp if seller_profile else p.whatsapp,
        }
    }


@router.get("/")
def list_products(
    q: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Product).filter(Product.status == "active")
    if category:
        query = query.filter(Product.category == category)
    if q:
        query = query.filter(Product.title.ilike(f"%{q}%"))
    products = query.order_by(Product.created_at.desc()).all()
    return [product_to_dict(p, db) for p in products]


@router.get("/seller/mine")
def my_products(
    current_user: User = Depends(require_role("seller")),
    db: Session = Depends(get_db)
):
    products = db.query(Product).filter(
        Product.seller_id == current_user.id,
        Product.status != "deleted"
    ).order_by(Product.created_at.desc()).all()
    return [product_to_dict(p, db) for p in products]


@router.post("/", status_code=201)
async def create_product(
    title: str = Form(...),
    price: float = Form(...),
    description: str = Form(""),
    category: str = Form("Other"),
    whatsapp: str = Form(...),
    images: list[UploadFile] = File(default=[]),
    current_user: User = Depends(require_role("seller")),
    db: Session = Depends(get_db)
):
    seller_profile = db.query(Seller).filter(Seller.user_id == current_user.id).first()
    if not seller_profile or seller_profile.verification_status != "verified":
        raise HTTPException(status_code=403, detail="Your seller account must be verified to list products")

    image_urls = []
    for img in images:
        content = await img.read()
        content = compress_image(content)
        filename = f"{uuid.uuid4()}.jpg"
        path = os.path.join(UPLOAD_DIR, filename)
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
async def update_product(
    product_id: str,
    title: str = Form(None),
    price: float = Form(None),
    description: str = Form(None),
    category: str = Form(None),
    whatsapp: str = Form(None),
    images: list[UploadFile] = File(default=[]),
    current_user: User = Depends(require_role("seller")),
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.seller_id == current_user.id
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if title is not None: product.title = title
    if price is not None: product.price = price
    if description is not None: product.description = description
    if category is not None: product.category = category
    if whatsapp is not None: product.whatsapp = whatsapp

    if images:
        image_urls = []
        for img in images:
            content = await img.read()
            content = compress_image(content)
            filename = f"{uuid.uuid4()}.jpg"
            path = os.path.join(UPLOAD_DIR, filename)
            with open(path, "wb") as f:
                f.write(content)
            image_urls.append(f"/uploads/products/{filename}")
        product.images = json.dumps(image_urls)

    db.commit()
    return product_to_dict(product, db)


@router.put("/{product_id}/toggle-status")
def toggle_product_status(
    product_id: str,
    current_user: User = Depends(require_role("seller")),
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.seller_id == current_user.id
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.status = "inactive" if product.status == "active" else "active"
    db.commit()
    return product_to_dict(product, db)


@router.delete("/{product_id}")
def delete_product(
    product_id: str,
    current_user: User = Depends(require_role("seller")),
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.seller_id == current_user.id
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.status = "deleted"
    db.commit()
    return {"message": "Product deleted"}


@router.get("/{product_id}")
def get_product(product_id: str, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id, Product.status == "active").first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product_to_dict(product, db)
