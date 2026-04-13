// ============================================================================
// CAR SPARE PARTS - CLIENT-SIDE JAVASCRIPT
// ============================================================================

// Initialize
document.addEventListener('DOMContentLoaded', function () {
    updateCartCount();
    initAddToCartButtons();
    initAnimations();
});

// ============================================================================
// CART FUNCTIONALITY
// ============================================================================

function updateCartCount(count = null) {
    if (count !== null) {
        document.getElementById('cart-count').textContent = count;
        animateCartBadge();
    } else {
        fetch('/api/cart/count')
            .then(response => response.json())
            .then(data => {
                document.getElementById('cart-count').textContent = data.count;
            });
    }
}

function initAddToCartButtons() {
    const buttons = document.querySelectorAll('.add-to-cart-btn');
    buttons.forEach(button => {
        button.addEventListener('click', function (e) {
            e.preventDefault();
            const productId = this.getAttribute('data-product-id');
            addToCart(productId);
        });
    });
}

function addToCart(productId, quantity = 1) {
    fetch('/api/cart/add', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            product_id: parseInt(productId),
            quantity: quantity
        })
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                updateCartCount(data.cart_count);
                showNotification('Added to cart!', 'success');
            } else {
                showNotification('Failed to add to cart', 'error');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showNotification('An error occurred', 'error');
        });
}

// ============================================================================
// ANIMATIONS
// ============================================================================

function animateCartBadge() {
    const badge = document.getElementById('cart-count');
    badge.style.animation = 'none';
    setTimeout(() => {
        badge.style.animation = 'bounce 0.5s ease';
    }, 10);
}

function initAnimations() {
    // Fade in elements on scroll
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('fade-in');
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);

    // Observe all cards
    document.querySelectorAll('.card').forEach(card => {
        observer.observe(card);
    });
}

// ============================================================================
// NOTIFICATIONS & CONFIRMATION MODALS
// ============================================================================

function showNotification(message, type = 'success', duration = 5000) {
    // Remove existing notifications
    document.querySelectorAll('.toast-notification').forEach(n => n.remove());

    const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
    const colors = {
        success: 'linear-gradient(135deg, #10b981, #059669)',
        error: 'linear-gradient(135deg, #ef4444, #dc2626)',
        warning: 'linear-gradient(135deg, #f59e0b, #d97706)',
        info: 'linear-gradient(135deg, #3b82f6, #2563eb)'
    };

    const toast = document.createElement('div');
    toast.className = 'toast-notification';
    toast.innerHTML = `
        <div style="display:flex;align-items:center;gap:12px;flex:1;">
            <span style="font-size:1.5rem;">${icons[type] || icons.info}</span>
            <span style="flex:1;font-weight:500;line-height:1.4;">${message}</span>
        </div>
        <button onclick="this.parentElement.remove()" style="background:none;border:none;color:white;font-size:1.2rem;cursor:pointer;padding:0;opacity:0.7;">✕</button>
        <div class="toast-progress" style="animation-duration:${duration}ms;"></div>
    `;
    toast.style.cssText = `
        position:fixed; top:24px; right:24px; max-width:420px; min-width:300px;
        padding:16px 20px; background:${colors[type] || colors.info};
        color:white; border-radius:12px; box-shadow:0 8px 32px rgba(0,0,0,0.3);
        z-index:10001; display:flex; align-items:center; gap:8px;
        animation:toastSlideIn 0.4s cubic-bezier(0.16,1,0.3,1);
        font-family:inherit; overflow:hidden;
    `;

    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'toastSlideOut 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

function showConfirm(message, { title = 'Confirm Action', confirmText = 'Yes, proceed', cancelText = 'Cancel', type = 'danger' } = {}) {
    return new Promise((resolve) => {
        const overlay = document.createElement('div');
        overlay.className = 'confirm-overlay';
        const accentColor = type === 'danger' ? 'var(--danger)' : 'var(--primary)';
        overlay.innerHTML = `
            <div class="confirm-modal">
                <div style="text-align:center;margin-bottom:20px;">
                    <div style="font-size:3rem;margin-bottom:12px;">${type === 'danger' ? '⚠️' : '❓'}</div>
                    <h3 style="margin:0 0 8px;font-size:1.25rem;color:var(--text-primary);">${title}</h3>
                    <p style="margin:0;color:var(--text-secondary);font-size:0.95rem;line-height:1.5;">${message}</p>
                </div>
                <div style="display:flex;gap:12px;">
                    <button class="confirm-btn-cancel">${cancelText}</button>
                    <button class="confirm-btn-ok" style="background:${accentColor};">${confirmText}</button>
                </div>
            </div>
        `;

        overlay.style.cssText = `
            position:fixed; inset:0; background:rgba(0,0,0,0.6); backdrop-filter:blur(4px);
            z-index:10002; display:flex; align-items:center; justify-content:center;
            animation:fadeIn 0.2s ease;
        `;

        const close = (result) => {
            overlay.style.animation = 'fadeOut 0.2s ease forwards';
            setTimeout(() => { overlay.remove(); resolve(result); }, 200);
        };

        overlay.querySelector('.confirm-btn-cancel').onclick = () => close(false);
        overlay.querySelector('.confirm-btn-ok').onclick = () => close(true);
        overlay.addEventListener('click', (e) => { if (e.target === overlay) close(false); });

        document.body.appendChild(overlay);
        overlay.querySelector('.confirm-btn-ok').focus();
    });
}

// Inject notification & modal styles
(function () {
    const s = document.createElement('style');
    s.textContent = `
        @keyframes toastSlideIn {
            from { transform:translateX(120%);opacity:0; }
            to   { transform:translateX(0);opacity:1; }
        }
        @keyframes toastSlideOut {
            from { transform:translateX(0);opacity:1; }
            to   { transform:translateX(120%);opacity:0; }
        }
        @keyframes fadeIn { from{opacity:0;} to{opacity:1;} }
        @keyframes fadeOut { from{opacity:1;} to{opacity:0;} }
        @keyframes progressShrink { from{width:100%;} to{width:0%;} }

        .toast-progress {
            position:absolute; bottom:0; left:0; height:3px;
            background:rgba(255,255,255,0.4); border-radius:0 0 12px 12px;
            animation:progressShrink linear forwards;
        }
        .confirm-modal {
            background:var(--bg-card); border:1px solid var(--glass-border);
            border-radius:16px; padding:32px; max-width:400px; width:90%;
            box-shadow:0 24px 64px rgba(0,0,0,0.4);
            animation:modalPop 0.3s cubic-bezier(0.16,1,0.3,1);
        }
        @keyframes modalPop {
            from { transform:scale(0.9);opacity:0; }
            to   { transform:scale(1);opacity:1; }
        }
        .confirm-btn-cancel, .confirm-btn-ok {
            flex:1; padding:12px 20px; border:none; border-radius:10px;
            font-weight:600; font-size:0.95rem; cursor:pointer; transition:all 0.2s;
            font-family:inherit;
        }
        .confirm-btn-cancel {
            background:var(--bg-tertiary); color:var(--text-primary);
            border:1px solid var(--glass-border);
        }
        .confirm-btn-cancel:hover { background:var(--bg-secondary); }
        .confirm-btn-ok { color:white; }
        .confirm-btn-ok:hover { filter:brightness(1.1); transform:translateY(-1px); }
    `;
    document.head.appendChild(s);
})();


// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function formatPrice(price) {
    return '$' + parseFloat(price).toFixed(2);
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// ============================================================================
// SMOOTH SCROLL
// ============================================================================

document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// ============================================================================
// FORM VALIDATION
// ============================================================================

function validateForm(formId) {
    const form = document.getElementById(formId);
    if (!form) return true;

    const inputs = form.querySelectorAll('[required]');
    let isValid = true;

    inputs.forEach(input => {
        if (!input.value.trim()) {
            input.style.borderColor = 'var(--danger)';
            isValid = false;
        } else {
            input.style.borderColor = 'var(--glass-border)';
        }
    });

    return isValid;
}

// ============================================================================
// ANIMATION KEYFRAMES (injected dynamically)
// ============================================================================

const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// ============================================================================
// MOBILE MENU (if needed in future)
// ============================================================================

function toggleMobileMenu() {
    const nav = document.querySelector('.navbar-nav');
    nav.classList.toggle('mobile-active');
}

// ============================================================================
// SEARCH ENHANCEMENTS
// ============================================================================

const searchInput = document.querySelector('input[name="search"]');
if (searchInput) {
    searchInput.addEventListener('input', debounce(function () {
        // Could add live search here
        console.log('Search:', this.value);
    }, 500));
}

console.log('🚗 AutoParts Pro - Loaded successfully!');
