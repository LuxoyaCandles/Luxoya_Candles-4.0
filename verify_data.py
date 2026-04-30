
from app import create_app
from models import Product, User
from extensions import db

app = create_app()
with app.app_context():
    print("--- PRODUCTS ---")
    products = Product.query.limit(5).all()
    for p in products:
        print(f"ID: {p.id}, Name: {p.name}, Image: {p.image_url}, Video: {p.video_url}")
    
    print("\n--- USERS ---")
    users = User.query.limit(5).all()
    for u in users:
        print(f"Email: {u.email}, Referral: {u.referral_code}, Points: {u.loyalty_points}")
