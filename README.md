# 🕯️ Luxoya Candles 3.0 — Modern Premium E-Commerce Platform

> **Pure Soy Luxury Since 2024 — Handcrafted candles for refined living.**

A full-stack e-commerce platform for Luxoya Candles, built with Flask (Python) and deployed for production. Features a premium consumer storefront, an admin console, AI chatbot, Razorpay payments, candle customization, and B2B corporate ordering.

---

## 📋 Table of Contents

- [Tech Stack](#-tech-stack)
- [Architecture Overview](#-architecture-overview)
- [Project Structure](#-project-structure)
- [Features](#-features)
- [Database Models](#-database-models)
- [System Stability & Hardening Audit](#-system-stability--hardening-audit-april-2026)
- [API Endpoints](#-api-endpoints)
- [Getting Started](#-getting-started)
- [Environment Variables](#-environment-variables)
- [Deployment](#-deployment)
- [Premium Features & Integration](#-premium-features--integration)

---

## 🛠 Tech Stack

### Backend
| Technology | Purpose |
|---|---|
| **Python 3.11+** | Core language |
| **Flask 3.x** | Web framework |
| **Flask-SQLAlchemy 3.x** | ORM / database abstraction |
| **Flask-JWT-Extended** | JWT authentication (cookie + header) |
| **Flask-Bcrypt** | Password hashing |
| **Flask-Migrate (Alembic)** | Database migrations |
| **Flask-WTF (CSRFProtect)** | CSRF protection |
| **Flask-CORS** | Cross-origin requests |
| **SQLAlchemy 2.x** | SQL toolkit |
| **psycopg2-binary** | PostgreSQL adapter |
| **Razorpay SDK** | Payment gateway (India) |
| **Google Gemini AI** | AI assistant (Generative response) |
| **Google Auth / OAuth** | Google Sign-In |
| **Pillow** | Image compression (WebP) |
| **python-dotenv** | Environment variable loading |
| **Gunicorn** | Production WSGI server |
| **smtplib** | Email (invoices, order updates) |

### Frontend
| Technology | Purpose |
|---|---|
| **Jinja2 Templates** | Server-side rendering |
| **Vanilla CSS** | Single `style.css` (124KB) — custom design system |
| **Vanilla JavaScript** | `main.js`, `auth.js`, `cart.js`, `checkout.js` |
| **Bootstrap Icons** | Icon library |
| **Google Fonts** | Typography |
| **Razorpay Checkout.js** | Payment UI |
| **Google Identity Services** | Google Sign-In button |

### Database
| Technology | Purpose |
|---|---|
| **PostgreSQL (Neon)** | Production database |
| **SQLite** | Local development fallback |

### Deployment Targets
| Platform | Status |
|---|---|
| **Vercel** | Configured (`vercel.json`) — Primary Deployment |
| **Docker / Cloud Run** | Configured (`Dockerfile`) |


---

## 🏗 Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                       CLIENT (Browser)                       │
│  ┌─────────────────┐  ┌──────────────┐  ┌───────────────┐   │
│  │   Storefront    │  │  Admin Panel  │  │  Auth Pages   │   │
│  │   (index.html)  │  │  (/admin/*)   │  │ (login/reg)   │   │
│  └─────────────────┘  └──────────────┘  └───────────────┘   │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTP / REST API
┌───────────────────────────▼──────────────────────────────────┐
│                    FLASK APPLICATION (app.py)                 │
│  ┌───────────────────────────────────────────────────────┐   │
│  │  Blueprints:                                           │   │
│  │  ├── auth_bp     → /login, /register, /api/auth/*     │   │
│  │  ├── products_bp → /collections, /api/products/*      │   │
│  │  ├── cart_bp     → /cart, /api/cart/*                  │   │
│  │  ├── orders_bp   → /orders, /api/orders/*             │   │
│  │  ├── admin_bp    → /admin/*, /admin/api/*             │   │
│  │  ├── b2b_bp      → /corporate, /api/b2b/*            │   │
│  │  └── chat_bp     → /api/chat                          │   │
│  └───────────────────────────────────────────────────────┘   │
│  ┌───────────────┐ ┌────────────┐ ┌────────────────────┐    │
│  │ JWT Auth      │ │ CSRF       │ │ Image Compression  │    │
│  │ (cookie-based)│ │ Protection │ │ (Pillow → WebP)    │    │
│  └───────────────┘ └────────────┘ └────────────────────┘    │
└───────────────────────────┬──────────────────────────────────┘
                            │
    ┌───────────────┐  ┌────▼─────┐  ┌────────────────┐
    │   Razorpay    │  │ Neon     │  │ Google Gemini  │
    │   Payment     │  │ Postgres │  │ AI Assistant   │
    │   Gateway     │  │          │  │                │
    └───────────────┘  └──────────┘  └────────────────┘
```

### Request Flow
1. Browser requests a page → Flask renders Jinja2 template (SSR)
2. Client-side JS calls REST API endpoints (`/api/*`) for data
3. JWT tokens are stored in HTTP-only cookies
4. Images are stored as binary blobs in the database (ImageStore) and served via `/img/store/<id>` with aggressive caching

---

## 📂 Project Structure

```
Luxoya-3.0/
├── app.py                  # Flask app factory + route registration
├── config.py               # Environment-specific configuration
├── extensions.py           # Flask extension instances (db, jwt, bcrypt...)
├── models.py               # SQLAlchemy models (15 tables)
├── utils.py                # Core utilities & Google Gemini integration
├── seed_data.py            # Database seeder (admin user + sample products)
│
├── routes/
│   ├── __init__.py
│   ├── auth.py             # Authentication (register, login, Google OAuth, profile)
│   ├── products.py         # Product listing, detail, reviews, search
│   ├── cart.py             # Shopping cart CRUD
│   ├── orders.py           # Order creation, payment, tracking, returns, complaints
│   ├── admin.py            # Admin dashboard, CRUD products/orders/customers/coupons
│   ├── b2b.py              # B2B / corporate order requests
│   └── chat.py             # AI assistant (FAQ + Gemini fallback)
│
├── templates/
│   ├── base.html           # Main storefront layout (nav, footer, chatbot widget)
│   ├── index.html          # Homepage (hero slider, featured, categories)
│   ├── about.html          # About page
│   ├── contact.html        # Contact page
│   ├── reels.html          # Reels / video showcase
│   ├── b2b.html            # B2B / Corporate orders page
│   ├── cart.html            # Cart page
│   ├── checkout.html       # Checkout + Razorpay integration
│   ├── profile.html        # User profile management
│   ├── auth/               # Login, Register, OTP, Setup Password
│   ├── products/           # Product listing, detail, customization pages
│   ├── orders/             # Order history, detail, tracking, complaints, confirmation
│   ├── admin/              # Admin dashboard, products, orders, customers, etc. (14 templates)
│   └── errors/             # 404 and 500 pages
│
├── static/
│   ├── css/style.css       # Single stylesheet (124KB — full design system)
│   ├── js/
│   │   ├── main.js         # Global JS (theme toggle, chatbot, search, notifications)
│   │   ├── auth.js         # Authentication logic (Google Sign-In, form validation)
│   │   ├── cart.js         # Cart operations
│   │   └── checkout.js    # Checkout + Razorpay payment flow
│   ├── images/             # Static images (logo, philosophy section)
│   ├── img/                # Placeholder images
│   ├── uploads/            # Legacy file upload directory
│   └── favicon.svg         # Favicon
│
├── requirements.txt        # Python dependencies
├── runtime.txt             # Python version (3.12)
├── Dockerfile              # Docker build configuration
├── .dockerignore           # Docker ignore rules
├── vercel.json             # Vercel deployment configuration
├── .env.example            # Environment variable template
├── .gitignore              # Git ignore rules
└── README.md
```

---

## ✨ Features

### Storefront (Customer-Facing)
- 🏠 **Homepage** — Hero image slider, featured products, category grid, philosophy section
- 🛍️ **Product Catalog** — Category filtering, sorting (price, rating, newest), search
- 📦 **Product Detail** — Image carousel, reviews (with Amazon-style rating bars), related products
- 🎨 **Candle Customization** — Jar type, colour, fragrance, wick type, custom label text
- 🛒 **Shopping Cart** — Add/remove/update, real-time totals
- 💳 **Checkout** — Razorpay payment (UPI, Cards, Net Banking, Wallets), coupon codes, 10-min payment window
- 📊 **Order Tracking** — Live status updates, tracking history timeline
- ↩️ **Returns** — 7-day return window, seal verification, refund calculation
- 📝 **Complaints** — Customer complaint submission and tracking
- 🧾 **Invoice** — Downloadable/printable HTML invoice with Instagram QR code
- 🤖 **AI Assistant** — Gemini-powered assistant for natural product queries and FAQ support
- 💬 **WhatsApp Integration** — Floating button for customer support
- 🔐 **Auth** — Google OAuth + email/password, JWT cookies, profile management
- 🌙 **Dark/Light Theme** — Seamless toggle with persistent storage
- 🌟 **Luxoya Rewards (LXP)** — Integrated loyalty system with points tracking and tier progress
- ❤️ **My Wishlist** — Persistent collection of favorite scents for members
- 🔗 **Referral System** — One-click link sharing to spread the brand light
- 📱 **Mobile Optimized** — High-contrast premium UI designed for high-end mobile devices

### Admin Console (`/admin/*`)
- 📊 **Dashboard** — Revenue stats, charts, top products, pending orders, low stock alerts
- 📦 **Product Management** — Full CRUD, multi-image upload with WebP compression, activation control
- 📋 **Order Management** — Status updates (with email notifications), cancellation with refunds, invoice generation
- 👥 **Customer Management** — Customer list, detail view, order history, spend tracking
- ⭐ **Review Moderation** — Approve/reject reviews
- 🎫 **Coupon Management** — Create/edit discount coupons (percentage/fixed, min order, expiry, usage limits)
- 🏢 **B2B Request Management** — View and manage corporate inquiry quotations
- 🎨 **Customization Options** — Manage jar types, colours, fragrances, wick types
- 🖼️ **Homepage Content** — Manage hero sliders, philosophy images, collection images
- ⚙️ **Settings** — GST number, Instagram handle, business configuration
- 📝 **Complaints** — View and respond to customer complaints
- ↩️ **Returns** — Approve/reject return requests
- 🚚 **Shiprocket Logistics** — Direct API integration for one-click fulfillment and tracking
- 📊 **Bulk Orders** — Batch status updates (Processing/Confirmed) for high-volume management
- 🗑️ **Order Management (Testing)** — Delete individual test orders or perform a global order reset to clear the dashboard
- 🧾 **Admin Invoice View** — Instant in-browser invoice viewing and PDF-style download for every order
- 🏗️ **Manufacturing Intelligence** — Real-time Unit Cost & Profit Estimator for custom batches
- ⚠️ **Critical Alerts** — Dashboard notifications for low inventory and pending B2B leads

---

## 🗄 Database Models

| Model | Table | Description |
|---|---|---|
| `User` | `users` | Customers & admins (Google OAuth + email/password) |
| `Category` | `categories` | Product categories with display ordering |
| `Product` | `products` | Candle products with pricing, stock, rating |
| `ProductImage` | `product_images` | Multi-image carousel for products |
| `ImageStore` | `image_store` | Binary image storage (WebP compressed) |
| `Customization` | `customizations` | User customization choices (jar, colour, fragrance, wick) |
| `CustomizationOption` | `customization_options` | Admin-managed customization options |
| `CartItem` | `cart_items` | Shopping cart items per user |
| `Order` | `orders` | Order with shipping, status, payment window |
| `OrderItem` | `order_items` | Line items per order |
| `Payment` | `payments` | Razorpay payment records |
| `OrderTracking` | `order_tracking` | Order status history timeline |
| `Coupon` | `coupons` | Discount codes with rules |
| `B2BRequest` | `b2b_requests` | Corporate order inquiries |
| `Review` | `reviews` | Product reviews with images |
| `Complaint` | `complaints` | Customer support tickets |
| `ReturnRequest` | `return_requests` | Product return requests |
| `SiteSettings` | `site_settings` | Key-value store for site configuration |

---

## 🌎 Luxoya 4.1 — International Hardening (Latest Release)

In the latest April 2026 update, the platform has transitioned from a domestic (Pan-India) focus to a **Global Storefront** with a focus on immersive video commerce and international reliability.

### 1. Internationalization & Branding
- **Global Footprint**: Rebranded all "Proudly Indian" messaging to **"International Shipping"** and **"Worldwide Reach"** across the footer, trust badges, and home sections.
- **Unit Standardization**: All product specifications are now globally standardized:
    - **Weight**: Displayed in **`grms`** (grams).
    * **Burn Time**: Displayed in **`hrs`** (hours).
- **Global Trust Badges**: Updated trust section to emphasize **"Express Worldwide Delivery"** and **"Shipping to 20+ Countries"**.

### 2. "Shop by Video" — Immersive Reels
- **Native Experience**: Implemented a social-media-style "Reels" interface for video-driven discovery.
- **Autoplay Logic**: Videos **autoplay on scroll** (muted by default) to maximize customer engagement without intrusive audio.
- **Audio Toggle**: Dedicated unmuting logic that allows customers to "unmute" one reel while keeping others silent for a seamless browsing experience.
- **Dedicated Reels Page**: A fully vertical, swipe-capable Reels dashboard (`/reels`) designed for high-end mobile devices.

### 3. Legal & Content Framework
- **Comprehensive Policies**: Implemented a full suite of professional legal documents:
    - `Shipping Policy`: Detailed domestic and international terms.
    - `Returns & Refunds`: 7-day luxury quality assurance terms.
    - `Privacy Policy`: Transparent data handling.
    - `Terms of Service`: Global governance.
- **Luxoya Stories (Blog)**: A dynamic journal for fragrance masters to share "The Psychology of Scent" and "Candle Styling Tips".

### 4. Interactive & UI Hardening
- **Hero Slider 2.0**: Hardened the homepage hero section with **manual touch gesture detection**, bypassing OS-level gesture conflicts for 100% reliable swiping on iOS and Android.
- **Footer Realignment**: Optimized the desktop footer layout (3-2-2-2-3 distribution) for better visual balance on ultra-wide screens.
- **JS Performance**: Removed stray script residues and consolidated initialization logic for faster TTI (Time to Interactive).

---

## 🔌 API Endpoints

### Authentication (`/api/auth/*`)
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/register` | Email/password registration |
| POST | `/api/auth/login` | Email/password login |
| POST | `/api/auth/google` | Google OAuth login/register |
| POST | `/api/auth/logout` | Logout (clear cookies) |
| GET | `/api/auth/me` | Get current user |
| PUT | `/api/auth/profile` | Update profile |
| PUT | `/api/auth/change-password` | Change password |
| POST | `/api/auth/refresh` | Refresh JWT token |
| GET | `/api/auth/google-client-id` | Get Google Client ID |

### Products (`/api/*`)
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/products` | List products (filters, sort, pagination) |
| GET | `/api/products/<slug>` | Get single product |
| GET | `/api/categories` | List categories |
| GET | `/api/search?q=` | Search products |
| POST | `/api/products/<id>/reviews` | Add review |
| GET | `/api/products/<id>/reviews` | Get reviews |
| POST | `/api/reviews/<id>/helpful` | Mark review helpful |

### Cart (`/api/cart/*`)
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/cart` | Get cart items |
| POST | `/api/cart` | Add to cart |
| PUT | `/api/cart/<id>` | Update quantity |
| DELETE | `/api/cart/<id>` | Remove item |
| DELETE | `/api/cart/clear` | Clear cart |
| GET | `/api/cart/count` | Get cart count |

### Orders (`/api/orders/*`)
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/orders` | Create order + Razorpay order |
| POST | `/api/orders/verify-payment` | Verify Razorpay payment |
| GET | `/api/orders` | List user orders |
| GET | `/api/orders/<number>` | Get order detail |
| POST | `/api/orders/<number>/cancel` | Cancel order |
| GET | `/api/orders/<number>/invoice` | Download invoice |
| GET | `/api/orders/<id>/tracking` | Get tracking timeline |
| GET | `/api/orders/payment-status` | Check payment cooldown |
| POST | `/api/coupons/validate` | Validate coupon code |
| POST | `/api/orders/<number>/return` | Request return |
| GET | `/api/orders/<number>/return` | Get return status |
| POST | `/api/complaints` | Create complaint |
| GET | `/api/complaints` | List user complaints |

### B2B (`/api/b2b/*`)
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/b2b/request` | Submit B2B request |
| GET | `/api/b2b/request/<id>` | Track B2B request |

### Chat (`/api/chat`)
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/chat` | Send message to Gemini AI assistant |

### Admin (`/admin/api/*`)
Full admin CRUD for products, orders, categories, customers, reviews, coupons, B2B requests, complaints, returns, settings, customization options, and homepage content.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.11+ installed
- PostgreSQL (optional — SQLite is used for local development)

### Installation

```bash
# 1. Clone the repository
git clone <repository-url>
cd Luxoya-main

# 2. Create virtual environment
python -m venv venv

# 3. Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Set up environment variables
cp .env.example .env
# Edit .env with your actual keys (see Environment Variables section)

# 6. Run the application
python app.py
```

The app will start on **http://localhost:5000**

### Seed Data (Optional)
```bash
python seed_data.py
```
Creates an admin user (`admin@luxoyacandles.com` / `Luxoya@123`) and sample products.

---

## 🔐 Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `FLASK_ENV` | ✅ | `development` or `production` |
| `SECRET_KEY` | ✅ | Flask secret key |
| `JWT_SECRET_KEY` | ✅ | JWT signing key |
| `DATABASE_URL` | ❌ | PostgreSQL URL (defaults to SQLite) |
| `RAZORPAY_KEY_ID` | ✅ | Razorpay API key |
| `RAZORPAY_KEY_SECRET` | ✅ | Razorpay secret |
| `GEMINI_API_KEY` | ✅ | Google Gemini key for AI assistant |
| `MAIL_USERNAME` | ❌ | Gmail address for emails |
| `MAIL_PASSWORD` | ❌ | Gmail App Password |
| `GOOGLE_CLIENT_ID` | ✅ | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | ✅ | Google OAuth secret |

---

## 🌐 Deployment

### Vercel
Already configured via `vercel.json`. Push to GitHub and connect to Vercel for the most stable experience.

### Docker / Cloud Run
```bash
docker build -t luxoya .
docker run -p 8080:8080 --env-file .env luxoya
```

### Firebase Hosting + Cloud Functions
See the dedicated section below for the current issues and recommended approach.

---

## 🔥 Firebase Deployment Notes

### Current Issue

The Firebase deployment is **failing** because the Firebase Functions setup has a critical architectural mismatch. Here's what's happening:

1. **`firebase.json`** is configured to deploy the **entire project root** (`.`) as a Python Cloud Function, with all routes rewritten to a function called `luxoya_app`.

2. **`main.py`** tries to import `luxoya_app` from `app.py` for Firebase, and `app.py` attempts to wrap the Flask WSGI app using `firebase_functions.https_fn`.

3. **The problem**: Firebase Cloud Functions for Python (2nd gen) have strict limitations:
   - The `firebase-functions` Python SDK expects a lightweight function, not a full Flask app with database connections, migrations, image processing, and 20+ dependencies.
   - The `serving.py` discovery process hangs during deployment (see `firebase-debug.log` line 68: `ECONNREFUSED`). This happens because your `app.py` runs heavy module-level initialization (`create_app()`, `db.create_all()`, inline ALTER TABLE migrations) immediately on import — and this crashes or times out during Firebase's function discovery phase.
   - The full dependency bundle (Flask, SQLAlchemy, Pillow, psycopg2, openai, razorpay, etc.) exceeds the limits for smooth Cloud Function cold starts.

### Root Cause (from debug log)

```
Failed to call quitquitquit. This often means the server failed to start
request to http://127.0.0.1:8081/__/quitquitquit failed,
reason: connect ECONNREFUSED 127.0.0.1:8081
```

The Firebase CLI starts a discovery server on port 8081 to introspect your functions. Your `app.py` executes `create_app()` at module level (line 256), which:
- Runs `db.create_all()` — tries to connect to a database that doesn't exist during CI/deploy
- Runs `ALTER TABLE` migrations — also requires a live database
- Imports all route blueprints — which import models, utils, etc.

This crashes before the discovery server can respond, causing the `ECONNREFUSED` error.

### Recommended Fix: Use Cloud Run Instead

Firebase Hosting + Cloud Functions for Python is **not the right fit** for this application. Here's why and what to do instead:

**Option A: Firebase Hosting + Cloud Run (Recommended)**

Cloud Run runs Docker containers — perfect for your full Flask app with PostgreSQL, Pillow, etc.

1. Deploy your Docker container to Cloud Run
2. Configure Firebase Hosting to proxy to your Cloud Run service

```json
// firebase.json (rewrite to Cloud Run)
{
  "hosting": {
    "public": "static",
    "rewrites": [
      {
        "source": "**",
        "run": {
          "serviceId": "luxoya-app",
          "region": "asia-south1"
        }
      }
    ]
  }
}
```

```bash
# Deploy to Cloud Run
gcloud run deploy luxoya-app \
  --source . \
  --region asia-south1 \
  --allow-unauthenticated \
  --set-env-vars "FLASK_ENV=production,DATABASE_URL=<your-neon-url>"

# Then deploy Firebase Hosting
firebase deploy --only hosting
```

**Option B: Vercel (Already Configured)**

Your `vercel.json` is already properly set up. Just push to GitHub and deploy via Vercel dashboard.

**Option C: Render.com / Railway.app**

These platforms support Flask + PostgreSQL out of the box with zero configuration beyond environment variables.

---

---

## 💎 Premium Features & Integration

### 🚀 Shiprocket Logistics
The platform is fully integrated with **Shiprocket**. 
- **Setup**: Add `SHIPROCKET_EMAIL` and `SHIPROCKET_PASSWORD` to your `.env`.
- **Flow**: From the Admin Logistics panel, select "Confirmed" orders and click **Ship Now** to automatically create the shipment in Shiprocket.

### 💰 Manufacturing & Profitability
The **Manufacturing Guide** (`/admin/manufacturing`) includes a live **Profit Estimator**.
- **Calculations**: It considers wax weight, fragrance percentage, and vessel costs.
- **Goal**: Maintain luxury margins (standard 4x markup) by modeling costs before production.

### ✨ Luxoya Rewards System
Customers earn **1 LXP per ₹1 spent**. 
- **Tiers**: Automatic progression from *Silver* to *Gold Circle*.
- **VIP Rewards**: Access to exclusive discounts and free gifts based on lifetime value (LTV).

---

## 📄 License

Proprietary — Luxoya Candles © 2024. All rights reserved.



### ??? Granular Staff Access (RBAC)
- **Role-Based Provisioning**: Create isolated 'Sales' roles in the Admin 'Staff Access' portal without needing backend redeployment.
- **Granular Permissions Grid**: Assign isolated read/write privileges (e.g., allow Employee A to access Orders and Invoices, Employee B to manage Inventory and the Home Editor). 
- **Live Session Toggling**: Instantly revoke access to any account or natively bypass locked credentials via forced password resets.
