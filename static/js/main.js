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
                showNotification('✅ Added to cart!', 'success');
            } else {
                showNotification('❌ Failed to add to cart', 'error');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showNotification('❌ An error occurred', 'error');
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
// NOTIFICATIONS
// ============================================================================

function showNotification(message, type = 'success') {
    // Create notification element
    const notification = document.createElement('div');
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 100px;
        right: 20px;
        padding: 1rem 1.5rem;
        background: ${type === 'success' ? 'var(--success)' : 'var(--danger)'};
        color: white;
        border-radius: var(--radius-md);
        box-shadow: var(--shadow-lg);
        z-index: 10000;
        font-weight: 600;
        animation: slideIn 0.3s ease;
    `;

    document.body.appendChild(notification);

    // Remove after 3 seconds
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => {
            document.body.removeChild(notification);
        }, 300);
    }, 3000);
}

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
