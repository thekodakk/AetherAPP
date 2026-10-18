/**
 * ===================================================================
 * AstralPaws / AetherAPP - Client-Side Interactive Engine
 * ===================================================================
 */

const state = {
    currentUser: null,
    activeView: 'friends', // 'friends', 'chat', 'nexus-explore', 'saved'
    activeConversationId: null,
    activeServerId: null,
    activeChannelId: null,
    activeNexusId: null,
    conversations: [],
    servers: [],
    friendsData: { friends: [], pending_incoming: [], pending_outgoing: [], blocked: [] },
    socket: null,
    replyToMessage: null,
    selectedFiles: [],
    typingTimeout: null,
    verifyEmail: ''
};

// --- DOM Initialization ---
document.addEventListener('DOMContentLoaded', async () => {
    initLucide();
    setupOtpInputBehavior();
    setupUrlHandlers();
    await checkAuthStatus();
});

function initLucide() {
    if (window.lucide) {
        lucide.createIcons();
    }
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    const iconName = type === 'success' ? 'check-circle' : (type === 'error' ? 'alert-circle' : 'info');
    toast.innerHTML = `<i data-lucide="${iconName}"></i> <span>${message}</span>`;
    container.appendChild(toast);
    initLucide();

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function setAppLoading(isLoading) {
    const loader = document.getElementById('app-loader');
    if (!loader) return;
    if (isLoading) {
        loader.classList.remove('hidden');
        loader.style.opacity = '1';
        loader.style.visibility = 'visible';
    } else {
        loader.style.opacity = '0';
        loader.style.visibility = 'hidden';
        setTimeout(() => loader.classList.add('hidden'), 400);
    }
}

// ===================================================================
// 1. AUTHENTICATION & SESSION MANAGEMENT
// ===================================================================

async function checkAuthStatus() {
    try {
        const res = await fetch('/api/auth/status');
        const data = await res.json();
        
        if (data.logged_in && data.user) {
            state.currentUser = data.user;
            showMainApp();
        } else {
            showAuthScreen();
        }
    } catch (err) {
        console.error("Auth check failed:", err);
        showAuthScreen();
    } finally {
        setAppLoading(false);
    }
}

function showAuthScreen() {
    document.getElementById('main-view').classList.add('hidden');
    document.getElementById('auth-view').classList.remove('hidden');
    initLucide();
}

function showMainApp() {
    document.getElementById('auth-view').classList.add('hidden');
    document.getElementById('main-view').classList.remove('hidden');
    
    updateUserBarUI();
    initSocketConnection();
    loadConversations();
    loadServers();
    showFriendsDashboard();
    initLucide();
}

function switchAuthTab(tab) {
    const loginForm = document.getElementById('form-login');
    const registerForm = document.getElementById('form-register');
    const verifyStep = document.getElementById('auth-verify-step');
    const twofaStep = document.getElementById('auth-2fa-step');
    const tabLogin = document.getElementById('tab-btn-login');
    const tabReg = document.getElementById('tab-btn-register');
    const alertBox = document.getElementById('auth-alert');

    if (alertBox) alertBox.classList.add('hidden');
    verifyStep.classList.add('hidden');
    twofaStep.classList.add('hidden');

    if (tab === 'login') {
        loginForm.classList.remove('hidden');
        registerForm.classList.add('hidden');
        tabLogin.classList.add('active');
        tabReg.classList.remove('active');
    } else {
        loginForm.classList.add('hidden');
        registerForm.classList.remove('hidden');
        tabReg.classList.add('active');
        tabLogin.classList.remove('active');
    }
    initLucide();
}

function setAuthAlert(message, type = 'error') {
    const alertBox = document.getElementById('auth-alert');
    const msgElem = document.getElementById('auth-alert-msg');
    if (!alertBox || !msgElem) return;

    msgElem.textContent = message;
    alertBox.className = `auth-alert ${type === 'success' ? 'success' : ''}`;
    alertBox.classList.remove('hidden');
    initLucide();
}

function fillDemo(username, password) {
    switchAuthTab('login');
    document.getElementById('login-identifier').value = username;
    document.getElementById('login-password').value = password;
}

function togglePasswordVisibility(fieldId, btn) {
    const input = document.getElementById(fieldId);
    if (!input) return;
    if (input.type === 'password') {
        input.type = 'text';
        btn.innerHTML = '<i data-lucide="eye-off"></i>';
    } else {
        input.type = 'password';
        btn.innerHTML = '<i data-lucide="eye"></i>';
    }
    initLucide();
}

// Handle Login Form Submit
async function handleLogin(e) {
    e.preventDefault();
    const identifier = document.getElementById('login-identifier').value.trim();
    const password = document.getElementById('login-password').value;
    const remember = document.getElementById('login-remember').checked;
    const submitBtn = document.getElementById('btn-login-submit');

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span>Giriş yapılıyor...</span>';

    try {
        const res = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: identifier, password, remember })
        });
        const data = await res.json();

        if (res.ok && data.success) {
            if (data.requires_2fa) {
                // Open 2FA step
                state.temp2faToken = data.temp_token;
                document.getElementById('form-login').classList.add('hidden');
                document.getElementById('auth-2fa-step').classList.remove('hidden');
                initLucide();
            } else {
                state.currentUser = data.user;
                showToast(`Tekrar hoş geldin, ${data.user.display_name || data.user.username}!`, 'success');
                showMainApp();
            }
        } else if (res.status === 403 && data.requires_verification) {
            state.verifyEmail = data.email;
            document.getElementById('verify-target-email').textContent = data.email;
            document.getElementById('form-login').classList.add('hidden');
            document.getElementById('auth-verify-step').classList.remove('hidden');
            setAuthAlert('Lütfen hesabınızı doğrulamak için e-postanıza gönderilen kodu girin.', 'error');
            initLucide();
        } else {
            setAuthAlert(data.message || 'Giriş yapılamadı. Bilgilerinizi kontrol edin.');
        }
    } catch (err) {
        setAuthAlert('Sunucu ile bağlantı kurulamadı.');
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<span>Giriş Yap</span><i data-lucide="arrow-right"></i>';
        initLucide();
    }
}

// Handle Registration Form Submit
async function handleRegister(e) {
    e.preventDefault();
    const email = document.getElementById('reg-email').value.trim();
    const username = document.getElementById('reg-username').value.trim();
    const displayName = document.getElementById('reg-display-name').value.trim();
    const password = document.getElementById('reg-password').value;
    const passwordConfirm = document.getElementById('reg-password-confirm').value;
    const submitBtn = document.getElementById('btn-reg-submit');

    if (password !== passwordConfirm) {
        setAuthAlert('Şifreler eşleşmiyor!');
        return;
    }

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span>Kayıt oluşturuluyor...</span>';

    try {
        const res = await fetch('/api/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, username, display_name: displayName, password, password_confirm: passwordConfirm })
        });
        const data = await res.json();

        if (res.ok && data.success) {
            state.verifyEmail = data.email || email;
            document.getElementById('verify-target-email').textContent = state.verifyEmail;
            document.getElementById('form-register').classList.add('hidden');
            document.getElementById('auth-verify-step').classList.remove('hidden');
            setAuthAlert('Doğrulama kodunuz e-postanıza gönderildi!', 'success');
            initLucide();
        } else {
            setAuthAlert(data.message || 'Kayıt işlemi başarısız.');
        }
    } catch (err) {
        setAuthAlert('Sunucu ile bağlantı kurulamadı.');
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<span>Hesap Oluştur</span><i data-lucide="sparkles"></i>';
        initLucide();
    }
}

// OTP Input Key Navigation
function setupOtpInputBehavior() {
    const boxes = document.querySelectorAll('.otp-box');
    boxes.forEach((box, idx) => {
        box.addEventListener('input', (e) => {
            if (box.value.length === 1 && idx < boxes.length - 1) {
                boxes[idx + 1].focus();
            }
        });
        box.addEventListener('keydown', (e) => {
            if (e.key === 'Backspace' && !box.value && idx > 0) {
                boxes[idx - 1].focus();
            } else if (e.key === 'Enter') {
                submitOtpCode();
            }
        });
    });
}

// Submit OTP Code
async function submitOtpCode() {
    const boxes = document.querySelectorAll('.otp-box');
    let code = '';
    boxes.forEach(b => code += b.value.trim());

    if (code.length < 6) {
        setAuthAlert('Lütfen 6 haneli kodu eksiksiz girin.');
        return;
    }

    try {
        const res = await fetch('/api/verify-email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: state.verifyEmail, code, remember: true })
        });
        const data = await res.json();

        if (res.ok && data.success) {
            state.currentUser = data.user;
            showToast('E-posta adresiniz başarıyla doğrulandı!', 'success');
            showMainApp();
        } else {
            setAuthAlert(data.message || 'Geçersiz doğrulama kodu.');
        }
    } catch (err) {
        setAuthAlert('Doğrulama sırasında hata oluştu.');
    }
}

// Resend OTP Code
async function handleResendVerification() {
    const resendBtn = document.getElementById('btn-resend-otp');
    const countdown = document.getElementById('resend-countdown');
    if (!state.verifyEmail) return;

    resendBtn.disabled = true;
    try {
        const res = await fetch('/api/resend-verification', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: state.verifyEmail })
        });
        const data = await res.json();
        if (data.success) {
            showToast(data.message || 'Yeni doğrulama kodu gönderildi.', 'success');
            let timeLeft = 60;
            countdown.classList.remove('hidden');
            countdown.textContent = `(${timeLeft}s)`;
            const timer = setInterval(() => {
                timeLeft--;
                countdown.textContent = `(${timeLeft}s)`;
                if (timeLeft <= 0) {
                    clearInterval(timer);
                    resendBtn.disabled = false;
                    countdown.classList.add('hidden');
                }
            }, 1000);
        } else {
            setAuthAlert(data.message);
            resendBtn.disabled = false;
        }
    } catch (err) {
        setAuthAlert('Kod gönderilemedi.');
        resendBtn.disabled = false;
    }
}

// Submit 2FA Code
async function submit2FACode() {
    const code = document.getElementById('twofa-code-input').value.trim();
    const trustDevice = document.getElementById('twofa-trust-device').checked;

    if (!code) {
        setAuthAlert('Lütfen 2FA güvenlik kodunu girin.');
        return;
    }

    try {
        const res = await fetch('/api/login/2fa', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ temp_token: state.temp2faToken, code, trust_device: trustDevice })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            state.currentUser = data.user;
            showToast('Giriş başarılı!', 'success');
            showMainApp();
        } else {
            setAuthAlert(data.message || 'Geçersiz 2FA kodu.');
        }
    } catch (err) {
        setAuthAlert('2FA doğrulaması başarısız.');
    }
}

// Logout
async function handleLogout() {
    try {
        await fetch('/api/logout', { method: 'POST' });
    } catch (e) {}
    state.currentUser = null;
    if (state.socket) state.socket.disconnect();
    closeModal('modal-settings');
    showAuthScreen();
    showToast('Çıkış yapıldı.', 'info');
}

// URL Handler for email token links
function setupUrlHandlers() {
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token');
    if (token) {
        // Auto verify via token
        fetch(`/api/verify-email?token=${token}`, { method: 'POST', headers: { 'Content-Type': 'application/json' } })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showToast('E-posta bağlantınız doğrulandı! Oturum açılıyor...', 'success');
                    window.history.replaceState({}, document.title, "/");
                    checkAuthStatus();
                }
            });
    }
}

// ===================================================================
// 2. SOCKET.IO REALTIME EVENTS
// ===================================================================

function initSocketConnection() {
    if (state.socket) state.socket.disconnect();
    
    state.socket = io({ transports: ['websocket', 'polling'] });

    state.socket.on('connect', () => {
        console.log('Socket.IO Connected to AstralPaws engine!');
    });

    state.socket.on('receive_message', (msg) => {
        handleIncomingMessage(msg);
    });

    state.socket.on('reaction_updated', (data) => {
        updateMessageReactionsInUI(data.message_id, data.reactions);
    });

    state.socket.on('message_edited', (msg) => {
        updateEditedMessageInUI(msg);
    });

    state.socket.on('message_deleted', (data) => {
        handleDeletedMessageInUI(data.message_id);
    });

    state.socket.on('user_typing', (data) => {
        if (data.conversation_id === state.activeConversationId && data.user_id !== state.currentUser.id) {
            const indicator = document.getElementById('typing-indicator');
            const text = document.getElementById('typing-text');
            if (indicator && text) {
                text.textContent = `${data.username} yazıyor...`;
                indicator.classList.remove('hidden');
                clearTimeout(state.typingTimeout);
                state.typingTimeout = setTimeout(() => indicator.classList.add('hidden'), 3000);
            }
        }
    });

    state.socket.on('user_stop_typing', (data) => {
        if (data.conversation_id === state.activeConversationId) {
            const indicator = document.getElementById('typing-indicator');
            if (indicator) indicator.classList.add('hidden');
        }
    });

    state.socket.on('conversation_updated', (data) => {
        loadConversations();
    });
}

// ===================================================================
// 3. NAVIGATION & VIEW SWITCHING
// ===================================================================

function openHomeView() {
    state.activeServerId = null;
    state.activeNexusId = null;
    
    document.querySelectorAll('.rail-item').forEach(b => b.classList.remove('active'));
    document.getElementById('rail-btn-home').classList.add('active');

    document.getElementById('sidebar-home').classList.remove('hidden');
    document.getElementById('sidebar-server').classList.add('hidden');
    document.getElementById('sidebar-nexus').classList.add('hidden');

    showFriendsDashboard();
}

function openNexusExploreView() {
    document.querySelectorAll('.rail-item').forEach(b => b.classList.remove('active'));
    document.getElementById('rail-btn-nexus').classList.add('active');

    hideAllWorkspaceViews();
    document.getElementById('view-nexus-explore').classList.remove('hidden');
    loadNexusExplore();
    initLucide();
}

function showFriendsDashboard() {
    state.activeView = 'friends';
    hideAllWorkspaceViews();
    document.getElementById('view-friends-dashboard').classList.remove('hidden');
    document.querySelectorAll('.sidebar-nav-item').forEach(b => b.classList.remove('active'));
    document.getElementById('btn-nav-friends').classList.add('active');
    loadFriendsDashboard();
    initLucide();
}

function showSavedMessagesView() {
    state.activeView = 'saved';
    hideAllWorkspaceViews();
    document.getElementById('view-saved-messages').classList.remove('hidden');
    document.querySelectorAll('.sidebar-nav-item').forEach(b => b.classList.remove('active'));
    document.getElementById('btn-nav-saved').classList.add('active');
    loadSavedMessages();
    initLucide();
}

function hideAllWorkspaceViews() {
    document.getElementById('view-friends-dashboard').classList.add('hidden');
    document.getElementById('view-chat').classList.add('hidden');
    document.getElementById('view-nexus-explore').classList.add('hidden');
    document.getElementById('view-saved-messages').classList.add('hidden');
}

function updateUserBarUI() {
    if (!state.currentUser) return;
    const dn = document.getElementById('user-bar-display-name');
    const cs = document.getElementById('user-bar-custom-status');
    const avatar = document.getElementById('user-bar-avatar');
    const placeholder = document.getElementById('user-bar-placeholder');
    const railAvatar = document.getElementById('rail-avatar-img');
    const railPlaceholder = document.getElementById('rail-avatar-placeholder');

    if (dn) dn.textContent = state.currentUser.display_name || state.currentUser.username;
    if (cs) cs.textContent = state.currentUser.custom_status || '✨ AstralPaws';

    const char = (state.currentUser.display_name || state.currentUser.username || 'U')[0].toUpperCase();
    if (placeholder) placeholder.textContent = char;
    if (railPlaceholder) railPlaceholder.textContent = char;

    if (state.currentUser.avatar) {
        if (avatar) { avatar.src = state.currentUser.avatar; avatar.classList.remove('hidden'); }
        if (placeholder) placeholder.classList.add('hidden');
        if (railAvatar) { railAvatar.src = state.currentUser.avatar; railAvatar.classList.remove('hidden'); }
        if (railPlaceholder) railPlaceholder.classList.add('hidden');
    }
}

// ===================================================================
// 4. CONVERSATIONS & CHAT ENGINE
// ===================================================================

async function loadConversations() {
    try {
        const res = await fetch('/api/conversations');
        const data = await res.json();
        if (data.success) {
            state.conversations = data.conversations;
            renderConversationsList();
        }
    } catch (err) {
        console.error("Failed to load conversations:", err);
    }
}

function renderConversationsList() {
    const list = document.getElementById('conversations-list');
    if (!list) return;
    list.innerHTML = '';

    if (state.conversations.length === 0) {
        list.innerHTML = '<div style="padding: 12px; color: var(--text-dim); font-size: 12px; text-align: center;">Henüz aktif bir sohbet yok.</div>';
        return;
    }

    state.conversations.forEach(c => {
        const item = document.createElement('div');
        item.className = `conv-item ${c.id === state.activeConversationId ? 'active' : ''}`;
        item.onclick = () => openConversation(c.id, c.name);

        const avatarChar = (c.name || 'S')[0].toUpperCase();
        const avatarHtml = c.icon_url 
            ? `<img src="${c.icon_url}" alt="${c.name}">` 
            : `<div class="avatar-placeholder">${avatarChar}</div>`;

        const lastMsgSnippet = c.last_message ? c.last_message.text : 'Sohbet başlatıldı';

        item.innerHTML = `
            <div class="conv-avatar-wrap">
                ${avatarHtml}
                <div class="presence-dot ${c.other_user ? c.other_user.presence_status : 'online'}"></div>
            </div>
            <div class="conv-details">
                <div class="conv-name">${c.name}</div>
                <div class="conv-last-msg">${lastMsgSnippet}</div>
            </div>
            ${c.unread_count > 0 ? `<span class="counter-tag">${c.unread_count}</span>` : ''}
        `;
        list.appendChild(item);
    });
}

async function openConversation(convId, name = 'Sohbet') {
    state.activeConversationId = convId;
    state.activeChannelId = null;
    state.activeView = 'chat';

    hideAllWorkspaceViews();
    document.getElementById('view-chat').classList.remove('hidden');

    document.getElementById('chat-title').textContent = name;
    document.getElementById('chat-header-icon').innerHTML = '<i data-lucide="message-circle"></i>';
    document.getElementById('chat-topic').textContent = 'Doğrudan Mesaj';

    if (state.socket) {
        state.socket.emit('join_conversation', { conversation_id: convId });
    }

    renderConversationsList();
    await loadMessages(convId);
    initLucide();
}

async function loadMessages(convId) {
    const scrollArea = document.getElementById('chat-messages-scroll');
    if (!scrollArea) return;
    scrollArea.innerHTML = '<div style="text-align: center; padding: 20px; color: var(--text-dim);">Mesajlar yükleniyor...</div>';

    try {
        const res = await fetch(`/api/conversations/${convId}/messages`);
        const data = await res.json();
        if (data.success) {
            scrollArea.innerHTML = '';
            data.messages.forEach(m => {
                appendMessageToChat(m);
            });
            scrollArea.scrollTop = scrollArea.scrollHeight;
        }
    } catch (err) {
        scrollArea.innerHTML = '<div style="text-align: center; color: var(--accent-rose);">Mesajlar yüklenirken bir sorun oluştu.</div>';
    }
}

function appendMessageToChat(msg) {
    const scrollArea = document.getElementById('chat-messages-scroll');
    if (!scrollArea) return;

    const row = document.createElement('div');
    row.className = 'msg-row';
    row.id = `msg-row-${msg.id}`;

    const sender = msg.sender || {};
    const username = msg.username || sender.username || 'Astral User';
    const displayName = msg.display_name || sender.display_name || username;
    const avatar = sender.avatar;
    const avatarChar = displayName[0].toUpperCase();
    const timeStr = msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';

    let attachmentHtml = '';
    if (msg.attachments && msg.attachments.length > 0) {
        msg.attachments.forEach(att => {
            if (att.file_type === 'image' || att.file_url.match(/\.(jpeg|jpg|png|gif|webp)$/i)) {
                attachmentHtml += `<div style="margin-top: 8px; max-width: 400px;"><img src="${att.file_url}" style="border-radius: 8px; max-width: 100%; border: 1px solid var(--glass-border);"></div>`;
            } else {
                attachmentHtml += `<div style="margin-top: 6px; padding: 8px 12px; background: rgba(0,0,0,0.3); border-radius: 6px; display: inline-flex; align-items: center; gap: 8px;"><i data-lucide="file"></i> <a href="${att.file_url}" target="_blank" download>${att.file_name}</a></div>`;
            }
        });
    }

    row.innerHTML = `
        <div class="msg-avatar" onclick="openUserProfileModal(${sender.id || 0})">
            ${avatar ? `<img src="${avatar}">` : avatarChar}
        </div>
        <div class="msg-body">
            <div class="msg-meta">
                <span class="msg-username" style="color: ${msg.color || '#8b5cf6'}">${displayName}</span>
                ${sender.id === 1 ? '<span class="msg-badge">👑 Kurucu</span>' : ''}
                <span class="msg-time">${timeStr}</span>
                ${msg.is_edited ? '<span class="msg-time">(düzenlendi)</span>' : ''}
            </div>
            ${msg.reply_to ? `<div style="font-size: 12px; color: var(--text-dim); border-left: 2px solid var(--accent-purple); padding-left: 8px; margin-bottom: 4px;"><b>${msg.reply_to.display_name}:</b> ${msg.reply_to.text}</div>` : ''}
            <div class="msg-text" id="msg-text-${msg.id}">${escapeHtml(msg.text)}</div>
            ${attachmentHtml}
            <div class="msg-reactions" id="msg-reactions-${msg.id}"></div>
        </div>
        <div class="msg-actions-hover">
            <button class="btn-icon-xs" title="Tepki Ekle" onclick="quickReact(${msg.id}, '❤️')">❤️</button>
            <button class="btn-icon-xs" title="Tepki Ekle" onclick="quickReact(${msg.id}, '🚀')">🚀</button>
            <button class="btn-icon-xs" title="Yanıtla" onclick="setReply(${msg.id}, '${escapeHtml(displayName)}', '${escapeHtml(msg.text)}')"><i data-lucide="reply"></i></button>
            <button class="btn-icon-xs" title="Kaydet" onclick="saveMessageBookmark(${msg.id})"><i data-lucide="bookmark"></i></button>
            ${sender.id === state.currentUser.id ? `<button class="btn-icon-xs" title="Sil" onclick="deleteMessage(${msg.id})"><i data-lucide="trash-2"></i></button>` : ''}
        </div>
    `;

    scrollArea.appendChild(row);
    initLucide();
}

function handleIncomingMessage(msg) {
    if (msg.conversation_id === state.activeConversationId || msg.channel_id === state.activeChannelId) {
        appendMessageToChat(msg);
        const scrollArea = document.getElementById('chat-messages-scroll');
        if (scrollArea) scrollArea.scrollTop = scrollArea.scrollHeight;
    }
}

function handleSendMessage(e) {
    e.preventDefault();
    const textarea = document.getElementById('message-textarea');
    const text = textarea.value.trim();
    if (!text && state.selectedFiles.length === 0) return;

    if (state.socket) {
        const payload = {
            text: text,
            conversation_id: state.activeConversationId,
            channel_id: state.activeChannelId,
            reply_to_id: state.replyToMessage ? state.replyToMessage.id : null
        };
        state.socket.emit('send_message', payload);
    }

    textarea.value = '';
    textarea.style.height = 'auto';
    cancelReply();
}

function handleTextareaKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSendMessage(e);
    }
}

function handleTypingEvent() {
    if (state.socket && state.activeConversationId) {
        state.socket.emit('typing', { conversation_id: state.activeConversationId });
    }
}

function setReply(id, username, snippet) {
    state.replyToMessage = { id, username, snippet };
    const bar = document.getElementById('reply-preview-bar');
    const userElem = document.getElementById('reply-to-user-name');
    const snipElem = document.getElementById('reply-to-text-snippet');
    if (bar && userElem && snipElem) {
        userElem.textContent = username;
        snipElem.textContent = snippet;
        bar.classList.remove('hidden');
    }
}

function cancelReply() {
    state.replyToMessage = null;
    const bar = document.getElementById('reply-preview-bar');
    if (bar) bar.classList.add('hidden');
}

async function quickReact(messageId, emoji) {
    if (state.socket) {
        state.socket.emit('message_reaction', { message_id: messageId, emoji });
    }
}

async function saveMessageBookmark(messageId) {
    try {
        const res = await fetch(`/api/messages/${messageId}/save`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast('Mesaj kaydedilenlere eklendi!', 'success');
        }
    } catch (e) {}
}

async function deleteMessage(messageId) {
    if (!confirm('Bu mesajı silmek istediğine emin misin?')) return;
    if (state.socket) {
        state.socket.emit('delete_message', { message_id: messageId, scope: 'everyone' });
    }
}

function updateMessageReactionsInUI(messageId, reactions) {
    const rxBox = document.getElementById(`msg-reactions-${messageId}`);
    if (!rxBox) return;
    rxBox.innerHTML = '';
    for (const [emoji, users] of Object.entries(reactions)) {
        if (users && users.length > 0) {
            const pill = document.createElement('button');
            pill.className = 'reaction-pill';
            pill.innerHTML = `${emoji} <span>${users.length}</span>`;
            pill.onclick = () => quickReact(messageId, emoji);
            rxBox.appendChild(pill);
        }
    }
}

function handleDeletedMessageInUI(messageId) {
    const textElem = document.getElementById(`msg-text-${messageId}`);
    if (textElem) {
        textElem.innerHTML = '<span style="color: var(--text-dim); font-style: italic;">🚫 Bu mesaj silindi.</span>';
    }
}

// ===================================================================
// 5. FRIENDS SYSTEM
// ===================================================================

async function loadFriendsDashboard() {
    try {
        const res = await fetch('/api/friends/dashboard');
        const data = await res.json();
        if (data.success) {
            state.friendsData = data;
            document.getElementById('friends-tab-pending-count').textContent = data.counts.pending || 0;
            filterFriends('online');
        }
    } catch (err) {
        console.error("Friends dashboard fetch failed:", err);
    }
}

function filterFriends(tab) {
    const content = document.getElementById('friends-dashboard-content');
    if (!content) return;

    document.querySelectorAll('.filter-tab').forEach(b => b.classList.remove('active'));
    
    if (tab === 'online') {
        const onlineFriends = (state.friendsData.friends || []).filter(f => f.presence_status !== 'offline');
        renderFriendsList(onlineFriends, 'Çevrimiçi Arkadaşlar');
    } else if (tab === 'all') {
        renderFriendsList(state.friendsData.friends || [], 'Tüm Arkadaşlar');
    } else if (tab === 'pending') {
        renderPendingFriends();
    } else if (tab === 'blocked') {
        renderBlockedUsers();
    } else if (tab === 'add') {
        renderAddFriendPanel();
    }
}

function renderFriendsList(friends, title) {
    const content = document.getElementById('friends-dashboard-content');
    if (!content) return;

    if (friends.length === 0) {
        content.innerHTML = `<div style="text-align: center; padding: 40px; color: var(--text-dim);">Burada gösterilecek arkadaş bulunamadı.</div>`;
        return;
    }

    let html = `<h4 style="margin-bottom: 14px; color: var(--text-muted); font-size: 13px;">${title} (${friends.length})</h4><div class="friends-grid">`;
    friends.forEach(f => {
        const char = (f.display_name || f.username)[0].toUpperCase();
        html += `
            <div class="friend-card">
                <div class="friend-info">
                    <div class="conv-avatar-wrap">
                        ${f.avatar ? `<img src="${f.avatar}">` : char}
                        <div class="presence-dot ${f.presence_status}"></div>
                    </div>
                    <div>
                        <div style="font-weight: 600;">${f.display_name}</div>
                        <div style="font-size: 12px; color: var(--text-dim);">@${f.username}</div>
                    </div>
                </div>
                <div class="friend-actions">
                    <button class="btn-icon-sm" title="Mesaj Gönder" onclick="openDirectMessageWithUser(${f.user_id})"><i data-lucide="message-circle"></i></button>
                    <button class="btn-icon-sm" title="Profil" onclick="openUserProfileModal(${f.user_id})"><i data-lucide="user"></i></button>
                </div>
            </div>
        `;
    });
    html += '</div>';
    content.innerHTML = html;
    initLucide();
}

function renderPendingFriends() {
    const content = document.getElementById('friends-dashboard-content');
    const incoming = state.friendsData.pending_incoming || [];
    const outgoing = state.friendsData.pending_outgoing || [];

    let html = `
        <h4 style="margin-bottom: 14px; color: var(--text-muted); font-size: 13px;">Gelen İstekler (${incoming.length})</h4>
        <div class="friends-grid" style="margin-bottom: 24px;">
    `;
    if (incoming.length === 0) {
        html += `<div style="color: var(--text-dim); font-size: 13px;">Gelen bekleyen istek yok.</div>`;
    } else {
        incoming.forEach(f => {
            html += `
                <div class="friend-card">
                    <div class="friend-info">
                        <div style="font-weight: 600;">${f.display_name} <span style="font-size: 12px; color: var(--text-dim);">@${f.username}</span></div>
                    </div>
                    <div class="friend-actions">
                        <button class="btn-primary-sm" onclick="acceptFriend(${f.friendship_id})">Kabul Et</button>
                        <button class="btn-secondary-flat" onclick="rejectFriend(${f.friendship_id})">Reddet</button>
                    </div>
                </div>
            `;
        });
    }
    html += `</div><h4 style="margin-bottom: 14px; color: var(--text-muted); font-size: 13px;">Gönderilen İstekler (${outgoing.length})</h4><div class="friends-grid">`;
    if (outgoing.length === 0) {
        html += `<div style="color: var(--text-dim); font-size: 13px;">Gönderilen bekleyen istek yok.</div>`;
    } else {
        outgoing.forEach(f => {
            html += `
                <div class="friend-card">
                    <div class="friend-info">
                        <div style="font-weight: 600;">${f.display_name} <span style="font-size: 12px; color: var(--text-dim);">@${f.username}</span></div>
                    </div>
                    <div class="friend-actions">
                        <button class="btn-danger-flat" onclick="cancelFriendRequest(${f.friendship_id})">İptal</button>
                    </div>
                </div>
            `;
        });
    }
    html += `</div>`;
    content.innerHTML = html;
    initLucide();
}

function renderAddFriendPanel() {
    const content = document.getElementById('friends-dashboard-content');
    content.innerHTML = `
        <div class="add-friend-panel">
            <h3>Arkadaş Ekle</h3>
            <p>Arkadaşını kullanıcı adı, e-posta adresi veya Astral ID (astral_...) ile arayabilirsin.</p>
            <form class="add-friend-form" onsubmit="handleSendFriendRequest(event)">
                <input type="text" id="add-friend-identifier" required placeholder="Örn: thekodak veya astral_...">
                <button type="submit" class="btn-primary">Arkadaşlık İsteği Gönder</button>
            </form>
        </div>
    `;
}

async function handleSendFriendRequest(e) {
    e.preventDefault();
    const idInput = document.getElementById('add-friend-identifier');
    const identifier = idInput.value.trim();
    if (!identifier) return;

    try {
        const res = await fetch('/api/friends/request', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ identifier })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            showToast('Arkadaşlık isteği gönderildi!', 'success');
            idInput.value = '';
            loadFriendsDashboard();
        } else {
            showToast(data.message || 'İstek gönderilemedi.', 'error');
        }
    } catch (err) {
        showToast('Sunucu hatası.', 'error');
    }
}

async function acceptFriend(friendshipId) {
    try {
        const res = await fetch('/api/friends/accept', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ friendship_id: friendshipId })
        });
        const data = await res.json();
        if (data.success) {
            showToast('Arkadaşlık kabul edildi!', 'success');
            loadFriendsDashboard();
        }
    } catch (e) {}
}

async function rejectFriend(friendshipId) {
    try {
        await fetch('/api/friends/reject', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ friendship_id: friendshipId })
        });
        showToast('İstek reddedildi.', 'info');
        loadFriendsDashboard();
    } catch (e) {}
}

async function cancelFriendRequest(friendshipId) {
    try {
        await fetch('/api/friends/cancel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ friendship_id: friendshipId })
        });
        showToast('İstek iptal edildi.', 'info');
        loadFriendsDashboard();
    } catch (e) {}
}

async function openDirectMessageWithUser(userId) {
    try {
        const res = await fetch('/api/conversations/direct', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_user_id: userId })
        });
        const data = await res.json();
        if (data.success) {
            loadConversations();
            openConversation(data.conversation.id, data.conversation.name);
        }
    } catch (e) {}
}

// ===================================================================
// 6. NEXUS COMMUNITIES ENGINE
// ===================================================================

async function loadNexusExplore(category = 'all', query = '') {
    const grid = document.getElementById('nexus-cards-grid');
    if (!grid) return;
    grid.innerHTML = '<div style="text-align: center; grid-column: 1/-1; padding: 40px; color: var(--text-dim);">Nexus toplulukları keşfediliyor...</div>';

    let url = '/api/nexus/explore';
    const params = new URLSearchParams();
    if (category !== 'all') params.append('category', category);
    if (query) params.append('q', query);
    if (params.toString()) url += `?${params.toString()}`;

    try {
        const res = await fetch(url);
        const data = await res.json();
        if (data.success) {
            grid.innerHTML = '';
            if (data.nexuses.length === 0) {
                grid.innerHTML = '<div style="text-align: center; grid-column: 1/-1; padding: 40px; color: var(--text-dim);">Bu kriterlere uygun Nexus topluluğu bulunamadı.</div>';
                return;
            }
            data.nexuses.forEach(n => {
                const card = document.createElement('div');
                card.className = 'nexus-card';
                card.innerHTML = `
                    <div class="nexus-card-banner" style="background: ${n.banner_color || '#8b5cf6'};"></div>
                    <div class="nexus-card-body">
                        <div class="nexus-card-header">
                            <h3 class="nexus-card-title">${n.name}</h3>
                            <span class="nexus-header-badge">${n.category}</span>
                        </div>
                        <p class="nexus-card-desc">${n.description || 'AstralPaws evreninde bir Nexus topluluğu.'}</p>
                        <div style="display: flex; align-items: center; justify-content: space-between; margin-top: auto;">
                            <span style="font-size: 12px; color: var(--text-dim);"><i data-lucide="users"></i> ${n.member_count} Üye</span>
                            <button class="btn-primary-sm" onclick="joinNexusCommunity(${n.id}, ${n.requires_application})">
                                ${n.is_member ? 'Aç' : (n.requires_application ? 'Başvur' : 'Katıl')}
                            </button>
                        </div>
                    </div>
                `;
                grid.appendChild(card);
            });
            initLucide();
        }
    } catch (err) {
        grid.innerHTML = '<div style="text-align: center; color: var(--accent-rose);">Nexus toplulukları yüklenemedi.</div>';
    }
}

function filterNexusCategory(cat) {
    document.querySelectorAll('.category-pill').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    loadNexusExplore(cat, document.getElementById('nexus-search-input').value.trim());
}

function handleNexusSearch() {
    const q = document.getElementById('nexus-search-input').value.trim();
    loadNexusExplore('all', q);
}

async function joinNexusCommunity(nexusId, requiresApp) {
    if (requiresApp) {
        const text = prompt('Bu topluluğa katılmak için başvuru yazınızı girin:');
        if (!text) return;
        try {
            const res = await fetch(`/api/nexus/${nexusId}/apply`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ application_text: text })
            });
            const data = await res.json();
            showToast(data.message || 'Başvurunuz iletildi!', data.success ? 'success' : 'error');
        } catch (e) {}
    } else {
        try {
            const res = await fetch(`/api/nexus/${nexusId}/join`, { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                showToast('Topluluğa katıldın!', 'success');
                loadServers();
            }
        } catch (e) {}
    }
}

async function handleCreateNexus(e) {
    e.preventDefault();
    const name = document.getElementById('nexus-name-input').value.trim();
    const category = document.getElementById('nexus-cat-input').value;
    const desc = document.getElementById('nexus-desc-input').value.trim();
    const tags = document.getElementById('nexus-tags-input').value.split(',').map(t => t.trim());
    const reqApp = document.getElementById('nexus-app-required').checked;

    try {
        const res = await fetch('/api/nexus', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, category, description: desc, tags, requires_application: reqApp })
        });
        const data = await res.json();
        if (data.success) {
            showToast('Nexus topluluğu başarıyla oluşturuldu!', 'success');
            closeModal('modal-create-nexus');
            loadServers();
            openNexusExploreView();
        }
    } catch (e) {
        showToast('Nexus oluşturulamadı.', 'error');
    }
}

// ===================================================================
// 7. SERVERS & CHANNELS
// ===================================================================

async function loadServers() {
    try {
        const res = await fetch('/api/servers');
        const data = await res.json();
        if (data.success) {
            state.servers = data.servers;
            renderServersRail();
        }
    } catch (e) {}
}

function renderServersRail() {
    const list = document.getElementById('rail-servers-list');
    if (!list) return;
    list.innerHTML = '';

    state.servers.forEach(s => {
        const btn = document.createElement('button');
        btn.className = `rail-item ${s.id === state.activeServerId ? 'active' : ''}`;
        btn.dataset.tooltip = s.name;
        btn.onclick = () => openServerView(s.id);
        const char = s.name[0].toUpperCase();
        btn.innerHTML = `<div class="rail-pill"></div><div class="rail-icon">${char}</div>`;
        list.appendChild(btn);
    });
}

async function openServerView(serverId) {
    state.activeServerId = serverId;
    state.activeConversationId = null;
    state.activeNexusId = null;

    document.querySelectorAll('.rail-item').forEach(b => b.classList.remove('active'));
    renderServersRail();

    document.getElementById('sidebar-home').classList.add('hidden');
    document.getElementById('sidebar-server').classList.remove('hidden');
    document.getElementById('sidebar-nexus').classList.add('hidden');

    try {
        const res = await fetch(`/api/servers/${serverId}`);
        const data = await res.json();
        if (data.success) {
            document.getElementById('sidebar-server-name').textContent = data.server.name;
            renderServerChannels(data.server.channels || []);
        }
    } catch (e) {}
}

function renderServerChannels(channels) {
    const textList = document.getElementById('server-text-channels');
    const voiceList = document.getElementById('server-voice-channels');
    if (textList) textList.innerHTML = '';
    if (voiceList) voiceList.innerHTML = '';

    channels.forEach(ch => {
        const item = document.createElement('div');
        item.className = `channel-item ${ch.id === state.activeChannelId ? 'active' : ''}`;
        item.onclick = () => openChannel(ch);

        if (ch.type === 'text') {
            item.innerHTML = `<i data-lucide="hash"></i> <span>${ch.name}</span>`;
            if (textList) textList.appendChild(item);
        } else {
            item.innerHTML = `<i data-lucide="volume-2"></i> <span>${ch.name}</span>`;
            if (voiceList) voiceList.appendChild(item);
        }
    });

    if (channels.length > 0 && !state.activeChannelId) {
        openChannel(channels[0]);
    }
    initLucide();
}

function openChannel(channel) {
    state.activeChannelId = channel.id;
    state.activeView = 'chat';

    hideAllWorkspaceViews();
    document.getElementById('view-chat').classList.remove('hidden');
    document.getElementById('chat-title').textContent = channel.name;
    document.getElementById('chat-header-icon').innerHTML = channel.type === 'text' ? '<i data-lucide="hash"></i>' : '<i data-lucide="volume-2"></i>';
    document.getElementById('chat-topic').textContent = `#${channel.name} kanalındasınız.`;

    if (state.socket) {
        state.socket.emit('join_chat_channel', { channel_id: channel.id });
    }
    loadChannelMessages(channel.id);
    initLucide();
}

async function loadChannelMessages(channelId) {
    const scrollArea = document.getElementById('chat-messages-scroll');
    if (!scrollArea) return;
    scrollArea.innerHTML = '<div style="text-align: center; padding: 20px; color: var(--text-dim);">Kanal mesajları yükleniyor...</div>';

    try {
        const res = await fetch(`/api/channels/${channelId}/messages`);
        const data = await res.json();
        if (data.success) {
            scrollArea.innerHTML = '';
            data.messages.forEach(m => appendMessageToChat(m));
            scrollArea.scrollTop = scrollArea.scrollHeight;
        }
    } catch (e) {
        scrollArea.innerHTML = '<div style="text-align: center; color: var(--accent-rose);">Mesajlar yüklenemedi.</div>';
    }
}

async function handleCreateServer(e) {
    e.preventDefault();
    const name = document.getElementById('srv-name').value.trim();
    const desc = document.getElementById('srv-desc').value.trim();
    if (!name) return;

    try {
        const res = await fetch('/api/servers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description: desc })
        });
        const data = await res.json();
        if (data.success) {
            showToast('Sunucu oluşturuldu!', 'success');
            closeModal('modal-create-server');
            loadServers();
            openServerView(data.server.id);
        }
    } catch (e) {}
}

// ===================================================================
// 8. USER PROFILE MODAL & SETTINGS
// ===================================================================

async function openUserProfileModal(userId) {
    if (!userId) return;
    try {
        const res = await fetch(`/api/profile/${userId}`);
        const data = await res.json();
        if (data.success) {
            const u = data.profile.user;
            document.getElementById('user-card-display-name').textContent = u.display_name || u.username;
            document.getElementById('user-card-username').textContent = `@${u.username} • ${u.public_id || ''}`;
            document.getElementById('user-card-bio').textContent = u.bio || 'Hakkında bilgi bulunmuyor.';
            document.getElementById('user-card-banner').style.backgroundColor = u.banner_color || '#8b5cf6';
            
            const badgesBox = document.getElementById('user-card-badges');
            badgesBox.innerHTML = '';
            (u.badges || []).forEach(b => {
                badgesBox.innerHTML += `<span class="msg-badge">${b}</span>`;
            });

            const actions = document.getElementById('user-card-actions');
            actions.innerHTML = `
                <button class="btn-primary-sm" onclick="openDirectMessageWithUser(${u.id})">Mesaj Gönder</button>
            `;

            document.getElementById('modal-user-profile').classList.remove('hidden');
            initLucide();
        }
    } catch (e) {}
}

function openSettingsModal(tab = 'profile') {
    document.getElementById('modal-settings').classList.remove('hidden');
    switchSettingsTab(tab);
    initLucide();
}

function switchSettingsTab(tab) {
    document.querySelectorAll('.settings-nav-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.settings-tab-panel').forEach(p => p.classList.add('hidden'));

    const tabTitle = document.getElementById('settings-tab-title');
    if (tab === 'profile') {
        tabTitle.textContent = 'Profilimi Özelleştir';
        document.getElementById('tab-settings-profile').classList.remove('hidden');
        populateProfileForm();
    } else if (tab === 'security') {
        tabTitle.textContent = 'Hesap Güvenliği & 2FA';
        document.getElementById('tab-settings-security').classList.remove('hidden');
    } else if (tab === 'sessions') {
        tabTitle.textContent = 'Aktif Oturumlar';
        document.getElementById('tab-settings-sessions').classList.remove('hidden');
        loadSessions();
    }
}

function populateProfileForm() {
    if (!state.currentUser) return;
    const u = state.currentUser;
    document.getElementById('set-display-name').value = u.display_name || '';
    document.getElementById('set-custom-status').value = u.custom_status || '';
    document.getElementById('set-status-emoji').value = u.custom_status_emoji || '✨';
    document.getElementById('set-bio').value = u.bio || '';
    document.getElementById('set-accent-color').value = u.profile_accent_color || '#8b5cf6';
    document.getElementById('preview-dn').textContent = u.display_name || u.username;
    document.getElementById('preview-un').textContent = `@${u.username}`;
}

async function saveProfileSettings(e) {
    e.preventDefault();
    const displayName = document.getElementById('set-display-name').value.trim();
    const customStatus = document.getElementById('set-custom-status').value.trim();
    const customStatusEmoji = document.getElementById('set-status-emoji').value.trim();
    const bio = document.getElementById('set-bio').value.trim();
    const accentColor = document.getElementById('set-accent-color').value;

    try {
        const res = await fetch('/api/account/profile', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                display_name: displayName,
                custom_status: customStatus,
                custom_status_emoji: customStatusEmoji,
                bio: bio,
                profile_accent_color: accentColor
            })
        });
        const data = await res.json();
        if (data.success) {
            state.currentUser = data.user;
            showToast('Profil güncellendi!', 'success');
            updateUserBarUI();
        }
    } catch (e) {}
}

async function loadSessions() {
    const list = document.getElementById('sessions-table-list');
    if (!list) return;
    list.innerHTML = '<div style="padding: 12px; color: var(--text-dim);">Oturumlar getiriliyor...</div>';

    try {
        const res = await fetch('/api/account/sessions');
        const data = await res.json();
        if (data.success) {
            list.innerHTML = '';
            data.sessions.forEach(s => {
                const item = document.createElement('div');
                item.className = 'session-card';
                item.style = "display: flex; align-items: center; justify-content: space-between; padding: 12px; background: rgba(0,0,0,0.3); border-radius: 8px; margin-bottom: 8px;";
                item.innerHTML = `
                    <div>
                        <div style="font-weight: 600;">${s.browser} • ${s.os} ${s.is_current ? '<span class="status-pill" style="background: rgba(16,185,129,0.2); color: #34d399; font-size: 10px; padding: 2px 6px; border-radius: 4px;">Mevcut Oturum</span>' : ''}</div>
                        <div style="font-size: 11px; color: var(--text-dim);">${s.ip_address} • Son Aktif: ${new Date(s.last_active_at || s.created_at).toLocaleString()}</div>
                    </div>
                    ${!s.is_current ? `<button class="btn-danger-flat" onclick="revokeSession(${s.id})">Sonlandır</button>` : ''}
                `;
                list.appendChild(item);
            });
        }
    } catch (e) {}
}

async function revokeOtherSessions() {
    if (!confirm('Diğer tüm cihazlardaki oturumları kapatmak istediğine emin misin?')) return;
    try {
        const res = await fetch('/api/account/sessions/revoke-others', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast(data.message, 'success');
            loadSessions();
        }
    } catch (e) {}
}

// ===================================================================
// 9. MODALS, POPUPS & EXTRA INTERACTIVE ACTIONS
// ===================================================================

function togglePresenceMenu(e) {
    e.stopPropagation();
    const menu = document.getElementById('presence-menu-popup');
    if (!menu) return;
    menu.classList.toggle('hidden');
    if (!menu.classList.contains('hidden')) {
        const rect = e.currentTarget.getBoundingClientRect();
        menu.style.position = 'fixed';
        menu.style.bottom = '60px';
        menu.style.left = `${rect.left}px`;
    }
}

document.addEventListener('click', (e) => {
    const presenceMenu = document.getElementById('presence-menu-popup');
    if (presenceMenu && !presenceMenu.contains(e.target)) {
        presenceMenu.classList.add('hidden');
    }
    const emojiMenu = document.getElementById('emoji-picker-popup');
    if (emojiMenu && !emojiMenu.contains(e.target) && !e.target.closest('.btn-input-action')) {
        emojiMenu.classList.add('hidden');
    }
});

async function setPresenceStatus(status) {
    try {
        const res = await fetch('/api/account/presence', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ presence_status: status })
        });
        const data = await res.json();
        if (data.success) {
            if (state.currentUser) state.currentUser.presence_status = status;
            const dot = document.getElementById('user-bar-presence');
            const railDot = document.getElementById('rail-presence-dot');
            if (dot) dot.className = `presence-dot ${status}`;
            if (railDot) railDot.className = `presence-dot ${status}`;
            showToast(`Durumun güncellendi: ${status}`, 'success');
        }
    } catch (e) {}
    const menu = document.getElementById('presence-menu-popup');
    if (menu) menu.classList.add('hidden');
}

function toggleMembersSidebar() {
    const sidebar = document.getElementById('members-sidebar');
    if (sidebar) sidebar.classList.toggle('hidden');
}

function togglePinnedMessagesPanel() {
    const bar = document.getElementById('pinned-messages-bar');
    if (bar) bar.classList.toggle('hidden');
}

function openGlobalSearch() {
    const q = prompt('AstralPaws içinde aramak istediğin terimi girin:');
    if (q) {
        showToast(`"${q}" için arama yapılıyor...`, 'info');
    }
}

function openChatSearch() {
    const q = prompt('Bu sohbette aramak istediğiniz mesaj:');
    if (!q) return;
    const items = document.querySelectorAll('.msg-text');
    let found = 0;
    items.forEach(el => {
        if (el.textContent.toLowerCase().includes(q.toLowerCase())) {
            el.closest('.msg-row').scrollIntoView({ behavior: 'smooth', block: 'center' });
            el.style.backgroundColor = 'rgba(139, 92, 246, 0.4)';
            setTimeout(() => el.style.backgroundColor = 'transparent', 3000);
            found++;
        }
    });
    showToast(found > 0 ? `${found} eşleşme bulundu.` : 'Eşleşen mesaj bulunamadı.', found > 0 ? 'success' : 'info');
}

function openForgotModal() {
    document.getElementById('modal-forgot-password').classList.remove('hidden');
    initLucide();
}

async function handleForgotPassword(e) {
    e.preventDefault();
    const email = document.getElementById('forgot-email-input').value.trim();
    if (!email) return;
    try {
        const res = await fetch('/api/forgot-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
        });
        const data = await res.json();
        showToast(data.message || 'Sıfırlama bağlantısı gönderildi.', 'info');
        closeModal('modal-forgot-password');
    } catch (e) {
        showToast('İşlem başarısız.', 'error');
    }
}

function openCreateGroupModal() {
    const list = document.getElementById('group-friends-select-list');
    if (list) {
        list.innerHTML = '';
        (state.friendsData.friends || []).forEach(f => {
            list.innerHTML += `
                <label class="custom-checkbox" style="margin-bottom: 6px;">
                    <input type="checkbox" name="group-friend-checkbox" value="${f.user_id}">
                    <span class="checkmark"></span>
                    <span>${f.display_name} (@${f.username})</span>
                </label>
            `;
        });
    }
    document.getElementById('modal-create-group').classList.remove('hidden');
    initLucide();
}

async function handleCreateGroup(e) {
    e.preventDefault();
    const name = document.getElementById('group-name-input').value.trim();
    const checks = document.querySelectorAll('input[name="group-friend-checkbox"]:checked');
    const userIds = Array.from(checks).map(c => parseInt(c.value));

    if (!name || userIds.length === 0) {
        showToast('Lütfen grup adı ve en az bir arkadaş seçin.', 'error');
        return;
    }

    try {
        const res = await fetch('/api/conversations/group', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, user_ids: userIds })
        });
        const data = await res.json();
        if (data.success) {
            showToast('Grup sohbeti oluşturuldu!', 'success');
            closeModal('modal-create-group');
            loadConversations();
            openConversation(data.conversation.id, data.conversation.name);
        }
    } catch (e) {}
}

function openCreateChannelModal(type = 'text') {
    const typeSelect = document.getElementById('channel-type-input');
    if (typeSelect) typeSelect.value = type;
    document.getElementById('modal-create-channel').classList.remove('hidden');
    initLucide();
}

function openCreateNexusChannelModal() {
    openCreateChannelModal('text');
}

async function handleCreateChannel(e) {
    e.preventDefault();
    const name = document.getElementById('channel-name-input').value.trim();
    const type = document.getElementById('channel-type-input').value;

    if (!name) return;
    if (!state.activeServerId && !state.activeNexusId) {
        showToast('Lütfen bir sunucu veya Nexus seçin.', 'error');
        return;
    }

    const endpoint = state.activeServerId 
        ? `/api/servers/${state.activeServerId}/channels`
        : `/api/nexus/${state.activeNexusId}/channels`;

    try {
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, type })
        });
        const data = await res.json();
        if (data.success) {
            showToast('Kanal başarıyla eklendi!', 'success');
            closeModal('modal-create-channel');
            if (state.activeServerId) openServerView(state.activeServerId);
        }
    } catch (e) {}
}

function openSoundboardModal() {
    document.getElementById('modal-soundboard').classList.remove('hidden');
    initLucide();
}

function playSoundEffect(soundName) {
    if (state.socket && state.activeConversationId) {
        state.socket.emit('soundboard_play', {
            sound_name: soundName,
            conversation_id: state.activeConversationId
        });
    }
    showToast(`Ses efekti çalındı: ${soundName}`, 'info');
    closeModal('modal-soundboard');
}

function openScheduleModal() {
    const mins = prompt('Mesaj kaç dakika sonra gönderilsin? (Örn: 10)');
    if (mins && !isNaN(mins)) {
        showToast(`Mesaj ${mins} dakika sonrasına zamanlanacak.`, 'info');
    }
}

function toggleEmojiPicker(e) {
    e.stopPropagation();
    const popup = document.getElementById('emoji-picker-popup');
    if (!popup) return;
    popup.classList.toggle('hidden');

    if (!popup.classList.contains('hidden')) {
        renderEmojiPickerList();
    }
}

function renderEmojiPickerList(query = '') {
    const grid = document.getElementById('emoji-grid-list');
    if (!grid) return;
    grid.innerHTML = '';
    const emojis = ['✨', '🔥', '🚀', '👑', '💖', '🎉', '👍', '🐱', '🐾', '🌟', '💻', '🎮', '🎵', '⚡', '🤖', '💯', '😂', '😍', '👏', '🏆'];
    
    emojis.filter(em => !query || em.includes(query)).forEach(em => {
        const btn = document.createElement('button');
        btn.className = 'emoji-pick-btn';
        btn.textContent = em;
        btn.onclick = () => {
            const textarea = document.getElementById('message-textarea');
            if (textarea) {
                textarea.value += em;
                textarea.focus();
            }
            document.getElementById('emoji-picker-popup').classList.add('hidden');
        };
        grid.appendChild(btn);
    });
}

function filterEmojis(q) {
    renderEmojiPickerList(q.trim());
}

async function uploadAvatar(e) {
    const file = e.target.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('avatar', file);

    try {
        const res = await fetch('/api/account/avatar', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.success) {
            showToast('Profil fotoğrafı güncellendi!', 'success');
            checkAuthStatus();
        }
    } catch (e) {}
}

async function uploadBanner(e) {
    const file = e.target.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('banner', file);

    try {
        const res = await fetch('/api/account/banner', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.success) {
            showToast('Profil afişi güncellendi!', 'success');
            checkAuthStatus();
        }
    } catch (e) {}
}

async function handleChangePassword(e) {
    e.preventDefault();
    const currentPassword = document.getElementById('chg-curr-pwd').value;
    const newPassword = document.getElementById('chg-new-pwd').value;
    const newPasswordConfirm = document.getElementById('chg-new-pwd-confirm').value;

    if (newPassword !== newPasswordConfirm) {
        showToast('Yeni şifreler eşleşmiyor.', 'error');
        return;
    }

    try {
        const res = await fetch('/api/account/change-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_password: currentPassword, new_password: newPassword, new_password_confirm: newPasswordConfirm })
        });
        const data = await res.json();
        showToast(data.message || 'Şifre güncellendi!', data.success ? 'success' : 'error');
        if (data.success) {
            document.getElementById('chg-curr-pwd').value = '';
            document.getElementById('chg-new-pwd').value = '';
            document.getElementById('chg-new-pwd-confirm').value = '';
        }
    } catch (e) {}
}

function handleFileSelection(e) {
    const files = Array.from(e.target.files);
    state.selectedFiles = files;
    const previewBar = document.getElementById('attachment-preview-bar');
    const previewList = document.getElementById('preview-item-list');
    if (!previewBar || !previewList) return;

    if (files.length === 0) {
        previewBar.classList.add('hidden');
        return;
    }

    previewList.innerHTML = '';
    files.forEach((f, idx) => {
        previewList.innerHTML += `
            <div style="display: inline-flex; align-items: center; gap: 6px; padding: 4px 8px; background: rgba(255,255,255,0.08); border-radius: 6px; font-size: 12px;">
                <i data-lucide="file"></i> <span>${f.name}</span>
            </div>
        `;
    });
    previewBar.classList.remove('hidden');
    initLucide();
}

function toggleServerMenu() {
    showToast('Sunucu seçenekleri açıldı.', 'info');
}

function openNexusApplicationsModal() {
    showToast('Bekleyen başvuru bulunmuyor.', 'info');
}

function handle2FASetupModal() {
    showToast('2FA yapılandırması başlatılıyor...', 'info');
}

function openAddProjectModal() {
    const title = prompt('Proje Başlığı:');
    if (title) showToast('Proje kaydedildi.', 'success');
}

function openAddLinkModal() {
    const title = prompt('Bağlantı Başlığı (Örn: GitHub):');
    const url = prompt('Bağlantı URL:');
    if (title && url) showToast('Bağlantı eklendi.', 'success');
}

// Modal Helpers
function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.add('hidden');
}

function handleModalBackdropClick(e, modalId) {
    if (e.target.id === modalId) {
        closeModal(modalId);
    }
}

function openCreateServerModal() {
    document.getElementById('modal-create-server').classList.remove('hidden');
    initLucide();
}

function openCreateNexusModal() {
    document.getElementById('modal-create-nexus').classList.remove('hidden');
    initLucide();
}

function triggerFileInput() {
    document.getElementById('file-upload-input').click();
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

