from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from routes.auth import get_current_user
import json

chat_bp = Blueprint('chat', __name__)

# Luxoya FAQ knowledge base
LUXOYA_FAQ = {
    "shipping": {
        "keywords": ["shipping", "delivery", "ship", "deliver", "dispatch", "courier", "when will", "how long", "arrive"],
        "response": "**Shipping Policy:**\n\n- Orders are dispatched within 2-3 business days\n- Standard delivery: 5-7 business days\n- Express delivery: 2-3 business days (Rs.149 extra)\n- Free shipping on orders above Rs.999\n- We ship across India via trusted courier partners\n- Tracking details are shared via email & SMS"
    },
    "returns": {
        "keywords": ["return", "refund", "exchange", "cancel", "damage", "broken", "wrong", "defective"],
        "response": "**Return & Refund Policy:**\n\n- Returns accepted within 7 days of delivery\n- Product must be unused and in original packaging\n- Customized candles cannot be returned\n- Damaged products will be replaced immediately\n- Refunds are processed within 5-7 business days\n- For issues, email us at support@luxoyacandles.com"
    },
    "customization": {
        "keywords": ["custom", "customize", "personalize", "engrave", "label", "jar", "colour", "fragrance", "wick", "scent", "design", "create", "make"],
        "response": "**Customization Guide:**\n\n- Choose from 4 jar types: Classic Glass, Matte Ceramic, Gold Tin, Marble Vessel\n- Select your colour: Ivory White, Blush Pink, Sage Green, Midnight Black\n- Pick your fragrance: Vanilla Oud, Rose & Sandalwood, Fresh Linen, Amber Noir\n- Wick options: Single, Double, or Triple\n- Add custom label text for personalization\n- Visit our Customize page to design your perfect candle!"
    },
    "payment": {
        "keywords": ["payment", "pay", "upi", "card", "net banking", "emi", "wallet", "razorpay", "gpay", "paytm", "phonepe"],
        "response": "**Payment Methods:**\n\n- UPI (Google Pay, PhonePe, Paytm)\n- Credit & Debit Cards (Visa, Mastercard, RuPay)\n- Net Banking (All major banks)\n- EMI options available\n- Digital Wallets\n- 100% secure payments via Razorpay"
    },
    "corporate": {
        "keywords": ["corporate", "bulk", "b2b", "business", "wholesale", "company", "office", "gift", "event", "wedding"],
        "response": "**Corporate & B2B Orders:**\n\n- Minimum order: 50 units\n- Custom branding & packaging available\n- Dedicated account manager\n- Special corporate pricing\n- Custom scent creation for your brand\n- Visit our Corporate page to request a quotation\n- Email: support@luxoyacandles.com"
    },
    "products": {
        "keywords": ["product", "candle", "candel", "candles", "candels", "collection", "range", "type", "category", "best", "recommend", "suggestion", "popular", "top", "favourite", "favorite", "which", "find", "show", "buy", "shop", "list", "available"],
        "response": "**Our Collections:**\n\n- **Luxury Jar Candles** - Premium soy candles in elegant vessels\n- **Designer Mould Candles** - Artistic sculptural candles\n- **Gift Hampers** - Curated luxury candle gift sets\n- **Festive Editions** - Limited seasonal collections\n- **Wedding & Event Favors** - Perfect wedding return gifts\n\nAll candles are handcrafted with 100% pure soy wax. Browse our Collections page to explore!"
    },
    "materials": {
        "keywords": ["soy", "wax", "ingredients", "material", "eco", "natural", "vegan", "organic", "safe", "chemical"],
        "response": "**Our Materials:**\n\n- 100% Pure Soy Wax - eco-friendly & clean burning\n- Premium fragrance oils - phthalate-free\n- Cotton wicks - lead-free\n- Hand-poured with care\n- Cruelty-free & vegan\n- Sustainable packaging"
    },
    "order_tracking": {
        "keywords": ["track", "order status", "where is my order", "order number", "tracking", "status", "my order"],
        "response": "**Track Your Order:**\n\n- Log in to your account and visit 'My Orders'\n- Enter your order number to see real-time status\n- You'll receive tracking updates via email & SMS\n- Status stages: Confirmed > Processing > Shipped > Delivered\n- Need help? Contact support@luxoyacandles.com"
    },
    "pricing": {
        "keywords": ["price", "cost", "expensive", "cheap", "affordable", "budget", "how much", "rate"],
        "response": "**Pricing:**\n\n- Mini Candles start from Rs.399\n- Signature Collection: Rs.899 - Rs.1499\n- Gift Hampers: Rs.1699 onwards\n- Custom Candles: Starting at Rs.499 (base price)\n- Free shipping on orders above Rs.999\n\nVisit our shop to see the full range with current offers!"
    },
    "greeting": {
        "keywords": ["hello", "hi", "hey", "good morning", "good evening", "help", "good afternoon", "hii", "helo", "greetings"],
        "response": "Welcome to Luxoya Candles! I'm your AI assistant.\n\nI can help you with:\n- Shipping & Delivery info\n- Returns & Refunds\n- Candle Customization\n- Payment options\n- Corporate orders\n- Product recommendations\n- Order tracking\n\nWhat would you like to know?"
    }
}


def get_faq_response(message):
    """Match user message to FAQ responses using fuzzy keyword matching."""
    message_lower = message.lower().strip()
    words = message_lower.split()
    
    best_match = None
    best_score = 0
    
    for topic, data in LUXOYA_FAQ.items():
        score = 0
        for keyword in data["keywords"]:
            # Exact substring match
            if keyword in message_lower:
                score += 2
                continue
            # Fuzzy: check if any word in the message is close to the keyword
            for word in words:
                if len(word) >= 3 and len(keyword) >= 3:
                    # Check if one contains the other (handles typos like 'candels' matching 'candle')
                    if word in keyword or keyword in word:
                        score += 1
                    # Check edit distance for short words
                    elif len(word) >= 4 and abs(len(word) - len(keyword)) <= 2:
                        common = sum(1 for a, b in zip(word, keyword) if a == b)
                        if common >= min(len(word), len(keyword)) * 0.6:
                            score += 1
        if score > best_score:
            best_score = score
            best_match = topic
    
    if best_match and best_score >= 1:
        return LUXOYA_FAQ[best_match]["response"]
    
    return None


def get_ai_response(message, conversation_history=None):
    """Get response from Gemini API via centralized utility, fallback to FAQ."""
    from utils import ask_ai
    
    # First check FAQ for quick matches
    faq_response = get_faq_response(message)
    if faq_response:
        return faq_response
    
    # System context for Gemini
    system_context = """You are the AI assistant for Luxoya Candles, a premium luxury soy candle brand from India.
    
Your role:
- Help customers with product info, order tracking, shipping, returns
- Recommend fragrances and products based on preferences
- Assist with customization options
- Handle corporate/B2B inquiries
- Be warm, helpful, and maintain a luxury brand tone

Brand Info:
- Founded: 2024
- Tagline: "Pure Soy Luxury Since 2024. Handcrafted candles for refined living."
- Products: Luxury Jar Candles, Designer Mould, Gift Hampers, Festive Editions, Wedding Favors
- Customization: Jar types (Classic Glass, Matte Ceramic, Gold Tin, Marble Vessel), Colors (Ivory White, Blush Pink, Sage Green, Midnight Black), Fragrances (Vanilla Oud, Rose & Sandalwood, Fresh Linen, Amber Noir), Wicks (Single, Double, Triple)
- Free shipping above ₹999
- Returns within 7 days (not for customized items)
- Payment: UPI, Cards, Net Banking, EMI, Wallets via Razorpay
- B2B: Min 50 units, custom branding available

Keep responses concise, friendly, and professional."""

    # Construct prompt with recent history
    history_str = ""
    if conversation_history:
        for msg in conversation_history[-6:]:
            role = "User" if msg.get("role") == "user" else "Assistant"
            history_str += f"{role}: {msg.get('content')}\n"
    
    full_prompt = f"Recent History:\n{history_str}\nNew Question: {message}"
    
    response = ask_ai(full_prompt, system_context)
    
    # Fallback to default if ask_ai fails or returns error msg
    if "unavailable" in response.lower() or "misconfigured" in response.lower():
        return "Thank you for reaching out! I'm currently unable to access my full knowledge base, but I can help with general info about our candles, shipping, and customization. You can also reach us at support@luxoyacandles.com"
        
    return response


# ─────────────────────────────────────────────
# API: Chat endpoint
# ─────────────────────────────────────────────
@chat_bp.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json()
    message = data.get('message', '').strip()
    history = data.get('history', [])
    
    if not message:
        return jsonify({'error': 'Message is required'}), 400
    
    response = get_ai_response(message, history)
    
    return jsonify({
        'response': response,
        'source': 'ai'
    })
