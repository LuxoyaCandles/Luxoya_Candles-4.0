import os, sys
from flask import Flask, request, jsonify
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app import app
from datetime import datetime
from models import FinanceRecord, db

with app.app_context():
    data = {
        'title': 'Inventory',
        'amount': '4319',
        'type': 'capital',
        'category': 'Raw Material',
        'date': '2026-04-18',
        'notes': '',
        'partner_id': ''
    }
    
    try:
        record = FinanceRecord(
            title=data.get('title'),
            amount=float(data.get('amount', 0)),
            record_type=data.get('type', 'expense'),
            category=data.get('category'),
            date=datetime.fromisoformat(data.get('date')) if data.get('date') and data.get('date') != 'null' else datetime.utcnow(),
            notes=data.get('notes'),
            partner_id=int(data.get('partner_id')) if data.get('partner_id') and data.get('partner_id') not in ['null', ''] else None,
            bill_url="test_url"
        )
        db.session.add(record)
        print("Success! record instantiated")
        db.session.rollback()
    except Exception as e:
        print(f"Error: {e}")
