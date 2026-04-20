"""
Luxoya Candles - Utility Functions
Email sending for invoices, order updates, and cancellations
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from datetime import datetime, timedelta
from flask import current_app


# ─────────────────────────────────────────────
# MAIL HELPER
# ─────────────────────────────────────────────
def _get_mail_config(is_auth=False):
    """Return SMTP config and formatted sender. Returns None if not configured."""
    username = current_app.config.get('STORE_MAIL_USER', '')
    password = current_app.config.get('STORE_MAIL_PASS', '')
    sender_email = current_app.config.get('MAIL_DEFAULT_SENDER', 'support@luxoyacandles.com')
    
    if is_auth:
        username = current_app.config.get('OTP_MAIL_USERNAME', username)
        password = current_app.config.get('OTP_MAIL_PASSWORD', password)
        sender_email = current_app.config.get('OTP_MAIL_SENDER', sender_email)

    cfg = {
        'server': current_app.config.get('MAIL_SERVER', 'smtp.gmail.com'),
        'port': current_app.config.get('MAIL_PORT', 587),
        'username': username,
        'password': password,
        'sender_email': sender_email,
    }
    cfg['sender'] = formataddr(('Luxoya Security' if is_auth else 'Luxoya Candles', cfg['sender_email']))
    return cfg


def _send_email(to_email, subject, html_body, plain_body=None, is_auth=False):
    """Send an email via SMTP. Returns (bool: success, str: error_msg)"""
    try:
        cfg = _get_mail_config(is_auth=is_auth)
        if not cfg['username'] or not cfg['password']:
            err = 'Email credentials (AUTH_MAIL_USER/AUTH_MAIL_PASS) are missing.'
            current_app.logger.error(f'CRITICAL: {err} Cannot send email to {to_email}.')
            return False, err

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = cfg['sender']
        msg['To'] = to_email
        msg['Reply-To'] = cfg['sender_email']

        if plain_body:
            msg.attach(MIMEText(plain_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))

        with smtplib.SMTP(cfg['server'], cfg['port']) as server:
            server.set_debuglevel(0)
            server.starttls()
            server.login(cfg['username'], cfg['password'])
            server.sendmail(cfg['sender_email'], to_email, msg.as_string())

        current_app.logger.info(f'SUCCESS: Email sent to {to_email}')
        return True, "Success"
    except smtplib.SMTPAuthenticationError:
        err = 'SMTP Authentication Failed. Please check your App Password.'
        current_app.logger.error(f'AUTH ERROR: {err}')
        return False, err
    except Exception as e:
        err = f'SMTP Error: {str(e)}'
        current_app.logger.error(f'GLOBAL ERROR: {err}')
        return False, err


# ─────────────────────────────────────────────
# WHATSAPP NOTIFICATION HELPER
# ─────────────────────────────────────────────
def send_whatsapp_message(to_phone, message):
    """
    Send a WhatsApp message via an external provider (Twilio, Interakt, etc.)
    Note: Requires provider API keys configured in environment variables.
    """
    import requests
    from flask import current_app
    
    # Clean phone number (add +91 if missing, etc.)
    phone = str(to_phone).replace(' ', '').replace('+', '')
    if len(phone) == 10:
        phone = f"91{phone}"
        
    # Pick up WhatsApp API token from environment
    wa_token = current_app.config.get('WHATSAPP_API_TOKEN', os.environ.get('WHATSAPP_API_TOKEN'))
    wa_url = current_app.config.get('WHATSAPP_API_URL', os.environ.get('WHATSAPP_API_URL'))
    
    if not wa_token or not wa_url:
        current_app.logger.warning(f"WhatsApp skipped for {phone}: WHATSAPP_API_TOKEN is missing in .env")
        return False
        
    try:
        # Example format for a generic WhatsApp Gateway or Meta Cloud API
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "text",
            "text": {"body": message}
        }
        headers = {
            "Authorization": f"Bearer {wa_token}",
            "Content-Type": "application/json"
        }
        resp = requests.post(wa_url, json=payload, headers=headers, timeout=5)
        if resp.status_code in (200, 201):
            return True
        current_app.logger.error(f"WhatsApp API Failed: {resp.text}")
        return False
    except Exception as e:
        current_app.logger.error(f"WhatsApp Error: {str(e)}")
        return False


# ── Shared email wrapper HTML ──
def _email_wrap(content_html):
    """Wrap content in the Luxoya branded email template."""
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8">
<style>
    body {{ font-family: 'DM Sans', Arial, sans-serif; background: #faf8f5; margin: 0; padding: 40px 20px; }}
    .email-wrapper {{ max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 16px;
                       box-shadow: 0 4px 24px rgba(0,0,0,0.08); overflow: hidden; }}
    .email-header {{ background: #1a1a1a; padding: 28px; text-align: center; }}
    .email-header h1 {{ color: #c9a96e; font-size: 26px; margin: 0; letter-spacing: 4px; font-weight: 700; }}
    .email-header p {{ color: rgba(255,255,255,.5); margin: 6px 0 0; font-size: 13px; }}
    .email-body {{ padding: 32px; }}
    .email-footer {{ background: #faf8f5; padding: 20px 32px; text-align: center; border-top: 1px solid #eee; }}
    .email-footer p {{ color: #999; font-size: 12px; margin: 4px 0; }}
    .email-footer a {{ color: #c9a96e; text-decoration: none; }}
    .gold {{ color: #c9a96e; }}
    .btn-gold {{ display: inline-block; background: #c9a96e; color: #fff; padding: 12px 32px;
                  border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 14px; }}
</style>
</head>
<body>
<div class="email-wrapper">
    <div class="email-header">
        <h1>LUXOYA</h1>
        <p>Pure Soy Luxury Candles</p>
    </div>
    <div class="email-body">
        {content_html}
    </div>
    <div class="email-footer">
        <p>Thank you for choosing <strong>Luxoya Candles</strong></p>
        <p>Questions? <a href="mailto:support@luxoyacandles.com">support@luxoyacandles.com</a> &bull; <a href="https://luxoyacandles.com">luxoyacandles.com</a></p>
        <p>&copy; {datetime.utcnow().year} Luxoya Candles. All rights reserved.</p>
    </div>
</div>
</body>
</html>"""


# ─────────────────────────────────────────────
# ORDER CANCELLATION EMAIL
# ─────────────────────────────────────────────
def send_cancellation_email(to_email, order_number, reason, cancelled_by='customer'):
    """Send order cancellation notification from noreply@luxoyacandles.com."""
    subject = f'Order {order_number} has been cancelled'
    by_text = ' by our team' if cancelled_by == 'admin' else ''

    content = f"""
    <div style="text-align: center; margin-bottom: 20px;">
        <div style="display: inline-block; width: 60px; height: 60px; background: #fee2e2; border-radius: 50%;
                    line-height: 60px; font-size: 28px;">&#10060;</div>
    </div>
    <h2 style="color: #1a1a1a; text-align: center; margin: 0 0 16px;">Order Cancelled</h2>
    <p style="color: #333; text-align: center;">
        Your order <strong style="color: #c9a96e;">{order_number}</strong> has been cancelled{by_text}.
    </p>
    <div style="background: #faf8f5; border-radius: 12px; padding: 16px; margin: 20px 0;">
        <p style="color: #666; margin: 0;"><strong>Reason:</strong> {reason}</p>
    </div>
    <p style="color: #666; font-size: 14px; text-align: center;">
        If payment was already processed, a refund will be initiated within <strong>5-7 business days</strong>.
    </p>
    """
    plain = f'Your Luxoya order {order_number} has been cancelled{by_text}. Reason: {reason}. Refund (if applicable) within 5-7 business days.'
    return _send_email(to_email, subject, _email_wrap(content), plain)


# ─────────────────────────────────────────────
# OTP VERIFICATION EMAIL
# ─────────────────────────────────────────────
def send_otp_email(to_email, otp_code):
    """Send an authentication OTP email."""
    subject = f'Your Luxoya Verification Code: {otp_code}'
    
    content = f"""
    <div style="text-align: center; margin-bottom: 24px;">
        <div style="display: inline-block; width: 60px; height: 60px; background: #faf3e0; border-radius: 50%;
                    line-height: 60px; font-size: 28px; color: #c9a96e;">&#128274;</div>
    </div>
    <h2 style="color: #1a1a1a; text-align: center; margin: 0 0 16px; font-weight: 700;">Verification Code</h2>
    <p style="color: #666; text-align: center; font-size: 16px; line-height: 1.6;">
        Use the following code to securely sign in to your Luxoya account.
    </p>
    <div style="text-align: center; margin: 32px 0;">
        <div style="display: inline-block; background: #1a1a1a; color: #c9a96e; padding: 16px 40px;
                    border-radius: 12px; font-size: 32px; font-weight: 700; letter-spacing: 8px;
                    box-shadow: 0 8px 16px rgba(0,0,0,0.1);">
            {otp_code}
        </div>
    </div>
    <p style="color: #999; text-align: center; font-size: 13px;">
        This code will expire in 10 minutes. <br>
        If you did not request this code, please ignore this email.
    </p>
    """
    plain = f'Your Luxoya verification code is: {otp_code}. Valid for 10 minutes.'
    return _send_email(to_email, subject, _email_wrap(content), plain, is_auth=True)


# ─────────────────────────────────────────────
# INVOICE / ORDER CONFIRMATION EMAIL
# ─────────────────────────────────────────────
def send_invoice_email(to_email, order):
    """Send a professional invoice email from noreply@luxoyacandles.com after payment confirmation."""
    from models import SiteSettings
    gst_number = SiteSettings.get('gst_number', '')
    instagram_handle = SiteSettings.get('instagram_handle', '')

    subject = f'Luxoya Candles - Invoice for Order #{order.order_number}'

    # Build items table rows
    items_html = ''
    for item in order.items:
        product_name = item.product.name if item.product else (item.product_name_snapshot or 'Product')
        items_html += f"""
        <tr>
            <td style="padding: 12px 16px; border-bottom: 1px solid #eee; color: #333;">{product_name}</td>
            <td style="padding: 12px 16px; border-bottom: 1px solid #eee; color: #333; text-align: center;">{item.quantity}</td>
            <td style="padding: 12px 16px; border-bottom: 1px solid #eee; color: #333; text-align: right;">&#8377;{item.price:,.2f}</td>
            <td style="padding: 12px 16px; border-bottom: 1px solid #eee; color: #333; text-align: right;">&#8377;{(item.quantity * item.price):,.2f}</td>
        </tr>"""

    payment_id = ''
    payment_method = ''
    if order.payment:
        payment_id = order.payment.razorpay_payment_id or ''
        payment_method = (order.payment.method or 'online').upper()

    order_date = order.created_at.strftime('%B %d, %Y') if order.created_at else datetime.utcnow().strftime('%B %d, %Y')

    content = f"""
    <div style="text-align: center; margin-bottom: 20px;">
        <div style="display: inline-block; width: 60px; height: 60px; background: #e8f5e9; border-radius: 50%;
                    line-height: 60px; font-size: 28px;">&#10004;</div>
    </div>
    <h2 style="color: #1a1a1a; text-align: center; margin: 0 0 8px;">Order Confirmed!</h2>
    <p style="color: #666; text-align: center; margin: 0 0 24px;">Thank you for your order. Here's your invoice:</p>

    <table style="width: 100%; margin-bottom: 20px;">
        <tr>
            <td style="padding: 4px 0;">
                <span style="color: #999; font-size: 11px; text-transform: uppercase; letter-spacing: 1px;">Order Number</span><br>
                <span style="color: #1a1a1a; font-weight: 600;">{order.order_number}</span>
            </td>
            <td style="padding: 4px 0;">
                <span style="color: #999; font-size: 11px; text-transform: uppercase; letter-spacing: 1px;">Date</span><br>
                <span style="color: #1a1a1a; font-weight: 600;">{order_date}</span>
            </td>
            <td style="padding: 4px 0;">
                <span style="color: #999; font-size: 11px; text-transform: uppercase; letter-spacing: 1px;">Payment</span><br>
                <span style="display: inline-block; background: #e8f5e9; color: #2e7d32; padding: 2px 10px;
                       border-radius: 20px; font-size: 12px; font-weight: 600;">PAID</span>
            </td>
        </tr>
    </table>

    {f'<p style="color: #666; font-size: 13px;">Payment ID: <strong>{payment_id}</strong> &bull; Method: <strong>{payment_method}</strong></p>' if payment_id else ''}

    <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
        <thead>
            <tr>
                <th style="background: #faf8f5; padding: 10px 16px; text-align: left; color: #999; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; border-bottom: 2px solid #c9a96e;">Product</th>
                <th style="background: #faf8f5; padding: 10px 16px; text-align: center; color: #999; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; border-bottom: 2px solid #c9a96e;">Qty</th>
                <th style="background: #faf8f5; padding: 10px 16px; text-align: right; color: #999; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; border-bottom: 2px solid #c9a96e;">Price</th>
                <th style="background: #faf8f5; padding: 10px 16px; text-align: right; color: #999; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; border-bottom: 2px solid #c9a96e;">Total</th>
            </tr>
        </thead>
        <tbody>{items_html}</tbody>
    </table>

    <div style="border-top: 2px solid #eee; padding-top: 12px; margin-top: 8px;">
        <div style="display: flex; justify-content: space-between; padding: 4px 16px; color: #666; font-size: 14px;">
            <span>Subtotal</span><span>&#8377;{order.subtotal:,.2f}</span>
        </div>
        {f'<div style="display: flex; justify-content: space-between; padding: 4px 16px; color: #2e7d32; font-size: 14px;"><span>Discount</span><span>-&#8377;{order.discount_amount:,.2f}</span></div>' if order.discount_amount else ''}
        <div style="display: flex; justify-content: space-between; padding: 4px 16px; color: #666; font-size: 14px;">
            <span>Shipping</span><span>{'FREE' if not order.shipping_cost else f'&#8377;{order.shipping_cost:,.2f}'}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 12px 16px; color: #1a1a1a; font-size: 18px; font-weight: 700; border-top: 2px solid #c9a96e; margin-top: 8px;">
            <span>Total Paid</span><span style="color: #c9a96e;">&#8377;{order.total_amount:,.2f}</span>
        </div>
    </div>

    <div style="background: #faf8f5; border-radius: 12px; padding: 16px; margin: 20px 0;">
        <h3 style="color: #1a1a1a; margin: 0 0 8px; font-size: 14px;">Shipping To</h3>
        <p style="color: #666; margin: 0; line-height: 1.6; font-size: 13px;">
            <strong>{order.shipping_name}</strong><br>
            {order.shipping_address}<br>
            {order.shipping_city}, {order.shipping_state} - {order.shipping_pincode}<br>
            Phone: {order.shipping_phone}
        </p>
    </div>

    {f'<p style="color:#888; font-size:12px; text-align:center; margin:16px 0 4px;">GSTIN: <strong style="color:#666;">{gst_number}</strong></p>' if gst_number else ''}
    {f'<p style="color:#c9a96e; font-size:13px; text-align:center; margin:4px 0 16px;">Follow us on Instagram: <strong>{instagram_handle}</strong></p>' if instagram_handle else ''}
    """

    # Plain text fallback
    plain = f"""LUXOYA CANDLES - ORDER INVOICE
================================
Order: {order.order_number}
Date: {order_date}
Status: PAID

Items:
"""
    for item in order.items:
        pn = item.product.name if item.product else 'Product'
        plain += f"  - {pn} x{item.quantity} @ Rs.{item.price:,.2f} = Rs.{(item.quantity * item.price):,.2f}\n"
    plain += f"""
Subtotal: Rs.{order.subtotal:,.2f}
{f'Discount: -Rs.{order.discount_amount:,.2f}' if order.discount_amount else ''}
Shipping: {'FREE' if not order.shipping_cost else f'Rs.{order.shipping_cost:,.2f}'}
Total: Rs.{order.total_amount:,.2f}

Shipping To: {order.shipping_name}, {order.shipping_address}, {order.shipping_city}, {order.shipping_state} - {order.shipping_pincode}
{f'Payment ID: {payment_id}' if payment_id else ''}

Thank you for shopping with Luxoya Candles!
Thank you for shopping with Luxoya Candles!
"""
    # Email Dispatch
    email_success, err = _send_email(to_email, subject, _email_wrap(content), plain)
    
    # WhatsApp Dispatch for Invoice
    if order.shipping_phone:
        wa_msg = f"luxoya candles (*order confirmed!*)\n\nThank you for shopping with us!\nOrder: #{order.order_number}\nTotal Paid: Rs.{order.total_amount:,.2f}\n\nWe will notify you as soon as it ships!"
        send_whatsapp_message(order.shipping_phone, wa_msg)
        
    return email_success, err


# ─────────────────────────────────────────────
# ORDER STATUS UPDATE EMAIL
# ─────────────────────────────────────────────
def send_order_status_email(to_email, order, new_status):
    """Send order status update email (shipped, delivered, etc.) from noreply@luxoyacandles.com."""
    status_info = {
        'confirmed': ('Order Confirmed', '&#10004;', '#e8f5e9', 'Your order has been confirmed and is being prepared.'),
        'processing': ('Order Processing', '&#9881;', '#fff3e0', 'Your order is being carefully prepared and packed.'),
        'shipped': ('Order Shipped', '&#128666;', '#e3f2fd', 'Your order is on its way! You will receive it soon.'),
        'delivered': ('Order Delivered', '&#127881;', '#e8f5e9', 'Your order has been delivered. Enjoy your candles!'),
    }
    info = status_info.get(new_status, ('Order Update', '&#128230;', '#f5f5f5', f'Your order status has been updated to: {new_status}'))
    title, icon, bg, msg = info

    subject = f'Luxoya Candles - {title} (#{order.order_number})'

    content = f"""
    <div style="text-align: center; margin-bottom: 20px;">
        <div style="display: inline-block; width: 60px; height: 60px; background: {bg}; border-radius: 50%;
                    line-height: 60px; font-size: 28px;">{icon}</div>
    </div>
    <h2 style="color: #1a1a1a; text-align: center; margin: 0 0 8px;">{title}</h2>
    <p style="color: #666; text-align: center; margin: 0 0 24px;">{msg}</p>

    <div style="background: #faf8f5; border-radius: 12px; padding: 16px; margin: 20px 0;">
        <table style="width: 100%;">
            <tr>
                <td style="padding: 4px 0;">
                    <span style="color: #999; font-size: 11px; text-transform: uppercase;">Order</span><br>
                    <span style="color: #1a1a1a; font-weight: 600;">{order.order_number}</span>
                </td>
                <td style="padding: 4px 0; text-align: right;">
                    <span style="color: #999; font-size: 11px; text-transform: uppercase;">Total</span><br>
                    <span style="color: #c9a96e; font-weight: 700;">&#8377;{order.total_amount:,.2f}</span>
                </td>
            </tr>
        </table>
    </div>

    <div style="text-align: center; margin-top: 24px;">
        <a href="https://luxoyacandles.com/orders/{order.id}" style="display: inline-block; background: #c9a96e; color: #fff;
           padding: 12px 32px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 14px;">
           Track Your Order
        </a>
    </div>
    """
    plain = f'Luxoya Candles - {title}\n\nOrder: {order.order_number}\nTotal: Rs.{order.total_amount:,.2f}\n\n{msg}'
    
    # Standard Email Dispatch
    email_success, err = _send_email(to_email, subject, _email_wrap(content), plain)
    
    # Automatic WhatsApp Dispatch
    if order.shipping_phone:
        whatsapp_text = f"luxoya candles\n\n*order update: {new_status.upper()}*\nOrder #{order.order_number}\nTotal: Rs.{order.total_amount:,.2f}\n\n{msg}\n\nTrack your order at luxoyacandles.com/orders/{order.id}"
        send_whatsapp_message(order.shipping_phone, whatsapp_text)
        
    return email_success, err


# ─────────────────────────────────────────────
# GENERATE DOWNLOADABLE INVOICE HTML
# ─────────────────────────────────────────────
def _generate_invoice_html(order):
    """Generate a standalone HTML invoice page for printing/downloading."""
    # Fetch GST and Instagram settings from DB
    from models import SiteSettings
    gst_number = SiteSettings.get('gst_number', '')
    instagram_handle = SiteSettings.get('instagram_handle', '')

    items_html = ''
    for item in order.items:
        product_name = item.product.name if item.product else (item.product_name_snapshot or 'Product')
        items_html += f"""
        <tr>
            <td style="padding:10px 12px; border-bottom:1px solid #eee;">{product_name}</td>
            <td style="padding:10px 12px; border-bottom:1px solid #eee; text-align:center;">{item.quantity}</td>
            <td style="padding:10px 12px; border-bottom:1px solid #eee; text-align:right;">&#8377;{item.price:,.2f}</td>
            <td style="padding:10px 12px; border-bottom:1px solid #eee; text-align:right;">&#8377;{(item.quantity * item.price):,.2f}</td>
        </tr>"""

    payment_id = ''
    payment_method = ''
    if order.payment:
        payment_id = order.payment.razorpay_payment_id or ''
        payment_method = (order.payment.method or 'online').upper()

    order_date = order.created_at.strftime('%B %d, %Y') if order.created_at else datetime.utcnow().strftime('%B %d, %Y')

    # GST info in header
    gst_html = f'<p style="color:rgba(255,255,255,.6); margin:2px 0 0; font-size:12px;">GSTIN: {gst_number}</p>' if gst_number else ''

    # Instagram QR + follow section
    ig_section = ''
    if instagram_handle:
        ig_username = instagram_handle.lstrip('@')
        ig_url = f'https://www.instagram.com/{ig_username}/'
        # Use a QR code API to generate the QR dynamically
        qr_url = f'https://api.qrserver.com/v1/create-qr-code/?size=120x120&data={ig_url}&bgcolor=faf8f5&color=1a1a1a&margin=4'
        ig_section = f"""
        <div style="margin-top:20px; padding:20px; background:#faf8f5; border-radius:10px; border:1px solid #eee; text-align:center;">
            <p style="color:#c9a96e; font-size:13px; text-transform:uppercase; letter-spacing:2px; margin:0 0 10px; font-weight:600;">Follow Us on Instagram</p>
            <img src="{qr_url}" alt="Instagram QR" style="width:120px; height:120px; border-radius:8px; border:2px solid #c9a96e; padding:4px; background:#fff;">
            <p style="margin:10px 0 0; font-size:14px; color:#333;">
                <strong style="color:#c9a96e;">{instagram_handle}</strong>
            </p>
            <p style="margin:4px 0 0; font-size:12px; color:#999;">Scan to follow us for updates &amp; new collections</p>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Invoice - {order.order_number}</title>
<style>
    @media print {{ body {{ margin: 0; }} .no-print {{ display: none !important; }} }}
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; color: #333; }}
    .invoice {{ max-width: 800px; margin: 0 auto; background: #fff; border-radius: 12px; box-shadow: 0 2px 20px rgba(0,0,0,0.08); overflow: hidden; }}
    .inv-header {{ background: #1a1a1a; color: #fff; padding: 32px; display: flex; justify-content: space-between; align-items: center; }}
    .inv-header h1 {{ color: #c9a96e; font-size: 28px; margin: 0; letter-spacing: 4px; }}
    .inv-header .inv-title {{ text-align: right; }}
    .inv-header .inv-title h2 {{ margin: 0; font-weight: 300; font-size: 24px; }}
    .inv-body {{ padding: 32px; }}
    .inv-meta {{ display: flex; justify-content: space-between; margin-bottom: 24px; }}
    .inv-meta-col {{ flex: 1; }}
    .inv-meta-col h4 {{ color: #c9a96e; font-size: 12px; text-transform: uppercase; letter-spacing: 2px; margin: 0 0 8px; }}
    .inv-meta-col p {{ margin: 2px 0; font-size: 14px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
    th {{ background: #faf8f5; padding: 10px 12px; text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #999; border-bottom: 2px solid #c9a96e; }}
    .totals {{ text-align: right; margin-top: 16px; }}
    .totals .row {{ display: flex; justify-content: flex-end; gap: 40px; padding: 4px 12px; font-size: 14px; }}
    .totals .total-row {{ font-size: 20px; font-weight: 700; color: #c9a96e; border-top: 2px solid #c9a96e; padding-top: 12px; margin-top: 8px; }}
    .inv-footer {{ background: #faf8f5; padding: 20px 32px; text-align: center; border-top: 1px solid #eee; }}
    .inv-footer p {{ color: #999; font-size: 12px; margin: 4px 0; }}
    .paid-badge {{ display: inline-block; background: #e8f5e9; color: #2e7d32; padding: 4px 16px; border-radius: 20px; font-size: 13px; font-weight: 600; }}
    .print-btn {{ position: fixed; top: 20px; right: 20px; background: #c9a96e; color: #fff; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; box-shadow: 0 2px 8px rgba(0,0,0,0.2); }}
    .print-btn:hover {{ background: #b8963e; }}
</style>
</head>
<body>
<button class="print-btn no-print" onclick="window.print()">&#128424; Print Invoice</button>
<div class="invoice">
    <div class="inv-header">
        <div style="display: flex; align-items: center; gap: 20px;">
            <img src="/static/images/logo-dark-theme.png" height="50" alt="LUXOYA" style="filter: brightness(0) invert(1);">
            <div>
                <h1 style="margin:0; line-height:1; font-size:24px;">LUXOYA</h1>
                <p style="color:rgba(255,255,255,.5); margin:4px 0 0; font-size:12px;">Pure Soy Luxury Candles</p>
            </div>
            {gst_html}
        </div>
        <div class="inv-title"><h2>INVOICE</h2><p style="color:rgba(255,255,255,.6); margin:4px 0 0;">#{order.order_number}</p></div>
    </div>

    <div class="inv-body">
        <div class="inv-meta">
            <div class="inv-meta-col">
                <h4>Billed To</h4>
                <p><strong>{order.shipping_name}</strong></p>
                <p>{order.shipping_address}</p>
                <p>{order.shipping_city}, {order.shipping_state} - {order.shipping_pincode}</p>
                <p>Phone: {order.shipping_phone}</p>
            </div>
            <div class="inv-meta-col" style="text-align:right;">
                <h4>Invoice Details</h4>
                <p><strong>Date:</strong> {order_date}</p>
                <p><strong>Status:</strong> <span class="paid-badge" style="background: {'#e8f5e9' if order.payment_status == 'paid' else '#fff3e0'}; color: {'#2e7d32' if order.payment_status == 'paid' else '#ef6c00'};">{(order.payment_status or 'PENDING').upper()}</span></p>
                {f'<p><strong>Payment ID:</strong> {payment_id}</p>' if payment_id else ''}
                {f'<p><strong>Method:</strong> {payment_method}</p>' if payment_method else ''}
            </div>
        </div>

        <table>
            <thead>
                <tr>
                    <th>Product</th>
                    <th style="text-align:center">Qty</th>
                    <th style="text-align:right">Unit Price</th>
                    <th style="text-align:right">Total</th>
                </tr>
            </thead>
            <tbody>{items_html}</tbody>
        </table>

        <div class="totals">
            <div class="row"><span>Subtotal</span><span>&#8377;{order.subtotal:,.2f}</span></div>
            {f'<div class="row" style="color:#2e7d32"><span>Discount</span><span>-&#8377;{order.discount_amount:,.2f}</span></div>' if order.discount_amount else ''}
            <div class="row"><span>Shipping</span><span>{'FREE' if not order.shipping_cost else f'&#8377;{order.shipping_cost:,.2f}'}</span></div>
            <div class="row total-row"><span>Total Paid</span><span>&#8377;{order.total_amount:,.2f}</span></div>
        </div>

        {ig_section}
    </div>
    <div class="inv-footer">
        <p>Thank you for shopping with <strong>Luxoya Candles</strong></p>
        {f'<p style="font-weight:600; color:#666;">GSTIN: {gst_number}</p>' if gst_number else ''}
        <p>support@luxoyacandles.com &bull; luxoyacandles.com</p>
        <p>&copy; {datetime.utcnow().year} Luxoya Candles. All rights reserved.</p>
    </div>
</div>
</body>
</html>"""

# ─────────────────────────────────────────────
# AI ASSISTANT UTILITY (Switching to Google Gemini)
# ─────────────────────────────────────────────
def ask_ai(prompt, system_context="You are the Luxoya AI Admin Assistant. You help manage a luxury soy candle store."):
    """Interact with Google Gemini and return a response."""
    from flask import current_app
    
    try:
        from google import genai
    except ImportError:
        current_app.logger.error("google-genai package is missing. Run 'pip install google-genai'")
        return "AI system is misconfigured: google-genai package not found."

    api_key = current_app.config.get('GEMINI_API_KEY') or os.environ.get('GEMINI_API_KEY')
    
    if not api_key or 'AIzaSy' not in api_key:
        return "AI (Gemini) is not configured. Please add your GEMINI_API_KEY to the environment variables."

    max_retries = 3
    import time
    
    for attempt in range(max_retries):
        try:
            client = genai.Client(api_key=api_key)
            
            # Combine system context and prompt
            full_prompt = f"{system_context}\n\nUser Question: {prompt}"
            
            # Use a stable Gemini model
            response = client.models.generate_content(
                model="gemini-1.5-flash", # Switched to 1.5-flash for maximum production stability
                contents=full_prompt
            )
            
            if response and response.text:
                return response.text
            return "AI returned an empty response."
            
        except Exception as e:
            err_msg = str(e)
            # If it's a 503 (service unavailable) or overload, retry after a short delay
            if "503" in err_msg or "overloaded" in err_msg.lower() or "limit" in err_msg.lower():
                if attempt < max_retries - 1:
                    time.sleep(1 + attempt)  # Incremental backoff
                    continue
            
            current_app.logger.error(f"Gemini AI Error (Attempt {attempt+1}): {err_msg}")
            if attempt == max_retries - 1:
                return f"Gemini Assistant is temporarily unavailable. (Error: {err_msg})"
    
    return "Gemini Assistant reset. Please try your request again."


# ─────────────────────────────────────────────
# SHIPROCKET LOGISTICS INTEGRATION
# ─────────────────────────────────────────────
import requests

class ShiprocketHelper:
    """Helper for Shiprocket API integration (Logistics & AWB generation)."""
    
    BASE_URL = "https://apiv2.shiprocket.in/v1/external"
    
    @staticmethod
    def get_token():
        """Authenticate with Shiprocket and return temporary Bearer token."""
        try:
            from flask import current_app
            from models import SiteSettings
            import json, time
            
            # Check Cache First
            cached_data = SiteSettings.get('shiprocket_token_cache')
            if cached_data:
                try:
                    cache_json = json.loads(cached_data)
                    # Use a 5-day expiration (Shiprocket lasts 9-10 days usually)
                    if time.time() - cache_json.get('timestamp', 0) < 432000: # 5 days
                        return cache_json.get('token')
                except: pass
                
            email = current_app.config.get('SHIPROCKET_EMAIL')
            password = current_app.config.get('SHIPROCKET_PASSWORD')
            
            if not email or not password:
                return None
            
            resp = requests.post(
                f"{ShiprocketHelper.BASE_URL}/auth/login",
                json={"email": email, "password": password},
                timeout=10
            )
            if resp.status_code != 200:
                current_app.logger.error(f"Shiprocket Auth Failed ({resp.status_code}): {resp.text}")
                return None
            data = resp.json()
            token = data.get('token')
            if token:
                SiteSettings.set('shiprocket_token_cache', json.dumps({'token': token, 'timestamp': time.time()}))
            return token
        except Exception as e:
            from flask import current_app
            current_app.logger.error(f"Shiprocket Auth Failed: {e}")
            return None

    @staticmethod
    def create_order(order):
        """Push an order to Shiprocket and return the response."""
        token = ShiprocketHelper.get_token()
        if not token:
            return {"error": "Authentication failed"}

        from datetime import datetime
        order_date = order.created_at.strftime('%Y-%m-%d %H:%M') if order.created_at else datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        
        # Prepare order items & calculate total weight
        items = []
        total_weight = 0
        for item in order.items:
            # Try to parse weight from product (e.g., "200g" -> 0.2)
            item_weight = 0.5 # Default 500g
            if item.product and item.product.weight:
                try:
                    weight_str = item.product.weight.lower()
                    if 'kg' in weight_str:
                        item_weight = float(weight_str.replace('kg', '').strip())
                    elif 'g' in weight_str:
                        item_weight = float(weight_str.replace('g', '').strip()) / 1000
                except: pass
            total_weight += (item_weight * item.quantity)

            items.append({
                "name": item.product.name if item.product else (item.product_name_snapshot or "Candle"),
                "sku": item.product.slug if item.product else f"candle-{item.id[:8]}",
                "units": item.quantity,
                "selling_price": item.price,
                "discount": 0,
                "tax": 0,
                "hsn": 3406
            })

        payload = {
            "order_id": order.order_number,
            "order_date": order_date,
            "pickup_location": "warehouse", 
            "billing_customer_name": order.shipping_name,
            "billing_last_name": "",
            "billing_address": order.shipping_address,
            "billing_city": order.shipping_city,
            "billing_pincode": order.shipping_pincode,
            "billing_state": order.shipping_state,
            "billing_country": "India",
            "billing_email": order.user.email if (order.user and order.user.email) else (order.shipping_email or "customer@luxoya.com"),
            "billing_phone": order.shipping_phone,
            "shipping_is_billing": True,
            "order_items": items,
            "payment_method": "Prepaid" if order.payment_status == 'paid' else "COD",
            "sub_total": order.subtotal,
            "shipping_charges": order.shipping_cost,
            "total_discount": order.discount_amount,
            "length": 12, # cm
            "breadth": 12,
            "height": 12,
            "weight": max(0.5, total_weight)
        }


        try:
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            resp = requests.post(f"{ShiprocketHelper.BASE_URL}/orders/create/adhoc", json=payload, headers=headers, timeout=15)
            if resp.status_code not in (200, 201):
                from flask import current_app
                current_app.logger.error(f"Shiprocket Error: {resp.text}")
                return {"error": f"Shiprocket API Error ({resp.status_code})", "details": resp.json() if resp.status_code == 422 else resp.text}
            return resp.json()
        except Exception as e:
            from flask import current_app
            current_app.logger.error(f"Shiprocket Exception: {e}")
            return {"error": str(e)}


    @staticmethod
    def get_tracking(awb_code):
        """Fetch real-time tracking from Shiprocket."""
        token = ShiprocketHelper.get_token()
        if not token: return None
        
        try:
            headers = {"Authorization": f"Bearer {token}"}
            resp = requests.get(f"{ShiprocketHelper.BASE_URL}/courier/track/awb/{awb_code}", headers=headers, timeout=10)
            return resp.json()
        except Exception:
            return None
