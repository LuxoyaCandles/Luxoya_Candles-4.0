from app import create_app
from extensions import db
from models import Category, Product, RawMaterial, User, SiteSettings
import os

def seed():
    app = create_app()
    with app.app_context():
        # 1. Create Tables
        db.create_all()
        
        # 2. Add Admin User if missing
        admin = User.query.filter_by(email='sales@luxoyacandles.com').first()
        if not admin:
            admin = User(
                email='sales@luxoyacandles.com',
                full_name='Luxoya Admin',
                role='admin'
            )
            admin.set_password('Luxoya2026!')
            db.session.add(admin)
            print("Admin user created.")

        # 3. Add Categories if missing
        cat_data = [
            {'name': 'Luxury Jar Candles', 'slug': 'luxury-jar-candles', 'description': 'Premium soy wax in designer glass Jars.'},
            {'name': 'Designer Mould Candles', 'slug': 'designer-mould-candles', 'description': 'Artistic shapes and intricate designs.'},
            {'name': 'Festive Editions', 'slug': 'festive-editions', 'description': 'Limited scents for celebration.'},
            {'name': 'Gift Hampers', 'slug': 'gift-hampers', 'description': 'Curated luxury sets for gifting.'}
        ]
        
        cats = {}
        for c in cat_data:
            cat = Category.query.filter_by(slug=c['slug']).first()
            if not cat:
                cat = Category(**c)
                db.session.add(cat)
                db.session.flush() # Get ID
                print(f"Category added: {c['name']}")
            cats[c['slug']] = cat

        # 4. Add Products if missing
        product_data = [
            {
                'name': 'Midnight Noir Suede', 
                'slug': 'midnight-noir-suede', 
                'description': 'A deep, sophisticated blend of night-blooming jasmine and weathered leather.',
                'price': 1499, 
                'category_slug': 'luxury-jar-candles',
                'stock': 50,
                'image_url': '/static/images/hero-luxury-candle.png'
            },
            {
                'name': 'Vanilla Bloom Jar', 
                'slug': 'vanilla-bloom-jar', 
                'description': 'Warm Madagascar vanilla beans with a hint of orchid.',
                'price': 1299, 
                'category_slug': 'luxury-jar-candles',
                'stock': 100,
                'image_url': '/static/images/luxury-candle-product.png'
            },
            {
                'name': 'Abstract Bloom Mould', 
                'slug': 'abstract-bloom-mould', 
                'description': 'Hand-poured designer mould candle in ivory white.',
                'price': 899, 
                'category_slug': 'designer-mould-candles',
                'stock': 30,
                'image_url': '/static/images/luxury-candle-product.png'
            },
            {
                'name': 'Signature Luxury Hamper', 
                'slug': 'signature-luxury-hamper', 
                'description': 'The ultimate gifting experience with three signature jars.',
                'price': 3499, 
                'category_slug': 'gift-hampers',
                'stock': 15,
                'image_url': '/static/images/hero-luxury-candle.png'
            }
        ]
        
        for p in product_data:
            prod = Product.query.filter_by(slug=p['slug']).first()
            if not prod:
                cat_slug = p.pop('category_slug')
                p['category_id'] = cats[cat_slug].id
                prod = Product(**p)
                db.session.add(prod)
                print(f"Product added: {p['name']}")

        # 5. Add Site Settings if missing
        settings_data = {
            'slider_img_1': '/static/images/hero-luxury-candle.png',
            'slider_img_2': '/static/images/luxury-candle-product.png',
            'custom_studio_img': '/static/images/hero-luxury-candle.png',
            'promo_limit_img': '/static/images/hero-luxury-candle.png',
            'gift_hampers_img_1': '/static/images/luxury-candle-product.png',
            'gift_hampers_img_2': '/static/images/hero-luxury-candle.png',
            'coll_img_1': '/static/images/luxury-candle-product.png',
            'coll_slug_1': 'luxury-jar-candles',
            'coll_img_2': '/static/images/hero-luxury-candle.png',
            'coll_slug_2': 'designer-mould-candles',
            'coll_img_3': '/static/images/luxury-candle-product.png',
            'coll_slug_3': 'festive-editions',
            'coll_img_4': '/static/images/hero-luxury-candle.png',
            'coll_slug_4': 'luxury-jar-candles',
            'coll_img_5': '/static/images/luxury-candle-product.png',
            'coll_slug_5': 'gift-hampers',
            'coll_img_6': '/static/images/hero-luxury-candle.png',
            'coll_slug_6': 'new-arrivals',
        }
        
        for k, v in settings_data.items():
            s = SiteSettings.query.filter_by(key=k).first()
            if not s:
                s = SiteSettings(key=k, value=v)
                db.session.add(s)
            else:
                s.value = v # Update to premium images
        
        db.session.commit()
        print("Success: Luxoya database updated with premium initial data and settings!")

if __name__ == '__main__':
    seed()
