/* ═══════════════════════════════════════════════════════════════
   LUXOYA CANDLES – Main JavaScript
   Shared utilities, navbar, search, chat, toast, cart badge
   ═══════════════════════════════════════════════════════════════ */

/* ── CSRF Protection Global Interceptor ── */
const originalFetch = window.fetch;
window.fetch = async function() {
    let [resource, config] = arguments;
    if (config && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(config.method?.toUpperCase())) {
        if (!config.headers) config.headers = {};
        const match = document.cookie.match(new RegExp('(^| )csrf_access_token=([^;]+)'));
        if (match) {
            config.headers['X-CSRF-TOKEN'] = match[2];
        }
    }
    return originalFetch(resource, config);
};

document.addEventListener('DOMContentLoaded', () => {
    AOS.init({ duration: 700, once: true, offset: 80 });
    initNavbar();
    initSearch();
    initChat();
    initUserMenu();
    updateCartBadge();
    initRevealGlow();
    initThemeIcon();
});

function initThemeIcon() {
    const theme = document.documentElement.getAttribute('data-theme') || 'dark';
    const icon = document.getElementById('themeIcon');
    if (icon) icon.className = theme === 'dark' ? 'bi bi-moon-stars' : 'bi bi-sun';
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('lx-theme', next);
    const icon = document.getElementById('themeIcon');
    if (icon) {
        icon.className = next === 'dark' ? 'bi bi-moon-stars' : 'bi bi-sun';
    }
}

/* ── Toast Utility ─────────────────────────────────────────── */
function showToast(message, duration = 3000) {
    const el = document.getElementById('liveToast');
    const msg = document.getElementById('toastMessage');
    if (!el || !msg) return;
    msg.textContent = message;
    const toast = bootstrap.Toast.getOrCreateInstance(el, { delay: duration });
    toast.show();
}

/* ── Navbar Scroll ─────────────────────────────────────────── */
function initNavbar() {
    const nav = document.getElementById('mainNav');
    if (!nav) return;
    const onScroll = () => nav.classList.toggle('scrolled', window.scrollY > 50);
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
}

/* ── Search ────────────────────────────────────────────────── */
function initSearch() {
    const input = document.getElementById('searchInput');
    const results = document.getElementById('searchResults');
    if (!input || !results) return;

    let timer;
    input.addEventListener('input', () => {
        clearTimeout(timer);
        const q = input.value.trim();
        if (q.length < 2) { results.innerHTML = ''; return; }
        timer = setTimeout(async () => {
            try {
                const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
                const data = await res.json();
                if (!data.products || !data.products.length) {
                    results.innerHTML = '<p class="text-muted text-center py-3">No results found</p>';
                    return;
                }
                results.innerHTML = data.products.slice(0, 8).map(p => `
                    <a href="/products/${p.slug}" class="search-result-item d-flex align-items-center gap-3 p-2 rounded text-decoration-none">
                        <div class="search-result-img">
                            ${p.image_url ? `<img src="${p.image_url}" alt="${p.name}">` : '<i class="bi bi-lamp text-gold"></i>'}
                        </div>
                        <div>
                            <div class="fw-600 search-result-name">${p.name}</div>
                            <div class="text-muted" style="font-size:.8rem">₹${parseFloat(p.price).toLocaleString('en-IN')}</div>
                        </div>
                    </a>
                `).join('');
            } catch { results.innerHTML = ''; }
        }, 300);
    });

    const modal = document.getElementById('searchModal');
    if (modal) {
        modal.addEventListener('shown.bs.modal', () => input.focus());
        modal.addEventListener('hidden.bs.modal', () => { input.value = ''; results.innerHTML = ''; });
    }
}

/* ── User Menu ─────────────────────────────────────────────── */
function initUserMenu() {
    const menu = document.getElementById('userMenu');
    if (!menu) return;

    fetch('/api/auth/me').then(r => r.json()).then(data => {
        if (data.user) {
            const u = data.user;
            menu.innerHTML = `
                <li><span class="dropdown-item-text fw-600">${u.full_name}</span></li>
                <li><hr class="dropdown-divider"></li>
                <li><a class="dropdown-item" href="/profile"><i class="bi bi-person me-2"></i>Profile</a></li>
                <li><a class="dropdown-item" href="/orders"><i class="bi bi-box me-2"></i>My Orders</a></li>
                <li><a class="dropdown-item" href="/complaints"><i class="bi bi-chat-square-text me-2"></i>Complaints</a></li>
                ${u.is_admin ? '<li><a class="dropdown-item" href="/admin"><i class="bi bi-gear me-2"></i>Admin Panel</a></li>' : ''}
                <li><hr class="dropdown-divider"></li>
                <li><a class="dropdown-item text-danger" href="#" onclick="logout()"><i class="bi bi-box-arrow-right me-2"></i>Logout</a></li>
            `;
        }
    }).catch(() => {});
}

async function logout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    window.location.href = '/login';
}

/* ── Cart Badge ────────────────────────────────────────────── */
async function updateCartBadge() {
    try {
        const res = await fetch('/api/cart', { credentials: 'same-origin' });
        if (!res.ok) return;
        const data = await res.json();
        const badge = document.getElementById('cartBadge');
        if (!badge) return;
        const count = (data.items || []).reduce((s, i) => s + i.quantity, 0);
        badge.textContent = count;
        badge.style.display = count > 0 ? 'flex' : 'none';
    } catch {}
}

/* ── Add to Cart (global helper) ───────────────────────────── */
async function addToCart(productId, quantity = 1, showModal = false) {
    try {
        const res = await fetch('/api/cart', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ product_id: productId, quantity })
        });

        if (res.status === 401) {
            showToast('Please login to continue shopping');
            setTimeout(() => { window.location.href = '/login'; }, 1200);
            return;
        }

        const data = await res.json();
        if (res.ok) {
            updateCartBadge();
            
            if (showModal) {
                const modalEl = document.getElementById('cartConfirmationModal');
                if (modalEl) {
                    const modal = new bootstrap.Modal(modalEl);
                    modal.show();
                } else {
                    showToast('Added to cart!');
                }
            } else {
                showToast('Added to cart!');
            }
        } else {
            showToast(data.error || 'Failed to add to cart');
        }
    } catch (e) {
        console.error('Cart Error:', e);
        showToast('Network error. Please try again.');
    }
}

async function buyNow(productId, quantity = 1) {
    // Shortcut for direct "Buy Now" experience
    await addToCart(productId, quantity, true);
}

/* ── Chat Widget ───────────────────────────────────────────── */
function initChat() {
    const toggle = document.getElementById('chatToggle');
    const close = document.getElementById('chatClose');
    const window_ = document.getElementById('chatWindow');
    const form = document.getElementById('chatForm');
    const body = document.getElementById('chatBody');
    const input = document.getElementById('chatInput');

    if (!toggle || !window_) return;

    toggle.addEventListener('click', () => {
        const visible = window_.style.display !== 'none';
        window_.style.display = visible ? 'none' : 'block';
        if (!visible) input?.focus();
    });

    close?.addEventListener('click', () => { window_.style.display = 'none'; });

    form?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const msg = input.value.trim();
        if (!msg) return;

        // User message
        body.innerHTML += `<div class="chat-msg user"><p>${escapeHtml(msg)}</p></div>`;
        input.value = '';
        body.scrollTop = body.scrollHeight;

        // Bot typing
        const typing = document.createElement('div');
        typing.className = 'chat-msg bot';
        typing.innerHTML = '<p><span class="spinner-border spinner-border-sm me-2"></span>Thinking...</p>';
        body.appendChild(typing);
        body.scrollTop = body.scrollHeight;

        try {
            const res = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: msg })
            });
            const data = await res.json();
            typing.querySelector('p').innerHTML = data.response || 'Sorry, I could not understand that.';
        } catch {
            typing.querySelector('p').innerHTML = 'Unable to connect. Please try again later.';
        }
        body.scrollTop = body.scrollHeight;
    });
}

/* ── HTML escape helper ────────────────────────────────────── */
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/* ── Password toggle (used in auth forms) ──────────────────── */
function togglePassword(fieldId) {
    const field = document.getElementById(fieldId);
    if (!field) return;
    field.type = field.type === 'password' ? 'text' : 'password';
    const icon = field.parentElement.querySelector('.bi-eye, .bi-eye-slash');
    if (icon) {
        icon.classList.toggle('bi-eye');
        icon.classList.toggle('bi-eye-slash');
    }
}


/* ═══════════════════════════════════════════════════════════════
   REVEAL GLOW – sections emerge from dark to bright on scroll
   ═══════════════════════════════════════════════════════════════ */
function initRevealGlow() {
    // Add reveal-glow class to major sections
    const sections = document.querySelectorAll(
        '.section-padding, .hero-section, .cta-section, .b2b-hero, .page-header'
    );
    sections.forEach(s => {
        if (!s.classList.contains('reveal-glow')) {
            s.classList.add('reveal-glow');
        }
    });

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('revealed');
            }
        });
    }, {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    });

    document.querySelectorAll('.reveal-glow').forEach(el => observer.observe(el));
}
