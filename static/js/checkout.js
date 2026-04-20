/* ═══════════════════════════════════════════════════════════════
   LUXOYA CANDLES – Checkout JavaScript
   Razorpay payment integration, order creation
   ═══════════════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('checkoutForm')) {
        loadCheckoutSummary();
        initCheckoutForm();
    }
});

async function loadCheckoutSummary() {
    try {
        const res = await fetch('/api/cart');
        const data = await res.json();

        if (!data.items || !data.items.length) {
            window.location.href = '/cart';
            return;
        }

        const itemsEl = document.getElementById('checkoutItems');
        if (itemsEl) {
            itemsEl.innerHTML = data.items.map(i => `
                <div class="checkout-item">
                    <div class="checkout-item-img">
                        ${i.product?.image_url ? `<img src="${i.product.image_url}">` : '<div style="background:#faf8f5;width:100%;height:100%;display:flex;align-items:center;justify-content:center;border-radius:8px"><i class="bi bi-lamp text-gold"></i></div>'}
                        <span class="checkout-qty-badge">${i.quantity}</span>
                    </div>
                    <div class="flex-grow-1">
                        <div style="font-size:.85rem;font-weight:600">${i.product?.name || 'Custom Candle'}</div>
                    </div>
                    <div style="font-weight:600">₹${(i.price * i.quantity).toLocaleString('en-IN')}</div>
                </div>
            `).join('');
        }

        const subtotal = data.items.reduce((s, i) => s + (i.price * i.quantity), 0);
        const shipping = subtotal >= 999 ? 0 : 99;
        const discount = data.discount_amount || 0;
        const total = subtotal - discount + shipping;

        setText('checkSubtotal', `₹${subtotal.toLocaleString('en-IN')}`);
        setText('checkShipping', shipping === 0 ? 'FREE' : `₹${shipping}`);
        setText('checkTotal', `₹${total.toLocaleString('en-IN')}`);

        const discRow = document.getElementById('checkDiscountRow');
        if (discount > 0 && discRow) {
            discRow.classList.remove('d-none');
            setText('checkDiscount', `-₹${discount.toLocaleString('en-IN')}`);
        }
    } catch {
        showToast('Failed to load checkout summary');
    }
}

function initCheckoutForm() {
    const form = document.getElementById('checkoutForm');
    form?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = document.getElementById('payButton');
        if (btn) btn.disabled = true;

        const payload = {
            shipping_name: val('shippingName'),
            shipping_phone: val('shippingPhone'),
            shipping_address: val('shippingAddress'),
            shipping_city: val('shippingCity'),
            shipping_state: val('shippingState'),
            shipping_pincode: val('shippingPincode'),
            notes: val('orderNotes')
        };

        try {
            // Step 1: Create order on backend
            const orderRes = await fetch('/api/orders', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify(payload)
            });
            const orderData = await orderRes.json();

            if (!orderRes.ok) {
                showToast(orderData.error || 'Failed to create order');
                if (btn) btn.disabled = false;
                return;
            }

            // Step 2: Initiate Razorpay payment
            if (orderData.razorpay_order) {
                initiatePayment(orderData);
            } else {
                // COD or free order
                window.location.href = `/orders/confirmation/${orderData.order.order_number}`;
            }
        } catch {
            showToast('Network error. Please try again.');
            if (btn) btn.disabled = false;
        }
    });
}

function initiatePayment(orderData) {
    const rzpOrder = orderData.razorpay_order;
    const orderNum = orderData.order.order_number;

    const options = {
        key: orderData.razorpay_key,
        amount: rzpOrder.amount,
        currency: rzpOrder.currency || 'INR',
        name: 'Luxoya Candles',
        description: `Order ${orderNum}`,
        order_id: rzpOrder.id,
        handler: async function(response) {
            // Step 3: Verify payment
            try {
                const verifyRes = await fetch('/api/orders/verify-payment', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'same-origin',
                    body: JSON.stringify({
                        order_number: orderNum,
                        razorpay_payment_id: response.razorpay_payment_id,
                        razorpay_order_id: response.razorpay_order_id,
                        razorpay_signature: response.razorpay_signature
                    })
                });
                const verifyData = await verifyRes.json();

                if (verifyRes.ok) {
                    window.location.href = `/orders/confirmation/${orderNum}`;
                } else {
                    showToast(verifyData.error || 'Payment verification failed');
                }
            } catch {
                showToast('Payment verification failed. Contact support if amount was deducted.');
            }
        },
        prefill: {
            name: val('shippingName'),
            email: val('shippingEmail'),
            contact: val('shippingPhone')
        },
        theme: {
            color: '#c9a96e'
        },
        modal: {
            ondismiss: function() {
                const btn = document.getElementById('payButton');
                if (btn) btn.disabled = false;
                showToast('Payment cancelled');
            }
        }
    };

    const rzp = new Razorpay(options);
    rzp.open();
}

function val(id) { return document.getElementById(id)?.value.trim() || ''; }
function setText(id, text) { const el = document.getElementById(id); if (el) el.textContent = text; }
