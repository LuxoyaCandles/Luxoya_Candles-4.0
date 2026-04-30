import os
import sys
import traceback
from flask import Flask, render_template, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

from config import config
from extensions import db, jwt, bcrypt, migrate, csrf
# No module-level model imports (Lazy loading for Vercel stability)


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(base_dir, 'templates')
    static_dir = os.path.join(base_dir, 'static')
    
    app = Flask(__name__, 
                template_folder=template_dir,
                static_folder=static_dir, 
                static_url_path='/static')
    app.config.from_object(config[config_name])
    
    # Call init_app if the config class defines one (e.g., ProductionConfig)
    config_class = config[config_name]
    if hasattr(config_class, 'init_app'):
        config_class.init_app(app)
    
    # Initialize extensions
    db.init_app(app)
    jwt.init_app(app)
    bcrypt.init_app(app)
    csrf.init_app(app)  # Required: registers csrf_token() in templates
    app.config['WTF_CSRF_ENABLED'] = False  # Disables enforcement, not the helper
    CORS(app, supports_credentials=True)
    
    # Only use Flask-Migrate locally (not on Vercel)
    is_vercel = os.environ.get('VERCEL', '') == '1'
    if not is_vercel:
        migrate.init_app(app, db)
    
    # Exempt API routes from CSRF (they use JWT)
    # Must pass actual Blueprint objects, not strings
    
    # Register blueprints (Strict isolated registration)
    from routes.auth import auth_bp
    from routes.products import products_bp
    from routes.cart import cart_bp
    from routes.orders import orders_bp
    from routes.admin import admin_bp
    from routes.b2b import b2b_bp
    from routes.chat import chat_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(b2b_bp)
    app.register_blueprint(chat_bp)
    
    # Create upload directory
    try:
        os.makedirs(app.config.get('UPLOAD_FOLDER', 'static/uploads'), exist_ok=True)
    except OSError:
        pass  # Read-only filesystem (Vercel)
    
    # Serve images stored in the database (ImageStore)
    from flask import send_from_directory, abort, Response, make_response
    @app.route('/img/store/<image_id>')
    def serve_db_image(image_id):
        from models import ImageStore
        record = db.session.get(ImageStore, image_id)
        if not record:
            placeholder = os.path.join(app.static_folder, 'img', 'placeholder.jpg')
            if os.path.exists(placeholder):
                return send_from_directory(os.path.join(app.static_folder, 'img'), 'placeholder.jpg')
            abort(404)
        resp = make_response(record.data)
        resp.headers['Content-Type'] = record.content_type or 'image/webp'
        resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        resp.headers['ETag'] = image_id
        return resp

    # Serve uploaded files from UPLOAD_FOLDER (legacy fallback)
    @app.route('/uploads/<path:filename>')
    def serve_upload(filename):
        upload_folder = app.config.get('UPLOAD_FOLDER', 'static/uploads')
        filepath = os.path.join(upload_folder, filename)
        if os.path.exists(filepath):
            return send_from_directory(upload_folder, filename)
        placeholder = os.path.join(app.static_folder, 'img', 'placeholder.jpg')
        if os.path.exists(placeholder):
            return send_from_directory(os.path.join(app.static_folder, 'img'), 'placeholder.jpg')
        abort(404)
    
    # JWT handlers
    @jwt.user_identity_loader
    def user_identity_lookup(user_id):
        return user_id
    
    @jwt.user_lookup_loader
    def user_lookup_callback(_jwt_header, jwt_data):
        from models import User
        identity = jwt_data["sub"]
        return db.session.get(User, identity)
    
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({'error': 'Token has expired', 'login_required': True}), 401
    
    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({'error': 'Invalid token', 'login_required': True}), 401
    
    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return jsonify({'error': 'Authorization required', 'login_required': True}), 401
    
    # Context processor - Static mode (user detection done client-side via JS)
    @app.context_processor
    def inject_globals():
        branding = {
            'org_name': 'Luxoya Candles',
            'org_phone': '+91 9705840457',
            'org_email': 'sales@luxoyacandles.com',
            'support_email': 'support@luxoyacandles.com',
            'sales_email': 'sales@luxoyacandles.com',
            'org_address': 'Villa No : 82,Mythri Lake View .S.No : 45,46 BC Colony ,Mallampet,Bollaram,Medchal ,Malkajgiri Dist-500090'
        }
        
        def user_has_perm(user, perm):
            from models import SiteSettings
            if not user: return False
            if user.is_admin: return True
            if not user.is_sales: return False
            perms = SiteSettings.get(f'sales_perms_{user.id}', '')
            return perm in perms
            
        return {
            'current_user': None, 
            'branding': branding, 
            'site_settings': branding, 
            'user_has_perm': user_has_perm
        }

    # ─────────────────────────────────────────
    # Main pages
    # ─────────────────────────────────────────
    @app.route('/')
    def index():
        try:
            from models import Product, Category, SiteSettings
            # Dictionary of site setting keys and their hardcoded fallbacks
            setting_map = {
                'home_phi_img_1': '/static/images/philosophy/candle-jars.jpg',
                'home_phi_img_2': '/static/images/philosophy/candle-ambience.jpg',
                'home_phi_img_3': '/static/images/philosophy/candle-lighting.jpg',
                'coll_img_1': 'https://images.unsplash.com/photo-1602607360922-47951de49a31?w=600',
                'coll_img_2': 'https://images.unsplash.com/photo-1603006905003-be475563bc59?w=600',
                'coll_img_3': 'https://images.unsplash.com/photo-1543332164-6e82f355badc?w=600',
                'coll_img_4': 'https://images.unsplash.com/photo-1572726729207-a78d6feb18d7?w=600',
                'coll_img_5': 'https://images.unsplash.com/photo-1608181831718-2501ef3e1420?w=600',
                'coll_img_6': 'https://images.unsplash.com/photo-1597318181409-cf64d0b5d8a2?w=600',
                'b2b_img': 'https://media.istockphoto.com/id/1504550028/photo/white-rose-and-burning-candles-on-black-mirror-surface-in-darkness-closeup-with-space-for.jpg?s=612x612&w=0&k=20&c=iBC04S7kiopE0S8GR2TykjmYZWtruRltxmQNK9mhKFw=',
                'slider_img_1': 'https://images.unsplash.com/photo-1602607360922-47951de49a31?w=1200',
                'slider_img_2': 'https://images.unsplash.com/photo-1603006905003-be475563bc59?w=1200',
                'slider_img_3': 'https://images.unsplash.com/photo-1543332164-6e82f355badc?w=1200',
                'slider_img_4': 'https://images.unsplash.com/photo-1572726729207-a78d6feb18d7?w=1200',
            }
            
            # List context keys from index() definition
            all_keys = [
                'home_phi_img_1', 'home_phi_img_2', 'home_phi_img_3',
                'coll_img_1', 'coll_name_1', 'coll_img_2', 'coll_name_2',
                'coll_img_3', 'coll_name_3', 'coll_img_4', 'coll_name_4',
                'coll_img_5', 'coll_name_5', 'coll_img_6', 'coll_name_6',
                'b2b_img', 'slider_img_1', 'slider_img_2', 'slider_img_3', 'slider_img_4',
                'slider_img_5', 'slider_img_6', 'slider_img_7', 'slider_img_8', 'slider_img_9', 'slider_img_10',
                'hero_vid_1', 'hero_vid_2', 'hero_vid_3', 'hero_vid_4', 'hero_vid_5',
                'hero_vid_6', 'hero_vid_7', 'hero_vid_8', 'hero_vid_9', 'hero_vid_10',
                'promo_limit_img', 'promo_limit_title', 'promo_limit_desc', 'promo_limit_link',
                'gift_hampers_header', 'gift_hampers_desc',
                'gift_hampers_img_1', 'gift_hampers_title_1', 'gift_hampers_desc_1', 'gift_hampers_link_1',
                'gift_hampers_img_2', 'gift_hampers_title_2', 'gift_hampers_desc_2', 'gift_hampers_link_2',
                'custom_studio_img', 'custom_studio_title', 'custom_studio_desc'
            ]
            
            # Batch fetch all relevant settings
            reel_keys = []
            for i in range(1, 11):
                reel_keys.extend([f'reel_{i}_url', f'reel_{i}_title', f'reel_{i}_thumb'])
            
            all_necessary_keys = all_keys + reel_keys
            
            db_settings = {}
            try:
                db_settings = {s.key: s.value for s in SiteSettings.query.filter(SiteSettings.key.in_(all_necessary_keys)).all()}
            except Exception as e:
                app.logger.warning(f"Homepage DB Settings Fetch Error (Cold Start?): {e}")

            # Populate home_images from DB Settings with fallbacks
            home_images = {}
            for k in all_keys:
                val = db_settings.get(k)
                home_images[k] = val if val else setting_map.get(k, '')
            
            # Special cases (non-image fallbacks)
            if not home_images.get('coll_name_1'): home_images['coll_name_1'] = 'Signature'
            if not home_images.get('coll_name_2'): home_images['coll_name_2'] = 'Aromatic'
            if not home_images.get('coll_name_3'): home_images['coll_name_3'] = 'Festive'
            if not home_images.get('coll_name_4'): home_images['coll_name_4'] = 'Luxury'
            if not home_images.get('coll_name_5'): home_images['coll_name_5'] = 'Gift Sets'
            if not home_images.get('coll_name_6'): home_images['coll_name_6'] = 'Limited'
            
            # Get Reels (from SiteSettings)
            reels_data = []
            for i in range(1, 11):
                url = db_settings.get(f'reel_{i}_url', '')
                if url:
                    reels_data.append({
                        'url': url,
                        'title': db_settings.get(f'reel_{i}_title', 'Luxoya Moment'),
                        'thumb': db_settings.get(f'reel_{i}_thumb', '') or 'https://images.unsplash.com/photo-1602607360922-47951de49a31?w=400'
                    })
            
            # Fetch Product Videos
            try:
                prod_vids = Product.query.filter(Product.video_url != None, Product.is_active == True).all()
                for p in prod_vids:
                    reels_data.insert(0, {
                        'url': p.video_url,
                        'title': p.name,
                        'thumb': p.image_url or 'https://images.unsplash.com/photo-1602607360922-47951de49a31?w=400',
                        'product_slug': p.slug
                    })
            except Exception as e:
                app.logger.warning(f"Error fetching product reels: {e}")

            # Fallback for empty reels
            if not reels_data:
                reels_data = [
                    {'url': 'https://assets.mixkit.co/videos/preview/mixkit-aromatic-candle-burning-in-the-dark-34440-large.mp4', 'title': 'Scent Pouring', 'thumb': 'https://images.unsplash.com/photo-1602607360922-47951de49a31?w=400'},
                    {'url': 'https://assets.mixkit.co/videos/preview/mixkit-hand-lighting-a-candle-in-a-dark-room-34441-large.mp4', 'title': 'Handmade Magic', 'thumb': 'https://images.unsplash.com/photo-1597318181409-cf64d0b5d8a2?w=400'},
                ]

            featured, all_products, categories = [], [], []
            try:
                # Simplified queries for reliability
                categories = Category.query.filter_by(is_active=True).order_by(Category.display_order).all()
                all_products = Product.query.filter_by(is_active=True).all()
                featured = Product.query.filter_by(is_featured=True, is_active=True).limit(8).all()
                
                if not featured and all_products:
                    featured = all_products[:8]
            except Exception as e:
                app.logger.warning(f'DB error on Homepage Data Fetch: {e}')

            return render_template(
                'index.html',
                featured=featured,
                all_products=all_products,
                categories=categories,
                home_images=home_images,
                reels_data=reels_data,
            )
        except Exception as e:
            app.logger.error(f"Critical Homepage Crash: {e}")
            return render_template(
                'index.html',
                featured=[],
                all_products=[],
                categories=[],
                home_images={},
                reels_data=[],
            )

    
    @app.route('/about')
    def about():
        return render_template('about.html')
        
    @app.route('/reels')
    def reels():
        from models import SiteSettings, Product
        reels_data = []
        try:
            # 1. Get manually configured reels
            db_settings = {s.key: s.value for s in SiteSettings.query.filter(SiteSettings.key.like('reel_%')).all()}
            for i in range(1, 11):
                url = db_settings.get(f'reel_{i}_url', '')
                if url:
                    reels_data.append({
                        'url': url,
                        'title': db_settings.get(f'reel_{i}_title', 'Luxoya Moment'),
                        'thumb': db_settings.get(f'reel_{i}_thumb', '') or 'https://images.unsplash.com/photo-1602607360922-47951de49a31?w=400',
                        'desc': db_settings.get(f'reel_{i}_desc', 'Experience the magic of handcrafted luxury.')
                    })
            
            # 2. Get Product videos
            prod_vids = Product.query.filter(Product.video_url != None, Product.is_active == True).all()
            for p in prod_vids:
                reels_data.insert(0, {
                    'url': p.video_url,
                    'title': p.name,
                    'thumb': p.image_url or 'https://images.unsplash.com/photo-1602607360922-47951de49a31?w=400',
                    'desc': p.short_description or f'Discover the fragrance of {p.name}.',
                    'product_slug': p.slug
                })
        except Exception as e:
            app.logger.warning(f"Reels fetch error: {e}")
        
        if not reels_data:
            reels_data = [
                {'url': 'https://assets.mixkit.co/videos/preview/mixkit-aromatic-candle-burning-in-the-dark-34440-large.mp4', 'title': 'Signature Glow', 'desc': 'Watch the magic of pure soy wax blending.', 'thumb': 'https://images.unsplash.com/photo-1602607360922-47951de49a31?w=800'},
                {'url': 'https://assets.mixkit.co/videos/preview/mixkit-hand-lighting-a-candle-in-a-dark-room-34441-large.mp4', 'title': 'Handmade Magic', 'desc': 'Every order packed with extreme precision.', 'thumb': 'https://images.unsplash.com/photo-1603006905003-be475563bc59?w=800'},
            ]
            
        return render_template('reels.html', reels_data=reels_data)
    
    @app.route('/contact')
    def contact():
        return render_template('contact.html')

    @app.route('/blog')
    def blog():
        return render_template('blog.html')

    @app.route('/shipping-policy')
    def shipping_policy():
        return render_template('legal/shipping.html')

    @app.route('/returns-refunds')
    def returns_refunds():
        return render_template('legal/returns.html')

    @app.route('/privacy-policy')
    def privacy_policy():
        return render_template('legal/privacy.html')

    @app.route('/terms-service')
    def terms_service():
        return render_template('legal/terms.html')
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        if request_wants_json():
            return jsonify({'error': 'Not found'}), 404
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def server_error(e):
        if request_wants_json():
            return jsonify({'error': 'Internal server error'}), 500
        return "Internal Server Error (Isolation Active)", 500

    # ─────────────────────────────────────────
    # SEO & Discoverability
    # ─────────────────────────────────────────
    @app.route('/robots.txt')
    def robots_txt():
        from flask import Response, request
        host_url = request.host_url.rstrip('/')
        content = f"User-agent: *\nAllow: /\nDisallow: /admin/\nDisallow: /api/\nSitemap: {host_url}/sitemap.xml"
        return Response(content, mimetype="text/plain")

    @app.route('/sitemap.xml')
    def sitemap_xml():
        from flask import Response, request
        from models import Product, Category
        host_url = request.host_url.rstrip('/')
        
        xml = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
        
        # Static Routes
        for route in ['/', '/about', '/reels', '/contact', '/login']:
            xml.append(f'  <url><loc>{host_url}{route}</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>')
            
        try:
            # Dynamic Products
            for product in Product.query.filter_by(is_active=True).all():
                xml.append(f'  <url><loc>{host_url}/products/{product.slug}</loc><changefreq>daily</changefreq><priority>0.9</priority></url>')
            
            # Dynamic Categories
            for category in Category.query.filter_by(is_active=True).all():
                xml.append(f'  <url><loc>{host_url}/category/{category.slug}</loc><changefreq>weekly</changefreq><priority>0.7</priority></url>')
        except: pass
        
        xml.append('</urlset>')
        return Response('\\n'.join(xml), mimetype="application/xml")

    # Minimal Health check (No Templates, No CSRF, No Context)
    @app.route('/api/health/minimal')
    def minimal_health():
        return "OK - Minimal Isolation Active"
    
    # Diagnostic: simulate context processor to see exact error
    @app.route('/api/health/ctx')
    def ctx_test():
        result = {}
        try:
            from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
            result['jwt_import'] = 'ok'
        except Exception as e:
            result['jwt_import'] = str(e)
            return jsonify(result)
        try:
            verify_jwt_in_request(optional=True)
            result['verify_jwt'] = 'ok'
        except Exception as e:
            result['verify_jwt'] = str(e)
            return jsonify(result)
        try:
            uid = get_jwt_identity()
            result['identity'] = uid
        except Exception as e:
            result['identity_error'] = str(e)
            return jsonify(result)
        if uid:
            try:
                from models import User
                user = db.session.get(User, uid)
                result['user'] = user.full_name if user else 'not_found'
            except Exception as e:
                result['db_error'] = str(e)
        try:
            rendered = render_template('about.html')
            result['template_render'] = 'ok'
        except Exception as e:
            result['template_error'] = str(e)
        return jsonify(result)
    
    # Emergency Debug Route (JSON only, avoid context processor issues)
    @app.route('/api/health/debug')
    def debug_info():
        import os
        from flask import current_app
        return jsonify({
            'DATABASE_URL_SET': bool(os.environ.get('DATABASE_URL')),
            'JWT_SECRET_SET': bool(os.environ.get('JWT_SECRET_KEY')),
            'TEMPLATES': [t for t in os.listdir('templates') if t.endswith('.html')],
            'STATIC_URL': current_app.static_url_path,
            'PWD': os.getcwd(),
            'CONTENTS': os.listdir('.')
        })

    @app.route('/api/health')
    def health_check():
        """Site health diagnostic API."""
        import os
        from sqlalchemy import text
        from models import Product, Category
        
        db_engine = "Unknown"
        db_host = "None"
        try:
            db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
            if 'postgresql' in db_uri or 'postgres' in db_uri:
                db_engine = 'PostgreSQL'
                db_host = db_uri.split('@')[-1].split('/')[0].split(':')[0]
            elif 'sqlite' in db_uri:
                db_engine = 'SQLite'
        except: pass

        info = {
            'status': 'ok',
            'db_type': db_engine,
            'db_host': db_host,
            'counts': {
                'products': 0,
                'categories': 0
            }
        }
        
        # Quick DB probe
        try:
            from sqlalchemy import text
            db.session.execute(text('SELECT 1'))
            info['db'] = 'connected'
            
            # Auto-Repair: If view_count is missing, add it silently
            try:
                db.session.execute(text('SELECT view_count FROM products LIMIT 1'))
            except Exception:
                db.session.rollback()
                db.session.execute(text('ALTER TABLE products ADD COLUMN IF NOT EXISTS view_count INTEGER DEFAULT 0'))
                db.session.commit()
            
            info['counts']['products'] = Product.query.count()
            info['counts']['categories'] = Category.query.count()
        except Exception as e:
            err_str = str(e)
            info['db'] = f'error'
            info['db_error'] = err_str # Send actual error for debugging
            info['status'] = 'degraded'
            
        return jsonify(info)

    @app.after_request
    def add_security_headers(response):
        """Add modern security headers for cross-browser compatibility."""
        # Required for Google Identity Services popups in modern browsers
        response.headers['Cross-Origin-Opener-Policy'] = 'same-origin-allow-popups'
        return response

    return app



def request_wants_json():
    from flask import request
    return request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json'


app = create_app()

# Alias for Cloud Run / Gunicorn
luxoya_app = app

if __name__ == '__main__':
    print("Starting Luxoya Server on http://0.0.0.0:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
