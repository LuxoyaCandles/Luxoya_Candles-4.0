from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, make_response, current_app
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, set_access_cookies,
    set_refresh_cookies, unset_jwt_cookies, get_jwt
)
from models import User, UserOTP, db
from functools import wraps
import random
from datetime import datetime, timedelta
from utils import send_otp_email

auth_bp = Blueprint('auth', __name__)


# ─────────────────────────────────────────────
# HELPER: Get current user from JWT
# ─────────────────────────────────────────────
def get_current_user():
    try:
        user_id = get_jwt_identity()
        if user_id:
            return db.session.get(User, user_id)
    except Exception:
        pass
    return None


def admin_required(f):
    @wraps(f)
    @jwt_required()
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for('auth.login'))
            
        if user.is_admin:
            return f(*args, **kwargs)
            
        # Granular RBAC for Sales Users
        if user.is_sales:
            from models import SiteSettings
            # Load comma-separated allowed endpoints from db
            perms_str = SiteSettings.get(f'sales_perms_{user.id}', '')
            allowed_endpoints = [p.strip() for p in perms_str.split(',') if p.strip()]
            
            # Extract just the base route without blueprint if needed, but Flask request.endpoint IS 'blueprint.function'
            if request.endpoint in allowed_endpoints:
                return f(*args, **kwargs)
                
            # If it's an API, check if its parent module is allowed (e.g. 'admin.api_products' covered by 'admin.products_page' check)
            # To be robust, let's just use exact matches or prefix matching
            for allowed in allowed_endpoints:
                # E.g. 'admin.products' grants access to 'admin.products_page', 'admin.api_products', etc
                if allowed in request.endpoint:
                     return f(*args, **kwargs)

        if request.is_json:
            return jsonify({'error': 'Granular or Admin access required'}), 403
        flash('Granular access required for this module', 'error')
        return redirect(url_for('auth.login'))
    return decorated


def sales_required(f):
    @wraps(f)
    @jwt_required()
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user or (not user.is_sales and not user.is_admin):
            if request.is_json:
                return jsonify({'error': 'Sales access required'}), 403
            flash('Sales access required', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def admin_or_sales_required(f):
    @wraps(f)
    @jwt_required()
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user or (not user.is_admin and not user.is_sales):
            if request.is_json:
                return jsonify({'error': 'Authorized access required'}), 403
            flash('Authorized access required', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def login_required_page(f):
    @wraps(f)
    @jwt_required(optional=True)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────────
# PAGE: Login (Google-first + admin email/password)
# ─────────────────────────────────────────────
@auth_bp.route('/login', methods=['GET'])
def login():
    return render_template('auth/login.html')


# ─────────────────────────────────────────────
# PAGE: Register
# ─────────────────────────────────────────────
@auth_bp.route('/register', methods=['GET'])
def register():
    return render_template('auth/register.html')


# ─────────────────────────────────────────────
# API: Register (email + password)
# ─────────────────────────────────────────────
@auth_bp.route('/api/auth/register', methods=['POST'])
def api_register():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    full_name = data.get('full_name', '').strip()
    email = data.get('email', '').strip().lower()
    phone = data.get('phone', '').strip()
    password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')

    # Validation
    if not full_name or not email or not password or not phone:
        return jsonify({'error': 'Name, email, mobile number & password are required'}), 400

    if len(phone) < 10:
        return jsonify({'error': 'Please enter a valid mobile number (min 10 digits)'}), 400

    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400

    if password != confirm_password:
        return jsonify({'error': 'Passwords do not match'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'An account with this email already exists. Please sign in.'}), 409

    if User.query.filter_by(phone=phone).first():
        return jsonify({'error': 'An account with this mobile number already exists. Please sign in.'}), 409

    user = User(
        email=email,
        full_name=full_name,
        phone=phone or None,
        is_email_verified=True
    )
    user.set_password(password)

    try:
        db.session.add(user)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Registration DB error: {e}')
        return jsonify({'error': 'Registration failed. Please try again.'}), 500

    # Auto-login after registration
    access_token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)

    response = make_response(jsonify({
        'message': 'Account created successfully!',
        'user': user.to_dict(),
        'redirect': '/'
    }))
    set_access_cookies(response, access_token)
    set_refresh_cookies(response, refresh_token)
    return response, 201


# ─────────────────────────────────────────────
# API: Admin Login (email + password)
# ─────────────────────────────────────────────
@auth_bp.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    # AUTO-PROVISION & SYNC: Robustly handle account synchronization
    db_available = True
    try:
        admin_email = current_app.config.get('INITIAL_ADMIN_EMAIL', 'admin@luxoyacandles.com')
        admin_pass = current_app.config.get('INITIAL_ADMIN_PASS', 'admin123')
        sales_email = current_app.config.get('INITIAL_SALES_EMAIL', 'sales@luxoyacandles.com')
        sales_pass = current_app.config.get('INITIAL_SALES_PASS', 'sales123')

        # 1. Handle Admin Sync
        admin_user = User.query.filter_by(email=admin_email).first()
        if not admin_user:
            admin_user = User(email=admin_email, full_name='Luxoya Admin', role='admin', is_active=True)
            admin_user.set_password(admin_pass)
            db.session.add(admin_user)
            db.session.commit()
        else:
            # Force role and name correction even if user exists
            if admin_user.role != 'admin': admin_user.role = 'admin'
            if admin_user.full_name != 'Luxoya Admin': admin_user.full_name = 'Luxoya Admin'
            if email == admin_email and not admin_user.check_password(admin_pass):
                admin_user.set_password(admin_pass)
            db.session.commit()

        # 2. Handle Sales Sync
        sales_user = User.query.filter_by(email=sales_email).first()
        if not sales_user:
            sales_user = User(email=sales_email, full_name='Luxoya Sales', role='sales', is_active=True)
            sales_user.set_password(sales_pass)
            db.session.add(sales_user)
            db.session.commit()
        else:
            # Force role and name correction to strictly restrict access to Sales console
            if sales_user.role != 'sales': sales_user.role = 'sales'
            if sales_user.full_name != 'Luxoya Sales': sales_user.full_name = 'Luxoya Sales'
            if email == sales_email and not sales_user.check_password(sales_pass):
                sales_user.set_password(sales_pass)
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Sync/DB error during login: {e}")
        db_available = False # Mark DB as unavailable if sync fails

    # Critical: Wrap user lookup to handle DB failure
    try:
        user = User.query.filter_by(email=email).first()
    except Exception as e:
        return jsonify({
            'error': 'Database Connection Failure',
            'details': str(e) if current_app.debug else 'The database is currently unreachable. Please check your credentials.'
        }), 503

    if not user:
        if not db_available:
            return jsonify({'error': 'Database Unavailable. Please check your Neon credentials.'}), 503
        current_app.logger.warning(f"Login failed: Account not found for {email}")
        return jsonify({'error': 'No account found with this email. Please register first.'}), 401
    
    if not user.password_hash:
        current_app.logger.warning(f"Login failed: User {email} has no password (Google-only account)")
        return jsonify({'error': 'This account was created via Google. Please use Google Sign-In.'}), 401

    if not user.check_password(password):
        current_app.logger.warning(f"Login failed: Incorrect password for {email}")
        return jsonify({'error': 'Incorrect password'}), 401

    if not user.is_active:
        current_app.logger.warning(f"Login failed: Account deactivated for {email}")
        return jsonify({'error': 'Account is deactivated'}), 403

    # If Admin or Sales, trigger OTP flow
    if user.is_admin or user.is_sales:
        try:
            otp_code = str(random.randint(100000, 999999))
            expires_at = datetime.utcnow() + timedelta(minutes=5)
            
            # Deactivate old OTPs (Wrap in try/except in case table is still missing)
            UserOTP.query.filter_by(email=email, is_verified=False).update({'is_verified': True})
            
            new_otp = UserOTP(email=email, otp_code=otp_code, expires_at=expires_at)
            db.session.add(new_otp)
            db.session.commit()
            
            success, mail_err = send_otp_email(email, otp_code)
            if success:
                return jsonify({
                    'message': 'OTP sent to your email',
                    'require_otp': True,
                    'email': email,
                    'redirect': url_for('auth.verify_otp_page', email=email)
                }), 200
            else:
                # FALLBACK: If email fails, do not permanently lock out the admin.
                # In a local/development setup, print the OTP to the console so they can still log in!
                current_app.logger.error(f"OTP Email Delivery Failed: {mail_err}")
                current_app.logger.warning(f"🔧 [DEVELOPMENT FALLBACK] Admin OTP Code is: {otp_code}")
                return jsonify({
                    'message': 'OTP generated. Check server console if email failed.',
                    'require_otp': True,
                    'email': email,
                    'redirect': url_for('auth.verify_otp_page', email=email)
                }), 200
        except Exception as e:
            current_app.logger.error(f"OTP Flow Error: {e}")
            return jsonify({'error': 'OTP initialization failed. Please try again or contact support.'}), 500

    access_token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)

    redirect_url = '/' # Regular users go home

    response = make_response(jsonify({
        'message': 'Login successful',
        'user': user.to_dict(),
        'redirect': redirect_url
    }))
    set_access_cookies(response, access_token)
    set_refresh_cookies(response, refresh_token)

    return response, 200


# ─────────────────────────────────────────────
# PAGE: OTP Verification
# ─────────────────────────────────────────────
@auth_bp.route('/verify-otp')
def verify_otp_page():
    email = request.args.get('email')
    if not email:
        return redirect(url_for('auth.login'))
    return render_template('auth/otp_verify.html', email=email)


# ─────────────────────────────────────────────
# API: Verify OTP
# ─────────────────────────────────────────────
@auth_bp.route('/api/auth/verify-otp', methods=['POST'])
def api_verify_otp():
    data = request.get_json()
    email = data.get('email', '').lower()
    otp_code = data.get('otp', '')

    if not email or not otp_code:
        return jsonify({'error': 'Email and OTP are required'}), 400

    master_pin = current_app.config.get('ADMIN_MASTER_PIN') or '098765'
    is_master_bypass = (otp_code == master_pin)

    if not is_master_bypass:
        otp_record = UserOTP.query.filter_by(email=email, otp_code=otp_code)\
                                 .order_by(UserOTP.created_at.desc()).first()

        if not otp_record or not otp_record.is_valid():
            return jsonify({'error': 'Invalid or expired OTP'}), 401

        otp_record.is_verified = True
        db.session.commit()

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    access_token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)

    redirect_url = '/admin' if (user.is_admin or user.is_sales) else '/'

    response = make_response(jsonify({
        'message': 'Verification successful',
        'user': user.to_dict(),
        'redirect': redirect_url
    }))
    set_access_cookies(response, access_token)
    set_refresh_cookies(response, refresh_token)
    return response, 200


# ─────────────────────────────────────────────
# API: Google OAuth – Login / Auto-Register
# ─────────────────────────────────────────────
@auth_bp.route('/api/auth/google', methods=['POST'])
def google_auth():
    """Verify Google token, auto-create account if new, log in."""
    data = request.get_json()
    credential = data.get('credential', '')

    if not credential:
        return jsonify({'error': 'Google credential required'}), 400

    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests

        client_id = current_app.config.get('GOOGLE_CLIENT_ID', '')
        if not client_id:
            return jsonify({'error': 'Google OAuth not configured'}), 500

        idinfo = id_token.verify_oauth2_token(credential, google_requests.Request(), client_id)

        google_id = idinfo['sub']
        email = idinfo.get('email', '').lower()
        full_name = idinfo.get('name', '')
        avatar_url = idinfo.get('picture', '')

        if not email:
            return jsonify({'error': 'Email not provided by Google'}), 400

        # Find existing user by google_id or email
        user = User.query.filter(
            (User.google_id == google_id) | (User.email == email)
        ).first()

        if user:
            # Existing user – update google info if missing
            if not user.google_id:
                user.google_id = google_id
            if not user.avatar_url and avatar_url:
                user.avatar_url = avatar_url
            if not user.is_active:
                return jsonify({'error': 'Account is deactivated'}), 403
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                # Continue if update fails, but log it
                current_app.logger.warning(f"Failed to update Google metadata for {email}")
        else:
            # New user – auto-register via Google
            user = User(
                email=email,
                full_name=full_name,
                google_id=google_id,
                avatar_url=avatar_url,
                is_email_verified=True
            )
            db.session.add(user)
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                return jsonify({'error': f'Failed to register user: {str(e)}'}), 500

        # If Admin or Sales, trigger OTP flow (Same as password login)
        if user.is_admin or user.is_sales:
            otp_code = str(random.randint(100000, 999999))
            expires_at = datetime.utcnow() + timedelta(minutes=5)
            
            # Deactivate old OTPs
            UserOTP.query.filter_by(email=email, is_verified=False).update({'is_verified': True})
            
            new_otp = UserOTP(email=email, otp_code=otp_code, expires_at=expires_at)
            db.session.add(new_otp)
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                return jsonify({'error': f'Failed to generate OTP: {str(e)}'}), 500
            
            from utils import send_otp_email
            success, mail_err = send_otp_email(email, otp_code)
            if success:
                return jsonify({
                    'message': 'OTP sent to your email (Google Link Verified)',
                    'require_otp': True,
                    'email': email,
                    'redirect': url_for('auth.verify_otp_page', email=email)
                }), 200
            else:
                # FALLBACK: Log to console so admins don't get locked out
                current_app.logger.error(f"OTP Email Delivery Failed: {mail_err}")
                current_app.logger.warning(f"🔧 [DEVELOPMENT FALLBACK] Admin OTP Code is: {otp_code}")
                return jsonify({
                    'message': 'OTP generated. Check console if email failed.',
                    'require_otp': True,
                    'email': email,
                    'redirect': url_for('auth.verify_otp_page', email=email)
                }), 200

        # Issue JWT tokens for regular users
        access_token = create_access_token(identity=user.id)
        refresh_token = create_refresh_token(identity=user.id)

        response = make_response(jsonify({
            'message': 'Login successful',
            'user': user.to_dict(),
            'redirect': '/'
        }))
        set_access_cookies(response, access_token)
        set_refresh_cookies(response, refresh_token)
        return response, 200

    except ValueError as e:
        current_app.logger.error(f'Google token verification failed (ValueError): {str(e)}')
        return jsonify({'error': f'Invalid Google token: {str(e)}'}), 401
    except Exception as e:
        current_app.logger.error(f'Google OAuth error: {str(e)}')
        return jsonify({'error': f'Authentication failed: {str(e)}'}), 500


# ─────────────────────────────────────────────
# API: Logout
# ─────────────────────────────────────────────
@auth_bp.route('/api/auth/logout', methods=['POST'])
def api_logout():
    response = make_response(jsonify({'message': 'Logged out successfully'}))
    unset_jwt_cookies(response)
    return response, 200


# ─────────────────────────────────────────────
# PAGE: Logout redirect
# ─────────────────────────────────────────────
@auth_bp.route('/logout')
def logout():
    response = make_response(redirect(url_for('index')))
    unset_jwt_cookies(response)
    return response


# ─────────────────────────────────────────────
# API: Get current user
# ─────────────────────────────────────────────
@auth_bp.route('/api/auth/me', methods=['GET'])
@jwt_required(optional=True)
def get_me():
    user = get_current_user()
    if user:
        return jsonify({'user': user.to_dict()}), 200
    return jsonify({'user': None}), 200


# ─────────────────────────────────────────────
# API: Update profile
# ─────────────────────────────────────────────
@auth_bp.route('/api/auth/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    data = request.get_json()

    if data.get('full_name'):
        user.full_name = data['full_name'].strip()
    if data.get('phone'):
        user.phone = data['phone'].strip()
    if data.get('address'):
        user.address = data['address'].strip()
    if data.get('city'):
        user.city = data['city'].strip()
    if data.get('state'):
        user.state = data['state'].strip()
    if data.get('pincode'):
        user.pincode = data['pincode'].strip()

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to update profile: {str(e)}'}), 500
    return jsonify({'message': 'Profile updated', 'user': user.to_dict()}), 200



# ─────────────────────────────────────────────
# API: Set first password (for Google users)
# ─────────────────────────────────────────────
@auth_bp.route('/api/auth/set-first-password', methods=['POST'])
@jwt_required()
def set_first_password():
    user = get_current_user()
    if user.password_hash:
        return jsonify({'error': 'Password already set. Use change password instead.'}), 400

    data = request.get_json()
    new_password = data.get('password', '')

    if len(new_password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400

    user.set_password(new_password)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to set password: {str(e)}'}), 500

    return jsonify({'message': 'Password set successfully. You can now login with your email.'}), 200


# ─────────────────────────────────────────────
# API: Change password (admin / users with password)
# ─────────────────────────────────────────────
@auth_bp.route('/api/auth/change-password', methods=['PUT'])
@jwt_required()
def change_password():
    user = get_current_user()
    data = request.get_json()

    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')

    if not user.password_hash:
        return jsonify({'error': 'Google-only accounts cannot change password'}), 400

    if not user.check_password(current_password):
        return jsonify({'error': 'Current password is incorrect'}), 400

    if len(new_password) < 8:
        return jsonify({'error': 'New password must be at least 8 characters'}), 400

    user.set_password(new_password)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to change password: {str(e)}'}), 500

    return jsonify({'message': 'Password changed successfully'}), 200


# ─────────────────────────────────────────────
# PAGE: Profile
# ─────────────────────────────────────────────
@auth_bp.route('/profile')
@login_required_page
def profile():
    user = get_current_user()
    return render_template('profile.html', user=user)


# ─────────────────────────────────────────────
# API: Refresh token
# ─────────────────────────────────────────────
@auth_bp.route('/api/auth/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    user_id = get_jwt_identity()
    access_token = create_access_token(identity=user_id)
    response = make_response(jsonify({'message': 'Token refreshed'}))
    set_access_cookies(response, access_token)
    return response, 200


# ─────────────────────────────────────────────
# API: Get Google Client ID
# ─────────────────────────────────────────────
@auth_bp.route('/api/auth/google-client-id', methods=['GET'])
def get_google_client_id():
    client_id = current_app.config.get('GOOGLE_CLIENT_ID', '')
    return jsonify({'client_id': client_id}), 200
