
from app import app
from models import Product, db

with app.app_context():
    prods = Product.query.all()
    for p in prods:
        print(f"ID: {p.id} | Name: {p.name} | Video: {p.video_url}")
