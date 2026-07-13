        // =====================================================
        // 1. PRODUCT DATA (chargé depuis Django)
        // =====================================================
        const products = window.PRODUCTS_DATA || [];
        const API_BASE = window.API_BASE || '';
        
        // =====================================================
        // 2. CAROUSEL
        // =====================================================
        let currentSlide = 0;
        const slides = document.querySelectorAll('.carousel-slide');
        const dotsContainer = document.getElementById('carouselDots');
        
        slides.forEach((_, i) => {
            const dot = document.createElement('button');
            if (i === 0) dot.classList.add('active');
            dot.addEventListener('click', () => goToSlide(i));
            dotsContainer.appendChild(dot);
        });
        
        function goToSlide(index) {
            slides.forEach(s => s.classList.remove('active'));
            slides[index].classList.add('active');
            document.querySelectorAll('.carousel-dots button').forEach((d, i) => {
                d.classList.toggle('active', i === index);
            });
            currentSlide = index;
        }
        
        function changeSlide(direction) {
            let newIndex = currentSlide + direction;
            if (newIndex < 0) newIndex = slides.length - 1;
            if (newIndex >= slides.length) newIndex = 0;
            goToSlide(newIndex);
        }
        
        document.getElementById('carouselPrev').addEventListener('click', () => changeSlide(-1));
        document.getElementById('carouselNext').addEventListener('click', () => changeSlide(1));
        
        let carouselInterval = setInterval(() => changeSlide(1), 5000);
        const carousel = document.getElementById('heroCarousel');
        carousel.addEventListener('mouseenter', () => clearInterval(carouselInterval));
        carousel.addEventListener('mouseleave', () => {
            carouselInterval = setInterval(() => changeSlide(1), 5000);
        });
        
        // Hero buttons
        document.getElementById('heroBtn1').addEventListener('click', () => { showToast('🔍 Découvrez notre catalogue !'); });
        document.getElementById('heroBtn2').addEventListener('click', () => { showToast('🔥 Promos exceptionnelles sur les PC !'); });
        document.getElementById('heroBtn3').addEventListener('click', () => { showToast('💳 Paiement sécurisé disponible'); });
        
        // =====================================================
        // 3. PRODUCT RENDER
        // =====================================================
        let cart = [];
        // Identifie le panier "anonyme" côté backend (persistant via localStorage).
        let cartSessionKey =
            localStorage.getItem("afripul_cart_session_key") ||
            (window.CART_SESSION_KEY ? window.CART_SESSION_KEY : "");
        if (!cartSessionKey) {
            try {
                cartSessionKey = crypto.randomUUID();
            } catch (e) {
                cartSessionKey = "sess_" + Math.random().toString(36).slice(2);
            }
            localStorage.setItem("afripul_cart_session_key", cartSessionKey);
        }
        let filtered = [...products];
        const grid = document.getElementById('productGrid');
        const cartItems = document.getElementById('cartItems');
        const cartCount = document.getElementById('cartCount');
        const cartItemCount = document.getElementById('cartItemCount');
        const cartSubtotal = document.getElementById('cartSubtotal');
        const cartTotal = document.getElementById('cartTotal');
        const toast = document.getElementById('toast');
        const toastMsg = document.getElementById('toastMsg');
        
        function render() {
            grid.innerHTML = '';
            if (filtered.length === 0) {
                grid.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:50px 0;color:#565959;"><i class="fas fa-search" style="font-size:2.5rem;opacity:0.3;margin-bottom:12px;"></i><p>Aucun produit trouvé</p></div>`;
                return;
            }
            filtered.forEach(p => {
                const div = document.createElement('div');
                div.className = 'product';
                let badge = '';
                if (p.badge) {
                    let cls = 'badge';
                    if (p.badge === 'Promo') cls += ' promo';
                    else if (p.badge === 'New') cls += ' new';
                    else if (p.badge === 'Best') cls += ' best';
                    badge = `<span class="${cls}">${p.badge}</span>`;
                }
                const old = p.oldPrice ? `<span class="old">${p.oldPrice.toLocaleString()} FCFA</span>` : '';
                const stars = '★'.repeat(Math.floor(p.rating)) + '☆'.repeat(5 - Math.floor(p.rating));
                div.innerHTML = `
                    ${badge}
                    <div class="img" style="background-image:url('${p.image}');">
                        <button class="quick">Vue rapide</button>
                    </div>
                    <div class="name">${p.name}</div>
                    <div class="cat">${p.category.replace('-',' ')}</div>
                    <div class="rating">${stars} <span>(${p.reviews})</span></div>
                    <div class="prices"><span class="current">${p.price.toLocaleString()} FCFA</span> ${old}</div>
                    <div class="actions">
                        <button class="add" data-id="${p.id}"><i class="fas fa-plus"></i> Ajouter</button>
                        <button class="wish"><i class="far fa-heart"></i></button>
                    </div>
                `;
                grid.appendChild(div);
            });
            document.querySelectorAll('.add').forEach(b => b.addEventListener('click', function() {
                const id = parseInt(this.dataset.id);
                const p = products.find(x => x.id === id);
                if (p) addToCart(p);
            }));
            // Quick view
            document.querySelectorAll('.quick').forEach(b => b.addEventListener('click', function() {
                const img = this.closest('.img').style.backgroundImage;
                showToast('🔍 Vue rapide : ' + this.closest('.product').querySelector('.name').textContent);
            }));
            // Wishlist
            document.querySelectorAll('.wish').forEach(b => b.addEventListener('click', function() {
                this.classList.toggle('active');
                if (this.classList.contains('active')) {
                    this.innerHTML = '<i class="fas fa-heart" style="color:#cc0c39;"></i>';
                    showToast('❤️ Ajouté à vos favoris');
                } else {
                    this.innerHTML = '<i class="far fa-heart"></i>';
                }
            }));
        }
        
        // =====================================================
        // 4. FILTERS
        // =====================================================
        function applyFilters() {
            const q = document.getElementById('search').value.toLowerCase().trim();
            const cat = document.getElementById('category').value;
            const max = parseFloat(document.getElementById('priceMax').value) || Infinity;
            const sort = document.getElementById('sort').value;
            filtered = products.filter(p => {
                return p.name.toLowerCase().includes(q) && (cat === 'all' || p.category === cat) && p.price <= max;
            });
            if (sort === 'price-asc') filtered.sort((a,b) => a.price - b.price);
            else if (sort === 'price-desc') filtered.sort((a,b) => b.price - a.price);
            else if (sort === 'popular') filtered.sort((a,b) => b.reviews - a.reviews);
            else filtered.sort((a,b) => a.id - b.id);
            render();
        }
        
        document.getElementById('search').addEventListener('input', applyFilters);
        document.getElementById('searchBtn').addEventListener('click', applyFilters);
        document.getElementById('category').addEventListener('change', applyFilters);
        document.getElementById('sort').addEventListener('change', applyFilters);
        document.getElementById('priceMax').addEventListener('input', applyFilters);
        document.getElementById('resetBtn').addEventListener('click', () => {
            document.getElementById('search').value = '';
            document.getElementById('category').value = 'all';
            document.getElementById('sort').value = 'default';
            document.getElementById('priceMax').value = '';
            applyFilters();
            showToast('🔄 Filtres réinitialisés');
        });
        
        document.getElementById('viewAllLink').addEventListener('click', (e) => {
            e.preventDefault();
            showToast('📦 Catalogue complet bientôt disponible');
        });
        
        document.getElementById('wishlistBtn').addEventListener('click', () => {
            showToast('❤️ Vos favoris (simulation)');
        });
        
        // =====================================================
        // 5. CART
        // =====================================================
        function csrfHeaders() {
            return {
                "Content-Type": "application/json",
                "X-CSRFToken": window.CSRF_TOKEN || ""
            };
        }

        async function syncCart() {
            try {
                const res = await fetch(`${API_BASE}/api/cart/?session_key=${encodeURIComponent(cartSessionKey)}`, {
                    method: "GET",
                    headers: { "Accept": "application/json" }
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.error || "Erreur panier");
                cart = data.items || [];
                updateCart();
            } catch (e) {
                // En cas de problème, on garde l'affichage local (vide au démarrage).
            }
        }

        async function apiUpdateCartItem(productId, quantityDelta) {
            const res = await fetch(`${API_BASE}/api/cart/items/`, {
                method: "POST",
                headers: csrfHeaders(),
                body: JSON.stringify({
                    session_key: cartSessionKey,
                    product_id: productId,
                    quantity_delta: quantityDelta
                })
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || "Erreur panier");
            cart = data.items || [];
            updateCart();
            return data;
        }

        async function apiClearCart() {
            const res = await fetch(`${API_BASE}/api/cart/clear/`, {
                method: "POST",
                headers: csrfHeaders(),
                body: JSON.stringify({ session_key: cartSessionKey })
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || "Erreur panier");
            cart = data.items || [];
            updateCart();
            return data;
        }

        async function addToCart(p) {
            try {
                await apiUpdateCartItem(p.id, 1);
                showToast(`${p.name} ajouté au panier !`);
            } catch (e) {
                showToast("Impossible d'ajouter au panier.");
            }
        }
        
        function removeFromCart(id) {
            const item = cart.find(x => x.id === id);
            if (!item) return;
            // Décrémente jusqu'à suppression côté backend.
            updateQty(id, -item.qty);
        }
        
        async function updateQty(id, delta) {
            try {
                await apiUpdateCartItem(id, delta);
            } catch (e) {
                showToast("Erreur lors de la mise à jour du panier.");
            }
        }
        
        function updateCart() {
            const count = cart.reduce((s, x) => s + x.qty, 0);
            const total = cart.reduce((s, x) => s + x.price * x.qty, 0);
            cartCount.textContent = count;
            cartItemCount.textContent = count;
            cartSubtotal.textContent = total.toLocaleString() + ' FCFA';
            cartTotal.textContent = total.toLocaleString() + ' FCFA';
            if (cart.length === 0) {
                cartItems.innerHTML = `<div class="cart-empty"><i class="fas fa-shopping-cart"></i><p>Votre panier est vide</p></div>`;
            } else {
                cartItems.innerHTML = cart.map(x => `
                    <div class="cart-item">
                        <div class="img" style="background-image:url('${x.image}');"></div>
                        <div class="info">
                            <h4>${x.name}</h4>
                            <div class="price">${x.price.toLocaleString()} FCFA</div>
                            <div class="qty">
                                <button onclick="updateQty(${x.id}, -1)">−</button>
                                <span class="num">${x.qty}</span>
                                <button onclick="updateQty(${x.id}, 1)">+</button>
                                <button class="remove" onclick="removeFromCart(${x.id})"><i class="fas fa-trash-alt"></i></button>
                            </div>
                        </div>
                    </div>
                `).join('');
            }
        }
        
        function showToast(msg) {
            toastMsg.textContent = msg;
            toast.classList.add('show');
            clearTimeout(window.toastTimer);
            window.toastTimer = setTimeout(() => toast.classList.remove('show'), 3500);
        }
        
        // =====================================================
        // 6. CART UI
        // =====================================================
        function openCart() {
            document.getElementById('cartSidebar').classList.add('open');
            document.getElementById('cartOverlay').classList.add('active');
            document.body.style.overflow = 'hidden';
            syncCart();
        }
        function closeCart() {
            document.getElementById('cartSidebar').classList.remove('open');
            document.getElementById('cartOverlay').classList.remove('active');
            document.body.style.overflow = '';
        }
        
        document.getElementById('openCartBtn').addEventListener('click', openCart);
        document.getElementById('closeCartBtn').addEventListener('click', closeCart);
        document.getElementById('cartOverlay').addEventListener('click', closeCart);
        document.getElementById('continueBtn').addEventListener('click', closeCart);
        
        // =====================================================
        // 7. CHECKOUT avec ENVOI D'EMAIL (simulation)
        // =====================================================
        document.getElementById('checkoutBtn').addEventListener('click', async function() {
            if (cart.length === 0) {
                showToast('Votre panier est vide !');
                return;
            }
            const total = cart.reduce((s, x) => s + x.price * x.qty, 0);
            const payload = {
                customer_name: userData.name || 'Client AFRIPUL',
                customer_email: userData.email || 'client@afripul.tg',
                customer_phone: userData.phone || '+22890000000',
                customer_address: userData.address || 'Lomé, Togo',
                items: cart.map(x => ({ product_id: x.id, quantity: x.qty }))
            };

            try {
                const response = await fetch(`${API_BASE}/api/orders/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': window.CSRF_TOKEN || ''
                    },
                    body: JSON.stringify(payload)
                });
                const data = await response.json();
                if (!response.ok) {
                    showToast(data.error || 'Erreur lors de la commande');
                    return;
                }
                showToast(`✅ Commande #${data.order_number} validée ! Total : ${total.toLocaleString()} FCFA`);
                addChatMessage('bot', `✅ Votre commande <strong>#${data.order_number}</strong> de <strong>${total.toLocaleString()} FCFA</strong> a été enregistrée.<br>Un agent vous contactera sous 24h.`);
                try {
                    await apiClearCart();
                } catch (e) {
                    cart = [];
                    updateCart();
                }
                closeCart();
            } catch (err) {
                showToast('Impossible de valider la commande. Réessayez.');
            }
        });
        
        // =====================================================
        // 8. WHATSAPP
        // =====================================================
        document.getElementById('whatsappBtn').addEventListener('click', function() {
            window.open('https://wa.me/22890000000?text=Bonjour%20AFRIPUL%2C%20je%20souhaite%20passer%20une%20commande.', '_blank');
        });
        
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                closeCart();
                closeChat();
            }
        });
        
        // =====================================================
        // 9. CHAT BOT (API /api/chat/ + Gemini)
        // =====================================================
        const chatWindow = document.getElementById('chatWindow');
        const chatOverlay = document.getElementById('chatOverlay');
        const chatMessages = document.getElementById('chatMessages');
        const chatInput = document.getElementById('chatInput');
        const chatSendBtn = document.getElementById('chatSendBtn');
        const chatBotBtn = document.getElementById('chatBotBtn');
        const closeChatBtn = document.getElementById('closeChatBtn');

        function openChat() {
            chatWindow.classList.add('open');
            chatOverlay.classList.add('active');
            chatBotBtn.style.display = 'none';
            document.body.style.overflow = 'hidden';
            chatInput.focus();
        }
        function closeChat() {
            chatWindow.classList.remove('open');
            chatOverlay.classList.remove('active');
            chatBotBtn.style.display = 'flex';
            document.body.style.overflow = '';
        }
        chatBotBtn.addEventListener('click', openChat);
        closeChatBtn.addEventListener('click', closeChat);
        chatOverlay.addEventListener('click', closeChat);

        function addChatMessage(type, text) {
            const div = document.createElement('div');
            div.className = `msg ${type}`;
            div.innerHTML = text.replace(/\n/g, '<br>');
            chatMessages.appendChild(div);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        function addTypingIndicator() {
            const div = document.createElement('div');
            div.className = 'msg bot';
            div.id = 'typingIndicator';
            div.innerHTML = '<span class="typing"></span><span class="typing"></span><span class="typing"></span>';
            chatMessages.appendChild(div);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
        function removeTypingIndicator() {
            const el = document.getElementById('typingIndicator');
            if (el) el.remove();
        }

        async function sendChatMessage() {
            const text = chatInput.value.trim();
            if (!text) return;

            chatInput.value = '';
            addChatMessage('user', text);
            addTypingIndicator();
            chatSendBtn.disabled = true;
            chatInput.disabled = true;

            try {
                const res = await fetch(`${API_BASE}/api/chat/`, {
                    method: 'POST',
                    headers: csrfHeaders(),
                    body: JSON.stringify({
                        message: text,
                        session_key: cartSessionKey,
                    }),
                });

                let data;
                try {
                    data = await res.json();
                } catch (parseErr) {
                    removeTypingIndicator();
                    addChatMessage('bot', 'Le serveur chat n\'est pas à jour. Redémarrez : <code>docker compose restart web</code>');
                    return;
                }

                removeTypingIndicator();

                if (!res.ok) {
                    addChatMessage('bot', data.error || 'Erreur serveur. Réessayez.');
                    return;
                }

                addChatMessage('bot', data.reply);

                if (data.actions && data.actions.some(a => a.type === 'cart_updated')) {
                    await syncCart();
                    const orderAction = data.actions.find(a => a.type === 'order_created');
                    if (orderAction) {
                        showToast(`✅ Commande #${orderAction.order_number} validée !`);
                    } else {
                        showToast('Produit(s) ajouté(s) au panier');
                    }
                }
            } catch (e) {
                removeTypingIndicator();
                addChatMessage('bot', 'Impossible de contacter l\'assistant. Réessayez dans un instant.');
            } finally {
                chatSendBtn.disabled = false;
                chatInput.disabled = false;
                chatInput.focus();
            }
        }

        chatSendBtn.addEventListener('click', sendChatMessage);
        chatInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendChatMessage();
        });

        setTimeout(() => {
            if (!chatWindow.classList.contains('open')) {
                openChat();
            }
        }, 4000);
        
        // =====================================================
        // 10. INIT
        // =====================================================
        applyFilters();
        syncCart();