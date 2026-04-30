from datetime import datetime
import uuid
from extensions import db, bcrypt


def generate_uuid():
    return str(uuid.uuid4())


def generate_order_number():
    return f"LUX-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"


# ─────────────────────────────────────────────
# USER MODEL
# ─────────────────────────────────────────────
class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=True)  # nullable for Google OAuth
    full_name = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20), nullable=True, unique=True)
    address = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(100), nullable=True)
    pincode = db.Column(db.String(10), nullable=True)
    role = db.Column(db.String(20), default='user', nullable=False)  # 'admin' or 'user'
    google_id = db.Column(db.String(255), nullable=True, unique=True)
    avatar_url = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    is_email_verified = db.Column(db.Boolean, default=False)
    
    # Restored April 25 Columns
    referral_code = db.Column(db.String(50), unique=True, nullable=True)
    loyalty_points = db.Column(db.Integer, default=0)
    referred_by_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    orders = db.relationship('Order', backref='user', lazy='dynamic')
    cart_items = db.relationship('CartItem', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    reviews = db.relationship('Review', backref='user', lazy='dynamic')
    
    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    
    def check_password(self, password):
        if not self.password_hash:
            return False
        return bcrypt.check_password_hash(self.password_hash, password)
    
    @property
    def is_admin(self):
        return self.role == 'admin'
    
    @property
    def is_sales(self):
        return self.role == 'sales'
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'full_name': self.full_name,
            'phone': self.phone,
            'address': self.address,
            'city': self.city,
            'state': self.state,
            'pincode': self.pincode,
            'role': self.role,
            'is_admin': self.is_admin,
            'avatar_url': self.avatar_url,
            'referral_code': self.referral_code,
            'loyalty_points': self.loyalty_points,
            'referred_by_id': self.referred_by_id,
            'has_password': self.password_hash is not None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ─────────────────────────────────────────────
# CATEGORY MODEL
# ─────────────────────────────────────────────
class Category(db.Model):
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    display_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    products = db.relationship('Product', backref='category', lazy='dynamic')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'description': self.description,
            'image_url': self.image_url,
            'is_active': self.is_active,
            'product_count': self.products.count()
        }


# ─────────────────────────────────────────────
# PRODUCT MODEL
# ─────────────────────────────────────────────
class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    short_description = db.Column(db.String(500), nullable=True)
    price = db.Column(db.Float, nullable=False)
    sale_price = db.Column(db.Float, nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    image_url = db.Column(db.String(500), nullable=True)
    images = db.Column(db.JSON, nullable=True)  # List of image URLs (legacy)
    stock = db.Column(db.Integer, default=0)
    weight = db.Column(db.String(50), nullable=True)  # e.g., "200g"
    burn_time = db.Column(db.String(50), nullable=True)  # e.g., "40 hours"
    fragrance = db.Column(db.String(255), nullable=True)
    wax_type = db.Column(db.String(100), nullable=True)
    video_url = db.Column(db.String(500), nullable=True)
    is_featured = db.Column(db.Boolean, default=False)
    is_customizable = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    rating_avg = db.Column(db.Float, default=0.0)
    rating_count = db.Column(db.Integer, default=0)
    view_count = db.Column(db.Integer, default=0)
    
    # Restored April 25 Columns
    recipe_id = db.Column(db.String(100), nullable=True)
    views = db.Column(db.Integer, default=0) # April 25 version of view_count
    occasion_tags = db.Column(db.String(255), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    reviews = db.relationship('Review', backref='product', lazy='dynamic')
    order_items = db.relationship('OrderItem', backref='product', lazy='dynamic')
    product_images = db.relationship('ProductImage', backref='product', lazy='dynamic',
                                      order_by='ProductImage.display_order', cascade='all, delete-orphan')
    
    @property
    def all_images(self):
        """Return all product images: from ProductImage model + legacy JSON field + main image_url."""
        imgs = [pi.image_url for pi in self.product_images.order_by(ProductImage.display_order).all()]
        if not imgs:
            # Fallback to legacy JSON images
            imgs = self.images or []
        if self.image_url and self.image_url not in imgs:
            imgs.insert(0, self.image_url)
        return imgs if imgs else []
    
    @property
    def effective_price(self):
        return self.sale_price if self.sale_price and self.sale_price < self.price else self.price
    
    @property
    def discount_percentage(self):
        if self.sale_price and self.sale_price < self.price:
            return round(((self.price - self.sale_price) / self.price) * 100)
        return 0
    
    @property
    def in_stock(self):
        return self.stock > 0
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'description': self.description,
            'short_description': self.short_description,
            'price': self.price,
            'sale_price': self.sale_price,
            'effective_price': self.effective_price,
            'discount_percentage': self.discount_percentage,
            'category_id': self.category_id,
            'category': self.category.to_dict() if self.category else None,
            'image_url': self.image_url,
            'images': self.images or [],
            'all_images': self.all_images,
            'stock': self.stock,
            'in_stock': self.in_stock,
            'weight': self.weight,
            'burn_time': self.burn_time,
            'fragrance': self.fragrance,
            'wax_type': self.wax_type,
            'video_url': self.video_url,
            'is_featured': self.is_featured,
            'is_customizable': self.is_customizable,
            'is_active': self.is_active,
            'rating_avg': self.rating_avg,
            'rating_count': self.rating_count,
            'view_count': self.view_count,
            'views': self.views,
            'recipe_id': self.recipe_id,
            'occasion_tags': self.occasion_tags,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ─────────────────────────────────────────────
# PRODUCT IMAGE MODEL (for carousel)
# ─────────────────────────────────────────────
class ProductImage(db.Model):
    __tablename__ = 'product_images'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    product_id = db.Column(db.String(36), db.ForeignKey('products.id'), nullable=False, index=True)
    image_url = db.Column(db.String(500), nullable=False)
    alt_text = db.Column(db.String(255), nullable=True)
    display_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'image_url': self.image_url,
            'alt_text': self.alt_text,
            'display_order': self.display_order
        }


# ─────────────────────────────────────────────
# IMAGE STORE MODEL (persistent image storage in DB)
# ─────────────────────────────────────────────
class ImageStore(db.Model):
    __tablename__ = 'image_store'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    data = db.Column(db.LargeBinary, nullable=False)
    content_type = db.Column(db.String(50), nullable=False, default='image/jpeg')
    filename = db.Column(db.String(255), nullable=True)
    size = db.Column(db.Integer, nullable=True)  # bytes
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────
# CUSTOMIZATION OPTION MODEL (admin-managed)
# ─────────────────────────────────────────────
class CustomizationOption(db.Model):
    __tablename__ = 'customization_options'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    category = db.Column(db.String(50), nullable=False, index=True)
    # category values: jar_type, colour, fragrance, wick_type, shape, ingredient, wax_type
    name = db.Column(db.String(100), nullable=False)           # Display name
    value = db.Column(db.String(100), nullable=False)          # Slug / internal key
    icon = db.Column(db.String(100), nullable=True)            # Bootstrap icon class
    color_hex = db.Column(db.String(10), nullable=True)        # For colour swatches
    price_addon = db.Column(db.Float, default=0.0)
    description = db.Column(db.String(255), nullable=True)
    display_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'category': self.category,
            'name': self.name,
            'value': self.value,
            'icon': self.icon,
            'color_hex': self.color_hex,
            'price_addon': self.price_addon,
            'description': self.description,
            'display_order': self.display_order,
            'is_active': self.is_active,
        }


# ─────────────────────────────────────────────
# CUSTOMIZATION MODEL
# ─────────────────────────────────────────────
class Customization(db.Model):
    __tablename__ = 'customizations'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    jar_type = db.Column(db.String(50), nullable=False)  # classic_glass, matte_ceramic, gold_tin, marble_vessel
    colour = db.Column(db.String(50), nullable=False)  # ivory_white, blush_pink, sage_green, midnight_black
    fragrance = db.Column(db.String(100), nullable=False)  # vanilla_oud, rose_sandalwood, fresh_linen, amber_noir
    wick_type = db.Column(db.String(20), nullable=False)  # single, double, triple
    label_text = db.Column(db.String(255), nullable=True)
    additional_notes = db.Column(db.Text, nullable=True)
    price_addon = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    cart_items = db.relationship('CartItem', backref='customization', lazy='dynamic')
    order_items = db.relationship('OrderItem', backref='customization', lazy='dynamic')
    
    def to_dict(self):
        return {
            'id': self.id,
            'jar_type': self.jar_type,
            'colour': self.colour,
            'fragrance': self.fragrance,
            'wick_type': self.wick_type,
            'label_text': self.label_text,
            'additional_notes': self.additional_notes,
            'price_addon': self.price_addon
        }


# ─────────────────────────────────────────────
# CART ITEM MODEL
# ─────────────────────────────────────────────
class CartItem(db.Model):
    __tablename__ = 'cart_items'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    product_id = db.Column(db.String(36), db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    customization_id = db.Column(db.String(36), db.ForeignKey('customizations.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    product = db.relationship('Product', backref='cart_items_rel')
    
    def to_dict(self):
        if self.product:
            base_price = self.product.effective_price
            addon = self.customization.price_addon if self.customization else 0
            unit_price = base_price + addon
        else:
            unit_price = self.customization.price_addon if self.customization else 0
        return {
            'id': self.id,
            'product': self.product.to_dict() if self.product else None,
            'quantity': self.quantity,
            'price': round(unit_price, 2),
            'customization': self.customization.to_dict() if self.customization else None,
            'subtotal': round(self.quantity * unit_price, 2),
            'is_custom': self.customization_id is not None
        }


# ─────────────────────────────────────────────
# ORDER MODEL
# ─────────────────────────────────────────────
class Order(db.Model):
    __tablename__ = 'orders'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    order_number = db.Column(db.String(50), unique=True, nullable=False, default=generate_order_number)
    
    # Pricing
    subtotal = db.Column(db.Float, nullable=False)
    discount_amount = db.Column(db.Float, default=0.0)
    shipping_cost = db.Column(db.Float, default=0.0)
    total_amount = db.Column(db.Float, nullable=False)
    
    # Shipping
    shipping_name = db.Column(db.String(255), nullable=False)
    shipping_address = db.Column(db.Text, nullable=False)
    shipping_city = db.Column(db.String(100), nullable=False)
    shipping_state = db.Column(db.String(100), nullable=False)
    shipping_pincode = db.Column(db.String(10), nullable=False)
    shipping_phone = db.Column(db.String(20), nullable=False)
    
    # Status
    status = db.Column(db.String(30), default='pending')  # pending, confirmed, processing, shipped, delivered, cancelled
    payment_status = db.Column(db.String(30), default='pending')  # pending, paid, failed, refunded
    
    # Razorpay
    razorpay_order_id = db.Column(db.String(255), nullable=True)
    
    # Coupon
    coupon_code = db.Column(db.String(50), nullable=True)
    
    # Notes
    notes = db.Column(db.Text, nullable=True)
    
    # Cancellation
    cancellation_reason = db.Column(db.Text, nullable=True)
    cancelled_by = db.Column(db.String(20), nullable=True)  # 'admin' or 'customer'
    cancelled_at = db.Column(db.DateTime, nullable=True)
    
    # Tracking / Shipping
    tracking_number = db.Column(db.String(100), nullable=True)
    carrier = db.Column(db.String(100), nullable=True)
    estimated_delivery = db.Column(db.DateTime, nullable=True)
    
    # Payment cooldown (10 min window)
    payment_expires_at = db.Column(db.DateTime, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    items = db.relationship('OrderItem', backref='order', lazy='dynamic', cascade='all, delete-orphan')
    payment = db.relationship('Payment', backref='order', uselist=False)
    tracking_updates = db.relationship('OrderTracking', backref='order', lazy='dynamic',
                                        order_by='OrderTracking.created_at')
    
    def to_dict(self):
        return {
            'id': self.id,
            'order_number': self.order_number,
            'user': self.user.to_dict() if self.user else None,
            'subtotal': self.subtotal,
            'discount_amount': self.discount_amount,
            'shipping_cost': self.shipping_cost,
            'total_amount': self.total_amount,
            'shipping_name': self.shipping_name,
            'shipping_address': self.shipping_address,
            'shipping_city': self.shipping_city,
            'shipping_state': self.shipping_state,
            'shipping_pincode': self.shipping_pincode,
            'shipping_phone': self.shipping_phone,
            'status': self.status,
            'payment_status': self.payment_status,
            'coupon_code': self.coupon_code,
            'cancellation_reason': self.cancellation_reason,
            'cancelled_by': self.cancelled_by,
            'cancelled_at': self.cancelled_at.isoformat() if self.cancelled_at else None,
            'tracking_number': self.tracking_number,
            'carrier': self.carrier,
            'estimated_delivery': self.estimated_delivery.isoformat() if self.estimated_delivery else None,
            'payment_expires_at': self.payment_expires_at.isoformat() if self.payment_expires_at else None,
            'items': [item.to_dict() for item in self.items],
            'payment': self.payment.to_dict() if self.payment else None,
            'tracking': [t.to_dict() for t in self.tracking_updates.order_by(OrderTracking.created_at).all()],
            'return_request': self.return_request.to_dict() if self.return_request else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ─────────────────────────────────────────────
# ORDER ITEM MODEL
# ─────────────────────────────────────────────
class OrderItem(db.Model):
    __tablename__ = 'order_items'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    order_id = db.Column(db.String(36), db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.String(36), db.ForeignKey('products.id'), nullable=True)
    product_name_snapshot = db.Column(db.String(255), nullable=True)  # Preserved after product deletion
    quantity = db.Column(db.Integer, nullable=False, default=1)
    price = db.Column(db.Float, nullable=False)  # Price at time of purchase
    customization_id = db.Column(db.String(36), db.ForeignKey('customizations.id'), nullable=True)
    
    def to_dict(self):
        prod_name = self.product.name if self.product else (self.product_name_snapshot or 'Deleted Product')
        return {
            'id': self.id,
            'product': self.product.to_dict() if self.product else {'name': prod_name, 'image_url': None, 'slug': None},
            'product_name': prod_name,
            'quantity': self.quantity,
            'price': self.price,
            'customization': self.customization.to_dict() if self.customization else None,
            'is_custom': self.customization_id is not None,
            'subtotal': self.quantity * self.price
        }


# ─────────────────────────────────────────────
# PAYMENT MODEL
# ─────────────────────────────────────────────
class Payment(db.Model):
    __tablename__ = 'payments'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    order_id = db.Column(db.String(36), db.ForeignKey('orders.id'), nullable=False, unique=True)
    razorpay_payment_id = db.Column(db.String(255), nullable=True)
    razorpay_order_id = db.Column(db.String(255), nullable=True)
    razorpay_signature = db.Column(db.String(500), nullable=True)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default='INR')
    status = db.Column(db.String(30), default='pending')  # pending, captured, failed, refunded
    method = db.Column(db.String(50), nullable=True)  # upi, card, netbanking, wallet
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'razorpay_payment_id': self.razorpay_payment_id,
            'razorpay_order_id': self.razorpay_order_id,
            'razorpay_signature': self.razorpay_signature,
            'amount': self.amount,
            'currency': self.currency,
            'status': self.status,
            'method': self.method,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ─────────────────────────────────────────────
# B2B REQUEST MODEL
# ─────────────────────────────────────────────
class B2BRequest(db.Model):
    __tablename__ = 'b2b_requests'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    company_name = db.Column(db.String(255), nullable=False)
    contact_person = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    product_type = db.Column(db.String(100), nullable=True)
    requirements = db.Column(db.Text, nullable=True)
    custom_scent = db.Column(db.String(255), nullable=True)
    branding_file = db.Column(db.String(500), nullable=True)
    budget_range = db.Column(db.String(100), nullable=True)
    delivery_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(30), default='pending')  # pending, reviewing, quoted, accepted, rejected
    admin_notes = db.Column(db.Text, nullable=True)
    quotation_amount = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'company_name': self.company_name,
            'contact_person': self.contact_person,
            'email': self.email,
            'phone': self.phone,
            'quantity': self.quantity,
            'product_type': self.product_type,
            'requirements': self.requirements,
            'custom_scent': self.custom_scent,
            'budget_range': self.budget_range,
            'delivery_date': self.delivery_date.isoformat() if self.delivery_date else None,
            'status': self.status,
            'admin_notes': self.admin_notes,
            'quotation_amount': self.quotation_amount,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ─────────────────────────────────────────────
# COUPON MODEL
# ─────────────────────────────────────────────
class Coupon(db.Model):
    __tablename__ = 'coupons'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    discount_type = db.Column(db.String(20), nullable=False)  # 'percentage' or 'fixed'
    discount_value = db.Column(db.Float, nullable=False)
    min_order = db.Column(db.Float, default=0.0)
    max_discount = db.Column(db.Float, nullable=True)
    usage_limit = db.Column(db.Integer, nullable=True)
    used_count = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def is_valid(self, order_total):
        if not self.is_active:
            return False, "Coupon is not active"
        if self.expires_at and self.expires_at < datetime.utcnow():
            return False, "Coupon has expired"
        if self.usage_limit and self.used_count >= self.usage_limit:
            return False, "Coupon usage limit reached"
        if order_total < self.min_order:
            return False, f"Minimum order amount is ₹{self.min_order}"
        return True, "Valid"
    
    def calculate_discount(self, order_total):
        if self.discount_type == 'percentage':
            discount = order_total * (self.discount_value / 100)
            if self.max_discount:
                discount = min(discount, self.max_discount)
        else:
            discount = self.discount_value
        return round(discount, 2)
    
    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'discount_type': self.discount_type,
            'discount_value': self.discount_value,
            'min_order': self.min_order,
            'max_discount': self.max_discount,
            'usage_limit': self.usage_limit,
            'used_count': self.used_count,
            'is_active': self.is_active,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None
        }


# ─────────────────────────────────────────────
# ORDER TRACKING MODEL (live status updates)
# ─────────────────────────────────────────────
class OrderTracking(db.Model):
    __tablename__ = 'order_tracking'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    order_id = db.Column(db.String(36), db.ForeignKey('orders.id'), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    location = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'status': self.status,
            'description': self.description,
            'location': self.location,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ─────────────────────────────────────────────# COMPLAINT MODEL
# ─────────────────────────────────────────────
class Complaint(db.Model):
    __tablename__ = 'complaints'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    order_id = db.Column(db.String(36), db.ForeignKey('orders.id'), nullable=True)
    subject = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), default='open')  # open, in_progress, resolved, closed
    priority = db.Column(db.String(20), default='medium')  # low, medium, high
    admin_response = db.Column(db.Text, nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('complaints', lazy='dynamic'))
    order = db.relationship('Order', backref=db.backref('complaints', lazy='dynamic'))

    def to_dict(self):
        return {
            'id': self.id,
            'user': self.user.to_dict() if self.user else None,
            'order_id': self.order_id,
            'order_number': self.order.order_number if self.order else None,
            'subject': self.subject,
            'description': self.description,
            'status': self.status,
            'priority': self.priority,
            'admin_response': self.admin_response,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


# ─────────────────────────────────────────────# REVIEW MODEL
# ─────────────────────────────────────────────
class Review(db.Model):
    __tablename__ = 'reviews'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    product_id = db.Column(db.String(36), db.ForeignKey('products.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1-5
    title = db.Column(db.String(255), nullable=True)
    comment = db.Column(db.Text, nullable=True)
    is_verified_purchase = db.Column(db.Boolean, default=False)
    helpful_count = db.Column(db.Integer, default=0)
    review_images = db.Column(db.JSON, nullable=True)  # List of image URLs attached to review
    is_approved = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user': {'full_name': self.user.full_name, 'avatar_url': self.user.avatar_url} if self.user else None,
            'user_name': self.user.full_name if self.user else 'Anonymous',
            'product_name': self.product.name if self.product else 'Unknown',
            'product_id': self.product_id,
            'rating': self.rating,
            'title': self.title,
            'comment': self.comment,
            'is_verified_purchase': self.is_verified_purchase,
            'is_approved': self.is_approved,
            'helpful_count': self.helpful_count,
            'review_images': self.review_images or [],
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ─────────────────────────────────────────────
# RETURN REQUEST MODEL
# ─────────────────────────────────────────────
class ReturnRequest(db.Model):
    __tablename__ = 'return_requests'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    order_id = db.Column(db.String(36), db.ForeignKey('orders.id'), nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    seal_intact = db.Column(db.Boolean, nullable=False, default=True)  # Customer confirms seal is not opened
    status = db.Column(db.String(30), default='pending')  # pending, approved, rejected, completed
    admin_notes = db.Column(db.Text, nullable=True)
    refund_amount = db.Column(db.Float, nullable=True)  # Total minus delivery charges
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    order = db.relationship('Order', backref=db.backref('return_request', uselist=False))
    user = db.relationship('User', backref=db.backref('return_requests', lazy='dynamic'))

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'order_number': self.order.order_number if self.order else None,
            'user': self.user.to_dict() if self.user else None,
            'reason': self.reason,
            'seal_intact': self.seal_intact,
            'status': self.status,
            'admin_notes': self.admin_notes,
            'refund_amount': self.refund_amount,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


# ─────────────────────────────────────────────
# SITE SETTINGS MODEL (Key-Value Store)
# ─────────────────────────────────────────────
class SiteSettings(db.Model):
    __tablename__ = 'site_settings'

    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get(key, default=None):
        """Get a setting value by key. Extremely resilient for template usage."""
        try:
            setting = SiteSettings.query.get(key)
            if setting and setting.value is not None:
                return setting.value
            return default if default is not None else ""
        except Exception:
            # Silently fail and return default if DB is unreachable
            return default if default is not None else ""

    @staticmethod
    def set(key, value):
        """Set a setting value by key (upsert)."""
        setting = SiteSettings.query.get(key)
        if setting:
            setting.value = value
        else:
            setting = SiteSettings(key=key, value=value)
            db.session.add(setting)
        db.session.commit()
        return setting

    def to_dict(self):
        return {
            'key': self.key,
            'value': self.value,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


# ─────────────────────────────────────────────
# PARTNERSHIP & AUDIT LOGGING
# ─────────────────────────────────────────────

class Partner(db.Model):
    """The four founders/partners of Luxoya Candles."""
    __tablename__ = 'partners'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    initial_share_percent = db.Column(db.Float, default=25.0)
    color_hex = db.Column(db.String(20), default='#f8d57e')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'share': self.initial_share_percent,
            'color': self.color_hex
        }


class AuditLog(db.Model):
    """Tracks administrative changes across the platform for transparency."""
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True) # Who performed the action
    user_name = db.Column(db.String(255), nullable=True) # Snapshot of name
    action = db.Column(db.String(50), nullable=False) # 'CREATE', 'UPDATE', 'DELETE'
    module = db.Column(db.String(100), nullable=False) # 'Finance', 'Inventory', 'Settings'
    target_id = db.Column(db.String(100), nullable=True) # ID of the affected record
    description = db.Column(db.Text, nullable=True) # Human readable summary
    details = db.Column(db.JSON, nullable=True) # JSON of changes {old_val, new_val}
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('audit_logs', lazy='dynamic'))

    def to_dict(self):
        return {
            'id': self.id,
            'user': self.user_name or (self.user.full_name if self.user else 'System'),
            'action': self.action,
            'module': self.module,
            'description': self.description,
            'created_at': self.created_at.isoformat()
        }


# ─────────────────────────────────────────────
# FINANCIAL TRACKING MODELS
# ─────────────────────────────────────────────

class FinanceRecord(db.Model):
    """Tracks expenses, capital infusions, and withdrawals."""
    __tablename__ = 'finance_records'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    # type: 'expense', 'capital', 'withdrawal', 'loss', 'other_income'
    record_type = db.Column(db.String(50), default='expense', nullable=False)
    # category: 'Marketing', 'Raw Material', 'Shipping', 'Rent', 'Salaries', etc.
    category = db.Column(db.String(100), nullable=True)
    date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    bill_url = db.Column(db.String(500), nullable=True) # Path to uploaded receipt
    partner_id = db.Column(db.Integer, db.ForeignKey('partners.id'), nullable=True)
    
    partner = db.relationship('Partner', backref=db.backref('records', lazy='dynamic'))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'amount': self.amount,
            'type': self.record_type,
            'category': self.category,
            'date': self.date.isoformat() if self.date else None,
            'notes': self.notes,
            'bill_url': self.bill_url,
            'partner_id': self.partner_id,
            'partner': self.partner.name if self.partner else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class RawMaterial(db.Model):
    """Tracks candle manufacturing supplies (wax, wicks, glass jars, etc.)"""
    __tablename__ = 'raw_materials'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    # type: 'wax', 'wick', 'jar', 'fragrance', 'packaging', 'other'
    material_type = db.Column(db.String(50), nullable=False)
    specific_type = db.Column(db.String(100), nullable=True) # e.g. 'Soy Flakes', 'Soft Soy', 'Lavender'
    stock_quantity = db.Column(db.Float, default=0.0)
    unit = db.Column(db.String(20), default='units') # 'kg', 'g', 'units', 'ml'
    reorder_level = db.Column(db.Float, default=10.0)
    cost_per_unit = db.Column(db.Float, default=0.0)
    supplier = db.Column(db.String(255), nullable=True)
    bill_url = db.Column(db.String(500), nullable=True)
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)
    purchased_by_id = db.Column(db.Integer, db.ForeignKey('partners.id'), nullable=True)
    
    purchased_by = db.relationship('Partner', backref=db.backref('materials', lazy='dynamic'))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'type': self.material_type,
            'specific_type': self.specific_type,
            'stock': self.stock_quantity,
            'unit': self.unit,
            'reorder_level': self.reorder_level,
            'cost': self.cost_per_unit,
            'supplier': self.supplier,
            'bill_url': self.bill_url,
            'purchase_date': self.purchase_date.isoformat() if self.purchase_date else None,
            'purchased_by': self.purchased_by.name if self.purchased_by else None,
            'purchased_by_id': self.purchased_by_id,
            'is_low_stock': self.stock_quantity <= self.reorder_level
        }


class ManufacturingRecipe(db.Model):
    """Stores recipes for candle series including wax/dye/fragrance ratios."""
    __tablename__ = 'manufacturing_recipes'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, index=True) # e.g. 'Ocean Breeze', 'Ivory White'
    category = db.Column(db.String(100), nullable=True) # 'Color', 'Fragrance', 'Full Recipe'
    
    # Ratios as JSON: e.g. {"wax": 1000, "dye": 5, "fragrance": 80}
    composition = db.Column(db.JSON, nullable=False)
    
    instructions = db.Column(db.Text, nullable=True)
    color_hex = db.Column(db.String(20), nullable=True) # Visual representation
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'category': self.category,
            'composition': self.composition,
            'instructions': self.instructions,
            'color_hex': self.color_hex,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ─────────────────────────────────────────────
# USER OTP MODEL
# ─────────────────────────────────────────────
class UserOTP(db.Model):
    """Stores one-time passwords for email authentication."""
    __tablename__ = 'user_otps'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    otp_code = db.Column(db.String(10), nullable=False)
    purpose = db.Column(db.String(50), default='login')  # 'login', 'reset_password'
    is_verified = db.Column(db.Boolean, default=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def is_valid(self):
        return not self.is_verified and datetime.utcnow() < self.expires_at

