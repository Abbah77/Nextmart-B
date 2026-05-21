from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from database import Base, engine
from routers import auth, products, tickets, payments, disputes, admin, reviews
import os

# Create all tables
Base.metadata.create_all(bind=engine)

# Create upload dirs
for d in ["uploads/products", "uploads/payments", "uploads/disputes"]:
    os.makedirs(d, exist_ok=True)

app = FastAPI(
    title="Nextmart API",
    description="WhatsApp Commerce + Trust Infrastructure",
    version="1.0.0"
)

# CORS — update origins for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace with your frontend domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static file serving for uploads
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Routers
app.include_router(auth.router)
app.include_router(products.router)
app.include_router(tickets.router)
app.include_router(payments.router)
app.include_router(disputes.router)
app.include_router(admin.router)
app.include_router(reviews.router)


@app.get("/")
def root():
    return {"message": "Nextmart API is running", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok"}
