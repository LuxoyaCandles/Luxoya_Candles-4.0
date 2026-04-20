import os
import uuid
import io
from flask import Blueprint, request, jsonify, render_template, current_app, make_response
from flask_jwt_extended import jwt_required
from werkzeug.utils import secure_filename
from models import (
    Product, Category, Order, OrderItem, User, Payment, CartItem,
    B2BRequest, Coupon, Review, ProductImage, ImageStore, CustomizationOption, Customization,
    Complaint, OrderTracking, ReturnRequest, SiteSettings, FinanceRecord, RawMaterial, ManufacturingRecipe, db
)
from routes.auth import admin_required, admin_or_sales_required, sales_required, get_current_user
from utils import send_cancellation_email, send_order_status_email, _generate_invoice_html
from datetime import datetime, timedelta
import re

def robust_parse_date(date_str):
    if not date_str or str(date_str).lower() == 'null':
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        try:
            return datetime.strptime(date_str, '%m/%d/%Y')
        except ValueError:
            return datetime.utcnow()

def allowed_file(filename):
    """Check if uploaded file extension is allowed."""
    allowed = current_app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'webm'})
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed


def _compress_image(file_data, content_type, max_size=1200, quality=75):
    """Compress image using Pillow for faster uploads. Returns (compressed_bytes, content_type).
    
    Args:
        file_data: Raw image bytes
        content_type: MIME type
        max_size: Max dimension (preserves aspect ratio)
        quality: WEBP quality (1-100, default 75 for balance of speed and quality)
    """
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(file_data))

        # Convert RGBA/palette to RGB for WEBP output
        if img.mode in ('RGBA', 'P', 'LA'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
            img = background

        # Resize if larger than max_size (preserving aspect ratio)
        if max(img.size) > max_size:
            img.thumbnail((max_size, max_size), Image.LANCZOS)

        # Save as WEBP with optimized settings for faster compression
        buf = io.BytesIO()
        img.save(buf, format='WEBP', quality=quality, method=3)  # method=3 is faster than method=4
        buf.seek(0)
        return buf.getvalue(), 'image/webp'
    except Exception as e:
        current_app.logger.warning(f'Image compression failed, storing original: {e}')
        return file_data, content_type


def save_upload(file, subfolder='products'):
    """Save an uploaded file to the database (Neon PostgreSQL) and return its URL.
    
    Images are compressed to WebP, stored as binary in the image_store table,
    and served via /img/store/<id> with aggressive caching for fast loading.
    """
    if not file or not file.filename:
        return None
    if not allowed_file(file.filename):
        return None

    from models import ImageStore

    # Read file data
    file_data = file.read()
    ext = file.filename.rsplit('.', 1)[1].lower()
    content_type_map = {
        'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
        'gif': 'image/gif', 'webp': 'image/webp',
        'mp4': 'video/mp4', 'webm': 'video/webm'
    }
    content_type = content_type_map.get(ext, 'application/octet-stream')

    # Compress image for faster loading (bypass for videos)
    if ext in ['mp4', 'webm']:
        compressed_data = file_data
        final_type = content_type
    else:
        compressed_data, final_type = _compress_image(file_data, content_type)

    # Store in PostgreSQL
    img_record = ImageStore(
        data=compressed_data,
        content_type=final_type,
        filename=secure_filename(file.filename),
        size=len(compressed_data)
    )
    db.session.add(img_record)
    db.session.flush()  # Get the ID without committing (caller will commit)

    return f"/img/store/{img_record.id}"


def log_admin_action(module, action, target_id, description, details=None):
    """Automatically log administrative actions for the audit trail."""
    try:
        user = get_current_user()
        log = AuditLog(
            user_id=user.id if user else None,
            user_name=user.full_name if user else 'System',
            action=action.upper(),
            module=module,
            target_id=str(target_id),
            description=description,
            details=details
        )
        db.session.add(log)
        # We don't commit here, as it will be part of the main transaction
    except Exception as e:
        current_app.logger.error(f"Audit Log Failed: {e}")


admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# ─────────────────────────────────────────────
# PAGE: Admin Dashboard
# ─────────────────────────────────────────────
@admin_bp.route('/')
@admin_bp.route('/dashboard')
@admin_or_sales_required
def dashboard():
    user = get_current_user()
    return render_template('admin/dashboard.html', user=user)


# ─────────────────────────────────────────────
# PAGE: Admin Products
# ─────────────────────────────────────────────
@admin_bp.route('/products')
@admin_or_sales_required
def products_page():
    user = get_current_user()
    categories = Category.query.order_by(Category.display_order).all()
    return render_template('admin/products.html', user=user, categories=categories)


# ─────────────────────────────────────────────
# PAGE: Admin Orders
# ─────────────────────────────────────────────
@admin_bp.route('/orders')
@admin_or_sales_required
def orders_page():
    user = get_current_user()
    return render_template('admin/orders.html', user=user)


# ─────────────────────────────────────────────
# PAGE: Admin B2B
# ─────────────────────────────────────────────
@admin_bp.route('/b2b')
@admin_or_sales_required
def b2b_page():
    user = get_current_user()
    return render_template('admin/b2b.html', user=user)


# ─────────────────────────────────────────────
# PAGE: Admin Reviews
# ─────────────────────────────────────────────
@admin_bp.route('/reviews')
@admin_or_sales_required
def reviews_page():
    user = get_current_user()
    return render_template('admin/reviews.html', user=user)


# ─────────────────────────────────────────────
# PAGE: Admin Categories
# ─────────────────────────────────────────────
@admin_bp.route('/categories')
@admin_required
def categories_page():
    user = get_current_user()
    return render_template('admin/categories.html', user=user)


# ─────────────────────────────────────────────
# API: Categories Management
# ─────────────────────────────────────────────
@admin_bp.route('/api/categories', methods=['GET'])
@admin_required
def get_categories():
    categories = Category.query.order_by(Category.display_order).all()
    return jsonify({'categories': [c.to_dict() for c in categories]})


@admin_bp.route('/api/categories', methods=['POST'])
@admin_required
def add_category():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400

    from slugify import slugify # Ensure slugify is used if available, or manual slug
    slug = data.get('slug') or name.lower().replace(' ', '-').replace('&', 'and')
    
    # Check duplicate slug
    if Category.query.filter_by(slug=slug).first():
        slug = f"{slug}-{int(datetime.utcnow().timestamp())}"

    cat = Category(
        name=name,
        slug=slug,
        description=data.get('description', ''),
        display_order=int(data.get('display_order', 0)),
        is_active=bool(data.get('is_active', True)),
        image_url=data.get('image_url', '')
    )
    db.session.add(cat)
    db.session.flush()

    log_admin_action(
        module='Category',
        action='CREATE',
        target_id=cat.id,
        description=f"Created Category: {cat.name}"
    )
    db.session.commit()
    return jsonify({'message': 'Category added', 'category': cat.to_dict()}), 201


@admin_bp.route('/api/categories/<int:cat_id>', methods=['PUT', 'POST']) # Support both for flexibility
@admin_required
def update_category(cat_id):
    cat = db.session.get(Category, cat_id)
    if not cat:
        return jsonify({'error': 'Category not found'}), 404

    data = request.get_json()
    if 'name' in data:
        cat.name = data['name'].strip()
    if 'description' in data:
        cat.description = data['description']
    if 'display_order' in data:
        cat.display_order = int(data['display_order'])
    if 'is_active' in data:
        cat.is_active = bool(data['is_active'])
    if 'image_url' in data:
        cat.image_url = data['image_url']
    if 'slug' in data and data['slug']:
        cat.slug = data['slug'].strip().lower().replace(' ', '-')

    log_admin_action(
        module='Category',
        action='UPDATE',
        target_id=cat.id,
        description=f"Updated Category: {cat.name}"
    )
    db.session.commit()
    return jsonify({'message': 'Category updated', 'category': cat.to_dict()})


@admin_bp.route('/api/categories/<int:cat_id>', methods=['DELETE'])
@admin_required
def delete_category(cat_id):
    cat = Category.query.get(cat_id)
    if not cat:
        return jsonify({'error': 'Category not found'}), 404

    # Check if category has products
    if cat.products and len(cat.products) > 0:
        return jsonify({'error': 'Cannot delete category with active products. Reassign or delete products first.'}), 400

    log_admin_action(
        module='Category',
        action='DELETE',
        target_id=cat.id,
        description=f"Deleted Category: {cat.name}"
    )
    db.session.delete(cat)
    db.session.commit()
    return jsonify({'message': 'Category deleted'})


# ─────────────────────────────────────────────
# PAGE: Admin Customers
# ─────────────────────────────────────────────
@admin_bp.route('/customers')
@admin_or_sales_required
def customers_page():
    user = get_current_user()
    return render_template('admin/customers.html', user=user)


# ─────────────────────────────────────────────
# API: Customers list
# ─────────────────────────────────────────────
@admin_bp.route('/api/customers', methods=['GET'])
@admin_or_sales_required
def get_customers():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '')  # 'active', 'inactive', ''

    query = User.query.filter_by(role='user')

    if search:
        query = query.filter(
            db.or_(
                User.full_name.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%'),
                User.phone.ilike(f'%{search}%')
            )
        )
    if status_filter == 'active':
        query = query.filter_by(is_active=True)
    elif status_filter == 'inactive':
        query = query.filter_by(is_active=False)

    query = query.order_by(User.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    customers = []
    for u in pagination.items:
        order_count = Order.query.filter_by(user_id=u.id).count()
        total_spent = db.session.query(db.func.sum(Order.total_amount))\
            .filter(Order.user_id == u.id, Order.payment_status == 'paid').scalar() or 0
        last_order = Order.query.filter_by(user_id=u.id).order_by(Order.created_at.desc()).first()
        customers.append({
            'id': u.id,
            'full_name': u.full_name,
            'email': u.email,
            'phone': u.phone or '-',
            'city': u.city or '-',
            'state': u.state or '-',
            'pincode': u.pincode or '-',
            'address': u.address or '-',
            'is_active': u.is_active,
            'avatar_url': u.avatar_url,
            'order_count': order_count,
            'total_spent': round(total_spent, 2),
            'last_order_date': last_order.created_at.isoformat() if last_order else None,
            'created_at': u.created_at.isoformat() if u.created_at else None,
        })

    # Summary stats
    total_customers = User.query.filter_by(role='user').count()
    active_customers = User.query.filter_by(role='user', is_active=True).count()
    # Customers who placed at least one order in the last 30 days
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_buyers = db.session.query(db.func.count(db.distinct(Order.user_id)))\
        .filter(Order.created_at >= thirty_days_ago).scalar() or 0

    return jsonify({
        'customers': customers,
        'total': pagination.total,
        'pages': pagination.pages,
        'page': pagination.page,
        'stats': {
            'total_customers': total_customers,
            'active_customers': active_customers,
            'recent_buyers': recent_buyers
        }
    })


# ─────────────────────────────────────────────
# API: Customer detail
# ─────────────────────────────────────────────
@admin_bp.route('/api/customers/<customer_id>', methods=['GET'])
@admin_or_sales_required
def get_customer_detail(customer_id):
    customer = User.query.filter_by(id=customer_id, role='user').first_or_404()
    orders = Order.query.filter_by(user_id=customer.id).order_by(Order.created_at.desc()).all()
    total_spent = db.session.query(db.func.sum(Order.total_amount))\
        .filter(Order.user_id == customer.id, Order.payment_status == 'paid').scalar() or 0

    return jsonify({
        'customer': {
            'id': customer.id,
            'full_name': customer.full_name,
            'email': customer.email,
            'phone': customer.phone or '-',
            'address': customer.address or '-',
            'city': customer.city or '-',
            'state': customer.state or '-',
            'pincode': customer.pincode or '-',
            'is_active': customer.is_active,
            'avatar_url': customer.avatar_url,
            'created_at': customer.created_at.isoformat() if customer.created_at else None,
        },
        'total_spent': round(total_spent, 2),
        'orders': [{
            'id': o.id,
            'order_number': o.order_number,
            'status': o.status,
            'payment_status': o.payment_status,
            'total_amount': o.total_amount,
            'created_at': o.created_at.isoformat() if o.created_at else None,
        } for o in orders]
    })


# ─────────────────────────────────────────────
# API: Dashboard stats
# ─────────────────────────────────────────────
@admin_bp.route('/api/stats', methods=['GET'])
@admin_or_sales_required
def get_stats():
    try:
        today = datetime.utcnow().date()
        month_start = today.replace(day=1)
        
        total_revenue = db.session.query(db.func.sum(Order.total_amount))\
            .filter(Order.payment_status == 'paid').scalar() or 0
        
        monthly_revenue = db.session.query(db.func.sum(Order.total_amount))\
            .filter(Order.payment_status == 'paid', Order.created_at >= month_start).scalar() or 0
        
        total_orders = Order.query.count()
        pending_orders = Order.query.filter_by(status='pending').count()
        total_customers = User.query.filter_by(role='user').count()
        total_products = Product.query.join(Category).filter(Product.is_active == True, Category.is_active == True).count()
        low_stock = Product.query.join(Category).filter(Product.stock < 10, Product.is_active == True, Category.is_active == True).count()
        pending_b2b = B2BRequest.query.filter_by(status='pending').count()
        pending_reviews = Review.query.filter_by(is_approved=False).count()
        
        # 1. Top Selling Products (by quantity)
        top_products_q = db.session.query(
            Product.name,
            db.func.sum(OrderItem.quantity).label('sold')
        ).join(OrderItem, OrderItem.product_id == Product.id)\
         .join(Order, Order.id == OrderItem.order_id)\
         .filter(Order.payment_status == 'paid')\
         .group_by(Product.id)\
         .order_by(db.desc('sold'))\
         .limit(5).all()
        top_products = [{'name': name, 'sold': int(sold)} for name, sold in top_products_q]

        # 2. Top Visited Products (Popularity)
        top_visited_q = Product.query.filter(Product.view_count > 0)\
                              .order_by(Product.view_count.desc()).limit(5).all()
        top_visited = [{'name': p.name, 'views': p.view_count or 0} for p in top_visited_q]
        
        # 3. Daily Sales Trend (Last 7 Days for Area Chart)
        daily_sales = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            next_d = d + timedelta(days=1)
            
            day_rev = db.session.query(db.func.sum(Order.total_amount))\
                .filter(
                    Order.payment_status == 'paid',
                    Order.created_at >= d,
                    Order.created_at < next_d
                ).scalar() or 0
            
            daily_sales.append({
                'date': d.strftime('%d %b'),
                'revenue': float(day_rev)
            })

        # 4. Live Viewers Simulation
        from random import randint
        today_users = User.query.filter(User.created_at >= today).count()
        live_viewers = max(randint(2, 5), today_users + randint(1, 8))

        # Monthly revenue chart data
        chart_data = []
        for i in range(5, -1, -1):
            d = today - timedelta(days=30 * i)
            m_start = d.replace(day=1)
            if d.month == 12:
                m_end = d.replace(year=d.year + 1, month=1, day=1)
            else:
                m_end = d.replace(month=d.month + 1, day=1)
            
            rev = db.session.query(db.func.sum(Order.total_amount))\
                .filter(
                    Order.payment_status == 'paid',
                    Order.created_at >= m_start,
                    Order.created_at < m_end
                ).scalar() or 0
            
            chart_data.append({
                'month': m_start.strftime('%b %Y'),
                'revenue': float(rev)
            })
        
        # Active B2B Leads
        pending_b2b = B2BRequest.query.filter_by(status='pending').count()
        
        # Recent orders
        recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
        
        # Order status distribution
        status_counts = db.session.query(Order.status, db.func.count(Order.id))\
            .group_by(Order.status).all()
        order_statuses = {status: int(count or 0) for status, count in status_counts}

        # Sales by category
        cat_sales_q = db.session.query(Category.name, db.func.sum(Order.total_amount))\
            .join(Product, Product.category_id == Category.id)\
            .join(OrderItem, OrderItem.product_id == Product.id)\
            .join(Order, Order.id == OrderItem.order_id)\
            .filter(Order.payment_status == 'paid')\
            .group_by(Category.id).all()
        category_sales = [{'name': name, 'value': float(val)} for name, val in cat_sales_q]

        # Finance stats
        total_expenses = db.session.query(db.func.sum(FinanceRecord.amount))\
            .filter(FinanceRecord.record_type == 'expense').scalar() or 0
        total_capital = db.session.query(db.func.sum(FinanceRecord.amount))\
            .filter(FinanceRecord.record_type == 'capital').scalar() or 0
        net_profit = total_revenue - total_expenses

        return jsonify({
            'total_revenue': float(total_revenue),
            'monthly_revenue': float(monthly_revenue),
            'total_expenses': float(total_expenses),
            'total_capital': float(total_capital),
            'net_profit': float(net_profit),
            'total_orders': total_orders,
            'pending_orders': pending_orders,
            'total_customers': total_customers,
            'total_products': total_products,
            'low_stock': low_stock,
            'pending_b2b': pending_b2b,
            'pending_reviews': pending_reviews,
            'order_statuses': order_statuses,
            'category_sales': category_sales,
            'chart_data': chart_data,
            'daily_sales': daily_sales,
            'top_products': top_products,
            'top_visited': top_visited,
            'live_viewers': live_viewers,
            'health': "Action Required" if low_stock > 0 else "Perfect",
            'recent_orders': [{
                'id': o.id,
                'order_number': o.order_number,
                'customer_name': o.user.full_name if o.user else 'Guest',
                'total_amount': o.total_amount,
                'status': o.status,
                'created_at': o.created_at.isoformat()
            } for o in recent_orders]
        })
    except Exception as e:
        return jsonify({
            'status': 'degraded',
            'error': str(e),
            'total_revenue': 0,
            'total_orders': 0,
            'recent_orders': []
        }), 200


# ─────────────────────────────────────────────
# API: Revenue chart data (daily for 7/30 days)
# ─────────────────────────────────────────────
@admin_bp.route('/api/revenue-chart', methods=['GET'])
@admin_or_sales_required
def revenue_chart():
    days = request.args.get('days', 30, type=int)
    if days not in (7, 30):
        days = 30
    today = datetime.utcnow().date()
    start_date = today - timedelta(days=days - 1)
    data_points = []
    for i in range(days):
        day = start_date + timedelta(days=i)
        day_start = datetime.combine(day, datetime.min.time())
        day_end = datetime.combine(day + timedelta(days=1), datetime.min.time())
        rev = db.session.query(db.func.sum(Order.total_amount))\
            .filter(Order.payment_status == 'paid',
                    Order.created_at >= day_start,
                    Order.created_at < day_end).scalar() or 0
        data_points.append({
            'date': day.strftime('%d %b'),
            'revenue': float(rev)
        })
    return jsonify({'data': data_points})


# ─────────────────────────────────────────────
# API: CRUD Products
# ─────────────────────────────────────────────
@admin_bp.route('/api/products', methods=['GET'])
@admin_or_sales_required
def get_products():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    
    query = Product.query
    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))
    
    products = query.order_by(Product.created_at.desc())\
                   .paginate(page=page, per_page=1000, error_out=False)
    
    return jsonify({
        'products': [p.to_dict() for p in products.items],
        'total': products.total,
        'pages': products.pages
    })


@admin_bp.route('/api/products', methods=['POST'])
@admin_required
def create_product():
    # Support both JSON and multipart form data
    if request.content_type and 'multipart/form-data' in request.content_type:
        data = request.form.to_dict()
        # Convert checkbox / boolean fields
        data['is_featured'] = data.get('is_featured', 'false').lower() in ('true', '1', 'on')
        data['is_active'] = data.get('is_active', 'true').lower() in ('true', '1', 'on')
        # Handle multiple image uploads
        uploaded_images = request.files.getlist('images')
        if uploaded_images and uploaded_images[0].filename:
            # First image becomes the main product image
            main_url = save_upload(uploaded_images[0])
            if main_url:
                data['image_url'] = main_url
            # Store remaining images for later ProductImage creation
            data['_extra_images'] = uploaded_images[1:]
        else:
            # Fallback: single image field
            main_image = request.files.get('image')
            if main_image:
                url = save_upload(main_image)
                if url:
                    data['image_url'] = url
            data['_extra_images'] = []
    else:
        data = request.get_json()
        data['_extra_images'] = []
    
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Product name is required'}), 400
    
    # Generate slug
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    existing = Product.query.filter_by(slug=slug).first()
    if existing:
        slug = f"{slug}-{Product.query.count() + 1}"
    
    # Safely parse category_id
    raw_cat = data.get('category_id')
    category_id = int(raw_cat) if raw_cat and str(raw_cat).strip() not in ('', 'None', 'null') else None
    
    product = Product(
        name=name,
        slug=slug,
        description=data.get('description', ''),
        short_description=data.get('short_description', ''),
        price=float(data.get('price', 0)),
        sale_price=float(data['sale_price']) if data.get('sale_price') and str(data['sale_price']).strip() else None,
        category_id=category_id,
        image_url=data.get('image_url', ''),
        images=data.get('images', []) if isinstance(data.get('images'), list) else [],
        stock=int(data.get('stock', 0)),
        weight=data.get('weight', ''),
        burn_time=data.get('burn_time', ''),
        fragrance=data.get('fragrance', ''),
        wax_type=data.get('wax_type', ''),
        video_url=data.get('video_url', ''),
        is_featured=data.get('is_featured', False),
        is_customizable=data.get('is_customizable', False),
        is_active=data.get('is_active', True)
    )
    
    db.session.add(product)
    db.session.flush()  # Get product.id before commit
    
    # Save additional uploaded images as ProductImage entries
    extra_images = data.get('_extra_images', [])
    for idx, img_file in enumerate(extra_images):
        if img_file and img_file.filename:
            img_url = save_upload(img_file)
            if img_url:
                pi = ProductImage(
                    product_id=product.id,
                    image_url=img_url,
                    alt_text=product.name,
                    display_order=idx + 1
                )
                db.session.add(pi)
    
    log_admin_action(
        module='Product',
        action='CREATE',
        target_id=product.id,
        description=f"Created Product: {product.name}",
        details={'price': product.price, 'stock': product.stock}
    )
    db.session.commit()
    
    return jsonify({'message': 'Product created', 'product': product.to_dict()}), 201


@admin_bp.route('/api/products/<product_id>', methods=['PUT'])
@admin_required
def update_product(product_id):
    product = db.session.get(Product, product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    
    # Support both JSON and multipart form data
    if request.content_type and 'multipart/form-data' in request.content_type:
        data = request.form.to_dict()
        # Handle multiple image uploads
        uploaded_images = request.files.getlist('images')
        if uploaded_images and uploaded_images[0].filename:
            # First image becomes the main product image
            main_url = save_upload(uploaded_images[0])
            if main_url:
                data['image_url'] = main_url
            # Save remaining images as ProductImage entries
            for idx, img_file in enumerate(uploaded_images[1:]):
                if img_file and img_file.filename:
                    img_url = save_upload(img_file)
                    if img_url:
                        max_order = db.session.query(db.func.max(ProductImage.display_order)).filter_by(product_id=product_id).scalar() or 0
                        pi = ProductImage(
                            product_id=product_id,
                            image_url=img_url,
                            alt_text=product.name,
                            display_order=max_order + idx + 1
                        )
                        db.session.add(pi)
        else:
            # Fallback: single image field
            main_image = request.files.get('image')
            if main_image:
                url = save_upload(main_image)
                if url:
                    data['image_url'] = url
    else:
        data = request.get_json()
    
    if data.get('name'):
        product.name = data['name'].strip()
    if 'description' in data:
        product.description = data['description']
    if 'short_description' in data:
        product.short_description = data['short_description']
    if 'price' in data:
        try:
            product.price = float(data['price'])
        except (ValueError, TypeError):
            pass
    if 'sale_price' in data:
        try:
            product.sale_price = float(data['sale_price']) if data['sale_price'] and str(data['sale_price']).strip() else None
        except (ValueError, TypeError):
            product.sale_price = None
    if 'category_id' in data:
        raw_cat = data['category_id']
        product.category_id = int(raw_cat) if raw_cat and str(raw_cat).strip() not in ('', 'None', 'null') else None
    if 'image_url' in data:
        product.image_url = data['image_url']
    if 'images' in data and isinstance(data.get('images'), list):
        product.images = data['images']
    if 'stock' in data:
        product.stock = int(data['stock'])
    if 'weight' in data:
        product.weight = data['weight']
    if 'burn_time' in data:
        product.burn_time = data['burn_time']
    if 'fragrance' in data:
        product.fragrance = data['fragrance']
    if 'wax_type' in data:
        product.wax_type = data['wax_type']
    if 'video_url' in data:
        product.video_url = data['video_url']
    if 'is_featured' in data:
        val = data['is_featured']
        product.is_featured = val if isinstance(val, bool) else str(val).lower() in ('true', '1', 'on')
    if 'is_customizable' in data:
        val = data['is_customizable']
        product.is_customizable = val if isinstance(val, bool) else str(val).lower() in ('true', '1', 'on')
    if 'is_active' in data:
        val = data['is_active']
        new_active = val if isinstance(val, bool) else str(val).lower() in ('true', '1', 'on')
        # Authorization required when activating an inactive product
        if new_active and not product.is_active:
            password = data.get('admin_password', '')
            if not password:
                return jsonify({'error': 'Admin password required to activate product', 'auth_required': True}), 403
            user = get_current_user()
            if not user or not user.check_password(password):
                return jsonify({'error': 'Invalid password'}), 403
        product.is_active = new_active
    
    log_admin_action(
        module='Product',
        action='UPDATE',
        target_id=product.id,
        description=f"Updated Product: {product.name}"
    )
    db.session.commit()
    return jsonify({'message': 'Product updated', 'product': product.to_dict()})


@admin_bp.route('/api/products/<product_id>', methods=['DELETE'])
@admin_required
def delete_product(product_id):
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404

    product_name = product.name
    cancelled_orders = []

    # ── Handle orders that contain this product ──────────────────
    order_items = OrderItem.query.filter_by(product_id=product_id).all()
    affected_order_ids = set()
    for oi in order_items:
        # Snapshot the product name so order history still shows it
        oi.product_name_snapshot = product_name
        oi.product_id = None  # Break FK so we can delete the product
        affected_order_ids.add(oi.order_id)

    # Cancel any non-delivered, non-cancelled orders that had this product
    for order_id in affected_order_ids:
        order = db.session.get(Order, order_id)
        if not order or order.status in ('delivered', 'cancelled'):
            continue

        reason = f'Sorry, "{product_name}" is out of stock and has been removed. Full refund will be processed.'
        order.status = 'cancelled'
        order.cancellation_reason = reason
        order.cancelled_by = 'admin'
        order.cancelled_at = datetime.utcnow()

        if order.payment_status == 'paid':
            order.payment_status = 'refunded'

        # Restore stock for OTHER products in this order (not the deleted one)
        for item in order.items:
            if item.product_id and item.product_id != product_id and item.product:
                item.product.stock += item.quantity

        # Add tracking entry
        tracking = OrderTracking(
            order_id=order.id,
            status='cancelled',
            description=reason
        )
        db.session.add(tracking)

        # Notify customer
        if order.user and order.user.email:
            try:
                send_cancellation_email(order.user.email, order.order_number, reason, 'admin')
            except Exception:
                pass

        cancelled_orders.append(order.order_number)

    # ── Clean up other references ────────────────────────────────
    CartItem.query.filter_by(product_id=product_id).delete()
    Review.query.filter_by(product_id=product_id).delete()

    # ProductImages cascade via relationship; delete the product
    log_admin_action(
        module='Product',
        action='DELETE',
        target_id=product_id,
        description=f"Deleted Product: {product_name}"
    )
    db.session.delete(product)
    db.session.commit()

    msg = f'Product "{product_name}" deleted.'
    if cancelled_orders:
        msg += f' {len(cancelled_orders)} order(s) cancelled & refunded: {", ".join(cancelled_orders)}.'
    return jsonify({'message': msg})


# ─────────────────────────────────────────────
# API: Verify Admin Password
# ─────────────────────────────────────────────
@admin_bp.route('/api/verify-password', methods=['POST'])
@admin_required
def verify_admin_password():
    """Verify the admin's password for sensitive operations."""
    data = request.get_json()
    password = data.get('password', '')
    if not password:
        return jsonify({'error': 'Password is required'}), 400
    user = get_current_user()
    if not user or not user.check_password(password):
        return jsonify({'error': 'Invalid password'}), 403
    return jsonify({'verified': True})


# ─────────────────────────────────────────────
# API: Toggle Product Status (requires password for activation)
# ─────────────────────────────────────────────
@admin_bp.route('/api/products/<product_id>/toggle-status', methods=['POST'])
@admin_required
def toggle_product_status(product_id):
    """Toggle product is_active. Requires admin password when activating."""
    product = db.session.get(Product, product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404

    data = request.get_json() or {}
    new_active = data.get('is_active', not product.is_active)

    # Authorization required when activating an inactive product
    if new_active and not product.is_active:
        password = data.get('password', '')
        if not password:
            return jsonify({'error': 'Admin password required to activate product', 'auth_required': True}), 403
        user = get_current_user()
        if not user or not user.check_password(password):
            return jsonify({'error': 'Invalid password'}), 403

    product.is_active = bool(new_active)
    db.session.commit()
    return jsonify({'message': f"Product {'activated' if product.is_active else 'deactivated'}", 'product': product.to_dict()})





# ─────────────────────────────────────────────
# API: Manage Orders
# ─────────────────────────────────────────────
@admin_bp.route('/api/orders', methods=['GET'])
@admin_or_sales_required
def get_orders():
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    
    query = Order.query
    if status:
        query = query.filter_by(status=status)
    
    orders = query.order_by(Order.created_at.desc())\
                 .paginate(page=page, per_page=20, error_out=False)
    
    return jsonify({
        'orders': [o.to_dict() for o in orders.items],
        'total': orders.total,
        'pages': orders.pages
    })


@admin_bp.route('/api/orders/<order_id>/status', methods=['PUT'])
@admin_or_sales_required
def update_order_status(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    
    data = request.get_json()
    new_status = data.get('status')
    
    valid_statuses = ['pending', 'confirmed', 'processing', 'shipped', 'delivered', 'cancelled']
    if new_status not in valid_statuses:
        return jsonify({'error': 'Invalid status'}), 400
    
    # Require cancellation reason when cancelling
    if new_status == 'cancelled':
        cancellation_reason = (data.get('cancellation_reason', '') or '').strip()
        if not cancellation_reason:
            return jsonify({'error': 'Cancellation reason is mandatory'}), 400
        
        order.cancellation_reason = cancellation_reason
        order.cancelled_by = 'admin'
        order.cancelled_at = datetime.utcnow()
        
        if order.payment_status == 'paid':
            order.payment_status = 'refunded'
        
        # Restore stock safely
        for item in order.items:
            if item.product and not item.product.is_customizable:
                item.product.stock += item.quantity
        
        # Send cancellation email to customer
        if order.user and order.user.email:
            send_cancellation_email(order.user.email, order.order_number, cancellation_reason, 'admin')
    
    # Build tracking description based on status transition
    tracking_descriptions = {
        'confirmed': 'Order confirmed by admin',
        'processing': 'Order is being prepared',
        'shipped': 'Order has been shipped',
        'delivered': 'Order delivered successfully',
        'cancelled': f'Order cancelled by admin — {data.get("cancellation_reason", "")}'
    }

    order.status = new_status

    # Add tracking entry
    tracking = OrderTracking(
        order_id=order.id,
        status=new_status,
        description=tracking_descriptions.get(new_status, f'Status updated to {new_status}'),
        location=data.get('location', '')
    )
    db.session.add(tracking)
    
    log_admin_action(
        module='Order',
        action='UPDATE',
        target_id=order.id,
        description=f"Updated Order Status: {new_status}",
        details={'order_number': order.order_number, 'status': new_status}
    )
    db.session.commit()

    # Send status update email to customer (for non-cancelled statuses)
    if new_status != 'cancelled' and order.user and order.user.email:
        try:
            send_order_status_email(order.user.email, order, new_status)
        except Exception as e:
            current_app.logger.error(f'Failed to send status email: {str(e)}')

    return jsonify({'message': 'Order status updated', 'order': order.to_dict()})


@admin_bp.route('/api/orders/<order_id>/shipping', methods=['PUT'])
@admin_or_sales_required
def update_order_shipping(order_id):
    """Update tracking number, carrier, and estimated delivery for an order."""
    order = db.session.get(Order, order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    data = request.get_json()
    updated_fields = []

    if 'tracking_number' in data:
        order.tracking_number = data['tracking_number']
        updated_fields.append(f'Tracking number: {data["tracking_number"]}')
    if 'carrier' in data:
        order.carrier = data['carrier']
        updated_fields.append(f'Carrier: {data["carrier"]}')
    if 'estimated_delivery' in data and data['estimated_delivery']:
        try:
            order.estimated_delivery = robust_parse_date(data['estimated_delivery'])
            updated_fields.append(f'Estimated delivery: {data["estimated_delivery"]}')
        except ValueError:
            return jsonify({'error': 'Invalid date format for estimated_delivery'}), 400

    if updated_fields:
        tracking = OrderTracking(
            order_id=order.id,
            status=order.status,
            description='Shipping details updated — ' + ', '.join(updated_fields)
        )
        db.session.add(tracking)

    log_admin_action(
        module='Order',
        action='UPDATE',
        target_id=order.id,
        description=f"Updated Order Shipping: {order.order_number}"
    )
    db.session.commit()
    return jsonify({'message': 'Shipping details updated', 'order': order.to_dict()})


# ─────────────────────────────────────────────
# API: Get single order with full transaction details
# ─────────────────────────────────────────────
@admin_bp.route('/api/orders/<order_id>', methods=['GET'])
@admin_or_sales_required
def get_order_detail(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    
    order_data = order.to_dict()
    
    # Add full payment/transaction details
    if order.payment:
        order_data['transaction'] = {
            'razorpay_payment_id': order.payment.razorpay_payment_id,
            'razorpay_order_id': order.payment.razorpay_order_id,
            'razorpay_signature': order.payment.razorpay_signature,
            'amount': order.payment.amount,
            'currency': order.payment.currency,
            'method': order.payment.method,
            'status': order.payment.status,
            'payment_date': order.payment.created_at.isoformat() if order.payment.created_at else None
        }
    
    # Add Razorpay order ID from the order itself
    order_data['razorpay_order_id'] = order.razorpay_order_id
    
    return jsonify({'order': order_data})


# ─────────────────────────────────────────────
# API: Delete individual order
# ─────────────────────────────────────────────
@admin_bp.route('/api/orders/<order_id>', methods=['DELETE'])
@admin_required
def delete_order(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    try:
        # Delete dependent records
        OrderItem.query.filter_by(order_id=order_id).delete()
        OrderTracking.query.filter_by(order_id=order_id).delete()
        Payment.query.filter_by(order_id=order_id).delete()
        Complaint.query.filter_by(order_id=order_id).delete()
        ReturnRequest.query.filter_by(order_id=order_id).delete()
        
        db.session.delete(order)
        db.session.commit()
        return jsonify({'message': f'Order {order.order_number} deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to delete order: {str(e)}'}), 500



# ─────────────────────────────────────────────
# API: Manage B2B Requests
# ─────────────────────────────────────────────
@admin_bp.route('/api/b2b', methods=['GET'])
@admin_required
def get_b2b_requests():
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    
    query = B2BRequest.query
    if status:
        query = query.filter_by(status=status)
    
    requests = query.order_by(B2BRequest.created_at.desc())\
                   .paginate(page=page, per_page=20, error_out=False)
    
    return jsonify({
        'requests': [r.to_dict() for r in requests.items],
        'total': requests.total,
        'pages': requests.pages
    })


@admin_bp.route('/api/b2b/<request_id>', methods=['PUT'])
@admin_required
def update_b2b_request(request_id):
    b2b = db.session.get(B2BRequest, request_id)
    if not b2b:
        return jsonify({'error': 'Request not found'}), 404
    
    data = request.get_json()
    
    if 'status' in data:
        b2b.status = data['status']
    if 'admin_notes' in data:
        b2b.admin_notes = data['admin_notes']
    if 'quotation_amount' in data:
        b2b.quotation_amount = float(data['quotation_amount'])
    
    log_admin_action(
        module='B2B',
        action='UPDATE',
        target_id=b2b.id,
        description=f"Updated B2B Request #{b2b.id}"
    )
    db.session.commit()
    return jsonify({'message': 'Request updated', 'request': b2b.to_dict()})


# ─────────────────────────────────────────────
# API: Manage Coupons
# ─────────────────────────────────────────────
@admin_bp.route('/coupons')
@admin_bp.route('/marketing')
@admin_or_sales_required
def coupons_page():
    user = get_current_user()
    return render_template('admin/coupons.html', user=user)


@admin_bp.route('/api/coupons', methods=['GET'])
@admin_required
def get_coupons():
    coupons = Coupon.query.order_by(Coupon.created_at.desc()).all()
    return jsonify({'coupons': [c.to_dict() for c in coupons]})


@admin_bp.route('/api/coupons', methods=['POST'])
@admin_required
def create_coupon():
    data = request.get_json()
    code = data.get('code', '').upper().strip()
    if not code:
        return jsonify({'error': 'Coupon code is required'}), 400
    if Coupon.query.filter_by(code=code).first():
        return jsonify({'error': 'Coupon code already exists'}), 400
    discount_value = float(data.get('discount_value', 0))
    if discount_value <= 0:
        return jsonify({'error': 'Discount value must be greater than 0'}), 400

    coupon = Coupon(
        code=code,
        discount_type=data.get('discount_type', 'percentage'),
        discount_value=discount_value,
        min_order=float(data.get('min_order', 0)),
        max_discount=float(data['max_discount']) if data.get('max_discount') else None,
        usage_limit=int(data['usage_limit']) if data.get('usage_limit') else None,
        expires_at=robust_parse_date(data['expires_at']) if data.get('expires_at') else None
    )

    db.session.add(coupon)
    db.session.commit()

    return jsonify({'message': 'Coupon created', 'coupon': coupon.to_dict()}), 201


@admin_bp.route('/api/coupons/<int:coupon_id>', methods=['PUT'])
@admin_required
def update_coupon(coupon_id):
    coupon = db.session.get(Coupon, coupon_id)
    if not coupon:
        return jsonify({'error': 'Coupon not found'}), 404
    data = request.get_json()

    new_code = data.get('code', '').upper().strip()
    if new_code and new_code != coupon.code:
        if Coupon.query.filter_by(code=new_code).first():
            return jsonify({'error': 'Coupon code already exists'}), 400
        coupon.code = new_code

    if 'discount_type' in data:
        coupon.discount_type = data['discount_type']
    if 'discount_value' in data:
        val = float(data['discount_value'])
        if val <= 0:
            return jsonify({'error': 'Discount value must be > 0'}), 400
        coupon.discount_value = val
    if 'min_order' in data:
        coupon.min_order = float(data['min_order']) if data['min_order'] else 0
    if 'max_discount' in data:
        coupon.max_discount = float(data['max_discount']) if data['max_discount'] else None
    if 'usage_limit' in data:
        coupon.usage_limit = int(data['usage_limit']) if data['usage_limit'] else None
    if 'expires_at' in data:
        coupon.expires_at = robust_parse_date(data['expires_at']) if data.get('expires_at') else None
    if 'is_active' in data:
        coupon.is_active = bool(data['is_active'])

    db.session.commit()
    return jsonify({'message': 'Coupon updated', 'coupon': coupon.to_dict()})


@admin_bp.route('/api/coupons/<int:coupon_id>/toggle', methods=['POST'])
@admin_required
def toggle_coupon(coupon_id):
    coupon = db.session.get(Coupon, coupon_id)
    if not coupon:
        return jsonify({'error': 'Coupon not found'}), 404
    coupon.is_active = not coupon.is_active
    db.session.commit()
    status = 'activated' if coupon.is_active else 'deactivated'
    return jsonify({'message': f'Coupon {status}', 'coupon': coupon.to_dict()})


@admin_bp.route('/api/coupons/<int:coupon_id>', methods=['DELETE'])
@admin_required
def delete_coupon(coupon_id):
    coupon = db.session.get(Coupon, coupon_id)
    if not coupon:
        return jsonify({'error': 'Coupon not found'}), 404
    db.session.delete(coupon)
    db.session.commit()
    return jsonify({'message': 'Coupon deleted'})



# ─────────────────────────────────────────────
# API: Manage Product Images (Carousel)
# ─────────────────────────────────────────────
@admin_bp.route('/api/products/<product_id>/images', methods=['GET'])
@admin_required
def get_product_images(product_id):
    product = db.session.get(Product, product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    images = ProductImage.query.filter_by(product_id=product_id)\
                               .order_by(ProductImage.display_order).all()
    return jsonify({'images': [img.to_dict() for img in images]})


@admin_bp.route('/api/products/<product_id>/images', methods=['POST'])
@admin_required
def add_product_image(product_id):
    product = db.session.get(Product, product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    
    # Support file upload (multipart) or JSON URL fallback
    image_url = None
    alt_text = ''
    
    if request.content_type and 'multipart/form-data' in request.content_type:
        file = request.files.get('image')
        if not file or not file.filename:
            return jsonify({'error': 'No image file provided'}), 400
        image_url = save_upload(file)
        if not image_url:
            return jsonify({'error': 'Invalid file type. Allowed: png, jpg, jpeg, gif, webp'}), 400
        alt_text = request.form.get('alt_text', product.name)
    else:
        data = request.get_json()
        image_url = (data.get('image_url') or '').strip()
        if not image_url:
            return jsonify({'error': 'Image URL is required'}), 400
        alt_text = data.get('alt_text', product.name)
    
    # Get next display order
    max_order = db.session.query(db.func.max(ProductImage.display_order))\
                          .filter_by(product_id=product_id).scalar() or 0
    
    img = ProductImage(
        product_id=product_id,
        image_url=image_url,
        alt_text=alt_text,
        display_order=max_order + 1
    )
    db.session.add(img)
    
    # Also set as main image_url if it's the first image
    if not product.image_url:
        product.image_url = image_url
    
    db.session.commit()
    return jsonify({'message': 'Image added', 'image': img.to_dict()}), 201


@admin_bp.route('/api/products/<product_id>/images/bulk', methods=['POST'])
@admin_required
def add_product_images_bulk(product_id):
    """Add multiple images at once via file upload or URL list."""
    product = db.session.get(Product, product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    
    max_order = db.session.query(db.func.max(ProductImage.display_order))\
                          .filter_by(product_id=product_id).scalar() or 0
    
    added = []
    
    if request.content_type and 'multipart/form-data' in request.content_type:
        files = request.files.getlist('images')
        if not files:
            return jsonify({'error': 'At least one image file is required'}), 400
        for i, file in enumerate(files):
            url = save_upload(file)
            if url:
                img = ProductImage(
                    product_id=product_id,
                    image_url=url,
                    alt_text=f"{product.name} - Image {max_order + i + 1}",
                    display_order=max_order + i + 1
                )
                db.session.add(img)
                added.append(img)
    else:
        data = request.get_json()
        image_urls = data.get('image_urls', [])
        if not image_urls:
            return jsonify({'error': 'At least one image URL is required'}), 400
        for i, url in enumerate(image_urls):
            url = url.strip()
            if url:
                img = ProductImage(
                    product_id=product_id,
                    image_url=url,
                    alt_text=f"{product.name} - Image {max_order + i + 1}",
                    display_order=max_order + i + 1
                )
                db.session.add(img)
                added.append(img)
    
    if not product.image_url and added:
        product.image_url = added[0].image_url
    
    db.session.commit()
    return jsonify({'message': f'{len(added)} images added', 'images': [i.to_dict() for i in added]}), 201


@admin_bp.route('/api/products/<product_id>/images/<image_id>', methods=['DELETE'])
@admin_required
def delete_product_image(product_id, image_id):
    img = ProductImage.query.filter_by(id=image_id, product_id=product_id).first()
    if not img:
        return jsonify({'error': 'Image not found'}), 404
    
    # Delete binary data from ImageStore if stored in DB
    if img.image_url and img.image_url.startswith('/img/store/'):
        from models import ImageStore
        store_id = img.image_url.split('/img/store/')[-1]
        store_record = ImageStore.query.get(store_id)
        if store_record:
            db.session.delete(store_record)
    
    db.session.delete(img)
    db.session.commit()
    return jsonify({'message': 'Image deleted'})


@admin_bp.route('/api/products/<product_id>/images/reorder', methods=['PUT'])
@admin_required
def reorder_product_images(product_id):
    """Reorder images by passing array of image_ids in desired order."""
    data = request.get_json()
    image_ids = data.get('image_ids', [])
    
    for i, img_id in enumerate(image_ids):
        img = ProductImage.query.filter_by(id=img_id, product_id=product_id).first()
        if img:
            img.display_order = i
    
    db.session.commit()
    return jsonify({'message': 'Images reordered'})


# ─────────────────────────────────────────────
# API: Manage Reviews (admin)
# ─────────────────────────────────────────────
@admin_bp.route('/api/reviews', methods=['GET'])
@admin_required
def get_reviews():
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    
    query = Review.query
    if status == 'pending':
        query = query.filter_by(is_approved=False)
    elif status == 'approved':
        query = query.filter_by(is_approved=True)
    
    reviews = query.order_by(Review.created_at.desc())\
                  .paginate(page=page, per_page=20, error_out=False)
    
    return jsonify({
        'reviews': [r.to_dict() for r in reviews.items],
        'total': reviews.total,
        'pages': reviews.pages
    })


@admin_bp.route('/api/reviews/<review_id>', methods=['PUT'])
@admin_required
def update_review(review_id):
    review = db.session.get(Review, review_id)
    if not review:
        return jsonify({'error': 'Review not found'}), 404
    
    data = request.get_json()
    if 'is_approved' in data:
        review.is_approved = data['is_approved']
    
    db.session.commit()
    return jsonify({'message': 'Review updated', 'review': review.to_dict()})


@admin_bp.route('/api/reviews/<review_id>', methods=['DELETE'])
@admin_required
def delete_review(review_id):
    review = db.session.get(Review, review_id)
    if not review:
        return jsonify({'error': 'Review not found'}), 404
    
    # Recalculate product rating
    product = review.product
    db.session.delete(review)
    db.session.flush()
    
    remaining = Review.query.filter_by(product_id=product.id, is_approved=True).all()
    if remaining:
        product.rating_avg = round(sum(r.rating for r in remaining) / len(remaining), 1)
        product.rating_count = len(remaining)
    else:
        product.rating_avg = 0.0
        product.rating_count = 0
    
    db.session.commit()
    return jsonify({'message': 'Review deleted'})


# ═════════════════════════════════════════════════════════════
# CUSTOMIZATION OPTIONS MANAGEMENT
# ═════════════════════════════════════════════════════════════

OPTION_CATEGORIES = [
    'jar_type', 'colour', 'fragrance', 'wick_type',
    'shape', 'ingredient', 'wax_type',
]

# ─────────────────────────────────────────────
# PAGE: Admin Customizations
# ─────────────────────────────────────────────
@admin_bp.route('/customizations')
@admin_required
def customizations_page():
    user = get_current_user()
    return render_template('admin/customizations.html', user=user, categories=OPTION_CATEGORIES)


# ─────────────────────────────────────────────
# API: List all customization options
# ─────────────────────────────────────────────
@admin_bp.route('/api/customization-options', methods=['GET'])
@admin_required
def get_customization_options():
    category = request.args.get('category', '')
    query = CustomizationOption.query

    if category:
        query = query.filter_by(category=category)

    options = query.order_by(
        CustomizationOption.category,
        CustomizationOption.display_order,
        CustomizationOption.name
    ).all()

    # Group by category
    grouped = {}
    for opt in options:
        grouped.setdefault(opt.category, []).append(opt.to_dict())

    return jsonify({
        'options': [o.to_dict() for o in options],
        'grouped': grouped,
        'categories': OPTION_CATEGORIES,
        'total': len(options),
    })


# ─────────────────────────────────────────────
# API: Create customization option
# ─────────────────────────────────────────────
@admin_bp.route('/api/customization-options', methods=['POST'])
@admin_required
def create_customization_option():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    category = data.get('category', '').strip()
    name = data.get('name', '').strip()
    value = data.get('value', '').strip()

    if not category or not name or not value:
        return jsonify({'error': 'Category, name and value are required'}), 400

    if category not in OPTION_CATEGORIES:
        return jsonify({'error': f'Invalid category. Must be one of: {", ".join(OPTION_CATEGORIES)}'}), 400

    # Check for duplicate value in same category
    existing = CustomizationOption.query.filter_by(category=category, value=value).first()
    if existing:
        return jsonify({'error': f'Option with value "{value}" already exists in {category}'}), 409

    option = CustomizationOption(
        category=category,
        name=name,
        value=value,
        icon=data.get('icon', '').strip() or None,
        color_hex=data.get('color_hex', '').strip() or None,
        price_addon=float(data.get('price_addon', 0)),
        description=data.get('description', '').strip() or None,
        display_order=int(data.get('display_order', 0)),
        is_active=data.get('is_active', True),
    )
    db.session.add(option)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to create option: {str(e)}'}), 500
    return jsonify({'message': 'Option created', 'option': option.to_dict()}), 201


# ─────────────────────────────────────────────
# API: Update customization option
# ─────────────────────────────────────────────
@admin_bp.route('/api/customization-options/<option_id>', methods=['PUT'])
@admin_required
def update_customization_option(option_id):
    option = db.session.get(CustomizationOption, option_id)
    if not option:
        return jsonify({'error': 'Option not found'}), 404

    data = request.get_json()
    if data.get('name'):
        option.name = data['name'].strip()
    if data.get('value'):
        # Check duplicate in same category
        dup = CustomizationOption.query.filter(
            CustomizationOption.category == option.category,
            CustomizationOption.value == data['value'].strip(),
            CustomizationOption.id != option.id,
        ).first()
        if dup:
            return jsonify({'error': f'Value "{data["value"]}" already exists in {option.category}'}), 409
        option.value = data['value'].strip()
    if 'icon' in data:
        option.icon = data['icon'].strip() or None
    if 'color_hex' in data:
        option.color_hex = data['color_hex'].strip() or None
    if 'price_addon' in data:
        option.price_addon = float(data['price_addon'])
    if 'description' in data:
        option.description = data['description'].strip() or None
    if 'display_order' in data:
        option.display_order = int(data['display_order'])
    if 'is_active' in data:
        option.is_active = bool(data['is_active'])

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to update option: {str(e)}'}), 500
    return jsonify({'message': 'Option updated', 'option': option.to_dict()})


# ─────────────────────────────────────────────
# API: Delete customization option
# ─────────────────────────────────────────────
@admin_bp.route('/api/customization-options/<option_id>', methods=['DELETE'])
@admin_required
def delete_customization_option(option_id):
    option = db.session.get(CustomizationOption, option_id)
    if not option:
        return jsonify({'error': 'Option not found'}), 404

    db.session.delete(option)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to delete option: {str(e)}'}), 500
    return jsonify({'message': 'Option deleted'})


# ─────────────────────────────────────────────
# PUBLIC API: Get active options (for customize page)
# ─────────────────────────────────────────────
@admin_bp.route('/api/public/customization-options', methods=['GET'])
def get_public_customization_options():
    options = CustomizationOption.query.filter_by(is_active=True)\
        .order_by(CustomizationOption.category, CustomizationOption.display_order).all()

    grouped = {}
    for opt in options:
        grouped.setdefault(opt.category, []).append(opt.to_dict())

    return jsonify({'options': grouped})


# ═════════════════════════════════════════════════════════════
# COMPLAINTS MANAGEMENT
# ═════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────
# PAGE: Admin Complaints
# ─────────────────────────────────────────────
@admin_bp.route('/complaints')
@admin_bp.route('/helpdesk')
@admin_or_sales_required
def complaints_page():
    user = get_current_user()
    return render_template('admin/complaints.html', user=user)


# ─────────────────────────────────────────────
# API: Get all complaints (admin)
# ─────────────────────────────────────────────
@admin_bp.route('/api/complaints', methods=['GET'])
@admin_required
def get_all_complaints():
    status = request.args.get('status', '')
    query = Complaint.query

    if status:
        query = query.filter_by(status=status)

    complaints = query.order_by(Complaint.created_at.desc()).all()
    return jsonify({'complaints': [c.to_dict() for c in complaints]})


# ─────────────────────────────────────────────
# API: Update complaint (admin)
# ─────────────────────────────────────────────
@admin_bp.route('/api/complaints/<complaint_id>', methods=['PUT'])
@admin_required
def update_complaint(complaint_id):
    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        return jsonify({'error': 'Complaint not found'}), 404

    data = request.get_json()
    if 'status' in data:
        complaint.status = data['status']
        if data['status'] == 'resolved':
            complaint.resolved_at = datetime.utcnow()
    if 'admin_response' in data:
        complaint.admin_response = data['admin_response'].strip()
    if 'priority' in data:
        complaint.priority = data['priority']

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to update complaint: {str(e)}'}), 500
    return jsonify({'message': 'Complaint updated', 'complaint': complaint.to_dict()})


# ═════════════════════════════════════════════════════════════
# INVOICES PAGE
# ═════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────
# PAGE: Admin Invoices
# ─────────────────────────────────────────────
@admin_bp.route('/invoices')
@admin_or_sales_required
def invoices_page():
    user = get_current_user()
    return render_template('admin/invoices.html', user=user)


# ─────────────────────────────────────────────
# API: Get paid orders for invoice listing
# ─────────────────────────────────────────────
@admin_bp.route('/api/invoices', methods=['GET'])
@admin_or_sales_required
def get_invoices():
    search = request.args.get('search', '').strip()
    query = Order.query.filter(Order.payment_status == 'paid')

    if search:
        query = query.filter(
            db.or_(
                Order.order_number.ilike(f'%{search}%'),
                Order.shipping_name.ilike(f'%{search}%'),
            )
        )

    orders = query.order_by(Order.created_at.desc()).all()

    invoices = []
    for o in orders:
        txn = o.payment
        invoices.append({
            'id': o.id,
            'order_number': o.order_number,
            'customer_name': o.user.full_name if o.user else '-',
            'customer_email': o.user.email if o.user else '-',
            'total_amount': o.total_amount,
            'payment_status': o.payment_status,
            'order_status': o.status,
            'razorpay_payment_id': txn.razorpay_payment_id if txn else None,
            'razorpay_order_id': txn.razorpay_order_id if txn else None,
            'payment_method': txn.method if txn else None,
            'payment_date': txn.created_at.isoformat() if txn and txn.created_at else None,
            'order_date': o.created_at.isoformat() if o.created_at else None,
        })

    return jsonify({'invoices': invoices})


# ─────────────────────────────────────────────
# API: Download invoice HTML (admin)
# ─────────────────────────────────────────────
@admin_bp.route('/api/orders/<order_id>/invoice', methods=['GET'])
@admin_or_sales_required
def download_invoice_admin(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    html = _generate_invoice_html(order)
    response = make_response(html)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    if request.args.get('download'):
        response.headers['Content-Disposition'] = f'attachment; filename=invoice_{order.order_number}.html'
    return response


# ─────────────────────────────────────────────
# PAGE: Admin Settings
# ─────────────────────────────────────────────
@admin_bp.route('/settings')
@admin_required
def settings_page():
    user = get_current_user()
    return render_template('admin/settings.html', user=user)


@admin_bp.route('/api/admin/profile', methods=['PUT'])
@admin_required
def update_admin_profile():
    """Update current admin profile fields used in settings page."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json(silent=True) or {}
    new_email = (data.get('email') or '').strip().lower()

    if not new_email:
        return jsonify({'error': 'Email cannot be empty'}), 400

    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', new_email):
        return jsonify({'error': 'Please enter a valid email address'}), 400

    existing_user = User.query.filter(
        User.email == new_email,
        User.id != user.id
    ).first()
    if existing_user:
        return jsonify({'error': 'This email is already in use'}), 409

    try:
        user.email = new_email
        db.session.commit()
        return jsonify({'message': 'Email updated successfully. Please login again.'}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Admin email update failed: {e}')
        return jsonify({'error': 'Failed to update email'}), 500


# ─────────────────────────────────────────────
# PAGE: Finance Management
# ─────────────────────────────────────────────
@admin_bp.route('/finance')
@admin_or_sales_required
def finance_page():
    user = get_current_user()
    return render_template('admin/finance.html', user=user)


# ─────────────────────────────────────────────
# API: Finance Records (Listing / CRUD)
# ─────────────────────────────────────────────
@admin_bp.route('/api/finance', methods=['GET'])
@admin_or_sales_required
def get_finance_records():
    records = FinanceRecord.query.order_by(FinanceRecord.date.desc()).all()
    
    # Calculate partner breakdown
    partners = Partner.query.all()
    base_shares = {p.id: {'name': p.name, 'invested': 0, 'color': p.color_hex} for p in partners}
    
    cap_records = FinanceRecord.query.filter_by(record_type='capital').all()
    for r in cap_records:
        if r.partner_id in base_shares:
            base_shares[r.partner_id]['invested'] += r.amount

    return jsonify({
        'records': [r.to_dict() for r in records],
        'total_expense': db.session.query(db.func.sum(FinanceRecord.amount)).filter_by(record_type='expense').scalar() or 0,
        'total_capital': db.session.query(db.func.sum(FinanceRecord.amount)).filter_by(record_type='capital').scalar() or 0,
        'partner_stats': list(base_shares.values())
    })


@admin_bp.route('/api/finance/partnership-stats', methods=['GET'])
@admin_or_sales_required
def get_partnership_stats():
    partners = Partner.query.all()
    stats = []
    total_cap = db.session.query(db.func.sum(FinanceRecord.amount)).filter_by(record_type='capital').scalar() or 0
    
    for p in partners:
        p_cap = db.session.query(db.func.sum(FinanceRecord.amount)).filter_by(partner_id=p.id, record_type='capital').scalar() or 0
        stats.append({
            'id': p.id,
            'name': p.name,
            'total_invested': p_cap,
            'share_percent': 25.0, # Base 25% each as agreed
            'color': p.color_hex
        })
    return jsonify({'partners': stats, 'total_capital': total_cap})

@admin_bp.route('/api/finance', methods=['POST'])
@admin_or_sales_required
def create_finance_record():
    # Support both JSON and multipart (for bills)
    if 'multipart/form-data' in request.content_type:
        data = request.form
        bill_file = request.files.get('bill')
    else:
        data = request.get_json()
        bill_file = None

    try:
        bill_url = save_upload(bill_file, subfolder='bills') if bill_file else None
        
        record = FinanceRecord(
            title=data.get('title'),
            amount=float(data.get('amount', 0)),
            record_type=data.get('type', 'expense'),
            category=data.get('category'),
            date=robust_parse_date(data.get('date')),
            notes=data.get('notes'),
            partner_id=data.get('partner_id') if data.get('partner_id') and data.get('partner_id') not in ['null', ''] else None,
            bill_url=bill_url
        )
        db.session.add(record)
        
        details={'amount': record.amount, 'type': record.record_type, 'partner': record.partner_id}

        # Handle Partner Personal Account Purchases (Expense paid by partner)
        if record.record_type == 'expense' and record.partner_id:
            cap_record = FinanceRecord(
                title=f"Capital Infusion (Auto - Covered Expense: {record.title})",
                amount=record.amount,
                record_type='capital',
                category='Partner Capital',
                date=record.date,
                notes=f"Auto-generated because the partner personally paid for the '{record.title}' expense.",
                partner_id=record.partner_id
            )
            db.session.add(cap_record)
            details['auto_capital_infusion'] = True
        
        # Logging
        log_admin_action(
            module='Finance',
            action='CREATE',
            target_id=None,
            description=f"Added {record.record_type} entry: {record.title} (₹{record.amount})",
            details=details
        )
        
        db.session.commit()
        return jsonify({'message': 'Finance record added', 'record': record.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400


@admin_bp.route('/api/finance/<int:record_id>', methods=['DELETE'])
@admin_required
def delete_finance_record(record_id):
    record = FinanceRecord.query.get_or_404(record_id)
    try:
        log_admin_action(
            module='Finance',
            action='DELETE',
            target_id=record.id,
            description=f"Deleted {record.record_type} entry: {record.title} (₹{record.amount})"
        )
        db.session.delete(record)
        db.session.commit()
        return jsonify({'message': 'Record deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────
# PAGE: Inventory Management (Raw Materials)
# ─────────────────────────────────────────────
@admin_bp.route('/inventory')
@admin_or_sales_required
def inventory_page():
    user = get_current_user()
    return render_template('admin/inventory.html', user=user)


# ─────────────────────────────────────────────
# API: Inventory (Raw Materials CRUD)
# ─────────────────────────────────────────────
@admin_bp.route('/api/inventory', methods=['GET'])
@admin_or_sales_required
def get_inventory():
    materials = RawMaterial.query.order_by(RawMaterial.name).all()
    return jsonify({
        'materials': [m.to_dict() for m in materials],
        'low_stock_count': RawMaterial.query.filter(RawMaterial.stock_quantity <= RawMaterial.reorder_level).count()
    })

@admin_bp.route('/api/inventory', methods=['POST'])
@admin_or_sales_required
def create_inventory_item():
    # Support both JSON and multipart (for bills)
    if 'multipart/form-data' in request.content_type:
        data = request.form
        bill_file = request.files.get('bill')
    else:
        data = request.get_json()
        bill_file = None

    try:
        stock = float(data.get('stock', 0))
        cost = float(data.get('cost', 0))
        
        # Support 'Total Cost' logic from bills
        if 'total_cost' in data and data['total_cost'] and stock > 0:
            cost = float(data['total_cost']) / stock

        bill_url = save_upload(bill_file, subfolder='bills') if bill_file else None

        item = RawMaterial(
            name=data.get('name'),
            material_type=data.get('type'),
            specific_type=data.get('specific_type'),
            stock_quantity=stock,
            unit=data.get('unit', 'units'),
            reorder_level=float(data.get('reorder_level', 10)),
            cost_per_unit=round(cost, 2),
            supplier=data.get('supplier'),
            bill_url=bill_url,
            purchase_date=robust_parse_date(data.get('date')),
            purchased_by_id=data.get('purchased_by_id') if data.get('purchased_by_id') and data.get('purchased_by_id') not in ['null', ''] else None
        )
        db.session.add(item)
        
        # Automation: Record Finance Entry
        if item.cost_per_unit > 0:
            total_cost = round(item.cost_per_unit * item.stock_quantity, 2)
            if item.purchased_by_id:
                record_type = 'capital'
                title = f"Inventory Purchase (Capital): {item.name}"
            else:
                record_type = 'expense'
                title = f"Inventory Purchase (Expense): {item.name}"
                
            cap_record = FinanceRecord(
                title=title,
                amount=total_cost,
                record_type=record_type,
                category='Raw Material',
                date=item.purchase_date,
                partner_id=item.purchased_by_id,
                bill_url=item.bill_url,
                notes=f"Auto-generated from Inventory procurement of {item.stock_quantity} {item.unit}."
            )
            db.session.add(cap_record)

        # Logging
        log_admin_action(
            module='Inventory',
            action='CREATE',
            target_id=None,
            description=f"Added Material: {item.name} ({item.stock_quantity} {item.unit})",
            details={'name': item.name, 'stock': item.stock_quantity, 'purchaser': item.purchased_by_id}
        )

        db.session.commit()
        return jsonify({'message': 'Inventory item added', 'item': item.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@admin_bp.route('/api/inventory/<int:item_id>', methods=['PUT'])
@admin_or_sales_required
def update_inventory_item(item_id):
    item = RawMaterial.query.get_or_404(item_id)
    
    if 'multipart/form-data' in request.content_type:
        data = request.form
        bill_file = request.files.get('bill')
    else:
        data = request.get_json()
        bill_file = None

    try:
        old_vals = item.to_dict()
        if 'name' in data: item.name = data['name']
        if 'type' in data: item.material_type = data['type']
        if 'specific_type' in data: item.specific_type = data['specific_type']
        if 'stock' in data: item.stock_quantity = float(data['stock'])
        if 'unit' in data: item.unit = data['unit']
        if 'reorder_level' in data: item.reorder_level = float(data['reorder_level'])
        
        if 'total_cost' in data and data['total_cost'] and item.stock_quantity > 0:
            item.cost_per_unit = round(float(data['total_cost']) / item.stock_quantity, 2)
        elif 'cost' in data: 
            item.cost_per_unit = float(data['cost'])
            
        if 'supplier' in data: item.supplier = data['supplier']
        if 'date' in data and data['date']: item.purchase_date = robust_parse_date(data['date'])
        if 'purchased_by_id' in data: 
            item.purchased_by_id = data['purchased_by_id'] if data['purchased_by_id'] != '' else None

        if bill_file:
            item.bill_url = save_upload(bill_file, subfolder='bills')

        # Logging
        log_admin_action(
            module='Inventory',
            action='UPDATE',
            target_id=item.id,
            description=f"Updated Material: {item.name}",
            details={'old': old_vals, 'new': item.to_dict()}
        )
        
        db.session.commit()
        return jsonify({'message': 'Inventory updated', 'item': item.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@admin_bp.route('/api/inventory/<int:item_id>', methods=['DELETE'])
@admin_or_sales_required
def delete_inventory_item(item_id):
    item = RawMaterial.query.get_or_404(item_id)
    try:
        log_admin_action(
            module='Inventory',
            action='DELETE',
            target_id=item.id,
            description=f"Deleted Material: {item.name}"
        )
        db.session.delete(item)
        db.session.commit()
        return jsonify({'message': 'Item removed from inventory'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/api/audit-logs', methods=['GET'])
@admin_required
def get_audit_logs():
    page = request.args.get('page', 1, type=int)
    module = request.args.get('module')
    
    query = AuditLog.query
    if module:
        query = query.filter_by(module=module)
        
    logs = query.order_by(AuditLog.created_at.desc())\
                .paginate(page=page, per_page=50, error_out=False)
                
    return jsonify({
        'logs': [l.to_dict() for l in logs.items],
        'total': logs.total,
        'pages': logs.pages
    })


@admin_bp.route('/audit-logs')
@admin_required
def audit_logs_page():
    user = get_current_user()
    return render_template('admin/audit_logs.html', user=user)


# ─────────────────────────────────────────────
# PAGE: Inventory & Delivery
# ─────────────────────────────────────────────
@admin_bp.route('/delivery')
@admin_or_sales_required
def delivery_page():
    user = get_current_user()
    return render_template('admin/delivery.html', user=user)


# ─────────────────────────────────────────────
# PAGE: Manufacturing Recipes (Composition Guide)
# ─────────────────────────────────────────────
@admin_bp.route('/manufacturing')
@admin_or_sales_required
def manufacturing_page():
    user = get_current_user()
    return render_template('admin/manufacturing.html', user=user)


@admin_bp.route('/api/manufacturing/recipes', methods=['GET'])
@admin_or_sales_required
def get_recipes():
    recipes = ManufacturingRecipe.query.order_by(ManufacturingRecipe.name).all()
    return jsonify([r.to_dict() for r in recipes])


@admin_bp.route('/api/manufacturing/recipes', methods=['POST'])
@admin_or_sales_required
def create_recipe():
    data = request.get_json()
    try:
        recipe = ManufacturingRecipe(
            name=data.get('name'),
            category=data.get('category', 'Color'),
            composition=data.get('composition', {}),
            instructions=data.get('instructions'),
            color_hex=data.get('color_hex')
        )
        db.session.add(recipe)
        db.session.commit()
        return jsonify(recipe.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400


@admin_bp.route('/api/manufacturing/recipes/<int:recipe_id>', methods=['DELETE'])
@admin_or_sales_required
def delete_recipe(recipe_id):
    recipe = ManufacturingRecipe.query.get_or_404(recipe_id)
    try:
        db.session.delete(recipe)
        db.session.commit()
        return jsonify({'message': 'Recipe deleted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500



# ─────────────────────────────────────────────
# PAGE: Admin Home Page Editor
# ─────────────────────────────────────────────
@admin_bp.route('/homepage')
@admin_bp.route('/homepage/')
@admin_bp.route('/home-page')
@admin_required
def homepage_page():
    user = get_current_user()
    return render_template('admin/homepage.html', user=user)
# ─────────────────────────────────────────────
# PAGE: Staff Management
# ─────────────────────────────────────────────
@admin_bp.route('/staff')
@admin_required
def staff_page():
    user = get_current_user()
    return render_template('admin/staff.html', user=user)

# ─────────────────────────────────────────────
# API: Manage Staff
# ─────────────────────────────────────────────
@admin_bp.route('/api/staff', methods=['GET'])
@admin_required
def get_staff_users():
    staff = User.query.filter(User.role.in_(['admin', 'sales'])).all()
    return jsonify({'staff': [u.to_dict() for u in staff]})

@admin_bp.route('/api/staff', methods=['POST'])
@admin_required
def create_staff():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    role = data.get('role', 'sales')
    full_name = data.get('full_name', '').strip()
    password = data.get('password', '')

    if not email or not password or not full_name:
        return jsonify({'error': 'All fields are required'}), 400

    # Privilege Escalation Protection
    current = get_current_user()
    if role == 'admin' and not current.is_admin:
        return jsonify({'error': 'Only Master Admins can create other Admin accounts'}), 403

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already exists'}), 400

    try:
        new_user = User(
            email=email,
            full_name=full_name,
            role=role,
            is_active=True,
            is_email_verified=True
        )
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.flush() # Get user id for audit if needed
        
        log_admin_action('Staff', 'CREATE', new_user.id, f"Created {role} account: {email}")
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Staff creation error: {e}")
        return jsonify({'error': 'Failed to create staff account'}), 500

    return jsonify({'message': 'Staff generated', 'staff': new_user.to_dict()}), 201

@admin_bp.route('/api/staff/<string:user_id>/toggle', methods=['POST'])
@admin_required
def toggle_staff(user_id):
    if not user:
        return jsonify({'error': 'Staff not found'}), 404
        
    current = get_current_user()
    
    # Privilege Escalation Protection
    if user.is_admin and not current.is_admin:
        return jsonify({'error': 'Only Master Admins can toggle other Admin accounts'}), 403
    if user.id == current.id:
        return jsonify({'error': 'Cannot toggle your own access'}), 400

    try:
        user.is_active = not user.is_active
        status = "Activated" if user.is_active else "Deactivated"
        
        log_admin_action('Staff', 'UPDATE', user.id, f"{status} staff account: {user.email}")
        db.session.commit()
        return jsonify({'message': f'Account {status}', 'is_active': user.is_active})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to toggle staff status'}), 500

@admin_bp.route('/api/staff/<string:user_id>/password', methods=['PUT'])
@admin_required
def update_staff_password(user_id):
    if not user:
        return jsonify({'error': 'Staff not found'}), 404

    current = get_current_user()
    # Privilege Escalation Protection
    if user.is_admin and not current.is_admin:
        return jsonify({'error': 'Only Master Admins can reset Admin passwords'}), 403

    data = request.get_json()
    new_pass = data.get('password', '')
    
    if len(new_pass) < 6:
        return jsonify({'error': 'Password too short (min 6 chars)'}), 400
        
    try:
        user.set_password(new_pass)
        log_admin_action('Staff', 'UPDATE', user.id, f"Reset password for staff: {user.email}")
        db.session.commit()
        return jsonify({'message': 'Password updated for ' + user.email})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to update password'}), 500

@admin_bp.route('/api/staff/<string:user_id>/permissions', methods=['GET', 'PUT'])
@admin_required
def manage_staff_permissions(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'Staff not found'}), 404
        
    # Privilege Escalation Protection
    current = get_current_user()
    if user.is_admin and not current.is_admin:
        return jsonify({'error': 'Permissions for Master Admins cannot be modified'}), 403
        
    key = f'sales_perms_{user.id}'
    
    if request.method == 'GET':
        perms = SiteSettings.get(key, '')
        return jsonify({'permissions': [p.strip() for p in perms.split(',') if p.strip()]})
        
    # PUT update
    data = request.get_json()
    new_perms = data.get('permissions', [])
    perms_str = ','.join(new_perms)
    
    try:
        SiteSettings.set(key, perms_str)
        log_admin_action('Staff', 'UPDATE', user.id, f"Updated permissions for: {user.email}")
        return jsonify({'message': 'Permissions updated'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to update permissions'}), 500


# ─────────────────────────────────────────────
# API: Get / Update Site Settings
# ─────────────────────────────────────────────
@admin_bp.route('/api/settings', methods=['GET'])
@admin_required
def get_settings():
    keys = [
        'slider_img_1', 'slider_img_2', 'slider_img_3', 'slider_img_4', 'slider_img_5',
        'slider_img_6', 'slider_img_7', 'slider_img_8', 'slider_img_9', 'slider_img_10',
        'gst_number',
        'instagram_handle',
        'org_name', 'org_address', 'org_phone', 'org_email',
        'support_email', 'sales_email',
        'home_phi_img_1',
        'home_phi_img_2',
        'home_phi_img_3',
        'coll_img_1', 'coll_name_1',
        'coll_img_2', 'coll_name_2',
        'coll_img_3', 'coll_name_3',
        'coll_img_4', 'coll_name_4',
        'coll_img_5', 'coll_name_5',
        'coll_img_6', 'coll_name_6',
        'b2b_img',
        'insta_img_1',
        'insta_img_2',
        'insta_img_3',
        'insta_img_4',
        'insta_img_5',
        'insta_img_6',
        'hero_vid_1', 'hero_vid_2', 'hero_vid_3', 'hero_vid_4', 'hero_vid_5',
        'hero_vid_6', 'hero_vid_7', 'hero_vid_8', 'hero_vid_9', 'hero_vid_10',
        'reel_1_url', 'reel_1_title', 'reel_1_thumb',
        'reel_2_url', 'reel_2_title', 'reel_2_thumb',
        'reel_3_url', 'reel_3_title', 'reel_3_thumb',
        'reel_4_url', 'reel_4_title', 'reel_4_thumb',
        'reel_5_url', 'reel_5_title', 'reel_5_thumb',
        'reel_6_url', 'reel_6_title', 'reel_6_thumb',
        'promo_limit_img', 'promo_limit_title', 'promo_limit_desc', 'promo_limit_link',
        'gift_hampers_header', 'gift_hampers_desc',
        'gift_hampers_img_1', 'gift_hampers_title_1', 'gift_hampers_desc_1', 'gift_hampers_link_1',
        'gift_hampers_img_2', 'gift_hampers_title_2', 'gift_hampers_desc_2', 'gift_hampers_link_2',
        'custom_studio_img', 'custom_studio_title', 'custom_studio_desc',
    ]
    settings = {}
    for key in keys:
        settings[key] = SiteSettings.get(key, '')
    return jsonify(settings)


@admin_bp.route('/api/settings', methods=['PUT'])
@admin_required
def update_settings():
    from flask_jwt_extended import get_jwt_identity
    from models import User
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
        
    password = data.get('password')
    if not password:
        return jsonify({'error': 'Password verification required'}), 403
        
    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)
    if not user or not user.check_password(password):
        return jsonify({'error': 'Invalid administrative password'}), 403
        
    updated = []

    home_image_keys = [
        'slider_img_1', 'slider_img_2', 'slider_img_3', 'slider_img_4', 'slider_img_5',
        'slider_img_6', 'slider_img_7', 'slider_img_8', 'slider_img_9', 'slider_img_10',
        'home_phi_img_1', 'home_phi_img_2', 'home_phi_img_3',
        'coll_img_1', 'coll_name_1', 'coll_img_2', 'coll_name_2',
        'coll_img_3', 'coll_name_3', 'coll_img_4', 'coll_name_4',
        'coll_img_5', 'coll_name_5', 'coll_img_6', 'coll_name_6',
        'b2b_img', 'insta_img_1', 'insta_img_2', 
        'insta_img_3', 'insta_img_4', 'insta_img_5', 'insta_img_6',
        'hero_vid_1', 'hero_vid_2', 'hero_vid_3', 'hero_vid_4', 'hero_vid_5',
        'hero_vid_6', 'hero_vid_7', 'hero_vid_8', 'hero_vid_9', 'hero_vid_10',
        'reel_1_url', 'reel_1_title', 'reel_1_thumb',
        'reel_2_url', 'reel_2_title', 'reel_2_thumb',
        'reel_3_url', 'reel_3_title', 'reel_3_thumb',
        'reel_4_url', 'reel_4_title', 'reel_4_thumb',
        'reel_5_url', 'reel_5_title', 'reel_5_thumb',
        'reel_6_url', 'reel_6_title', 'reel_6_thumb',
        'promo_limit_img', 'promo_limit_title', 'promo_limit_desc', 'promo_limit_link',
        'gift_hampers_header', 'gift_hampers_desc',
        'gift_hampers_img_1', 'gift_hampers_title_1', 'gift_hampers_desc_1', 'gift_hampers_link_1',
        'gift_hampers_img_2', 'gift_hampers_title_2', 'gift_hampers_desc_2', 'gift_hampers_link_2',
        'custom_studio_img', 'custom_studio_title', 'custom_studio_desc'
    ]

    if 'gst_number' in data:
        gst = (data['gst_number'] or '').strip().upper()
        if gst and not re.match(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$', gst):
            return jsonify({'error': 'Invalid GST number format. Expected format: 22AAAAA0000A1Z5'}), 400
        SiteSettings.set('gst_number', gst)
        updated.append('gst_number')

    if 'instagram_handle' in data:
        handle = (data['instagram_handle'] or '').strip()
        if handle and not handle.startswith('@'):
            handle = '@' + handle
        SiteSettings.set('instagram_handle', handle)
        updated.append('instagram_handle')

    # Organization Profile Fields
    for k in ['org_name', 'org_address', 'org_phone', 'org_email', 'support_email', 'sales_email', 'warehouse_spoc_1', 'warehouse_spoc_2']:
        if k in data:
            SiteSettings.set(k, data[k].strip())
            updated.append(k)


    for key in home_image_keys:
        if key in data:
            value = (data.get(key) or '').strip()
            if value and not (
                value.startswith('/')
                or value.startswith('http://')
                or value.startswith('https://')
            ):
                return jsonify({'error': f'Invalid URL for {key}. Use /img/store/... or http(s)://...'}), 400
            SiteSettings.set(key, value)
            updated.append(key)

    log_admin_action(
        module='Settings',
        action='UPDATE',
        target_id=None,
        description=f"Updated Site Settings: {len(updated)} fields",
        details={'updated_keys': updated}
    )
    return jsonify({'message': f'Settings updated: {", ".join(updated)}', 'updated': updated})


@admin_bp.route('/api/settings/image', methods=['POST'])
@admin_required
def upload_setting_image():
    """Upload and optimize image for homepage settings.
    
    Handles connection issues gracefully with proper error messages.
    """
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image file uploaded'}), 400
            
        file = request.files['image']
        key = request.form.get('key')
        
        if not file or not file.filename:
            return jsonify({'error': 'Empty file'}), 400
        if not key:
            return jsonify({'error': 'Setting key is required'}), 400
        
        # Validate file size early; keep tighter limit on Vercel to avoid platform body-limit failures.
        is_vercel = os.environ.get('VERCEL', '') == '1'
        MAX_SIZE = (4 if is_vercel else 10) * 1024 * 1024
        file_size = len(file.read())
        file.seek(0)  # Reset after reading for validation
        
        if file_size > MAX_SIZE:
            return jsonify({'error': f'File too large (max {MAX_SIZE/1024/1024:.0f}MB)'}), 413
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file format. Allowed: Images & MP4/WEBM Video'}), 415
            
        # Process upload with timeout handling
        url = save_upload(file, subfolder='settings')
        if not url:
            return jsonify({'error': 'Failed to save image (invalid format or server error)'}), 500
            
        SiteSettings.set(key, url)
        db.session.commit()  # Ensure changes are saved
        
        return jsonify({
            'success': True, 
            'url': url, 
            'key': key,
            'message': 'Image uploaded successfully'
        }), 200
        
    except Exception as e:
        current_app.logger.error(f'Image upload error: {str(e)}')
        return jsonify({
            'error': 'Server error during upload. Please try again.'
        }), 500


# ─────────────────────────────────────────────
# PAGE: Admin Returns
# ─────────────────────────────────────────────
@admin_bp.route('/returns')
@admin_or_sales_required
def returns_page():
    user = get_current_user()
    return render_template('admin/returns.html', user=user)


# ─────────────────────────────────────────────
# API: Get all return requests (admin)
# ─────────────────────────────────────────────
@admin_bp.route('/api/returns', methods=['GET'])
@admin_required
def get_returns():
    status = request.args.get('status', '').strip()
    query = ReturnRequest.query
    if status:
        query = query.filter_by(status=status)
    returns = query.order_by(ReturnRequest.created_at.desc()).all()
    return jsonify({'returns': [r.to_dict() for r in returns]})


# ─────────────────────────────────────────────
# API: Update return request status (admin)
# ─────────────────────────────────────────────
@admin_bp.route('/api/returns/<return_id>', methods=['PUT'])
@admin_required
def update_return(return_id):
    ret = db.session.get(ReturnRequest, return_id)
    if not ret:
        return jsonify({'error': 'Return request not found'}), 404

    data = request.get_json()
    new_status = data.get('status')
    admin_notes = data.get('admin_notes', '').strip()

    if new_status not in ('approved', 'rejected', 'completed'):
        return jsonify({'error': 'Invalid status. Must be approved, rejected, or completed'}), 400

    ret.status = new_status
    if admin_notes:
        ret.admin_notes = admin_notes

    # On approval, update refund_amount if provided
    if new_status == 'approved' and 'refund_amount' in data:
        ret.refund_amount = data['refund_amount']

    # On completion, mark payment as refunded and restore stock
    if new_status == 'completed':
        order = ret.order
        if order:
            order.payment_status = 'refunded'
            for item in order.items:
                if item.product and not item.product.is_customizable:
                    item.product.stock += item.quantity
            tracking = OrderTracking(
                order_id=order.id,
                status='returned',
                description=f'Return completed — refund of ₹{ret.refund_amount} processed'
            )
            db.session.add(tracking)

    if new_status == 'rejected':
        tracking = OrderTracking(
            order_id=ret.order_id,
            status='return_rejected',
            description=f'Return request rejected: {admin_notes or "No reason provided"}'
        )
        db.session.add(tracking)

    try:
        db.session.commit()
        return jsonify({'message': f'Return request {new_status}', 'return_request': ret.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to update return: {str(e)}'}), 500


# ─────────────────────────────────────────────
# API: Database Management — Clear Tables
# ─────────────────────────────────────────────
DB_CLEARABLE_TABLES = {
    'products':       {'label': 'Products',              'icon': 'box-seam',          'color': 'primary'},
    'orders':         {'label': 'Orders',                'icon': 'bag',               'color': 'warning'},
    'customizations': {'label': 'Customized Products',   'icon': 'palette',           'color': 'info'},
    'reviews':        {'label': 'Reviews',               'icon': 'star',              'color': 'success'},
    'complaints':     {'label': 'Complaints',            'icon': 'chat-square-text',  'color': 'danger'},
    'b2b_requests':   {'label': 'B2B Requests',          'icon': 'building',          'color': 'secondary'},
    'coupons':        {'label': 'Coupons',               'icon': 'ticket-perforated', 'color': 'primary'},
    'categories':     {'label': 'Categories',            'icon': 'tags',              'color': 'info'},
    'cart_items':     {'label': 'Cart Items',            'icon': 'cart3',             'color': 'warning'},
}


@admin_bp.route('/api/db/tables', methods=['GET'])
@admin_required
def db_get_tables():
    """Return clearable tables with row counts."""
    tables = []
    model_map = {
        'products': Product, 'orders': Order, 'customizations': Customization,
        'reviews': Review, 'complaints': Complaint, 'b2b_requests': B2BRequest,
        'coupons': Coupon, 'categories': Category, 'cart_items': CartItem,
    }
    for key, meta in DB_CLEARABLE_TABLES.items():
        model = model_map.get(key)
        count = model.query.count() if model else 0
        tables.append({**meta, 'key': key, 'count': count})
    return jsonify({'tables': tables})


@admin_bp.route('/api/db/clear', methods=['POST'])
@admin_required
def db_clear_table():
    """Clear data from a specific table (admin password required)."""
    data = request.get_json()
    table_key = data.get('table', '').strip()
    password = data.get('password', '').strip()

    if table_key not in DB_CLEARABLE_TABLES:
        return jsonify({'error': 'Invalid table'}), 400

    # Verify admin password
    if not password:
        return jsonify({'error': 'Admin password is required'}), 400
    
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
        
    # Security: Fallback to ADMIN_MASTER_PIN for admins without a password hash (social accounts)
    master_pin = current_app.config.get('ADMIN_MASTER_PIN')
    is_master_pin = (master_pin and password == master_pin)
    
    if user.password_hash:
        # Standard password check
        if not user.check_password(password) and not is_master_pin:
            return jsonify({'error': 'Incorrect admin password'}), 403
    else:
        # Social login user - MUST use ADMIN_MASTER_PIN to clear tables
        if not is_master_pin:
             return jsonify({'error': 'Social Admin: Please use the Admin Master PIN to authorize this sensitive action'}), 403

    deleted = 0
    try:
        if table_key == 'products':
            # Must clear dependent tables first
            deleted += CartItem.query.filter(CartItem.product_id.isnot(None)).delete(synchronize_session=False)
            Review.query.delete(synchronize_session=False)
            # Null-out order_item product references (preserve order history)
            db.session.execute(db.text(
                "UPDATE order_items SET product_name_snapshot = "
                "(SELECT name FROM products WHERE products.id = order_items.product_id) "
                "WHERE product_id IS NOT NULL AND product_name_snapshot IS NULL"
            ))
            db.session.execute(db.text("UPDATE order_items SET product_id = NULL"))
            ProductImage.query.delete(synchronize_session=False)
            ImageStore.query.delete(synchronize_session=False)
            deleted = Product.query.delete(synchronize_session=False)
            Category.query.delete(synchronize_session=False)

        elif table_key == 'orders':
            ReturnRequest.query.delete(synchronize_session=False)
            Complaint.query.delete(synchronize_session=False)
            OrderTracking.query.delete(synchronize_session=False)
            Payment.query.delete(synchronize_session=False)
            OrderItem.query.delete(synchronize_session=False)
            deleted = Order.query.delete(synchronize_session=False)

        elif table_key == 'customizations':
            # Null out customization_id on cart_items and order_items first
            db.session.execute(db.text("UPDATE cart_items SET customization_id = NULL WHERE customization_id IS NOT NULL"))
            db.session.execute(db.text("UPDATE order_items SET customization_id = NULL WHERE customization_id IS NOT NULL"))
            deleted = Customization.query.delete(synchronize_session=False)
            CustomizationOption.query.delete(synchronize_session=False)

        elif table_key == 'reviews':
            deleted = Review.query.delete(synchronize_session=False)
            # Reset product rating caches
            db.session.execute(db.text("UPDATE products SET rating_avg = 0, rating_count = 0"))

        elif table_key == 'complaints':
            deleted = Complaint.query.delete(synchronize_session=False)

        elif table_key == 'b2b_requests':
            deleted = B2BRequest.query.delete(synchronize_session=False)

        elif table_key == 'coupons':
            deleted = Coupon.query.delete(synchronize_session=False)

        elif table_key == 'categories':
            # Null out category_id on products first
            db.session.execute(db.text("UPDATE products SET category_id = NULL WHERE category_id IS NOT NULL"))
            deleted = Category.query.delete(synchronize_session=False)

        elif table_key == 'cart_items':
            deleted = CartItem.query.delete(synchronize_session=False)

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to clear: {str(e)}'}), 500

    label = DB_CLEARABLE_TABLES[table_key]['label']
    return jsonify({'message': f'{label} cleared — {deleted} record(s) removed.'})


# ─────────────────────────────────────────────
# DATABASE SEED / INITIALIZATION
# ─────────────────────────────────────────────
@admin_bp.route('/api/seed', methods=['POST'])
@admin_required
def seed_database():
    """Populate database with initial categories, products and settings."""
    try:
        # 0. Initialize Schema
        db.create_all()

        # 0.1 Partners
        partners_data = [
            {'name': 'Dunna Vivek', 'color_hex': '#f8d57e'},
            {'name': 'Maddikunta Kalyani', 'color_hex': '#17a2b8'},
            {'name': 'Ladugu Dhanusha', 'color_hex': '#6f42c1'},
            {'name': 'Sudheer Paani', 'color_hex': '#28a745'}
        ]
        for p in partners_data:
            if not Partner.query.filter_by(name=p['name']).first():
                db.session.add(Partner(**p))
        db.session.flush()
        
        # 1. Categories
        cats_data = [
            {'name': 'Luxury Jar Candles', 'slug': 'luxury-jar-candles', 'description': 'Premium hand-poured jar candles.'},
            {'name': 'Gift Hampers', 'slug': 'gift-hampers', 'description': 'Curated gift sets for every occasion.'},
            {'name': 'Designer Moulds', 'slug': 'designer-mould-candles', 'description': 'Artistically shaped candles.'},
            {'name': 'Festive Editions', 'slug': 'festive-editions', 'description': 'Limited scents for celebration.'}
        ]
        cat_map = {}
        for c in cats_data:
            obj = Category.query.filter_by(slug=c['slug']).first()
            if not obj:
                obj = Category(**c, is_active=True)
                db.session.add(obj)
                db.session.flush()
            cat_map[c['slug']] = obj.id
        
        # 2. Premium Sample Products
        prods = [
            {
                'name': 'Midnight Noir Suede', 
                'slug': 'midnight-noir-suede', 
                'description': 'A deep, sophisticated blend of night-blooming jasmine and weathered leather.',
                'price': 1499, 
                'category_id': cat_map['luxury-jar-candles'],
                'stock': 50,
                'is_featured': True,
                'is_active': True,
                'image_url': '/static/images/hero-luxury-candle.png'
            },
            {
                'name': 'Vanilla Bloom Jar', 
                'slug': 'vanilla-bloom-jar', 
                'description': 'Warm Madagascar vanilla beans with a hint of orchid.',
                'price': 1299, 
                'category_id': cat_map['luxury-jar-candles'],
                'stock': 100,
                'is_featured': True,
                'is_active': True,
                'image_url': '/static/images/luxury-candle-product.png'
            },
            {
                'name': 'Abstract Bloom Mould', 
                'slug': 'abstract-bloom-mould', 
                'description': 'Hand-poured designer mould candle in ivory white.',
                'price': 899, 
                'category_id': cat_map['designer-mould-candles'],
                'stock': 30,
                'is_featured': False,
                'is_active': True,
                'image_url': '/static/images/luxury-candle-product.png'
            }
        ]
        for p in prods:
            if not Product.query.filter_by(slug=p['slug']).first():
                db.session.add(Product(**p))

        # 3. Essential Site Settings
        default_settings = {
            'org_name': 'Luxoya Candles',
            'org_address': 'Villa No : 82,Mythri Lake View .S.No : 45,46 BC Colony ,Mallampet,Bollaram,Medchal ,Malkajgiri Dist-500090, Mythri Lake View, K.V.Rangareddy, Telangana, India, 500090',
            'support_email': 'support@luxoyacandles.com',
            'sales_email': 'sales@luxoyacandles.com',
            'warehouse_spoc_1': 'PARAPATHI ADHARSH | 9705840457',
            'warehouse_spoc_2': 'DUNNA VIVEK | 87903129645',
            'gift_hampers_header': 'Curated Gift Box Collections',
            'gift_hampers_desc': 'Discover our elegant gift hampers.',
            'promo_limit_title': 'Midnight Moss Collection',
            'promo_limit_desc': 'Limited edition fragrances.',
            'custom_studio_title': 'Custom Candle Studio',
            'custom_studio_desc': 'Design your signature scent.',
            'home_phi_img_1': '/static/images/philosophy/candle-jars.jpg',
            'home_phi_img_2': '/static/images/philosophy/candle-ambience.jpg',
            'home_phi_img_3': '/static/images/philosophy/candle-lighting.jpg'
        }
        for k, v in default_settings.items():
            if not SiteSettings.query.filter_by(key=k).first():
                SiteSettings.set(k, v)

        db.session.commit()
        return jsonify({'success': True, 'message': 'Store initialized with sample data.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/sync-4.0', methods=['POST'])
@admin_required
def sync_from_4_0():
    """Sync data from a remote Luxoya 4.0 instance."""
    import requests
    data = request.get_json()
    remote_url = data.get('remote_url', '').strip().rstrip('/')
    sync_key = data.get('sync_key', '').strip()

    if not remote_url or not sync_key:
        return jsonify({'error': 'Remote URL and Sync Key are required'}), 400

    try:
        # 1. Fetch data from remote export endpoint
        # Conventional endpoint for Luxoya sync is /api/products/export
        resp = requests.get(f"{remote_url}/api/products/export", params={'key': sync_key}, timeout=20)
        
        if resp.status_code == 404:
            # Try alternative common endpoint
            resp = requests.get(f"{remote_url}/admin/api/export", params={'key': sync_key}, timeout=20)

        if resp.status_code != 200:
            return jsonify({'error': f'Remote site returned error ({resp.status_code}): {resp.text[:100]}'}), resp.status_code

        cloud_data = resp.json()
        categories = cloud_data.get('categories', [])
        products = cloud_data.get('products', [])

        # 2. Sync Categories
        cat_map = {}
        for c in categories:
            obj = Category.query.filter_by(slug=c['slug']).first()
            if not obj:
                obj = Category(
                    name=c['name'],
                    slug=c['slug'],
                    description=c.get('description', ''),
                    image_url=c.get('image_url', ''),
                    is_active=True
                )
                db.session.add(obj)
                db.session.flush()
            cat_map[c['slug']] = obj.id

        # 3. Sync Products
        synced_count = 0
        for p in products:
            if not Product.query.filter_by(slug=p['slug']).first():
                cat_id = cat_map.get(p.get('category_slug'))
                # If category slug doesn't match a recently synced one, try finding existing
                if not cat_id and p.get('category_slug'):
                    existing_cat = Category.query.filter_by(slug=p['category_slug']).first()
                    if existing_cat: cat_id = existing_cat.id

                new_p = Product(
                    name=p['name'],
                    slug=p['slug'],
                    description=p.get('description', ''),
                    price=p.get('price', 0),
                    sale_price=p.get('sale_price'),
                    stock=p.get('stock', 0),
                    category_id=cat_id,
                    image_url=p.get('image_url', ''),
                    is_active=True,
                    is_featured=p.get('is_featured', False)
                )
                db.session.add(new_p)
                synced_count += 1

        db.session.commit()
        return jsonify({
            'success': True, 
            'message': f'Successfully synced {len(categories)} categories and {synced_count} products from Luxoya 4.0.'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Cloud sync failed: {str(e)}'}), 500


@admin_bp.route('/api/db/force-sync', methods=['POST'])
@admin_required
def db_force_sync():
    """Force all products and categories to be active and visible."""
    try:
        from models import Product, Category
        # Update all categories to active
        Category.query.update({Category.is_active: True})
        # Update all products to active
        Product.query.update({Product.is_active: True})
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'All data forced to Active. Storefront should now be synced.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/db/sync-all', methods=['POST'])
@admin_required
def db_sync_all():
    """Manual sync that forces all branding + active status."""
    from models import Product, Category, SiteSettings
    from sqlalchemy import text
    
    # 1. Branding Data (Syncing for Hero/Philosophy/Collections)
    branding_data = {
        # Hero Slider
        'slider_img_1': 'https://images.unsplash.com/photo-1602607360922-47951de49a31?w=1600&q=80',
        'slider_img_2': 'https://images.unsplash.com/photo-1603006905003-be475563bc59?w=1600&q=80',
        'slider_img_3': 'https://images.unsplash.com/photo-1543332164-6e82f355badc?w=1600&q=80',
        'slider_img_4': 'https://images.unsplash.com/photo-1572726729207-a78d6feb18d7?w=1600&q=80',
        
        # Philosophy / About
        'home_phi_img_1': 'https://images.unsplash.com/photo-1605651202774-7d573fd3f12d?w=800&q=80',
        'home_phi_title_1': 'Traditional Craft',
        'home_phi_desc_1': 'Our candles are hand-poured in small batches, infused with pure soy wax and premium fragrance oils from the world\'s finest perfumeries.',
        'home_phi_img_2': 'https://images.unsplash.com/photo-1603006905003-be475563bc59?w=800&q=80',
        'home_phi_title_2': 'Pure Soil Soul',
        'home_phi_desc_2': 'We believe in sustainable luxury. Every component, from our cotton wicks to our reusable glass jars, is chosen with the earth in mind.',
        'home_phi_img_3': 'https://images.unsplash.com/photo-1608181831718-2501ef3e1420?w=800&q=80',
        'home_phi_title_3': 'Illuminated Living',
        'home_phi_desc_3': 'More than just a scent, a Luxoya candle is a ritual of self-care, turning everyday spaces into sanctuaries of light and peace.',

        # Collection Highlights
        'coll_img_1': 'https://images.unsplash.com/photo-1602607360922-47951de49a31?w=600',
        'coll_name_1': 'Signature',
        'coll_slug_1': 'luxury-jar-candles',
        'coll_img_2': 'https://images.unsplash.com/photo-1603006905003-be475563bc59?w=600',
        'coll_name_2': 'Aromatic',
        'coll_slug_2': 'designer-mould-candles',
        'coll_img_3': 'https://images.unsplash.com/photo-1543332164-6e82f355badc?w=600',
        'coll_name_3': 'Festive',
        'coll_slug_3': 'festive-editions',
        
        # Promo Section
        'promo_limit_title': 'Midnight Moss Collection',
        'promo_limit_desc': 'Experience the depth of evening fragrances with our limited edition jars.',
        'promo_limit_img': 'https://images.unsplash.com/photo-1543332164-6e82f355badc?w=1200'
    }
    for k, v in branding_data.items():
        SiteSettings.set(k, v)

    # 2. Force Active
    Category.query.update({Category.is_active: True})
    Product.query.update({Product.is_active: True})
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Sync Step 1 Failed: {str(e)}'}), 500
    
    # 0. Sync Users (Admin & Sales)
    admin_email = current_app.config.get('INITIAL_ADMIN_EMAIL', 'admin@luxoyacandles.com')
    sales_email = current_app.config.get('INITIAL_SALES_EMAIL', 'sales@luxoyacandles.com')
    
    admin_pass = current_app.config.get('INITIAL_ADMIN_PASS', 'admin123')
    sales_pass = current_app.config.get('INITIAL_SALES_PASS', 'sales123')
    
    if not User.query.filter_by(email=admin_email).first():
        admin_user = User(
            email=admin_email,
            full_name='Luxoya Admin',
            role='admin',
            is_active=True
        )
        admin_user.set_password(admin_pass)
        db.session.add(admin_user)

    if not User.query.filter_by(email=sales_email).first():
        sales_user = User(
            email=sales_email,
            full_name='Luxoya Sales',
            role='sales',
            is_active=True
        )
        sales_user.set_password(sales_pass)
        db.session.add(sales_user)
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Sync Step 2 Failed: {str(e)}'}), 500

    # 3. Diagnostic Counts (According to Flask)
    p_count = Product.query.count()
    c_count = Category.query.count()
    s_count = SiteSettings.query.count()
    
    return jsonify({
        'success': True,
        'counts': {'products': p_count, 'categories': c_count, 'settings': s_count},
        'message': f'Sync complete. Found {p_count} products and {c_count} categories in current session.'
    })


# AI ASSISTANT ROUTES
@admin_bp.route('/api/ai/chat', methods=['POST'])
@admin_or_sales_required
def ai_chat():
    from utils import ask_ai
    data = request.get_json()
    prompt = data.get('prompt', '')
    if not prompt:
        return jsonify({'error': 'No prompt provided'}), 400
    
    # Simple context
    total_prods = Product.query.count()
    total_orders = Order.query.count()
    low_stock = RawMaterial.query.filter(RawMaterial.stock_quantity <= RawMaterial.reorder_level).count()
    
    # Financial context
    expenses = db.session.query(db.func.sum(FinanceRecord.amount)).filter(FinanceRecord.record_type == 'expense').scalar() or 0
    revenue = db.session.query(db.func.sum(Order.total_amount)).scalar() or 0
    
    summary = f"Luxoya Store Facts: {total_prods} products, {total_orders} total orders. Revenue: ₹{revenue:,.0f}, Expenses: ₹{expenses:,.0f}. There are {low_stock} raw materials low in stock."
    
    system_context = f"You are the Luxoya AI Admin Assistant. {summary} Be professional, helpful, and concise. Help the admin with store tasks, marketing ideas, or product management."
    
    response = ask_ai(prompt, system_context)
    return jsonify({'response': response})


@admin_bp.route('/api/ai/suggest-description', methods=['POST'])
@admin_or_sales_required
def ai_suggest_description():
    from utils import ask_ai
    data = request.get_json()
    name = data.get('name', '')
    fragrance = data.get('fragrance', '')
    wax = data.get('wax', 'Soy')
    
    if not name:
        return jsonify({'error': 'Name is required'}), 400
        
    prompt = f"Write a luxury sensory product description (about 100 words) for a candle named '{name}'. Fragrance notes: {fragrance}. Wax type: {wax}. Use words that feel premium and inviting."
    system_context = "You are a luxury branding expert for Luxoya Candles."
    
    description = ask_ai(prompt, system_context)
    return jsonify({'description': description})


@admin_bp.route('/api/ai/insights', methods=['GET'])
@admin_or_sales_required
def ai_insights():
    from utils import ask_ai
    # Fetch top selling info
    top_prods = db.session.query(Product.name, db.func.sum(OrderItem.quantity).label('sold'))\
                  .join(OrderItem).group_by(Product.id).order_by(db.desc('sold')).limit(3).all()
    
    context_bits = [f"{p[0]} ({int(p[1])} sold)" for p in top_prods]
    context = "Top products: " + ", ".join(context_bits) if context_bits else "No sales data yet."
    
    prompt = f"Based on this store data, give 3 short, actionable business growth insights. {context}"
    system_context = "You are a business growth analyst for Luxoya Candles."
    
    insights = ask_ai(prompt, system_context)
    return jsonify({'insights': insights})


@admin_bp.route('/api/ai/inventory-forecast', methods=['POST'])
@admin_or_sales_required
def ai_inventory_forecast():
    from utils import ask_ai
    materials = RawMaterial.query.all()
    low_stock = [m for m in materials if m.stock_quantity <= m.reorder_level]
    
    # Recent sales trend
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_volume = db.session.query(db.func.sum(OrderItem.quantity))\
        .join(Order).filter(Order.created_at >= thirty_days_ago, Order.payment_status == 'paid').scalar() or 0
    
    m_list = [f"{m.name} ({m.stock_quantity}{m.unit} left, reorder at {m.reorder_level})" for m in materials]
    context = f"Current Inventory: {', '.join(m_list[:15])}. "
    if low_stock:
        context += f"CRITICAL LOW: {', '.join([m.name for m in low_stock])}. "
    context += f"Sales volume past 30 days: {recent_volume} items."
    
    prompt = f"Analyze this inventory and sales data for Luxoya Candles. Suggest 3 specific procurement actions to ensure 100% fulfillability for the next month. Be concise."
    system_context = "You are a supply chain expert for a luxury candle brand."
    
    forecast = ask_ai(prompt, system_context)
    return jsonify({'forecast': forecast})


@admin_bp.route('/api/ai/generate-product-content', methods=['POST'])
@admin_or_sales_required
def api_generate_product_content():
    """AI endpoint to generate product names and descriptions based on raw materials."""
    from utils import ask_ai
    import json
    
    data = request.get_json()
    wax = data.get('wax', '')
    fragrance = data.get('fragrance', '')
    glass = data.get('glass', '')
    color = data.get('color', '')
    wick = data.get('wick', '')

    if not fragrance:
        return jsonify({'error': 'Please provide at least a fragrance/scent profile'}), 400

    prompt = f"""
    Luxoya Candles is a luxury 100% natural soy candle brand. 
    Generate a creative, evocative product NAME and a professional, luxury-retail DESCRIPTION (about 3-4 sentences) for a candle with these specs:
    - Wax: {wax or 'Premium Soy Wax'}
    - Fragrance: {fragrance}
    - Glass/Container: {glass or 'Luxury Clear Glass'}
    - Color: {color or 'Natural Cream'}
    - Wick: {wick or 'Cotton Core'}

    Return the result strictly as a valid JSON object with keys "name" and "description". Do not include any other text.
    """
    
    system_context = "You are a senior copywriter for a high-end luxury lifestyle brand specializing in home fragrances."
    
    ai_raw = ask_ai(prompt, system_context)
    
    try:
        # Clean potential markdown from AI response
        cleaned_json = ai_raw.replace('```json', '').replace('```', '').strip()
        result = json.loads(cleaned_json)
        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f"AI Content Genesis Failed: {e}. Raw: {ai_raw}")
        return jsonify({
            'name': f"{fragrance} Luxury Candle",
            'description': f"A beautiful {fragrance} candle crafted with premium materials for an exceptional aromatic experience."
        })


# ─────────────────────────────────────────────
# API: Shiprocket Shipment Management
# ─────────────────────────────────────────────
@admin_bp.route('/api/shiprocket/create/<order_id>', methods=['POST'])
@admin_required
def shiprocket_create_order(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404
        
    if order.status == 'cancelled':
        return jsonify({'error': 'Cannot ship a cancelled order'}), 400

    from utils import ShiprocketHelper
    result = ShiprocketHelper.create_order(order)
    
    if 'order_id' in result:
        # Update order with Shiprocket details
        shipment_id = result.get('shipment_id')
        order.status = 'shipped'
        # Add tracking entry
        tracking = OrderTracking(
            order_id=order.id,
            status='shipped',
            description=f"Shipment created via Shiprocket. Shipment ID: {shipment_id}"
        )
        db.session.add(tracking)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Shiprocket local sync failed: {str(e)}')
            # We don't return 500 here because the Shiprocket order WAS technically created
            return jsonify({**result, "warning": "Shipment created in Shiprocket but failed to update local records. Please refresh."})
        
    return jsonify(result)


@admin_bp.route('/api/shiprocket/track/<awb_code>', methods=['GET'])
@admin_required
def shiprocket_track(awb_code):
    from utils import ShiprocketHelper
    result = ShiprocketHelper.get_tracking(awb_code)
    if not result:
        return jsonify({'error': 'Tracking info unavailable'}), 404
    return jsonify(result)
