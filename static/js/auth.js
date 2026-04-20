/* ═══════════════════════════════════════════════════════════════
   LUXOYA CANDLES – Auth JavaScript
   Login (email/password) + Register + Google OAuth
   ═══════════════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {
    initLoginForm();
    initRegisterForm();
    initGoogleLogin(); // Pre-load and Initialize Google
});

/* ── LOGIN (email + password) ──────────────────────────────── */
function initLoginForm() {
    const form = document.getElementById('loginForm');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = document.getElementById('loginBtn');
        const errEl = document.getElementById('loginError');
        setLoading(btn, true);
        errEl.classList.add('d-none');

        const email = document.getElementById('email').value.trim();
        const password = document.getElementById('password').value;

        try {
            const res = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({ email, password })
            });
            const data = await res.json();

            if (res.ok) {
                window.location.href = data.redirect || '/';
            } else {
                errEl.textContent = data.error || 'Invalid credentials';
                errEl.classList.remove('d-none');
            }
        } catch {
            errEl.textContent = 'Network error. Please try again.';
            errEl.classList.remove('d-none');
        } finally {
            setLoading(btn, false);
        }
    });
}

/* ── REGISTER (email + password) ────────────────────────────── */
function initRegisterForm() {
    const form = document.getElementById('registerForm');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = document.getElementById('registerBtn');
        const errEl = document.getElementById('registerError');
        const successEl = document.getElementById('registerSuccess');
        setLoading(btn, true);
        errEl.classList.add('d-none');
        successEl.classList.add('d-none');

        const full_name = document.getElementById('full_name').value.trim();
        const email = document.getElementById('email').value.trim();
        const phone = document.getElementById('phone')?.value.trim() || '';
        const password = document.getElementById('password').value;
        const confirm_password = document.getElementById('confirm_password').value;

        if (!phone || phone.length < 10) {
            errEl.textContent = 'Please enter a valid mobile number (min 10 digits)';
            errEl.classList.remove('d-none');
            setLoading(btn, false);
            return;
        }
        if (password !== confirm_password) {
            errEl.textContent = 'Passwords do not match';
            errEl.classList.remove('d-none');
            setLoading(btn, false);
            return;
        }
        if (password.length < 8) {
            errEl.textContent = 'Password must be at least 8 characters';
            errEl.classList.remove('d-none');
            setLoading(btn, false);
            return;
        }

        try {
            const res = await fetch('/api/auth/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({ full_name, email, phone, password, confirm_password })
            });
            const data = await res.json();

            if (res.ok) {
                successEl.textContent = data.message || 'Account created! Redirecting...';
                successEl.classList.remove('d-none');
                setTimeout(() => {
                    window.location.href = data.redirect || '/';
                }, 800);
            } else {
                errEl.textContent = data.error || 'Registration failed';
                errEl.classList.remove('d-none');
            }
        } catch {
            errEl.textContent = 'Network error. Please try again.';
            errEl.classList.remove('d-none');
        } finally {
            setLoading(btn, false);
        }
    });
}

/* ── GOOGLE OAUTH ──────────────────────────────────────────── */
async function initGoogleLogin() {
    // Load Google Identity Services if not already there
    if (!window.google || !window.google.accounts) {
        try {
            await loadScript('https://accounts.google.com/gsi/client');
        } catch (err) {
            console.error('Failed to load Google Identity Services:', err);
            return;
        }
    }

    // Get client ID from meta tag
    let clientId = document.querySelector('meta[name="google-client-id"]')?.content;
    
    // If meta is empty or contains the unparsed Jinja placeholder
    if (!clientId || clientId.includes('{{') || clientId.includes('config.')) {
        // Fallback: fetch from backend
        try {
            const cfgRes = await fetch('/api/auth/google-client-id');
            const cfgData = await cfgRes.json();
            clientId = cfgData.client_id;
        } catch (err) {
            console.error('Failed to fetch Google Client ID:', err);
        }
    }

    if (clientId) {
        google.accounts.id.initialize({
            client_id: clientId,
            callback: handleGoogleResponse,
            auto_select: false,
            ux_mode: 'popup'
        });
        
        // Optionally render the official button for better reliability
        const buttonWrapper = document.getElementById('googleButtonContainer');
        if (buttonWrapper) {
            google.accounts.id.renderButton(buttonWrapper, {
                theme: 'outline',
                size: 'large',
                width: '100%',
                text: 'continue_with',
                shape: 'rectangular'
            });
        }
    }
}

async function googleLogin() {
    const errEl = document.getElementById('googleError') || document.getElementById('loginError');
    
    // Check if initialized
    if (!window.google || !window.google.accounts) {
        await initGoogleLogin();
    }

    try {
        google.accounts.id.prompt((notification) => {
            if (notification.isNotDisplayed()) {
                console.warn('One Tap Not Displayed:', notification.getNotDisplayedReason());
                // Fallback: This is where we might want the standard button to be visible
            }
            if (notification.isSkippedMoment()) {
                console.warn('One Tap Skipped:', notification.getSkippedMomentReason());
            }
        });
    } catch (err) {
        console.error('Google Prompt Error:', err);
        if (errEl) {
            errEl.textContent = 'Google Login error. Please check your browser settings.';
            errEl.classList.remove('d-none');
        }
    }
}

async function handleGoogleResponse(response) {
    const errEl = document.getElementById('googleError');
    const successEl = document.getElementById('googleSuccess');

    try {
        const res = await fetch('/api/auth/google', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ credential: response.credential })
        });
        const data = await res.json();

        if (res.ok) {
            if (successEl) {
                successEl.textContent = data.message || 'Login successful! Redirecting...';
                successEl.classList.remove('d-none');
            }
            setTimeout(() => {
                window.location.href = data.redirect || '/';
            }, 500);
        } else {
            if (errEl) {
                errEl.textContent = data.error || 'Google login failed';
                errEl.classList.remove('d-none');
            }
        }
    } catch {
        if (errEl) {
            errEl.textContent = 'Network error during Google login';
            errEl.classList.remove('d-none');
        }
    }
}

function loadScript(src) {
    return new Promise((resolve, reject) => {
        if (document.querySelector(`script[src="${src}"]`)) { resolve(); return; }
        const s = document.createElement('script');
        s.src = src;
        s.onload = resolve;
        s.onerror = reject;
        document.head.appendChild(s);
    });
}

/* ── HELPERS ───────────────────────────────────────────────── */
function togglePassword(fieldId, btnEl) {
    const field = document.getElementById(fieldId);
    if (field) {
        const type = field.type === 'password' ? 'text' : 'password';
        field.type = type;
        
        // Find icon inside btn
        if (btnEl) {
            const icon = btnEl.querySelector('i');
            if (icon) {
                icon.className = type === 'password' ? 'bi bi-eye' : 'bi bi-eye-slash';
            }
        }
    }
}

function setLoading(btn, loading) {
    if (!btn) return;
    const text = btn.querySelector('.btn-text');
    const spinner = btn.querySelector('.btn-loading');
    if (loading) {
        btn.disabled = true;
        text?.classList.add('d-none');
        spinner?.classList.remove('d-none');
    } else {
        btn.disabled = false;
        text?.classList.remove('d-none');
        spinner?.classList.add('d-none');
    }
}
