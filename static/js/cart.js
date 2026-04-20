/* ═══════════════════════════════════════════════════════════════
   LUXOYA CANDLES – Cart JavaScript
   Cart page operations, coupon, quantity
   ═══════════════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('cartContent')) loadCart();
});

let cartData = { items: [], subtotal: 0, shipping_cost: 0, total: 0 };
let appliedCoupon = null;

async function loadCart() {
    document.getElementById('cartLoading')?.classList.remove('d-none');
    document.getElementById('cartEmpty')?.classList.add('d-none');
    document.getElementById('cartContent')?.classList.add('d-none');

    try {
        const res = await fetch('/api/cart', { credentials: 'same-origin' });
        cartData = await res.json();

        document.getElementById('cartLoading')?.classList.add('d-none');

        if (!cartData.items || !cartData.items.length) {
            document.getElementById('cartEmpty')?.classList.remove('d-none');
            return;
        }

        document.getElementById('cartContent')?.classList.remove('d-none');
        renderCartItems();
        updateCartSummary();
    } catch {
        document.getElementById('cartLoading')?.classList.add('d-none');
        document.getElementById('cartEmpty')?.classList.remove('d-none');
    }
}

function renderCartItems() {
    const list = document.getElementById('cartItemsList');
    if (!list) return;

    list.innerHTML = cartData.items.map(item => `
        <div class="cart-item-card">
            <div class="d-flex gap-3 align-items-center">
                <div class="cart-item-img">
                    ${item.product?.image_url
                        ? `<img src="${item.product.image_url}" alt="${item.product?.name || 'Product'}">`
                        : '<div class="cart-placeholder"><i class="bi bi-lamp text-gold"></i></div>'
                    }
                </div>
                <div class="flex-grow-1">
                    <h6 class="cart-item-name mb-1">${item.product?.name || 'Custom Candle'}</h6>
                    ${item.customization ? `<small class="text-muted">${item.customization.jar_type} | ${item.customization.colour} | ${item.customization.fragrance}</small>` : ''}
                    <div class="d-flex align-items-center gap-3 mt-2">
                        <div class="quantity-selector quantity-sm">
                            <button class="qty-btn" onclick="updateQty('${item.id}', ${item.quantity - 1})">−</button>
                            <input type="text" class="qty-input" value="${item.quantity}" readonly>
                            <button class="qty-btn" onclick="updateQty('${item.id}', ${item.quantity + 1})">+</button>
                        </div>
                        <strong>₹${(item.price * item.quantity).toLocaleString('en-IN')}</strong>
                    </div>
                </div>
                <button class="btn btn-sm btn-outline-danger" onclick="removeItem('${item.id}')" title="Remove">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
        </div>
    `).join('');
}

function updateCartSummary() {
    const subtotal = cartData.items.reduce((s, i) => s + (i.price * i.quantity), 0);
    const shipping = subtotal >= 999 ? 0 : 99;
    const discount = cartData.discount_amount || 0;
    const total = subtotal - discount + shipping;

    document.getElementById('cartSubtotal').textContent = `₹${subtotal.toLocaleString('en-IN')}`;
    document.getElementById('cartShipping').textContent = shipping === 0 ? 'FREE' : `₹${shipping}`;
    document.getElementById('cartTotal').textContent = `₹${total.toLocaleString('en-IN')}`;

    const discountRow = document.getElementById('discountRow');
    if (discount > 0 && discountRow) {
        discountRow.classList.remove('d-none');
        document.getElementById('cartDiscount').textContent = `-₹${discount.toLocaleString('en-IN')}`;
    } else if (discountRow) {
        discountRow.classList.add('d-none');
    }

    // Free shipping notice
    const notice = document.getElementById('freeShipNotice');
    const msg = document.getElementById('freeShipMsg');
    if (notice && msg) {
        if (subtotal >= 999) {
            msg.textContent = 'You qualify for FREE shipping!';
            notice.classList.remove('d-none');
        } else {
            const remaining = 999 - subtotal;
            msg.textContent = `Add ₹${remaining.toLocaleString('en-IN')} more for FREE shipping`;
            notice.classList.remove('d-none');
        }
    }

    // Update global badge
    updateCartBadge();
}

async function updateQty(itemId, newQty) {
    if (newQty < 1) { removeItem(itemId); return; }

    try {
        await fetch(`/api/cart/${itemId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ quantity: newQty })
        });
        loadCart();
    } catch {
        showToast('Failed to update quantity');
    }
}

async function removeItem(itemId) {
    try {
        await fetch(`/api/cart/${itemId}`, { method: 'DELETE', credentials: 'same-origin' });
        showToast('Item removed');
        loadCart();
    } catch {
        showToast('Failed to remove item');
    }
}

async function applyCoupon() {
    const input = document.getElementById('couponInput');
    const msg = document.getElementById('couponMsg');
    const code = input?.value.trim();

    if (!code) { msg.textContent = 'Enter a coupon code'; msg.className = 'small text-danger mt-1'; return; }

    try {
        const subtotal = cartData.items.reduce((s, i) => s + (i.price * i.quantity), 0);
        const res = await fetch('/api/coupons/validate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ code, subtotal })
        });
        const data = await res.json();

        if (res.ok) {
            msg.textContent = `Coupon applied! You save ₹${data.discount}`;
            msg.className = 'small text-success mt-1';
            appliedCoupon = code;
            cartData.discount_amount = data.discount;
            updateCartSummary();
        } else {
            msg.textContent = data.error || 'Invalid coupon';
            msg.className = 'small text-danger mt-1';
        }
    } catch {
        msg.textContent = 'Failed to apply coupon';
        msg.className = 'small text-danger mt-1';
    }
}

async function clearCart() {
    if (!confirm('Clear all items from your cart?')) return;
    try {
        await fetch('/api/cart/clear', { method: 'DELETE', credentials: 'same-origin' });
        showToast('Cart cleared');
        loadCart();
    } catch {
        showToast('Failed to clear cart');
    }
}
