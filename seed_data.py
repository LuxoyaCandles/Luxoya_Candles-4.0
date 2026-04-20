"""
Luxoya Candles – Seed Data Script
Run: python seed_data.py
Creates initial categories, sample products, and admin user.
"""

import os
import sys

# Ensure the app context is available
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db, bcrypt
from models import Category, Product, User


def seed():
    app = create_app()
    with app.app_context():
        db.create_all()
        print("Database tables created")

        # --- Admin User ---
        if not User.query.filter_by(email='support@luxoyacandles.com').first():
            admin = User(
                email='support@luxoyacandles.com',
                password_hash=bcrypt.generate_password_hash('Luxoya@123').decode('utf-8'),
                full_name='Admin User',
                role='admin',
                is_active=True,
                is_email_verified=True
            )
            db.session.add(admin)
            print("Admin user created (support@luxoyacandles.com / Luxoya@123)")
        else:
            print("Admin user already exists")

        # ─── Categories ───
        categories_data = [
            {'name': 'Luxury Jar Candles', 'slug': 'luxury-jar-candles', 'description': 'Premium hand-poured luxury jar candles with exquisite fragrances', 'image_url': ''},
            {'name': 'Designer Mould Candles', 'slug': 'designer-mould-candles', 'description': 'Artistically crafted designer mould candles in unique shapes', 'image_url': ''},
            {'name': 'Gift Hampers', 'slug': 'gift-hampers', 'description': 'Beautifully curated candle gift hampers for every occasion', 'image_url': ''},
            {'name': 'Festive Editions', 'slug': 'festive-editions', 'description': 'Limited edition festive candles for Diwali, Christmas & more', 'image_url': ''},
            {'name': 'Wedding & Event Favors', 'slug': 'wedding-event-favors', 'description': 'Elegant candle favors perfect for weddings and special events', 'image_url': ''},
        ]

        cat_map = {}
        for cat_data in categories_data:
            existing = Category.query.filter_by(slug=cat_data['slug']).first()
            if not existing:
                cat = Category(**cat_data)
                db.session.add(cat)
                db.session.flush()
                cat_map[cat_data['slug']] = cat.id
                print(f"  Category: {cat_data['name']}")
            else:
                cat_map[cat_data['slug']] = existing.id
                print(f"  Category exists: {cat_data['name']}")

        # ─── Products ───
        products_data = [
            {
                'name': 'Vanilla & Oud Signature',
                'slug': 'vanilla-oud-signature',
                'description': 'A warm, sophisticated blend of Madagascar vanilla and premium oud wood. Hand-poured in our artisan studio using 100% natural soy wax.',
                'price': 1299.0,
                'sale_price': None,
                'stock': 50,
                'category_slug': 'luxury-jar-candles',
                'weight': '250g',
                'burn_time': '45 hours',
                'fragrance': 'Vanilla & Oud',
                'is_featured': True,
                'image_url': 'https://images.unsplash.com/photo-1602607360922-47951de49a31?w=600'
            },
            {
                'name': 'Rose & Sandalwood Bliss',
                'slug': 'rose-sandalwood-bliss',
                'description': 'Delicate Damask rose meets earthy sandalwood in this calming luxury candle. Perfect for meditation and self-care rituals.',
                'price': 1199.0,
                'sale_price': 999.0,
                'stock': 35,
                'category_slug': 'luxury-jar-candles',
                'weight': '220g',
                'burn_time': '40 hours',
                'fragrance': 'Rose & Sandalwood',
                'is_featured': True,
                'image_url': 'https://images.unsplash.com/photo-1603006905003-be475563bc59?w=600'
            },
            {
                'name': 'Fresh Linen Morning',
                'slug': 'fresh-linen-morning',
                'description': 'Clean, crisp notes of sun-dried linen with hints of white tea. Wake up to a fresh, inviting space every day.',
                'price': 899.0,
                'sale_price': None,
                'stock': 80,
                'category_slug': 'luxury-jar-candles',
                'weight': '200g',
                'burn_time': '35 hours',
                'fragrance': 'Fresh Linen',
                'is_featured': True,
                'image_url': 'https://images.unsplash.com/photo-1572726729207-a78d6feb18d7?w=600'
            },
            {
                'name': 'Amber Noir Collection',
                'slug': 'amber-noir-collection',
                'description': 'Rich amber, black pepper, and musk create a bold, mysterious atmosphere. Our darkest, most dramatic fragrance.',
                'price': 1499.0,
                'sale_price': None,
                'stock': 25,
                'category_slug': 'luxury-jar-candles',
                'weight': '300g',
                'burn_time': '55 hours',
                'fragrance': 'Amber Noir',
                'is_featured': True,
                'image_url': 'https://images.unsplash.com/photo-1608181831718-2501ef3e1420?w=600'
            },
            {
                'name': 'Festive Diwali Set',
                'slug': 'festive-diwali-set',
                'description': 'A curated set of 3 mini candles with traditional Indian fragrances: Mogra, Chandan, and Gulab. Perfect for gifting.',
                'price': 1999.0,
                'sale_price': 1699.0,
                'stock': 40,
                'category_slug': 'gift-hampers',
                'weight': '450g',
                'burn_time': '30 hours',
                'fragrance': 'Mogra, Chandan, Gulab',
                'is_featured': True,
                'image_url': 'https://images.unsplash.com/photo-1607602132700-068b4307fa7e?w=600'
            },
            {
                'name': 'Monsoon Petrichor',
                'slug': 'monsoon-petrichor',
                'description': 'Capture the magical scent of first rain on dry earth. Earthy, warm notes with a hint of wet greenery.',
                'price': 999.0,
                'sale_price': None,
                'stock': 60,
                'category_slug': 'festive-editions',
                'weight': '200g',
                'burn_time': '35 hours',
                'fragrance': 'Petrichor',
                'is_featured': False,
                'image_url': 'https://images.unsplash.com/photo-1597318181409-cf64d0b5d8a2?w=600'
            },
            {
                'name': 'Jasmine Dreams Mini',
                'slug': 'jasmine-dreams-mini',
                'description': 'Pocket-sized luxury with the intoxicating fragrance of Indian jasmine. Ideal for small spaces and travel.',
                'price': 399.0,
                'sale_price': None,
                'stock': 100,
                'category_slug': 'designer-mould-candles',
                'weight': '80g',
                'burn_time': '15 hours',
                'fragrance': 'Jasmine',
                'is_featured': False,
                'image_url': 'https://images.unsplash.com/photo-1616401776206-83ee0c910de5?w=600'
            },
            {
                'name': 'Lavender Serenity',
                'slug': 'lavender-serenity',
                'description': 'French lavender essential oil candle for deep relaxation and restful sleep. Naturally calming and stress-relieving.',
                'price': 1099.0,
                'sale_price': 899.0,
                'stock': 45,
                'category_slug': 'luxury-jar-candles',
                'weight': '220g',
                'burn_time': '40 hours',
                'fragrance': 'Lavender',
                'is_featured': False,
                'image_url': 'https://images.unsplash.com/photo-1599751449128-eb7249c3d6b1?w=600'
            },
        ]

        for p_data in products_data:
            cat_slug = p_data.pop('category_slug')
            p_data['category_id'] = cat_map.get(cat_slug)

            existing = Product.query.filter_by(slug=p_data['slug']).first()
            if not existing:
                product = Product(**p_data)
                db.session.add(product)
                print(f"  Product: {p_data['name']}")
            else:
                print(f"  Product exists: {p_data['name']}")

        db.session.commit()
        print("\nSeed data loaded successfully!")
        print(f"   Categories: {Category.query.count()}")
        print(f"   Products: {Product.query.count()}")
        print(f"   Users: {User.query.count()}")


if __name__ == '__main__':
    seed()
