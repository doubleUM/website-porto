// ============================================================================
// AUTOPARTS PRO — APEX // CLIENT TELEMETRY, GARAGE FITMENT, CART DRAWER & AI
// ============================================================================

const GARAGE_STORAGE_KEY = 'ap-garage-vehicle';

document.addEventListener('DOMContentLoaded', function () {
    initThemeToggle();
    initTelemetrySelects();
    initAddToCartButtons();
    initCartDrawerTrigger();
    initGarageSystem();
    initQuickViewKeyboard();
    initMechanicAssistant();
});

// ============================================================================
// 1. UNIFIED PORTFOLIO THEME TOGGLE
// ============================================================================

function initThemeToggle() {
    const themeToggle = document.getElementById('theme-toggle');
    const html = document.documentElement;
    if (!themeToggle) return;

    themeToggle.addEventListener('click', () => {
        const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        html.setAttribute('data-theme', next);
        localStorage.setItem('hub-theme', next);
    });
}

function toggleMobileMenu() {
    const drawer = document.getElementById('ap-mobile-drawer');
    if (drawer) drawer.classList.toggle('is-open');
}

// ============================================================================
// 2. "MY GARAGE" VEHICLE FITMENT ENGINE
// ============================================================================

function getGarageVehicles() {
    return Array.isArray(window.AP_GARAGE_VEHICLES) ? window.AP_GARAGE_VEHICLES : [];
}

function getSelectedGarageId() {
    return localStorage.getItem(GARAGE_STORAGE_KEY) || '';
}

function getSelectedGarageVehicle() {
    const id = getSelectedGarageId();
    if (!id) return null;
    return getGarageVehicles().find(v => v.id === id) || null;
}

function setGarageVehicle(vehicleId) {
    if (!vehicleId) {
        localStorage.removeItem(GARAGE_STORAGE_KEY);
    } else {
        localStorage.setItem(GARAGE_STORAGE_KEY, vehicleId);
    }
    refreshGarageUI();
    window.dispatchEvent(new CustomEvent('ap:garage-changed', {
        detail: { vehicle: getSelectedGarageVehicle() }
    }));
}

function evaluateFitment(compatibleCarsStr, vehicle) {
    if (!vehicle) return { status: 'none', label: '' };
    const hay = String(compatibleCarsStr || '').toLowerCase();
    if (!hay) return { status: 'mismatch', label: 'VERIFY FIT' };

    const isExact = (vehicle.exact_terms || []).some(t => hay.includes(t.toLowerCase()));
    if (isExact) {
        return { status: 'exact', label: `✓ EXACT FIT · ${vehicle.name.split(' ').slice(-1)[0].toUpperCase()}` };
    }

    const isUniversal = (vehicle.universal_terms || []).some(t => hay.includes(t.toLowerCase()));
    if (isUniversal) {
        return { status: 'universal', label: '◎ UNIVERSAL / PLATFORM FIT' };
    }

    return { status: 'mismatch', label: 'OTHER CHASSIS' };
}

function refreshGarageUI() {
    const vehicle = getSelectedGarageVehicle();

    // Navbar Pill
    const pill = document.getElementById('ap-garage-trigger');
    const navLabel = document.getElementById('ap-nav-garage-label');
    if (pill && navLabel) {
        if (vehicle) {
            pill.classList.add('has-vehicle');
            navLabel.textContent = vehicle.name;
        } else {
            pill.classList.remove('has-vehicle');
            navLabel.textContent = 'Select Ride';
        }
    }

    // AI Mechanic Header Context
    const aiCtx = document.getElementById('ai-garage-context');
    if (aiCtx) {
        aiCtx.textContent = vehicle
            ? `ACTIVE GARAGE // ${vehicle.name.toUpperCase()} (${vehicle.trim.toUpperCase()})`
            : 'NO GARAGE VEHICLE SET · ALL CHASSIS';
    }

    // Modal option highlights
    document.querySelectorAll('#ap-garage-modal-list .ap-garage-option').forEach(btn => {
        const id = btn.getAttribute('data-vehicle-id');
        btn.classList.toggle('is-active', Boolean(vehicle && vehicle.id === id));
    });

    // Update all product cards with [data-fitment-cars]
    document.querySelectorAll('[data-fitment-cars]').forEach(card => {
        const badge = card.querySelector('.ap-fit-badge');
        if (!badge) return;
        const compat = card.getAttribute('data-fitment-cars') || '';
        const res = evaluateFitment(compat, vehicle);
        badge.className = 'ap-fit-badge';
        if (res.status !== 'none') {
            badge.classList.add('is-visible', `is-${res.status}`);
            badge.textContent = res.label;
        } else {
            badge.textContent = '';
        }
    });
}

function initGarageSystem() {
    // Sync URL ?vehicle=... into My Garage if user navigated via vehicle filter
    const params = new URLSearchParams(window.location.search);
    const urlVehicle = params.get('vehicle');
    if (urlVehicle && getGarageVehicles().some(v => v.id === urlVehicle)) {
        localStorage.setItem(GARAGE_STORAGE_KEY, urlVehicle);
    }
    refreshGarageUI();
}

function openGarageModal() {
    const modal = document.getElementById('ap-garage-modal');
    if (modal) {
        modal.classList.add('is-open');
        refreshGarageUI();
    }
}

function closeGarageModal() {
    const modal = document.getElementById('ap-garage-modal');
    if (modal) modal.classList.remove('is-open');
}

function selectGarageFromModal(vehicleId) {
    setGarageVehicle(vehicleId);
    const v = getSelectedGarageVehicle();
    if (v) showNotification(`Parked ${v.name} in My Garage — fitment badges updated.`, 'success', 3200);
}

function clearGarageVehicle() {
    setGarageVehicle('');
    closeGarageModal();
    showNotification('Garage vehicle cleared.', 'info', 2500);
}

function shopForGarageVehicle() {
    const v = getSelectedGarageVehicle();
    closeGarageModal();
    if (v) {
        window.location.href = '/car-spareparts/products?vehicle=' + encodeURIComponent(v.id);
    } else {
        window.location.href = '/car-spareparts/products';
    }
}

// ============================================================================
// 3. CART API & SLIDE-OUT LIVE PIT-BOX DRAWER
// ============================================================================

function initCartDrawerTrigger() {
    const btn = document.getElementById('ap-cart-drawer-btn');
    if (!btn) return;
    btn.addEventListener('click', function (e) {
        // On the cart page itself, let it stay or open drawer cleanly
        e.preventDefault();
        openCartDrawer();
    });
}

function updateCartCount(count = null) {
    const badge = document.getElementById('cart-count');
    if (!badge) return;

    if (count !== null) {
        badge.textContent = count;
        badge.style.display = count > 0 ? 'inline-flex' : 'none';
    } else {
        fetch('/car-spareparts/api/cart/count')
            .then(r => r.json())
            .then(data => {
                badge.textContent = data.count;
                badge.style.display = data.count > 0 ? 'inline-flex' : 'none';
            });
    }
}

function initAddToCartButtons() {
    document.querySelectorAll('.add-to-cart-btn').forEach(button => {
        if (button.dataset.bound === '1') return;
        button.dataset.bound = '1';
        button.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            const productId = this.getAttribute('data-product-id');
            addToCart(productId, 1, true);
        });
    });
}

function addToCart(productId, quantity = 1, openDrawer = true) {
    fetch('/car-spareparts/api/cart/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            product_id: parseInt(productId, 10),
            quantity: parseInt(quantity, 10) || 1
        })
    })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                updateCartCount(data.cart_count);
                if (data.cart) renderCartDrawer(data.cart);
                if (openDrawer) {
                    openCartDrawer(false);
                } else {
                    showNotification('Component added to Pit Cart.', 'success');
                }
            } else {
                showNotification('Could not add component to cart.', 'error');
            }
        })
        .catch(() => {
            showNotification('Network error updating cart.', 'error');
        });
}

function openCartDrawer(shouldFetch = true) {
    const backdrop = document.getElementById('ap-cart-backdrop');
    const drawer = document.getElementById('ap-cart-drawer');
    if (!backdrop || !drawer) return;
    backdrop.classList.add('is-open');
    drawer.classList.add('is-open');
    document.body.style.overflow = 'hidden';
    if (shouldFetch) loadCartDrawer();
}

function closeCartDrawer() {
    const backdrop = document.getElementById('ap-cart-backdrop');
    const drawer = document.getElementById('ap-cart-drawer');
    if (!backdrop || !drawer) return;
    backdrop.classList.remove('is-open');
    drawer.classList.remove('is-open');
    document.body.style.overflow = '';
}

function loadCartDrawer() {
    fetch('/car-spareparts/api/cart')
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                updateCartCount(data.cart_count);
                renderCartDrawer(data);
            }
        })
        .catch(() => {
            const wrap = document.getElementById('ap-drawer-items');
            if (wrap) wrap.innerHTML = '<p style="text-align:center;padding:2rem 0;">Unable to load cart.</p>';
        });
}

function escHtml(str) {
    const d = document.createElement('div');
    d.textContent = str == null ? '' : String(str);
    return d.innerHTML;
}

function renderCartDrawer(cart) {
    const itemsWrap = document.getElementById('ap-drawer-items');
    const countEl = document.getElementById('ap-drawer-count');
    const subEl = document.getElementById('ap-drawer-subtotal');
    const taxEl = document.getElementById('ap-drawer-tax');
    const totEl = document.getElementById('ap-drawer-total');
    const shipText = document.getElementById('ap-drawer-ship-text');
    const shipPct = document.getElementById('ap-drawer-ship-pct');
    const shipFill = document.getElementById('ap-drawer-ship-fill');
    const checkoutBtn = document.getElementById('ap-drawer-checkout-btn');

    if (!itemsWrap) return;

    const items = cart.items || [];
    if (countEl) countEl.textContent = `(${cart.cart_count || 0})`;
    if (subEl) subEl.textContent = formatPrice(cart.subtotal || 0);
    if (taxEl) taxEl.textContent = formatPrice(cart.tax || 0);
    if (totEl) totEl.textContent = formatPrice(cart.total || 0);

    const threshold = cart.free_shipping_threshold || 100;
    const pct = Math.min(100, Math.round(((cart.subtotal || 0) / threshold) * 100));
    if (shipFill) shipFill.style.width = `${pct}%`;
    if (shipPct) shipPct.textContent = `${pct}%`;
    if (shipText) {
        shipText.innerHTML = cart.free_shipping_unlocked
            ? '<strong style="color:var(--accent);">✓ Priority Track-Day Dispatch Unlocked!</strong>'
            : `Add <strong>${formatPrice(cart.amount_to_free_shipping || 0)}</strong> for Priority Track-Day Dispatch`;
    }

    if (checkoutBtn) {
        checkoutBtn.style.pointerEvents = items.length ? 'auto' : 'none';
        checkoutBtn.style.opacity = items.length ? '1' : '0.45';
    }

    if (!items.length) {
        itemsWrap.innerHTML = `
            <div style="text-align:center; padding: 2.5rem 1rem;">
                <div class="mono" style="font-size:0.75rem; color:var(--text-muted); letter-spacing:0.12em; margin-bottom:0.5rem;">[ PIT-BOX EMPTY ]</div>
                <h4 style="font-size:1.1rem; text-transform:uppercase; margin-bottom:0.4rem;">No Components Staged</h4>
                <p style="font-size:0.85rem; margin-bottom:1.25rem;">Browse OEM+ brake, engine, suspension, or lighting hardware to build your order.</p>
                <a href="/car-spareparts/products" class="btn btn-outline btn-sm">Explore Catalog &rarr;</a>
            </div>
        `;
        return;
    }

    itemsWrap.innerHTML = items.map(item => {
        const img = (item.image_url && item.image_url.startsWith('/static/'))
            ? escHtml(item.image_url)
            : '/static/images/products/air-filter.webp';
        return `
            <div class="ap-drawer-item">
                <a href="/car-spareparts/product/${Number(item.product_id)}" class="ap-drawer-thumb">
                    <img src="${img}" alt="${escHtml(item.name)}" loading="lazy" decoding="async">
                </a>
                <div style="min-width:0;">
                    <div class="mono" style="font-size:0.65rem; color:var(--primary); text-transform:uppercase;">
                        ${escHtml(item.brand)} ${item.part_number ? '// ' + escHtml(item.part_number) : ''}
                    </div>
                    <a href="/car-spareparts/product/${Number(item.product_id)}" style="font-family:var(--font-display); font-weight:700; font-size:0.94rem; display:block; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                        ${escHtml(item.name)}
                    </a>
                    <div style="display:flex; align-items:center; gap:0.6rem; margin-top:0.45rem;">
                        <div class="quantity-control" style="height:28px;">
                            <button type="button" class="quantity-btn" style="width:26px;height:28px;font-size:0.85rem;" onclick="drawerChangeQty(${Number(item.id)}, ${Number(item.quantity) - 1})">−</button>
                            <span class="quantity-value" style="min-width:28px;font-size:0.78rem;">${Number(item.quantity)}</span>
                            <button type="button" class="quantity-btn" style="width:26px;height:28px;font-size:0.85rem;" onclick="drawerChangeQty(${Number(item.id)}, ${Number(item.quantity) + 1})">+</button>
                        </div>
                        <button type="button" onclick="drawerRemoveItem(${Number(item.id)})" style="background:none;border:none;color:var(--text-muted);font-family:var(--font-mono);font-size:0.68rem;cursor:pointer;text-transform:uppercase;">Remove</button>
                    </div>
                </div>
                <div class="mono" style="font-weight:700; font-size:0.92rem; text-align:right;">
                    ${formatPrice(item.line_total)}
                </div>
            </div>
        `;
    }).join('');
}

function drawerChangeQty(itemId, newQty) {
    if (newQty <= 0) {
        drawerRemoveItem(itemId);
        return;
    }
    fetch('/car-spareparts/api/cart/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item_id: itemId, quantity: newQty })
    })
        .then(r => r.json())
        .then(data => {
            if (data.success && data.cart) {
                updateCartCount(data.cart_count);
                renderCartDrawer(data.cart);
                if (window.location.pathname === '/car-spareparts/cart') {
                    window.location.reload();
                }
            }
        });
}

function drawerRemoveItem(itemId) {
    fetch('/car-spareparts/api/cart/remove/' + itemId, { method: 'DELETE' })
        .then(r => r.json())
        .then(data => {
            if (data.success && data.cart) {
                updateCartCount(data.cart_count);
                renderCartDrawer(data.cart);
                if (window.location.pathname === '/car-spareparts/cart') {
                    window.location.reload();
                }
            }
        });
}

// ============================================================================
// 4. QUICK-VIEW TECHNICAL DATASHEET MODAL
// ============================================================================

let modalQty = 1;
let modalStock = 0;
let modalProductId = null;

function openProductModal(productId) {
    const modal = document.getElementById('product-modal');
    const body = document.getElementById('pd-body');
    if (!modal || !body) return;

    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
    body.innerHTML = '<div style="padding:4rem 0;text-align:center;font-family:var(--font-mono);color:var(--text-muted);">LOADING COMPONENT TELEMETRY...</div>';
    modalQty = 1;
    modalProductId = productId;

    fetch('/car-spareparts/api/product/' + productId)
        .then(r => r.json())
        .then(p => {
            modalStock = p.stock || 0;
            const inStock = modalStock > 0;
            const imgUrl = (p.image_url && p.image_url.startsWith('/static/'))
                ? escHtml(p.image_url)
                : '/static/images/products/air-filter.webp';

            const vehicle = getSelectedGarageVehicle();
            const fit = evaluateFitment(p.compatible_cars || '', vehicle);
            let fitBanner = '';
            if (vehicle) {
                const colorMap = {
                    exact: 'var(--accent)',
                    universal: 'var(--secondary)',
                    mismatch: 'var(--text-muted)'
                };
                fitBanner = `
                    <div style="padding:0.65rem 0.85rem; background:var(--bg-tertiary); border-left:3px solid ${colorMap[fit.status] || 'var(--primary)'}; border-radius:var(--radius-xs); margin-bottom:1rem; font-family:var(--font-mono); font-size:0.75rem;">
                        <strong>${escHtml(fit.label)}</strong> &mdash; Checked against ${escHtml(vehicle.name)}
                    </div>
                `;
            }

            const askPrompt = `Tell me about ${p.name} (SKU ${p.part_number || 'N/A'}) by ${p.brand || 'OEM'} — what vehicles does it fit and when should it be replaced?`;

            body.innerHTML = `
                <div style="background:var(--bg-stage); height:250px; display:flex; align-items:center; justify-content:center; padding:1.75rem; border-bottom:1px solid var(--glass-border);">
                    <img src="${imgUrl}" alt="${escHtml(p.name)}" style="max-height:100%; max-width:100%; object-fit:contain;" decoding="async">
                </div>
                <div style="padding:1.65rem 1.85rem;">
                    <div style="display:flex; gap:0.45rem; flex-wrap:wrap; margin-bottom:0.75rem;">
                        <span class="badge badge-neutral">${escHtml(p.brand || 'OEM')} // ${escHtml(p.part_number || 'SPEC')}</span>
                        ${inStock
                            ? `<span class="badge badge-success">IN STOCK · ${Number(modalStock)} UNITS</span>`
                            : `<span class="badge badge-danger">OUT OF STOCK</span>`}
                        ${p.featured ? '<span class="badge badge-warning">TRACK FEATURED</span>' : ''}
                    </div>

                    <h2 style="font-size:1.6rem; text-transform:uppercase; margin-bottom:0.35rem;">${escHtml(p.name)}</h2>
                    <div class="mono" style="font-size:1.45rem; font-weight:700; color:var(--primary); margin-bottom:0.9rem;">
                        ${formatPrice(p.price || 0)}
                    </div>

                    ${fitBanner}

                    <p style="font-size:0.92rem; line-height:1.6; margin-bottom:1.1rem;">
                        ${escHtml(p.description || 'Precision automotive replacement component.')}
                    </p>

                    <div class="ap-spec-matrix">
                        <div class="ap-spec-box">
                            <div class="ap-spec-lbl">Manufacturer</div>
                            <div class="ap-spec-val">${escHtml(p.brand || '—')}</div>
                        </div>
                        <div class="ap-spec-box">
                            <div class="ap-spec-lbl">Part Number</div>
                            <div class="ap-spec-val">${escHtml(p.part_number || '—')}</div>
                        </div>
                        <div class="ap-spec-box">
                            <div class="ap-spec-lbl">System Category</div>
                            <div class="ap-spec-val">${escHtml(p.category_name || '—')}</div>
                        </div>
                        <div class="ap-spec-box">
                            <div class="ap-spec-lbl">Compatible Chassis</div>
                            <div class="ap-spec-val">${escHtml(p.compatible_cars || 'Universal')}</div>
                        </div>
                        ${p.specifications ? `
                        <div class="ap-spec-box is-wide">
                            <div class="ap-spec-lbl">Technical Specifications</div>
                            <div class="ap-spec-val">${escHtml(p.specifications)}</div>
                        </div>` : ''}
                    </div>

                    <div style="display:flex; gap:0.65rem; flex-wrap:wrap; align-items:center; margin-top:1.25rem;">
                        <div class="quantity-control">
                            <button type="button" class="quantity-btn" onclick="modalChangeQty(-1)">−</button>
                            <span class="quantity-value" id="modal-qty">1</span>
                            <button type="button" class="quantity-btn" onclick="modalChangeQty(1)">+</button>
                        </div>
                        ${inStock
                            ? `<button type="button" class="btn btn-primary" style="flex:1;" onclick="modalAddToCart()">+ Add to Pit Cart</button>`
                            : `<button type="button" class="btn btn-primary" style="flex:1;" disabled>Out of Stock</button>`}
                        <a href="/car-spareparts/product/${Number(p.id)}" class="btn btn-outline">Full Datasheet</a>
                    </div>

                    <div style="margin-top:0.85rem; text-align:right;">
                        <button type="button" id="modal-ask-ai-btn" style="background:none;border:none;color:var(--text-secondary);font-family:var(--font-mono);font-size:0.72rem;cursor:pointer;text-decoration:underline;">
                            Ask AI Mechanic about compatibility &rarr;
                        </button>
                    </div>
                </div>
            `;

            const askBtn = document.getElementById('modal-ask-ai-btn');
            if (askBtn) {
                askBtn.onclick = () => {
                    closeProductModal();
                    askMechanicPrompt(askPrompt);
                };
            }
        })
        .catch(() => {
            body.innerHTML = '<div style="padding:3rem;text-align:center;">Failed to load component telemetry.</div>';
        });
}

function closeProductModal() {
    const modal = document.getElementById('product-modal');
    if (!modal || modal.style.display === 'none') return;
    modal.style.display = 'none';
    document.body.style.overflow = '';
}

function modalChangeQty(delta) {
    modalQty = Math.max(1, Math.min(modalStock || 1, modalQty + delta));
    const el = document.getElementById('modal-qty');
    if (el) el.textContent = modalQty;
}

function modalAddToCart() {
    if (!modalProductId) return;
    const id = modalProductId;
    const qty = modalQty;
    closeProductModal();
    addToCart(id, qty, true);
}

function initQuickViewKeyboard() {
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            closeProductModal();
            closeCartDrawer();
            closeGarageModal();
        }
    });
}

// ============================================================================
// 5. UPGRADED AI PIT-CREW MECHANIC ASSISTANT
// ============================================================================

let apChatHistory = '';

function initMechanicAssistant() {
    const btn = document.getElementById('ai-chat-btn');
    const modal = document.getElementById('ai-chat-modal');
    const closeBtn = document.getElementById('ai-chat-close');
    const clearBtn = document.getElementById('ai-chat-clear');
    const input = document.getElementById('ai-input');
    const sendBtn = document.getElementById('ai-send-btn');

    if (!btn || !modal) return;

    btn.addEventListener('click', () => {
        modal.classList.toggle('is-open');
        if (modal.classList.contains('is-open') && input) input.focus();
    });

    if (closeBtn) {
        closeBtn.addEventListener('click', () => modal.classList.remove('is-open'));
    }

    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            apChatHistory = '';
            const msgWrap = document.getElementById('ai-messages');
            if (msgWrap) {
                msgWrap.innerHTML = `
                    <div class="ai-msg ai-msg-other">
                        <div class="ai-msg-bubble">
                            <strong>Diagnostic memory cleared.</strong> Ready for a new symptom, chassis query, or part comparison.
                        </div>
                    </div>
                `;
            }
        });
    }

    if (sendBtn) sendBtn.addEventListener('click', () => sendMechanicMessage());
    if (input) {
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') sendMechanicMessage();
        });
    }
}

function openMechanicChat() {
    const modal = document.getElementById('ai-chat-modal');
    const input = document.getElementById('ai-input');
    if (modal) {
        modal.classList.add('is-open');
        if (input) input.focus();
    }
}

function askMechanicPrompt(promptText) {
    const modal = document.getElementById('ai-chat-modal');
    const input = document.getElementById('ai-input');
    if (!modal || !input) return;
    modal.classList.add('is-open');
    input.value = promptText;
    sendMechanicMessage();
}

function formatMechanicMarkdown(text) {
    let html = escHtml(text);
    html = html.replace(/`([^`]+)`/g, '<code style="font-family:var(--font-mono);background:var(--bg-secondary);padding:1px 5px;border-radius:3px;">$1</code>');
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
    html = html.replace(/\n/g, '<br>');
    return html;
}

async function sendMechanicMessage() {
    const msgContainer = document.getElementById('ai-messages');
    const input = document.getElementById('ai-input');
    const sendBtn = document.getElementById('ai-send-btn');
    if (!input || !msgContainer) return;

    const text = input.value.trim();
    if (!text) return;

    input.value = '';
    input.disabled = true;
    if (sendBtn) sendBtn.disabled = true;

    const mine = document.createElement('div');
    mine.className = 'ai-msg ai-msg-mine';
    mine.innerHTML = `<div class="ai-msg-bubble">${formatMechanicMarkdown(text)}</div>`;
    msgContainer.appendChild(mine);
    msgContainer.scrollTop = msgContainer.scrollHeight;

    apChatHistory += `User: ${text}\n`;

    const typing = document.createElement('div');
    typing.id = 'ai-typing';
    typing.className = 'mono';
    typing.style.cssText = 'font-size:0.72rem;color:var(--text-muted);padding:0 4px;';
    typing.textContent = 'SCANNING INVENTORY & FITMENT TELEMETRY...';
    msgContainer.appendChild(typing);
    msgContainer.scrollTop = msgContainer.scrollHeight;

    const vehicle = getSelectedGarageVehicle();
    const garageLabel = vehicle ? `${vehicle.name} (${vehicle.trim})` : '';

    try {
        const res = await fetch('/car-spareparts/api/ask', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: text,
                history: apChatHistory,
                garage_vehicle: garageLabel
            })
        });
        const data = await res.json();
        typing.remove();

        const reply = document.createElement('div');
        reply.className = 'ai-msg ai-msg-other';
        const msgText = data.success ? data.response : (data.message || 'Diagnostic service unavailable.');
        reply.innerHTML = `<div class="ai-msg-bubble">${formatMechanicMarkdown(msgText)}</div>`;
        msgContainer.appendChild(reply);
        msgContainer.scrollTop = msgContainer.scrollHeight;

        if (data.success) apChatHistory += `AI: ${data.response}\n`;
    } catch {
        typing.remove();
        const err = document.createElement('div');
        err.className = 'ai-msg ai-msg-other';
        err.innerHTML = `<div class="ai-msg-bubble">Telemetry link interrupted. Please retry in a moment.</div>`;
        msgContainer.appendChild(err);
    } finally {
        input.disabled = false;
        if (sendBtn) sendBtn.disabled = false;
        input.focus();
    }
}

// ============================================================================
// 6. TELEMETRY TOAST NOTIFICATIONS & CONFIRMATION DIALOGS
// ============================================================================

function showNotification(message, type = 'success', duration = 4200) {
    document.querySelectorAll('.toast-notification').forEach(n => n.remove());

    const borderColors = {
        success: 'var(--accent)',
        error: 'var(--danger)',
        warning: 'var(--secondary)',
        info: 'var(--info)'
    };
    const tags = {
        success: 'OK // CONFIRMED',
        error: 'ERR // FAULT',
        warning: 'WARN // NOTICE',
        info: 'SYS // INFO'
    };

    const toast = document.createElement('div');
    toast.className = 'toast-notification';
    toast.style.cssText = `
        position:fixed; top:20px; right:20px; max-width:400px; min-width:290px;
        padding:14px 16px; background:var(--bg-secondary); color:var(--text-primary);
        border:1px solid var(--border-strong); border-left:4px solid ${borderColors[type] || borderColors.info};
        border-radius:var(--radius-sm); box-shadow:var(--shadow-xl); z-index:10010;
        display:flex; align-items:flex-start; justify-content:space-between; gap:12px;
        animation:fadeInUp 0.25s ease;
    `;
    toast.innerHTML = `
        <div>
            <div style="font-family:var(--font-mono);font-size:0.65rem;letter-spacing:0.1em;color:${borderColors[type] || borderColors.info};margin-bottom:2px;">
                ${tags[type] || tags.info}
            </div>
            <div style="font-size:0.88rem;font-weight:500;line-height:1.4;">${escHtml(message)}</div>
        </div>
        <button type="button" onclick="this.parentElement.remove()" style="background:none;border:none;color:var(--text-muted);font-size:1.1rem;cursor:pointer;line-height:1;">&times;</button>
    `;

    document.body.appendChild(toast);
    setTimeout(() => {
        if (toast.parentElement) toast.remove();
    }, duration);
}

function showConfirm(message, { title = 'Confirm Action', confirmText = 'Confirm', cancelText = 'Cancel', type = 'danger' } = {}) {
    return new Promise((resolve) => {
        const overlay = document.createElement('div');
        overlay.style.cssText = `
            position:fixed; inset:0; background:rgba(5,7,11,0.72); backdrop-filter:blur(5px);
            z-index:10011; display:flex; align-items:center; justify-content:center; padding:1rem;
        `;
        const btnClass = type === 'danger' ? 'btn btn-danger' : 'btn btn-primary';
        overlay.innerHTML = `
            <div style="background:var(--bg-secondary);border:1px solid var(--border-strong);border-radius:var(--radius-md);padding:1.75rem;max-width:420px;width:100%;box-shadow:var(--shadow-xl);">
                <div class="mono" style="font-size:0.68rem;color:var(--primary);letter-spacing:0.12em;text-transform:uppercase;margin-bottom:0.35rem;">AUTHORIZATION REQUIRED</div>
                <h3 style="font-size:1.25rem;text-transform:uppercase;margin-bottom:0.5rem;">${escHtml(title)}</h3>
                <p style="font-size:0.9rem;margin-bottom:1.35rem;">${escHtml(message)}</p>
                <div style="display:flex;gap:0.65rem;justify-content:flex-end;">
                    <button type="button" class="btn btn-outline btn-sm" id="ap-cfm-cancel">${escHtml(cancelText)}</button>
                    <button type="button" class="${btnClass} btn-sm" id="ap-cfm-ok">${escHtml(confirmText)}</button>
                </div>
            </div>
        `;

        const close = (val) => {
            overlay.remove();
            resolve(val);
        };

        overlay.querySelector('#ap-cfm-cancel').onclick = () => close(false);
        overlay.querySelector('#ap-cfm-ok').onclick = () => close(true);
        overlay.addEventListener('click', (e) => { if (e.target === overlay) close(false); });

        document.body.appendChild(overlay);
    });
}

function formatPrice(price) {
    return '$' + parseFloat(price || 0).toFixed(2);
}

// ============================================================================
// 7. CUSTOM PIT-WALL TELEMETRY SELECT DROPDOWNS (.ap-select)
// ============================================================================

function parseOptionParts(opt) {
    const explicitTitle = opt.getAttribute('data-title');
    const explicitMeta = opt.getAttribute('data-meta');
    if (explicitTitle !== null) {
        return { title: explicitTitle, meta: explicitMeta || '' };
    }
    const raw = (opt.textContent || '').trim().replace(/^—\s*|\s*—$/g, '');
    const m = raw.match(/^(.*?)\s*\(([^)]+)\)\s*$/);
    if (m) {
        return { title: m[1].trim(), meta: m[2].trim() };
    }
    return { title: raw, meta: '' };
}

function closeAllTelemetrySelects(exceptWrap = null) {
    document.querySelectorAll('.ap-select.is-open').forEach(wrap => {
        if (wrap !== exceptWrap) {
            wrap.classList.remove('is-open');
            const trig = wrap.querySelector('.ap-select-trigger');
            if (trig) trig.setAttribute('aria-expanded', 'false');
        }
    });
}

function initTelemetrySelects() {
    const selects = document.querySelectorAll('select.form-control');
    if (!selects.length) return;

    const nativeValueDesc = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');

    selects.forEach(sel => {
        if (sel.dataset.apEnhanced === '1') return;
        sel.dataset.apEnhanced = '1';

        const isCompact = sel.classList.contains('ap-select-compact') || sel.id === 'pdp-garage-select';
        const wrap = document.createElement('div');
        wrap.className = 'ap-select' + (isCompact ? ' ap-select--compact' : '');

        sel.parentNode.insertBefore(wrap, sel);
        wrap.appendChild(sel);
        sel.classList.add('ap-native-select-hidden');
        sel.tabIndex = -1;

        const options = Array.from(sel.options);
        const hasSearch = options.length >= 7;

        const trigger = document.createElement('button');
        trigger.type = 'button';
        trigger.className = 'ap-select-trigger';
        trigger.setAttribute('aria-haspopup', 'listbox');
        trigger.setAttribute('aria-expanded', 'false');
        trigger.innerHTML = `
            <span class="ap-select-lhs">
                <span class="ap-select-pip" aria-hidden="true"></span>
                <span class="ap-select-val-group">
                    <span class="ap-select-main"></span>
                    <span class="ap-select-meta" style="display:none;"></span>
                </span>
            </span>
            <span class="ap-select-arrow" aria-hidden="true">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                    <path d="m6 9 6 6 6-6"/>
                </svg>
            </span>
        `;

        const menu = document.createElement('div');
        menu.className = 'ap-select-menu';
        menu.setAttribute('role', 'listbox');

        let searchInput = null;
        if (hasSearch) {
            const searchWrap = document.createElement('div');
            searchWrap.className = 'ap-select-search-wrap';
            searchWrap.innerHTML = `
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
                </svg>
                <input type="text" class="ap-select-search" placeholder="Filter make, model or chassis..." autocomplete="off">
            `;
            menu.appendChild(searchWrap);
            searchInput = searchWrap.querySelector('.ap-select-search');
        }

        const list = document.createElement('div');
        list.className = 'ap-select-list';
        menu.appendChild(list);

        const emptyMsg = document.createElement('div');
        emptyMsg.className = 'ap-select-empty';
        emptyMsg.style.display = 'none';
        emptyMsg.textContent = 'No matching chassis';
        list.appendChild(emptyMsg);

        const optionButtons = options.map((opt, idx) => {
            const { title, meta } = parseOptionParts(opt);
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'ap-select-option' + (opt.value === '' && idx === 0 ? ' is-placeholder-opt' : '');
            btn.setAttribute('role', 'option');
            btn.dataset.val = opt.value;
            btn.dataset.search = `${title} ${meta}`.toLowerCase();
            btn.innerHTML = `
                <span class="ap-opt-lhs">
                    <span class="ap-opt-dot" aria-hidden="true"></span>
                    <span class="ap-opt-title">${escHtml(title)}</span>
                </span>
                <span class="ap-opt-rhs">
                    ${meta ? `<span class="ap-opt-meta">${escHtml(meta)}</span>` : ''}
                    <span class="ap-opt-check" aria-hidden="true">✓</span>
                </span>
            `;

            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const changed = sel.value !== opt.value;
                nativeValueDesc.set.call(sel, opt.value);
                syncUI();
                closeMenu();
                trigger.focus();
                if (changed) {
                    sel.dispatchEvent(new Event('change', { bubbles: true }));
                }
            });
            list.appendChild(btn);
            return btn;
        });

        wrap.appendChild(trigger);
        wrap.appendChild(menu);

        const mainEl = trigger.querySelector('.ap-select-main');
        const metaEl = trigger.querySelector('.ap-select-meta');
        let focusedIndex = -1;

        function syncUI() {
            const activeOpt = sel.options[sel.selectedIndex] || sel.options[0];
            if (!activeOpt) return;
            const { title, meta } = parseOptionParts(activeOpt);
            const hasVal = activeOpt.value !== '';

            wrap.classList.toggle('has-selection', hasVal);
            mainEl.textContent = title;
            if (meta && (!isCompact || hasVal)) {
                metaEl.textContent = meta;
                metaEl.style.display = 'inline-block';
            } else {
                metaEl.style.display = 'none';
            }

            optionButtons.forEach((btn, i) => {
                const isSel = btn.dataset.val === activeOpt.value;
                btn.classList.toggle('is-selected', isSel);
                btn.setAttribute('aria-selected', isSel ? 'true' : 'false');
                if (isSel) focusedIndex = i;
            });
        }

        function filterOptions(q) {
            const term = String(q || '').trim().toLowerCase();
            let visibleCount = 0;
            optionButtons.forEach(btn => {
                const match = !term || btn.dataset.search.includes(term);
                btn.style.display = match ? '' : 'none';
                if (match) visibleCount++;
            });
            emptyMsg.style.display = visibleCount === 0 ? 'block' : 'none';
        }

        function setFocusedOption(idx) {
            const visible = optionButtons.filter(b => b.style.display !== 'none');
            if (!visible.length) return;
            const clamped = ((idx % visible.length) + visible.length) % visible.length;
            optionButtons.forEach(b => b.classList.remove('is-focused'));
            const target = visible[clamped];
            target.classList.add('is-focused');
            target.scrollIntoView({ block: 'nearest' });
            focusedIndex = clamped;
        }

        function openMenu() {
            closeAllTelemetrySelects(wrap);
            wrap.classList.add('is-open');
            trigger.setAttribute('aria-expanded', 'true');
            if (searchInput) {
                searchInput.value = '';
                filterOptions('');
                setTimeout(() => searchInput.focus(), 20);
            }
            const selBtn = optionButtons.find(b => b.classList.contains('is-selected'));
            if (selBtn) selBtn.scrollIntoView({ block: 'nearest' });
        }

        function closeMenu() {
            wrap.classList.remove('is-open');
            trigger.setAttribute('aria-expanded', 'false');
            optionButtons.forEach(b => b.classList.remove('is-focused'));
        }

        trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            if (wrap.classList.contains('is-open')) closeMenu();
            else openMenu();
        });

        wrap.addEventListener('keydown', (e) => {
            const isOpen = wrap.classList.contains('is-open');
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                if (!isOpen) openMenu();
                else setFocusedOption(focusedIndex + 1);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                if (!isOpen) openMenu();
                else setFocusedOption(focusedIndex - 1);
            } else if (e.key === 'Enter') {
                if (isOpen) {
                    const focused = list.querySelector('.ap-select-option.is-focused');
                    if (focused && focused.style.display !== 'none') {
                        e.preventDefault();
                        focused.click();
                    }
                }
            } else if (e.key === 'Escape' && isOpen) {
                e.preventDefault();
                e.stopPropagation();
                closeMenu();
                trigger.focus();
            }
        });

        if (searchInput) {
            searchInput.addEventListener('click', e => e.stopPropagation());
            searchInput.addEventListener('input', function () {
                filterOptions(this.value);
                setFocusedOption(0);
            });
        }

        // Intercept programmatic `selectEl.value = ...` so UI stays synced automatically
        if (nativeValueDesc && nativeValueDesc.get && nativeValueDesc.set) {
            Object.defineProperty(sel, 'value', {
                get() {
                    return nativeValueDesc.get.call(this);
                },
                set(newVal) {
                    nativeValueDesc.set.call(this, newVal);
                    syncUI();
                },
                configurable: true
            });
        }

        sel._apSync = syncUI;
        syncUI();
    });

    document.addEventListener('click', (e) => {
        if (!e.target.closest('.ap-select')) {
            closeAllTelemetrySelects();
        }
    });
}
