from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Product, Category, Review, User, OrderItem, Order, ProductImage, CustomizationOption, db
from routes.auth import get_current_user
from routes.admin import save_upload

products_bp = Blueprint('products', __name__)

# ─────────────────────────────────────────────
# API: Upload Reference Image for Bespoke
# ─────────────────────────────────────────────
@products_bp.route('/api/customize/upload-reference', methods=['POST'])
def upload_reference():
    """Allows customers to upload inspiration images for bespoke orders."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    try:
        url = save_upload(file, subfolder='bespoke')
        if not url:
            return jsonify({'error': 'File type not allowed'}), 400
            
        db.session.commit()
        return jsonify({'url': url}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────
# PAGE: All products
# ─────────────────────────────────────────────
@products_bp.route('/collections')
@products_bp.route('/collections/<slug>')
def collections(slug=None):
    categories = Category.query.filter_by(is_active=True).order_by(Category.display_order).all()
    current_category = None
    if slug:
        current_category = Category.query.filter_by(slug=slug, is_active=True).first_or_404()
    return render_template('products/listing.html', 
                         categories=categories, 
                         current_category=current_category)


# ─────────────────────────────────────────────
# PAGE: Product detail
@products_bp.route('/product/<slug>')
def product_detail(slug):
    # Only show active products in active categories
    product = Product.query.outerjoin(Category).filter(
        Product.slug == slug,
        Product.is_active == True
    ).first()
    
    if product:
        # Increment view count
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            # Non-blocking: fail silently for view count
    
    if not product:
        product = Product.query.filter_by(slug=slug).first_or_404()
        
    reviews = Review.query.filter_by(product_id=product.id, is_approved=True)\
                         .order_by(Review.created_at.desc()).limit(10).all()
    
    related = Product.query.outerjoin(Category).filter(
        Product.category_id == product.category_id,
        Product.id != product.id,
        Product.is_active == True
    ).limit(4).all()
    
    # Rating distribution (for Amazon-style bar chart)
    rating_dist = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    all_reviews = Review.query.filter_by(product_id=product.id, is_approved=True).all()
    for r in all_reviews:
        if r.rating in rating_dist:
            rating_dist[r.rating] += 1
    total_reviews = len(all_reviews)
    rating_pct = {}
    for star, count in rating_dist.items():
        rating_pct[star] = round((count / total_reviews * 100)) if total_reviews > 0 else 0
    
    # Get all product images for carousel
    product_images = product.all_images
    
    return render_template('products/detail.html', 
                         product=product, 
                         reviews=reviews,
                         related=related,
                         rating_dist=rating_dist,
                         rating_pct=rating_pct,
                         total_reviews=total_reviews,
                         product_images=product_images)


# ─────────────────────────────────────────────
# PAGE: Customize candle
# ─────────────────────────────────────────────
@products_bp.route('/customize')
def customize():
    return render_template('products/customize.html')


# ─────────────────────────────────────────────
# API: Get products (with filters)
# ─────────────────────────────────────────────
@products_bp.route('/api/products', methods=['GET'])
def api_get_products():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 12, type=int)
    category = request.args.get('category', None)
    sort = request.args.get('sort', 'newest')
    search = request.args.get('search', None)
    min_price = request.args.get('min_price', None, type=float)
    max_price = request.args.get('max_price', None, type=float)
    featured = request.args.get('featured', None)
    
    query = Product.query.outerjoin(Category).filter(
        Product.is_active == True,
        db.or_(Category.is_active == True, Product.category_id == None)
    )
    
    if category:
        cat = Category.query.filter_by(slug=category).first()
        if cat:
            query = query.filter_by(category_id=cat.id)
    
    if search:
        query = query.filter(
            db.or_(
                Product.name.ilike(f'%{search}%'),
                Product.description.ilike(f'%{search}%'),
                Product.fragrance.ilike(f'%{search}%')
            )
        )
    
    if min_price:
        query = query.filter(Product.price >= min_price)
    if max_price:
        query = query.filter(Product.price <= max_price)
    
    if featured:
        query = query.filter_by(is_featured=True)
    
    # Sorting
    if sort == 'price_low':
        query = query.order_by(Product.price.asc())
    elif sort == 'price_high':
        query = query.order_by(Product.price.desc())
    elif sort == 'rating':
        query = query.order_by(Product.rating_avg.desc())
    elif sort == 'name':
        query = query.order_by(Product.name.asc())
    else:  # newest
        query = query.order_by(Product.created_at.desc())
    
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'products': [p.to_dict() for p in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page,
        'has_next': pagination.has_next,
        'has_prev': pagination.has_prev
    })


# ─────────────────────────────────────────────
# API: Get single product
# ─────────────────────────────────────────────
@products_bp.route('/api/products/<slug>', methods=['GET'])
def api_get_product(slug):
    product = Product.query.filter_by(slug=slug, is_active=True).first()
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    return jsonify({'product': product.to_dict()})


# ─────────────────────────────────────────────
# API: Get categories
# ─────────────────────────────────────────────
@products_bp.route('/api/categories', methods=['GET'])
def api_get_categories():
    categories = Category.query.filter_by(is_active=True)\
                               .order_by(Category.display_order).all()
    return jsonify({'categories': [c.to_dict() for c in categories]})


# ─────────────────────────────────────────────
# API: Add review
# ─────────────────────────────────────────────
@products_bp.route('/api/products/<product_id>/reviews', methods=['POST'])
@jwt_required()
def add_review(product_id):
    user = get_current_user()
    data = request.get_json()
    
    product = db.session.get(Product, product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    
    # Check if user already reviewed this product
    existing = Review.query.filter_by(user_id=user.id, product_id=product_id).first()
    if existing:
        return jsonify({'error': 'You have already reviewed this product'}), 409
    
    rating = data.get('rating', 5)
    if rating < 1 or rating > 5:
        return jsonify({'error': 'Rating must be between 1 and 5'}), 400
    
    # Check if user has purchased this product (verified purchase)
    is_verified = db.session.query(OrderItem).join(Order).filter(
        Order.user_id == user.id,
        OrderItem.product_id == product_id,
        Order.payment_status == 'paid'
    ).first() is not None
    
    review = Review(
        user_id=user.id,
        product_id=product_id,
        rating=rating,
        title=data.get('title', ''),
        comment=data.get('comment', ''),
        is_verified_purchase=is_verified,
        review_images=data.get('review_images', [])
    )
    
    db.session.add(review)
    
    # Update product rating
    all_reviews = Review.query.filter_by(product_id=product_id, is_approved=True).all()
    all_reviews_ratings = [r.rating for r in all_reviews] + [rating]
    product.rating_avg = round(sum(all_reviews_ratings) / len(all_reviews_ratings), 1)
    product.rating_count = len(all_reviews_ratings)
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Review submission failed: {str(e)}')
        return jsonify({'error': 'Failed to add review'}), 500
    
    return jsonify({'message': 'Review added', 'review': review.to_dict()}), 201


# ─────────────────────────────────────────────
# API: Mark review as helpful
# ─────────────────────────────────────────────
@products_bp.route('/api/reviews/<review_id>/helpful', methods=['POST'])
def mark_review_helpful(review_id):
    review = db.session.get(Review, review_id)
    if not review:
        return jsonify({'error': 'Review not found'}), 404
    review.helpful_count = (review.helpful_count or 0) + 1
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Failed to update helpful count'}), 500
    return jsonify({'message': 'Marked as helpful', 'helpful_count': review.helpful_count})


# ─────────────────────────────────────────────
# API: Get product reviews
# ─────────────────────────────────────────────
@products_bp.route('/api/products/<product_id>/reviews', methods=['GET'])
def get_reviews(product_id):
    page = request.args.get('page', 1, type=int)
    reviews = Review.query.filter_by(product_id=product_id, is_approved=True)\
                         .order_by(Review.created_at.desc())\
                         .paginate(page=page, per_page=10, error_out=False)
    
    return jsonify({
        'reviews': [r.to_dict() for r in reviews.items],
        'total': reviews.total,
        'pages': reviews.pages
    })


# ─────────────────────────────────────────────
# API: Search products
# ─────────────────────────────────────────────
@products_bp.route('/api/search', methods=['GET'])
def search_products():
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify({'products': []})
    
    products = Product.query.join(Category).filter(
        Product.is_active == True,
        Category.is_active == True,
        db.or_(
            Product.name.ilike(f'%{query}%'),
            Product.description.ilike(f'%{query}%'),
            Product.fragrance.ilike(f'%{query}%')
        )
    ).limit(10).all()
    
    return jsonify({'products': [p.to_dict() for p in products]})


# ─────────────────────────────────────────────
# PAGE: Catalog Download (Print/PDF)
# ─────────────────────────────────────────────
@products_bp.route('/catalog/download')
def catalog_download():
    """Render a print-optimized catalog of all active products."""
    from datetime import datetime
    categories = Category.query.filter_by(is_active=True).order_by(Category.display_order).all()
    
    catalog_data = {}
    for cat in categories:
        prods = Product.query.filter_by(category_id=cat.id, is_active=True).all()
        if prods:
            catalog_data[cat.name] = prods

    # Include uncategorized products if any
    uncategorized = Product.query.filter_by(category_id=None, is_active=True).all()
    if uncategorized:
        catalog_data['Signature Collections'] = uncategorized

    return render_template('products/catalog_print.html', 
                         catalog=catalog_data, 
                         now=datetime.utcnow())
