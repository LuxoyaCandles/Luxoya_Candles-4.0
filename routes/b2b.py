from flask import Blueprint, request, jsonify, render_template
from models import B2BRequest, db
from datetime import datetime

b2b_bp = Blueprint('b2b', __name__)


# ─────────────────────────────────────────────
# PAGE: B2B / Corporate Orders
# ─────────────────────────────────────────────
@b2b_bp.route('/corporate')
def corporate_page():
    return render_template('b2b.html')


# ─────────────────────────────────────────────
# API: Submit B2B Request
# ─────────────────────────────────────────────
@b2b_bp.route('/api/b2b/request', methods=['POST'])
def submit_b2b_request():
    data = request.get_json()
    
    required_fields = ['company_name', 'contact_person', 'email', 'phone', 'quantity']
    for field in required_fields:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    
    delivery_date = None
    if data.get('delivery_date'):
        try:
            delivery_date = datetime.strptime(data['delivery_date'], '%Y-%m-%d').date()
        except ValueError:
            pass
    
    b2b_request = B2BRequest(
        company_name=data['company_name'].strip(),
        contact_person=data['contact_person'].strip(),
        email=data['email'].strip().lower(),
        phone=data['phone'].strip(),
        quantity=int(data['quantity']),
        product_type=data.get('product_type', ''),
        requirements=data.get('requirements', ''),
        custom_scent=data.get('custom_scent', ''),
        budget_range=data.get('budget_range', ''),
        delivery_date=delivery_date
    )
    
    db.session.add(b2b_request)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to submit request. Please try again.'}), 500
    
    return jsonify({
        'message': 'Your quotation request has been submitted successfully. Our team will contact you within 24 hours.',
        'request_id': b2b_request.id
    }), 201


# ─────────────────────────────────────────────
# API: Track B2B Request
# ─────────────────────────────────────────────
@b2b_bp.route('/api/b2b/request/<request_id>', methods=['GET'])
def track_b2b_request(request_id):
    b2b = db.session.get(B2BRequest, request_id)
    if not b2b:
        return jsonify({'error': 'Request not found'}), 404
    return jsonify({'request': b2b.to_dict()})
