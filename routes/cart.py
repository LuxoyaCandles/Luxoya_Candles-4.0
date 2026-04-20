import re
from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import jwt_required
from models import CartItem, Product, Customization, db
from routes.auth import get_current_user, login_required_page

cart_bp = Blueprint('cart', __name__)


def get_custom_candle_product():
    """Find or create the base 'Custom Candle' product used for customized orders."""
    product = Product.query.filter_by(slug='custom-candle-base').first()
    if not product:
        product = Product(
            name='Custom Candle',
            slug='custom-candle-base',
            description='A personalized candle crafted to your specifications.',
            short_description='Your custom-designed candle',
            price=499.0,
            stock=9999,
            is_customizable=True,
            is_active=True,
            is_featured=False,
            image_url='/static/img/custom-candle.png',
        )
        db.session.add(product)
        db.session.flush()
    return product


# ─────────────────────────────────────────────
# PAGE: Cart
# ─────────────────────────────────────────────
@cart_bp.route('/cart')
@login_required_page
def cart_page():
    user = get_current_user()
    return render_template('cart.html', user=user)


# ─────────────────────────────────────────────
# API: Get cart items
# ─────────────────────────────────────────────
@cart_bp.route('/api/cart', methods=['GET'])
@jwt_required(optional=True)
def get_cart():
    user = get_current_user()
    if not user:
        return jsonify({'items': [], 'total': 0, 'count': 0})
    items = CartItem.query.filter_by(user_id=user.id).all()
    
    cart_total = 0
    cart_items = []
    for item in items:
        item_dict = item.to_dict()
        cart_items.append(item_dict)
        cart_total += item_dict['subtotal']
    
    return jsonify({
        'items': cart_items,
        'total': round(cart_total, 2),
        'count': len(items)
    })


# ─────────────────────────────────────────────
# API: Add to cart
# ─────────────────────────────────────────────
@cart_bp.route('/api/cart', methods=['POST'])
@jwt_required()
def add_to_cart():
    user = get_current_user()
    data = request.get_json()
    
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)
    customization_data = data.get('customization', None)
    
    # If no product_id but has customization, use the Custom Candle base product
    if not product_id and customization_data:
        product = get_custom_candle_product()
        product_id = product.id
    else:
        product = db.session.get(Product, product_id)
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        # Verify product visibility
        if not product.is_active or (product.category and not product.category.is_active):
            return jsonify({'error': 'This product is currently unavailable'}), 403
    
    if not product.is_customizable:
        if not product.in_stock:
            return jsonify({'error': 'Product is out of stock'}), 400
        
        if quantity > product.stock:
            return jsonify({'error': f'Only {product.stock} items available'}), 400
    
    customization_id = None
    if customization_data:
        customization = Customization(
            jar_type=customization_data.get('jar_type', 'classic_glass'),
            colour=customization_data.get('colour', 'ivory_white'),
            fragrance=customization_data.get('fragrance', 'vanilla_oud'),
            wick_type=customization_data.get('wick_type', 'single'),
            label_text=customization_data.get('label_text', ''),
            additional_notes=customization_data.get('additional_notes', ''),
            price_addon=customization_data.get('price_addon', 0.0)
        )
        db.session.add(customization)
        db.session.flush()
        customization_id = customization.id
    
    # Check if same product (without customization) already in cart
    existing = CartItem.query.filter_by(
        user_id=user.id,
        product_id=product_id,
        customization_id=None
    ).first() if not customization_id else None
    
    if existing:
        existing.quantity += quantity
        if existing.quantity > product.stock:
            existing.quantity = product.stock
    else:
        cart_item = CartItem(
            user_id=user.id,
            product_id=product_id,
            quantity=quantity,
            customization_id=customization_id
        )
        db.session.add(cart_item)
    
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Failed to add to cart'}), 500
    
    # Return updated cart count
    count = CartItem.query.filter_by(user_id=user.id).count()
    return jsonify({'message': 'Added to cart', 'cart_count': count}), 201


# ─────────────────────────────────────────────
# API: Update cart item quantity
# ─────────────────────────────────────────────
@cart_bp.route('/api/cart/<item_id>', methods=['PUT'])
@jwt_required()
def update_cart_item(item_id):
    user = get_current_user()
    data = request.get_json()
    quantity = data.get('quantity', 1)
    
    item = CartItem.query.filter_by(id=item_id, user_id=user.id).first()
    if not item:
        return jsonify({'error': 'Cart item not found'}), 404
    
    if quantity <= 0:
        # Cleanup customization if it's an orphan
        if item.customization_id:
            cust_id = item.customization_id
            db.session.delete(item)
            db.session.flush()
            # Only delete customization if it's not linked to any OrderItem (history)
            from models import OrderItem
            if not OrderItem.query.filter_by(customization_id=cust_id).first():
                customization = db.session.get(Customization, cust_id)
                if customization:
                    db.session.delete(customization)
        else:
            db.session.delete(item)
    else:
        if not item.product.is_customizable and quantity > item.product.stock:
            return jsonify({'error': f'Only {item.product.stock} items available'}), 400
        item.quantity = quantity
    
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Failed to update cart'}), 500
    return jsonify({'message': 'Cart updated'}), 200


# ─────────────────────────────────────────────
# API: Remove cart item
# ─────────────────────────────────────────────
@cart_bp.route('/api/cart/<item_id>', methods=['DELETE'])
@jwt_required()
def remove_cart_item(item_id):
    user = get_current_user()
    item = CartItem.query.filter_by(id=item_id, user_id=user.id).first()
    if not item:
        return jsonify({'error': 'Cart item not found'}), 404
    
    # Cleanup customization if it's an orphan
    if item.customization_id:
        cust_id = item.customization_id
        db.session.delete(item)
        db.session.flush()
        from models import OrderItem
        if not OrderItem.query.filter_by(customization_id=cust_id).first():
            customization = db.session.get(Customization, cust_id)
            if customization:
                db.session.delete(customization)
    else:
        db.session.delete(item)
        
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Failed to remove item'}), 500
    
    count = CartItem.query.filter_by(user_id=user.id).count()
    return jsonify({'message': 'Item removed', 'cart_count': count}), 200


# ─────────────────────────────────────────────
# API: Clear cart
# ─────────────────────────────────────────────
@cart_bp.route('/api/cart/clear', methods=['DELETE'])
@jwt_required()
def clear_cart():
    user = get_current_user()
    items = CartItem.query.filter_by(user_id=user.id).all()
    
    for item in items:
        if item.customization_id:
            cust_id = item.customization_id
            db.session.delete(item)
            db.session.flush()
            from models import OrderItem
            if not OrderItem.query.filter_by(customization_id=cust_id).first():
                customization = db.session.get(Customization, cust_id)
                if customization:
                    db.session.delete(customization)
        else:
            db.session.delete(item)
            
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Failed to clear cart'}), 500
    
    return jsonify({'message': 'Cart cleared'}), 200


# ─────────────────────────────────────────────
# API: Get cart count
# ─────────────────────────────────────────────
@cart_bp.route('/api/cart/count', methods=['GET'])
@jwt_required(optional=True)
def cart_count():
    user = get_current_user()
    if not user:
        return jsonify({'count': 0})
    count = CartItem.query.filter_by(user_id=user.id).count()
    return jsonify({'count': count})
