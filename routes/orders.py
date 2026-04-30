from flask import Blueprint, request, jsonify, render_template, current_app, make_response
from flask_jwt_extended import jwt_required
from models import Order, OrderItem, CartItem, Payment, Coupon, Product, Complaint, OrderTracking, ReturnRequest, db
from routes.auth import get_current_user, login_required_page
from utils import send_cancellation_email, send_invoice_email, _generate_invoice_html
from datetime import datetime, timedelta
import razorpay
import hmac
import hashlib

orders_bp = Blueprint('orders', __name__)


def get_razorpay_client():
    key_id = current_app.config.get('RAZORPAY_KEY_ID')
    key_secret = current_app.config.get('RAZORPAY_KEY_SECRET')
    if key_id and key_secret:
        return razorpay.Client(auth=(key_id, key_secret))
    return None


# ─────────────────────────────────────────────
# PAGE: Checkout
# ─────────────────────────────────────────────
@orders_bp.route('/checkout')
@login_required_page
def checkout_page():
    user = get_current_user()
    return render_template('checkout.html', user=user,
                         razorpay_key=current_app.config.get('RAZORPAY_KEY_ID', ''))


# ─────────────────────────────────────────────
# PAGE: Order history
# ─────────────────────────────────────────────
@orders_bp.route('/orders')
@login_required_page
def orders_page():
    user = get_current_user()
    return render_template('orders/history.html', user=user)


# ─────────────────────────────────────────────
# PAGE: Order detail
# ─────────────────────────────────────────────
@orders_bp.route('/orders/<order_id>')
@login_required_page
def order_detail_page(order_id):
    user = get_current_user()
    # Accept both order_number (LUX-...) and UUID id
    order = Order.query.filter_by(order_number=order_id, user_id=user.id).first()
    if not order:
        order = Order.query.filter_by(id=order_id, user_id=user.id).first_or_404()
    return render_template('orders/detail.html', order=order, user=user)


# ─────────────────────────────────────────────
# PAGE: Order confirmation
# ─────────────────────────────────────────────
@orders_bp.route('/order-confirmation/<order_id>')
@login_required_page
def order_confirmation(order_id):
    user = get_current_user()
    order = Order.query.filter_by(order_number=order_id, user_id=user.id).first()
    if not order:
        order = Order.query.filter_by(id=order_id, user_id=user.id).first_or_404()
    return render_template('orders/confirmation.html', order=order, user=user)


# ─────────────────────────────────────────────
# PAGE: Live order tracking
# ─────────────────────────────────────────────
@orders_bp.route('/orders/<order_id>/track')
@login_required_page
def order_tracking_page(order_id):
    user = get_current_user()
    order = Order.query.filter_by(order_number=order_id, user_id=user.id).first()
    if not order:
        order = Order.query.filter_by(id=order_id, user_id=user.id).first_or_404()
    return render_template('orders/tracking.html', order=order, user=user)


# ─────────────────────────────────────────────
# API: Create order  (FCFS – first-come-first-served)
# ─────────────────────────────────────────────
@orders_bp.route('/api/orders', methods=['POST'])
@jwt_required()
def create_order():
    user = get_current_user()
    data = request.get_json()
    
    # ── 10-min payment cooldown check ───────────────────────
    pending_order = Order.query.filter_by(user_id=user.id, payment_status='pending')\
        .filter(Order.payment_expires_at > datetime.utcnow())\
        .first()
    if pending_order:
        remaining = (pending_order.payment_expires_at - datetime.utcnow()).total_seconds()
        return jsonify({
            'error': 'You have a pending payment. Please complete or wait for it to expire.',
            'payment_pending': True,
            'order_number': pending_order.order_number,
            'expires_in': int(remaining)
        }), 429
    
    # Auto-expire old pending orders (older than 10 min) and restore stock globally
    expired_orders = Order.query.filter_by(payment_status='pending')\
        .filter(Order.payment_expires_at <= datetime.utcnow()).all()
    for exp_order in expired_orders:
        exp_order.payment_status = 'expired'
        exp_order.status = 'cancelled'
        exp_order.cancellation_reason = 'Payment window expired (10 minutes)'
        exp_order.cancelled_by = 'system'
        exp_order.cancelled_at = datetime.utcnow()
        for item in exp_order.items:
            if item.product and not item.product.is_customizable:
                item.product.stock += item.quantity
        # Add tracking entry
        tracking = OrderTracking(order_id=exp_order.id, status='cancelled',
                                  description='Order cancelled — payment window expired')
        db.session.add(tracking)
    if expired_orders:
        db.session.flush()
    
    # Get cart items
    cart_items = CartItem.query.filter_by(user_id=user.id).all()
    if not cart_items:
        return jsonify({'error': 'Cart is empty'}), 400
    
    # ── FCFS: Lock product rows & validate stock ────────────
    product_ids = [ci.product_id for ci in cart_items if ci.product_id]
    locked_products = {}
    if product_ids:
        products_query = Product.query.filter(Product.id.in_(product_ids))
        # Row-level locking only works on PostgreSQL, skip on SQLite
        db_url = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if db_url.startswith(('postgresql', 'postgres')):
            products_query = products_query.with_for_update()
        locked_products = {p.id: p for p in products_query.all()}

    out_of_stock = []
    for item in cart_items:
        # Custom candle items (is_customizable products) skip strict stock check
        prod = locked_products.get(item.product_id)
        if not prod and item.product_id:
            out_of_stock.append({'product': f'Product #{item.product_id}', 'available': 0, 'requested': item.quantity})
        elif prod and not prod.is_customizable and prod.stock < item.quantity:
            out_of_stock.append({'product': prod.name, 'available': prod.stock, 'requested': item.quantity})

    if out_of_stock:
        db.session.rollback()          # release locks
        return jsonify({
            'error': 'Some items are out of stock. Another customer completed their order first.',
            'out_of_stock': out_of_stock
        }), 409
    # ── END FCFS check ──────────────────────────────────────
    
    # Calculate totals
    subtotal = 0
    for item in cart_items:
        if item.product:
            price = item.product.effective_price
        else:
            price = 0
        if item.customization:
            price += item.customization.price_addon
        subtotal += price * item.quantity
    
    # Apply coupon
    discount_amount = 0
    coupon_code = data.get('coupon_code')
    if coupon_code:
        coupon = Coupon.query.filter_by(code=coupon_code.upper()).first()
        if coupon:
            is_valid, msg = coupon.is_valid(subtotal)
            if is_valid:
                discount_amount = coupon.calculate_discount(subtotal)
                coupon.used_count += 1
    
    # Shipping (free above ₹999)
    shipping_cost = 0 if subtotal >= 999 else 99
    total_amount = round(subtotal - discount_amount + shipping_cost, 2)
    
    # Create order
    order = Order(
        user_id=user.id,
        subtotal=subtotal,
        discount_amount=discount_amount,
        shipping_cost=shipping_cost,
        total_amount=total_amount,
        shipping_name=data.get('shipping_name', user.full_name),
        shipping_address=data.get('shipping_address', user.address or ''),
        shipping_city=data.get('shipping_city', user.city or ''),
        shipping_state=data.get('shipping_state', user.state or ''),
        shipping_pincode=data.get('shipping_pincode', user.pincode or ''),
        shipping_phone=data.get('shipping_phone', user.phone or ''),
        coupon_code=coupon_code,
        notes=data.get('notes', '')
    )
    db.session.add(order)
    db.session.flush()
    
    # Create order items & reduce stock atomically (FCFS)
    for cart_item in cart_items:
        if cart_item.product:
            price = cart_item.product.effective_price
        else:
            price = 0
        if cart_item.customization:
            price += cart_item.customization.price_addon
        
        order_item = OrderItem(
            order_id=order.id,
            product_id=cart_item.product_id,
            quantity=cart_item.quantity,
            price=price,
            customization_id=cart_item.customization_id
        )
        db.session.add(order_item)
        
        # Reduce stock on the locked row (skip for customizable/virtual products)
        prod = locked_products.get(cart_item.product_id)
        if prod and not prod.is_customizable:
            prod.stock -= cart_item.quantity
    
    # Create Razorpay order if method is online
    payment_method = data.get('payment_method', 'razorpay')
    razorpay_order_data = None
    
    if payment_method == 'razorpay':
        client = get_razorpay_client()
        if client:
            try:
                razorpay_order_data = client.order.create({
                    'amount': int(total_amount * 100),  # Amount in paise
                    'currency': 'INR',
                    'receipt': order.order_number,
                    'notes': {
                        'order_id': order.id,
                        'customer_email': user.email
                    }
                })
                order.razorpay_order_id = razorpay_order_data['id']
            except Exception as e:
                current_app.logger.error(f"Razorpay order creation failed: {str(e)}")
                db.session.rollback()
                return jsonify({'error': 'Payment gateway error. Please try again later.'}), 502
        else:
            # Razorpay keys not configured, force COD or error
            db.session.rollback()
            return jsonify({'error': 'Online payment is currently unavailable. Please use Cash on Delivery.'}), 503
    elif payment_method == 'cod':
        order.payment_status = 'pending'  # Stays pending until delivered
        order.status = 'confirmed'       # Automatically confirmed for COD test
        
        # Send confirmation email for COD orders immediately
        try:
            if user and user.email:
                send_invoice_email(user.email, order)
        except Exception as e:
            current_app.logger.error(f'Failed to send COD confirmation email: {str(e)}')
    else:
        db.session.rollback()
        return jsonify({'error': 'Invalid payment method'}), 400
    
    # Set 10-minute payment window
    order.payment_expires_at = datetime.utcnow() + timedelta(minutes=10)
    
    # Create payment record
    payment = Payment(
        order_id=order.id,
        razorpay_order_id=razorpay_order_data['id'] if razorpay_order_data else None,
        amount=total_amount,
        currency='INR',
        method='cod' if payment_method == 'cod' else None,
        status='pending'
    )
    db.session.add(payment)
    
    # Create initial tracking entry
    tracking = OrderTracking(
        order_id=order.id,
        status='pending',
        description='Order placed — awaiting payment'
    )
    db.session.add(tracking)
    
    # Clear cart
    CartItem.query.filter_by(user_id=user.id).delete()
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Order commit failed: {str(e)}')
        return jsonify({'error': 'Failed to create order. Please try again.'}), 500
    
    return jsonify({
        'message': 'Order created',
        'order': order.to_dict(),
        'razorpay_order': razorpay_order_data,
        'razorpay_key': current_app.config.get('RAZORPAY_KEY_ID', ''),
        'payment_expires_in': 600  # 10 minutes in seconds
    }), 201


# ─────────────────────────────────────────────
# API: Verify payment
# ─────────────────────────────────────────────
@orders_bp.route('/api/orders/verify-payment', methods=['POST'])
@jwt_required()
def verify_payment():
    data = request.get_json()
    
    razorpay_payment_id = data.get('razorpay_payment_id')
    razorpay_order_id = data.get('razorpay_order_id')
    razorpay_signature = data.get('razorpay_signature')
    
    # Verify signature
    key_secret = current_app.config.get('RAZORPAY_KEY_SECRET', '')
    msg = f"{razorpay_order_id}|{razorpay_payment_id}"
    generated_signature = hmac.new(
        key_secret.encode(),
        msg.encode(),
        hashlib.sha256
    ).hexdigest()
    
    payment = Payment.query.filter_by(razorpay_order_id=razorpay_order_id).first()
    if not payment:
        return jsonify({'error': 'Payment not found'}), 404
    
    order = payment.order
    
    if generated_signature == razorpay_signature:
        payment.razorpay_payment_id = razorpay_payment_id
        payment.razorpay_signature = razorpay_signature
        payment.status = 'captured'
        payment.method = data.get('method', 'unknown')
        
        order.payment_status = 'paid'
        order.status = 'confirmed'
        order.payment_expires_at = None  # Clear payment window
        
        # Add tracking entry for payment confirmed
        tracking = OrderTracking(
            order_id=order.id,
            status='confirmed',
            description='Payment received — order confirmed'
        )
        db.session.add(tracking)
        
        try:
            # --- LOYALTY & REFERRAL SYSTEM ---
            user = order.user
            if user:
                # 1. Award points to the buyer (1 LXP per ₹1)
                earned = int(order.total_amount)
                user.loyalty_points = (user.loyalty_points or 0) + earned
                
                # 2. If this is the user's first paid order, award points to the referrer
                if user.referred_by_id:
                    # Check if any other 'paid' orders exist for this user
                    paid_orders_count = Order.query.filter_by(user_id=user.id, payment_status='paid').count()
                    if paid_orders_count == 0: # This is the first paid order (including this one, wait, this one is about to be marked paid)
                        referrer = db.session.get(User, user.referred_by_id)
                        if referrer:
                            referrer.loyalty_points = (referrer.loyalty_points or 0) + 250
            
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Loyalty points award failed: {str(e)}')
            # Non-critical: don't fail the payment verification if loyalty points fail
        
        # Send invoice email to customer
        try:
            user = order.user
            if user and user.email:
                send_invoice_email(user.email, order)
        except Exception as e:
            current_app.logger.error(f'Failed to send invoice email: {str(e)}')
        
        return jsonify({
            'message': 'Payment verified',
            'order_number': order.order_number
        }), 200
    else:
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Payment failure commit failed: {str(e)}')
        
        return jsonify({'error': 'Payment verification failed'}), 400


# ─────────────────────────────────────────────
# API: Get user orders
# ─────────────────────────────────────────────
@orders_bp.route('/api/orders', methods=['GET'])
@jwt_required()
def get_orders():
    user = get_current_user()
    page = request.args.get('page', 1, type=int)
    
    orders = Order.query.filter_by(user_id=user.id)\
                       .order_by(Order.created_at.desc())\
                       .paginate(page=page, per_page=10, error_out=False)
    
    return jsonify({
        'orders': [o.to_dict() for o in orders.items],
        'total': orders.total,
        'pages': orders.pages,
        'current_page': page
    })


# ─────────────────────────────────────────────
# API: Get single order
# ─────────────────────────────────────────────
@orders_bp.route('/api/orders/<order_number>', methods=['GET'])
@jwt_required()
def get_order(order_number):
    user = get_current_user()
    order = Order.query.filter_by(order_number=order_number, user_id=user.id).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    return jsonify({'order': order.to_dict()})


# ─────────────────────────────────────────────
# API: Apply coupon
# ─────────────────────────────────────────────
@orders_bp.route('/api/coupons/validate', methods=['POST'])
@jwt_required()
def validate_coupon():
    data = request.get_json()
    code = data.get('code', '').upper().strip()
    subtotal = data.get('subtotal', 0)
    
    coupon = Coupon.query.filter_by(code=code).first()
    if not coupon:
        return jsonify({'error': 'Invalid coupon code'}), 404
    
    is_valid, message = coupon.is_valid(subtotal)
    if not is_valid:
        return jsonify({'error': message}), 400
    
    discount = coupon.calculate_discount(subtotal)
    return jsonify({
        'valid': True,
        'discount': discount,
        'coupon': coupon.to_dict()
    })


# ─────────────────────────────────────────────
# API: Cancel order (customer)
# ─────────────────────────────────────────────
@orders_bp.route('/api/orders/<order_number>/cancel', methods=['POST'])
@jwt_required()
def cancel_order(order_number):
    user = get_current_user()
    data = request.get_json()
    
    cancellation_reason = (data.get('cancellation_reason', '') or '').strip()
    if not cancellation_reason:
        return jsonify({'error': 'Cancellation reason is mandatory'}), 400
    
    if len(cancellation_reason) < 10:
        return jsonify({'error': 'Please provide a more detailed reason (min 10 characters)'}), 400
    
    order = Order.query.filter_by(order_number=order_number, user_id=user.id).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    
    # Only allow cancellation for pending/confirmed orders
    if order.status not in ('pending', 'confirmed'):
        return jsonify({'error': f'Cannot cancel order with status "{order.status}". Contact support for assistance.'}), 400
    
    order.status = 'cancelled'
    order.cancellation_reason = cancellation_reason
    order.cancelled_by = 'customer'
    order.cancelled_at = datetime.utcnow()
    
    if order.payment_status == 'paid':
        order.payment_status = 'refunded'
    
    # Restore stock (skip customizable/virtual products)
    for item in order.items:
        if item.product and not item.product.is_customizable:
            item.product.stock += item.quantity
    
    # Add tracking entry
    tracking = OrderTracking(
        order_id=order.id,
        status='cancelled',
        description=f'Order cancelled by customer: {cancellation_reason}'
    )
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Order cancellation commit failed: {str(e)}')
        return jsonify({'error': 'Failed to save order cancellation'}), 500
    
    # Send cancellation email (non-blocking — don't fail the request)
    try:
        send_cancellation_email(user.email, order.order_number, cancellation_reason, 'customer')
    except Exception as e:
        current_app.logger.error(f'Failed to send cancellation email: {str(e)}')
    
    return jsonify({
        'message': 'Order cancelled successfully. Refund will be processed within 5-7 business days.',
        'order': order.to_dict()
    })


# ─────────────────────────────────────────────
# API: Download invoice (customer)
# ─────────────────────────────────────────────
@orders_bp.route('/api/orders/<order_number>/invoice', methods=['GET'])
@jwt_required()
def download_invoice(order_number):
    user = get_current_user()
    order = Order.query.filter_by(order_number=order_number, user_id=user.id).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    if order.payment_status == 'failed':
        return jsonify({'error': 'Invoice not available for failed payments'}), 400
    html = _generate_invoice_html(order)
    response = make_response(html)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    if request.args.get('download'):
        response.headers['Content-Disposition'] = f'attachment; filename=invoice_{order.order_number}.html'
    return response


# ─────────────────────────────────────────────
# PAGE: Complaints
# ─────────────────────────────────────────────
@orders_bp.route('/complaints')
@login_required_page
def complaints_page():
    user = get_current_user()
    return render_template('orders/complaints.html', user=user)


# ─────────────────────────────────────────────
# API: Create complaint (customer)
# ─────────────────────────────────────────────
@orders_bp.route('/api/complaints', methods=['POST'])
@jwt_required()
def create_complaint():
    user = get_current_user()
    data = request.get_json()

    subject = (data.get('subject', '') or '').strip()
    description = (data.get('description', '') or '').strip()
    order_id = data.get('order_id') or None

    if not subject or not description:
        return jsonify({'error': 'Subject and description are required'}), 400

    if len(description) < 20:
        return jsonify({'error': 'Please provide a more detailed description (min 20 characters)'}), 400

    # Validate order belongs to user if provided
    if order_id:
        order = Order.query.filter_by(id=order_id, user_id=user.id).first()
        if not order:
            return jsonify({'error': 'Order not found'}), 404

    complaint = Complaint(
        user_id=user.id,
        order_id=order_id,
        subject=subject,
        description=description,
        priority=data.get('priority', 'medium')
    )
    db.session.add(complaint)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Complaint submission commit failed: {str(e)}')
        return jsonify({'error': 'Failed to submit complaint. Please try again.'}), 500

    return jsonify({'message': 'Complaint submitted successfully. We will get back to you soon.', 'complaint': complaint.to_dict()}), 201


# ─────────────────────────────────────────────
# API: Get user complaints (customer)
# ─────────────────────────────────────────────
@orders_bp.route('/api/complaints', methods=['GET'])
@jwt_required()
def get_complaints():
    user = get_current_user()
    complaints = Complaint.query.filter_by(user_id=user.id)\
                                .order_by(Complaint.created_at.desc()).all()
    return jsonify({'complaints': [c.to_dict() for c in complaints]})


# ─────────────────────────────────────────────
# API: Get live tracking for an order (customer polling)
# ─────────────────────────────────────────────
@orders_bp.route('/api/orders/<order_id>/tracking', methods=['GET'])
@jwt_required()
def get_order_tracking(order_id):
    user = get_current_user()
    order = Order.query.filter_by(order_number=order_id, user_id=user.id).first()
    if not order:
        order = Order.query.filter_by(id=order_id, user_id=user.id).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    return jsonify({
        'order_number': order.order_number,
        'status': order.status,
        'payment_status': order.payment_status,
        'tracking_number': order.tracking_number,
        'carrier': order.carrier,
        'estimated_delivery': order.estimated_delivery.isoformat() if order.estimated_delivery else None,
        'tracking': [t.to_dict() for t in order.tracking_updates.order_by(OrderTracking.created_at).all()]
    })


# ─────────────────────────────────────────────
# API: Check payment cooldown status
# ─────────────────────────────────────────────
@orders_bp.route('/api/orders/payment-status', methods=['GET'])
@jwt_required()
def check_payment_status():
    user = get_current_user()
    pending_order = Order.query.filter_by(user_id=user.id, payment_status='pending')\
        .filter(Order.payment_expires_at > datetime.utcnow())\
        .first()
    if pending_order:
        remaining = (pending_order.payment_expires_at - datetime.utcnow()).total_seconds()
        return jsonify({
            'payment_pending': True,
            'order_number': pending_order.order_number,
            'order_id': pending_order.id,
            'total_amount': pending_order.total_amount,
            'expires_in': int(remaining),
            'razorpay_order_id': pending_order.razorpay_order_id
        })
    return jsonify({'payment_pending': False})


# ─────────────────────────────────────────────
# API: Request return (customer)
# ─────────────────────────────────────────────
@orders_bp.route('/api/orders/<order_number>/return', methods=['POST'])
@jwt_required()
def request_return(order_number):
    user = get_current_user()
    data = request.get_json()

    order = Order.query.filter_by(order_number=order_number, user_id=user.id).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    if order.status != 'delivered':
        return jsonify({'error': 'Returns are only accepted for delivered orders'}), 400

    # Check if return already requested
    existing = ReturnRequest.query.filter_by(order_id=order.id).first()
    if existing:
        return jsonify({'error': 'A return request already exists for this order', 'return_request': existing.to_dict()}), 409

    # Check 7-day return window
    if order.updated_at:
        days_since_delivery = (datetime.utcnow() - order.updated_at).days
        if days_since_delivery > 7:
            return jsonify({'error': 'Return window has expired (7 days from delivery)'}), 400

    # Validate seal status
    seal_intact = data.get('seal_intact', False)
    if not seal_intact:
        return jsonify({'error': 'We can only accept returns if the product seal is not opened. Please ensure the seal is intact.'}), 400

    reason = (data.get('reason', '') or '').strip()
    if not reason or len(reason) < 10:
        return jsonify({'error': 'Please provide a detailed reason for return (min 10 characters)'}), 400

    # Check for customized items (non-returnable)
    has_custom = any(item.customization_id for item in order.items)
    if has_custom:
        return jsonify({'error': 'Customized candles are non-returnable'}), 400

    # Refund = total - shipping cost (delivery charges are not refundable)
    refund_amount = round(order.total_amount - order.shipping_cost, 2)

    return_req = ReturnRequest(
        order_id=order.id,
        user_id=user.id,
        reason=reason,
        seal_intact=seal_intact,
        refund_amount=refund_amount
    )
    db.session.add(return_req)

    # Add tracking entry
    tracking = OrderTracking(
        order_id=order.id,
        status='return_requested',
        description=f'Return requested by customer: {reason}'
    )
    db.session.add(tracking)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Return request commit failed: {str(e)}')
        return jsonify({'error': 'Failed to submit return request'}), 500

    return jsonify({
        'message': 'Return request submitted successfully. We will review it within 2-3 business days.',
        'return_request': return_req.to_dict()
    }), 201


# ─────────────────────────────────────────────
# API: Get return status (customer)
# ─────────────────────────────────────────────
@orders_bp.route('/api/orders/<order_number>/return', methods=['GET'])
@jwt_required()
def get_return_status(order_number):
    user = get_current_user()
    order = Order.query.filter_by(order_number=order_number, user_id=user.id).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    return_req = ReturnRequest.query.filter_by(order_id=order.id).first()
    if not return_req:
        return jsonify({'return_request': None})

    return jsonify({'return_request': return_req.to_dict()})
