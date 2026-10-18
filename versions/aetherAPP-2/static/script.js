/**
 * NEON CHAT ULTRA - CORE ENGINE & CLIENT CONTROLLER
 * Comprehensive, feature-rich real-time communication client.
 */

document.addEventListener('DOMContentLoaded', () => {
    function safeOn(el, evt, handler) {
        if (el) el.addEventListener(evt, handler);
    }
    // --- Global State ---
    let socket = null;
    let currentUser = null;
    let currentConversationId = null; // Active Conversation (DM or Group) ID
    let cachedConversations = [];
    let currentTargetId = null; // Legacy DM User ID
    let currentTargetName = null;
    let currentTargetColor = null;
    let currentServerId = null;
    let currentChannelId = null; // Channel ID
    let currentChannelType = 'text'; // 'text', 'voice', 'canvas'
    let currentVoiceChannelId = null;
    let activeReplyMessage = null; // { id, username, text }
    let activePendingDeleteMsgId = null;
    let activePendingDeleteIsMine = false;
    let activeForwardMsgId = null;
    let isSpoilerActive = false;
    let typingTimeout = null;
    let soundEffectsEnabled = true;
    let soundboardVolume = 0.8;
    let globalMicMuted = false;
    let globalDeafened = false;

    // --- Direct 1-on-1 Voice Call State ---
    let directCallState = {
        active: false,
        isCaller: false,
        peerId: null,
        peerName: null,
        peerColor: null,
        pc: null,
        localStream: null,
        remoteAudio: null,
        timerInterval: null,
        seconds: 0
    };

    // --- Audio Synthesis Engine (Web Audio API) ---
    const AudioEngine = {
        ctx: null,
        incomingRingTimer: null,
        outgoingRingTimer: null,

        init() {
            if (!this.ctx) {
                const AudioContext = window.AudioContext || window.webkitAudioContext;
                if (AudioContext) this.ctx = new AudioContext();
            }
            if (this.ctx && this.ctx.state === 'suspended') {
                this.ctx.resume();
            }
        },

        play(name) {
            if (!soundEffectsEnabled) return;
            try {
                this.init();
                if (!this.ctx) return;
                const now = this.ctx.currentTime;

                if (name === 'message_incoming') {
                    // Soft Dual Chime: D5 (587Hz) -> A5 (880Hz)
                    const osc = this.ctx.createOscillator();
                    const gain = this.ctx.createGain();
                    osc.type = 'sine';
                    osc.frequency.setValueAtTime(587.33, now);
                    osc.frequency.exponentialRampToValueAtTime(880, now + 0.1);
                    gain.gain.setValueAtTime(0.2, now);
                    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
                    osc.connect(gain);
                    gain.connect(this.ctx.destination);
                    osc.start(now);
                    osc.stop(now + 0.35);

                } else if (name === 'message_sent') {
                    // Quick Snappy Upward Chirp: 750Hz -> 1200Hz
                    const osc = this.ctx.createOscillator();
                    const gain = this.ctx.createGain();
                    osc.type = 'triangle';
                    osc.frequency.setValueAtTime(750, now);
                    osc.frequency.exponentialRampToValueAtTime(1200, now + 0.07);
                    gain.gain.setValueAtTime(0.12, now);
                    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.08);
                    osc.connect(gain);
                    gain.connect(this.ctx.destination);
                    osc.start(now);
                    osc.stop(now + 0.08);

                } else if (name === 'call_connected') {
                    // Upward 3-Tone Triumphant Arpeggio: C5 -> E5 -> G5
                    [523.25, 659.25, 783.99].forEach((freq, i) => {
                        const osc = this.ctx.createOscillator();
                        const gain = this.ctx.createGain();
                        osc.type = 'sine';
                        osc.frequency.setValueAtTime(freq, now + i * 0.09);
                        gain.gain.setValueAtTime(0.18, now + i * 0.09);
                        gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.09 + 0.22);
                        osc.connect(gain);
                        gain.connect(this.ctx.destination);
                        osc.start(now + i * 0.09);
                        osc.stop(now + i * 0.09 + 0.22);
                    });

                } else if (name === 'call_ended') {
                    // Downward 2-Tone Cadence: G4 -> C4
                    [392.00, 261.63].forEach((freq, i) => {
                        const osc = this.ctx.createOscillator();
                        const gain = this.ctx.createGain();
                        osc.type = 'sine';
                        osc.frequency.setValueAtTime(freq, now + i * 0.14);
                        gain.gain.setValueAtTime(0.16, now + i * 0.14);
                        gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.14 + 0.25);
                        osc.connect(gain);
                        gain.connect(this.ctx.destination);
                        osc.start(now + i * 0.14);
                        osc.stop(now + i * 0.14 + 0.25);
                    });

                } else if (name === 'voice_join') {
                    // Deep Futuristic Resonant Sweep: 180Hz -> 360Hz Saw with Low-Pass filter
                    const osc = this.ctx.createOscillator();
                    const filter = this.ctx.createBiquadFilter();
                    const gain = this.ctx.createGain();
                    osc.type = 'sawtooth';
                    osc.frequency.setValueAtTime(180, now);
                    osc.frequency.exponentialRampToValueAtTime(360, now + 0.2);
                    filter.type = 'lowpass';
                    filter.frequency.setValueAtTime(400, now);
                    filter.frequency.exponentialRampToValueAtTime(1200, now + 0.2);
                    filter.Q.setValueAtTime(4, now);
                    gain.gain.setValueAtTime(0.15, now);
                    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
                    osc.connect(filter);
                    filter.connect(gain);
                    gain.connect(this.ctx.destination);
                    osc.start(now);
                    osc.stop(now + 0.35);

                } else if (name === 'voice_leave') {
                    // Soft Airy Downward Blip: 440Hz -> 220Hz
                    const osc = this.ctx.createOscillator();
                    const gain = this.ctx.createGain();
                    osc.type = 'sine';
                    osc.frequency.setValueAtTime(440, now);
                    osc.frequency.exponentialRampToValueAtTime(220, now + 0.18);
                    gain.gain.setValueAtTime(0.15, now);
                    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
                    osc.connect(gain);
                    gain.connect(this.ctx.destination);
                    osc.start(now);
                    osc.stop(now + 0.25);

                } else if (name === 'mic_mute') {
                    // Crisp Double Thud: 320Hz -> 200Hz
                    const osc = this.ctx.createOscillator();
                    const gain = this.ctx.createGain();
                    osc.type = 'square';
                    osc.frequency.setValueAtTime(320, now);
                    osc.frequency.exponentialRampToValueAtTime(200, now + 0.08);
                    gain.gain.setValueAtTime(0.1, now);
                    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.08);
                    osc.connect(gain);
                    gain.connect(this.ctx.destination);
                    osc.start(now);
                    osc.stop(now + 0.08);

                } else if (name === 'mic_unmute') {
                    // Crisp High Pop: 450Hz -> 650Hz
                    const osc = this.ctx.createOscillator();
                    const gain = this.ctx.createGain();
                    osc.type = 'sine';
                    osc.frequency.setValueAtTime(450, now);
                    osc.frequency.exponentialRampToValueAtTime(650, now + 0.08);
                    gain.gain.setValueAtTime(0.14, now);
                    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.08);
                    osc.connect(gain);
                    gain.connect(this.ctx.destination);
                    osc.start(now);
                    osc.stop(now + 0.08);

                } else if (name === 'deafen') {
                    // Descending Tone: 350Hz -> 180Hz
                    const osc = this.ctx.createOscillator();
                    const gain = this.ctx.createGain();
                    osc.type = 'triangle';
                    osc.frequency.setValueAtTime(350, now);
                    osc.frequency.exponentialRampToValueAtTime(180, now + 0.12);
                    gain.gain.setValueAtTime(0.15, now);
                    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.15);
                    osc.connect(gain);
                    gain.connect(this.ctx.destination);
                    osc.start(now);
                    osc.stop(now + 0.15);

                } else if (name === 'undeafen') {
                    // Ascending Tone: 180Hz -> 350Hz
                    const osc = this.ctx.createOscillator();
                    const gain = this.ctx.createGain();
                    osc.type = 'triangle';
                    osc.frequency.setValueAtTime(180, now);
                    osc.frequency.exponentialRampToValueAtTime(350, now + 0.12);
                    gain.gain.setValueAtTime(0.15, now);
                    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.15);
                    osc.connect(gain);
                    gain.connect(this.ctx.destination);
                    osc.start(now);
                    osc.stop(now + 0.15);

                } else if (name === 'friend_request') {
                    // Sparkling Crystal Bell: E6 (1318Hz) -> G#6 (1661Hz) -> B6 (1975Hz)
                    [1318.51, 1661.22, 1975.53].forEach((freq, i) => {
                        const osc = this.ctx.createOscillator();
                        const gain = this.ctx.createGain();
                        osc.type = 'sine';
                        osc.frequency.setValueAtTime(freq, now + i * 0.08);
                        gain.gain.setValueAtTime(0.12, now + i * 0.08);
                        gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.08 + 0.3);
                        osc.connect(gain);
                        gain.connect(this.ctx.destination);
                        osc.start(now + i * 0.08);
                        osc.stop(now + i * 0.08 + 0.3);
                    });

                } else if (name === 'reaction_pop') {
                    // Organic Bubble Pop: 320Hz -> 480Hz -> 240Hz
                    const osc = this.ctx.createOscillator();
                    const gain = this.ctx.createGain();
                    osc.type = 'sine';
                    osc.frequency.setValueAtTime(320, now);
                    osc.frequency.exponentialRampToValueAtTime(480, now + 0.04);
                    osc.frequency.exponentialRampToValueAtTime(240, now + 0.1);
                    gain.gain.setValueAtTime(0.15, now);
                    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.1);
                    osc.connect(gain);
                    gain.connect(this.ctx.destination);
                    osc.start(now);
                    osc.stop(now + 0.1);

                } else if (name === 'voice_search_start') {
                    // High-Tech Listen Ping: 800Hz pure tone
                    const osc = this.ctx.createOscillator();
                    const gain = this.ctx.createGain();
                    osc.type = 'sine';
                    osc.frequency.setValueAtTime(800, now);
                    gain.gain.setValueAtTime(0.18, now);
                    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.18);
                    osc.connect(gain);
                    gain.connect(this.ctx.destination);
                    osc.start(now);
                    osc.stop(now + 0.18);

                } else if (name === 'voice_search_success') {
                    // Dual Confirmation Chirp: 600Hz -> 900Hz
                    [600, 900].forEach((freq, i) => {
                        const osc = this.ctx.createOscillator();
                        const gain = this.ctx.createGain();
                        osc.type = 'sine';
                        osc.frequency.setValueAtTime(freq, now + i * 0.07);
                        gain.gain.setValueAtTime(0.15, now + i * 0.07);
                        gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.07 + 0.14);
                        osc.connect(gain);
                        gain.connect(this.ctx.destination);
                        osc.start(now + i * 0.07);
                        osc.stop(now + i * 0.07 + 0.14);
                    });

                } else if (name === 'error_buzzer') {
                    // Low Square Filtered Double Buzz: 180Hz -> 140Hz
                    const osc = this.ctx.createOscillator();
                    const filter = this.ctx.createBiquadFilter();
                    const gain = this.ctx.createGain();
                    osc.type = 'sawtooth';
                    osc.frequency.setValueAtTime(180, now);
                    osc.frequency.linearRampToValueAtTime(140, now + 0.2);
                    filter.type = 'lowpass';
                    filter.frequency.setValueAtTime(500, now);
                    gain.gain.setValueAtTime(0.15, now);
                    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.22);
                    osc.connect(filter);
                    filter.connect(gain);
                    gain.connect(this.ctx.destination);
                    osc.start(now);
                    osc.stop(now + 0.22);
                }
            } catch (e) { console.warn('Audio synth error:', e); }
        },

        // Backward compatibility
        playChime(type = 'ping') {
            if (type === 'ping') this.play('message_incoming');
            else if (type === 'pop') this.play('reaction_pop');
            else if (type === 'join') this.play('voice_join');
            else this.play(type);
        },

        startIncomingRing() {
            if (!soundEffectsEnabled) return;
            this.stopIncomingRing();
            const ringMelody = () => {
                try {
                    this.init();
                    if (!this.ctx) return;
                    const now = this.ctx.currentTime;
                    // Catchy modern 6-note ringtone loop: C5 -> E5 -> G5 -> C6 -> G5 -> C6
                    const notes = [523.25, 659.25, 783.99, 1046.50, 783.99, 1046.50];
                    notes.forEach((freq, i) => {
                        const osc = this.ctx.createOscillator();
                        const gain = this.ctx.createGain();
                        osc.type = 'sine';
                        osc.frequency.setValueAtTime(freq, now + i * 0.12);
                        gain.gain.setValueAtTime(0.18, now + i * 0.12);
                        gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.12 + 0.25);
                        osc.connect(gain);
                        gain.connect(this.ctx.destination);
                        osc.start(now + i * 0.12);
                        osc.stop(now + i * 0.12 + 0.25);
                    });
                } catch (e) { }
            };
            ringMelody();
            this.incomingRingTimer = setInterval(ringMelody, 2200);
        },

        stopIncomingRing() {
            if (this.incomingRingTimer) {
                clearInterval(this.incomingRingTimer);
                this.incomingRingTimer = null;
            }
        },

        startOutgoingRing() {
            if (!soundEffectsEnabled) return;
            this.stopOutgoingRing();
            const dialTone = () => {
                try {
                    this.init();
                    if (!this.ctx) return;
                    const now = this.ctx.currentTime;
                    // Dual tone dial tone: 440Hz + 480Hz
                    [440, 480].forEach(freq => {
                        const osc = this.ctx.createOscillator();
                        const gain = this.ctx.createGain();
                        osc.type = 'sine';
                        osc.frequency.setValueAtTime(freq, now);
                        gain.gain.setValueAtTime(0.12, now);
                        gain.gain.exponentialRampToValueAtTime(0.001, now + 1.2);
                        osc.connect(gain);
                        gain.connect(this.ctx.destination);
                        osc.start(now);
                        osc.stop(now + 1.2);
                    });
                } catch (e) { }
            };
            dialTone();
            this.outgoingRingTimer = setInterval(dialTone, 3000);
        },

        stopOutgoingRing() {
            if (this.outgoingRingTimer) {
                clearInterval(this.outgoingRingTimer);
                this.outgoingRingTimer = null;
            }
        },

        playSoundboard(soundKey) {
            try {
                this.init();
                if (!this.ctx) return;
                const now = this.ctx.currentTime;
                const gain = this.ctx.createGain();
                gain.gain.setValueAtTime(0.3 * soundboardVolume, now);
                gain.connect(this.ctx.destination);

                if (soundKey === 'airhorn') {
                    // Multi-tone chord for airhorn
                    [466.16, 466.16 * 1.5, 466.16 * 2].forEach(freq => {
                        const o = this.ctx.createOscillator();
                        o.type = 'sawtooth';
                        o.frequency.setValueAtTime(freq, now);
                        o.connect(gain);
                        o.start(now);
                        o.stop(now + 0.6);
                    });
                    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.6);
                } else if (soundKey === 'victory' || soundKey === 'gg') {
                    const freqs = [523.25, 659.25, 783.99, 1046.50]; // C Major arpeggio
                    freqs.forEach((freq, idx) => {
                        const o = this.ctx.createOscillator();
                        o.type = 'triangle';
                        o.frequency.setValueAtTime(freq, now + idx * 0.1);
                        o.connect(gain);
                        o.start(now + idx * 0.1);
                        o.stop(now + idx * 0.1 + 0.3);
                    });
                } else if (soundKey === 'bruh') {
                    const o = this.ctx.createOscillator();
                    o.type = 'sawtooth';
                    o.frequency.setValueAtTime(140, now);
                    o.frequency.linearRampToValueAtTime(90, now + 0.4);
                    o.connect(gain);
                    o.start(now);
                    o.stop(now + 0.5);
                    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.5);
                } else if (soundKey === 'coin') {
                    const o = this.ctx.createOscillator();
                    o.type = 'sine';
                    o.frequency.setValueAtTime(987.77, now); // B5
                    o.frequency.setValueAtTime(1318.51, now + 0.08); // E6
                    o.connect(gain);
                    o.start(now);
                    o.stop(now + 0.4);
                    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.4);
                } else if (soundKey === 'laser') {
                    const o = this.ctx.createOscillator();
                    o.type = 'sawtooth';
                    o.frequency.setValueAtTime(900, now);
                    o.frequency.exponentialRampToValueAtTime(80, now + 0.25);
                    o.connect(gain);
                    o.start(now);
                    o.stop(now + 0.25);
                    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
                } else {
                    // Generic arcade punchy blip
                    const o = this.ctx.createOscillator();
                    o.type = 'square';
                    o.frequency.setValueAtTime(440, now);
                    o.frequency.exponentialRampToValueAtTime(220, now + 0.2);
                    o.connect(gain);
                    o.start(now);
                    o.stop(now + 0.2);
                    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.2);
                }
            } catch (e) { console.warn('Soundboard error:', e); }
        }
    };

    // --- Emoji Database ---
    const EMOJI_DATABASE = {
        smileys: ['😀', '😃', '😄', '😁', '😆', '😅', '😂', '🤣', '😊', '😇', '🙂', '😉', '😍', '🥰', '😘', '😋', '😛', '😜', '🤪', '😎', '🤩', '🥳', '😏', '🤗', '🤔', '🤫', '🤭', '😴', '😷', '🤒', '🤢'],
        gestures: ['👍', '👎', '👌', '✌️', '🤞', '🤟', '🤘', '🤙', '👈', '👉', '👆', '👇', '✋', '🤚', '🖐️', '🖖', '👋', '🤝', '👏', '🙌', '👐', '🤲', '🙏', '💪', '🦾', '✍️', '💅'],
        nature: ['🔥', '⚡', '✨', '🌟', '💫', '💥', '🌈', '☀️', '🌙', '⭐', '🪐', '🚀', '🛸', '🌍', '🌊', '🌪️', '🌋', '🌺', '🌸', '🌹', '🌻', '🍀', '🍁', '🍂', '🍄', '🌴'],
        objects: ['💻', '🖥️', '📱', '🕹️', '🎮', '🎲', '🎯', '🏆', '🥇', '🎁', '🎉', '🎊', '🎈', '💎', '👑', '🔮', '🧿', '🎧', '🎤', '🎵', '🎶', '🎸', '🎹', '🥁', '📡'],
        symbols: ['❤️', '🧡', '💛', '💚', '💙', '💜', '🖤', '🤍', '🤎', '💔', '❣️', '💕', '💞', '💓', '💗', '💖', '💘', '💝', '💟', '☮️', '✝️', '☪️', '🕉️', '☸️', '✡️', '🔯', '💠']
    };

    // --- Sidebars & Lists ---
    const serverList = document.getElementById('server-list');
    const navHome = document.getElementById('nav-home');
    const navAiBot = document.getElementById('nav-ai-bot');
    const addServerBtn = document.getElementById('add-server-btn');
    const navSoundboardBtn = document.getElementById('nav-soundboard-btn');
    const homeView = document.getElementById('home-view');
    const serverView = document.getElementById('server-view');
    const sidebarTitle = document.getElementById('sidebar-title');
    const channelList = document.getElementById('channel-list') || document.getElementById('text-channel-list');
    const sidebarDmList = document.getElementById('sidebar-dm-list');
    const currentServerInvite = document.getElementById('current-server-invite');
    const btnCopyInvite = document.getElementById('btn-copy-invite');
    const activitySidebar = document.getElementById('activity-sidebar');
    const serverMembersList = document.getElementById('server-members-list');
    const serverMembersCount = document.getElementById('server-members-count');

    // Main Workspaces
    const homeDashboard = document.getElementById('friends-dashboard') || document.getElementById('home-dashboard');
    const mainChatArea = document.getElementById('chat-messages-pane') || document.getElementById('main-chat-area');
    const mainWhiteboardArea = document.getElementById('canvas-pane') || document.getElementById('main-whiteboard-area');
    const mainVoiceArea = document.getElementById('voice-pane') || document.getElementById('main-voice-area');

    // Chat Controls
    const chatTargetIcon = document.getElementById('header-icon-pill') || document.getElementById('chat-target-icon');
    const chatTargetName = document.getElementById('header-channel-title') || document.getElementById('chat-target-name');
    const chatTargetSub = document.getElementById('header-channel-desc') || document.getElementById('chat-target-sub');
    const chatHistory = document.getElementById('chat-history');
    const chatForm = document.getElementById('chat-form');
    const messageInput = document.getElementById('message-input');
    const typingIndicator = document.getElementById('typing-indicator');
    const typingText = document.getElementById('typing-text');
    const replyPreviewBar = document.getElementById('reply-dock') || document.getElementById('reply-preview-bar');
    const replyToUser = document.getElementById('reply-to-user');
    const replyToSnippet = document.getElementById('reply-to-text') || document.getElementById('reply-to-snippet');
    const btnCancelReply = document.getElementById('btn-cancel-reply');
    const fileUploadInput = document.getElementById('chat-file-input') || document.getElementById('file-upload-input');
    const btnAttachFile = document.getElementById('btn-attach-file');
    const btnRecordVoiceNote = document.getElementById('btn-record-voice-note') || document.getElementById('btn-voice-memo');
    const voiceRecordBar = document.getElementById('voice-recording-dock') || document.getElementById('voice-record-bar');
    const voiceRecordTimer = document.getElementById('voice-record-timer');
    const btnCancelVoice = document.getElementById('btn-cancel-voice-record') || document.getElementById('btn-cancel-voice');
    const btnSendVoice = document.getElementById('btn-send-voice-record') || document.getElementById('btn-send-voice');
    const chatSearchInput = document.getElementById('chat-search-input');
    const chatSearchClear = document.getElementById('chat-search-clear');
    const btnStartDmVoiceCall = document.getElementById('btn-start-dm-voice-call');

    // Modals & Call Elements
    const userProfileModal = document.getElementById('user-profile-modal');
    const settingsModal = document.getElementById('settings-modal');
    const twofaSetupModal = document.getElementById('twofa-setup-modal');
    const recoveryCodesModal = document.getElementById('recovery-codes-modal');
    const dangerConfirmModal = document.getElementById('danger-confirm-modal');
    const soundboardModal = document.getElementById('soundboard-modal');
    const pinsModal = document.getElementById('pins-modal');
    const emojiPickerPopover = document.getElementById('emoji-picker-popover');
    const addServerModal = document.getElementById('add-server-modal');
    const addChannelModal = document.getElementById('add-channel-modal');

    // Public Auth Elements
    const authScreen = document.getElementById('auth-screen');
    const appScreen = document.getElementById('app-screen');
    const loginFormContainer = document.getElementById('login-form-container');
    const loginForm = document.getElementById('login-form');
    const login2faForm = document.getElementById('login-2fa-form');
    const registerFormContainer = document.getElementById('register-form-container');
    const registerForm = document.getElementById('register-form');
    const verifyFormContainer = document.getElementById('verify-form-container');
    const verifyForm = document.getElementById('verify-form');
    const verifyCodeInput = document.getElementById('verify-code');
    const verifyEmailDisplay = document.getElementById('verify-email-display');
    const verifyError = document.getElementById('verify-error');
    const verifySuccess = document.getElementById('verify-success');
    const btnResendCode = document.getElementById('btn-resend-code');
    const resendCountdown = document.getElementById('resend-countdown');
    const forgotFormContainer = document.getElementById('forgot-form-container');
    const forgotPasswordForm = document.getElementById('forgot-password-form');
    const resetFormContainer = document.getElementById('reset-form-container');
    const resetPasswordForm = document.getElementById('reset-password-form');
    const loginRemember = document.getElementById('login-remember');
    const showRegister = document.getElementById('show-register');
    const showLogin = document.getElementById('show-login');
    const showLoginFromVerify = document.getElementById('show-login-from-verify');
    const showLoginFromForgot = document.getElementById('show-login-from-forgot');
    const showLoginFromReset = document.getElementById('show-login-from-reset');
    const linkForgotPassword = document.getElementById('link-forgot-password');
    const btnToggleRecoveryMode = document.getElementById('btn-toggle-recovery-mode');
    const btnBackFrom2fa = document.getElementById('btn-back-from-2fa');
    const twofaCodeLabel = document.getElementById('twofa-code-label');
    const login2faCodeInput = document.getElementById('login-2fa-code');

    // --- Authentication State & Logic ---
    let pendingVerificationEmail = '';
    let pendingVerificationUsername = '';
    let pending2faTempToken = '';
    let is2faRecoveryMode = false;
    let resendCountdownTimer = null;
    let dangerActionCallback = null;

    // Init App
    loadRememberedUser();
    // Lucide Icon Renderer Helper
    function renderLucideIcons() {
        if (window.lucide && typeof window.lucide.createIcons === 'function') {
            window.lucide.createIcons();
        }
    }
    window.renderLucideIcons = renderLucideIcons;

    checkUrlQueryParams();
    checkAuth();
    loadLocalTheme();
    initSettingsDashboard();
    initVoiceRecognitionSystem();
    initQuickButtonListeners();
    initPasswordToggleButtons();
    initEmojiPicker();
    initSoundboard();
    renderLucideIcons();

    function loadRememberedUser() {
        try {
            const savedUser = localStorage.getItem('astral_remember_user');
            if (savedUser && document.getElementById('login-username')) {
                document.getElementById('login-username').value = savedUser;
                if (loginRemember) loginRemember.checked = true;
            }
        } catch (e) {}
    }

    function loadLocalTheme() {
        try {
            const savedTheme = localStorage.getItem('astral_theme') || 'modern-dark';
            document.documentElement.setAttribute('data-theme', savedTheme);
            document.body.className = `theme-${savedTheme}`;
            document.querySelectorAll('.theme-card').forEach(card => {
                if (card.dataset.theme === savedTheme) {
                    card.classList.add('active');
                } else {
                    card.classList.remove('active');
                }
            });
            renderLucideIcons();
        } catch (e) {}
    }

    function initPasswordToggleButtons() {
        document.querySelectorAll('.btn-toggle-pwd').forEach(btn => {
            btn.addEventListener('click', () => {
                const targetId = btn.getAttribute('data-target');
                const input = document.getElementById(targetId);
                if (input) {
                    if (input.type === 'password') {
                        input.type = 'text';
                        btn.innerHTML = '<i data-lucide="eye-off" class="icon-sm"></i>';
                    } else {
                        input.type = 'password';
                        btn.innerHTML = '<i data-lucide="eye" class="icon-sm"></i>';
                    }
                    renderLucideIcons();
                }
            });
        });
    }

    // Check for ?token= in URL (for Email Verification link or Password Reset link)
    function checkUrlQueryParams() {
        const urlParams = new URLSearchParams(window.location.search);
        const token = urlParams.get('token');
        const path = window.location.pathname;

        if (token) {
            if (path.includes('reset-password') || urlParams.get('action') === 'reset-password') {
                toggleAuth('reset');
                const tokenInput = document.getElementById('reset-token-input');
                if (tokenInput) tokenInput.value = token;
            } else if (path.includes('verify-email') || urlParams.get('action') === 'verify-email') {
                // Auto verify with link token
                autoVerifyEmailWithToken(token);
            }
        }
    }

    async function autoVerifyEmailWithToken(token) {
        try {
            const res = await fetch('/api/verify-email', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: token, remember: true })
            });
            const data = await res.json();
            if (data.success) {
                showFloatingToast('✓ E-posta adresiniz başarıyla doğrulandı!');
                initApp(data.user);
            } else {
                toggleAuth('login');
                document.getElementById('login-error').textContent = data.message || 'Doğrulama bağlantısı geçersiz.';
            }
        } catch (e) {
            toggleAuth('login');
        }
    }

    // Auth Screen Switcher
    safeOn(showRegister, 'click', (e) => { e.preventDefault(); toggleAuth('register'); });
    safeOn(showLogin, 'click', (e) => { e.preventDefault(); toggleAuth('login'); });
    if (showLoginFromVerify) safeOn(showLoginFromVerify, 'click', (e) => { e.preventDefault(); toggleAuth('login'); });
    if (showLoginFromForgot) safeOn(showLoginFromForgot, 'click', (e) => { e.preventDefault(); toggleAuth('login'); });
    if (showLoginFromReset) safeOn(showLoginFromReset, 'click', (e) => { e.preventDefault(); toggleAuth('login'); });
    if (linkForgotPassword) safeOn(linkForgotPassword, 'click', (e) => { e.preventDefault(); toggleAuth('forgot'); });

    function toggleAuth(type) {
        loginFormContainer.style.display = type === 'login' ? 'block' : 'none';
        loginForm.style.display = 'block';
        login2faForm.style.display = 'none';
        registerFormContainer.style.display = type === 'register' ? 'block' : 'none';
        if (verifyFormContainer) verifyFormContainer.style.display = type === 'verify' ? 'block' : 'none';
        if (forgotFormContainer) forgotFormContainer.style.display = type === 'forgot' ? 'block' : 'none';
        if (resetFormContainer) resetFormContainer.style.display = type === 'reset' ? 'block' : 'none';

        // Clear error messages
        document.getElementById('login-error').textContent = '';
        document.getElementById('login-2fa-error').textContent = '';
        document.getElementById('register-error').textContent = '';
        if (verifyError) verifyError.textContent = '';
        if (verifySuccess) verifySuccess.style.display = 'none';
        if (document.getElementById('forgot-error')) document.getElementById('forgot-error').textContent = '';
        if (document.getElementById('forgot-success')) document.getElementById('forgot-success').style.display = 'none';
        if (document.getElementById('reset-error')) document.getElementById('reset-error').textContent = '';
        if (document.getElementById('reset-success')) document.getElementById('reset-success').style.display = 'none';
    }

    function showVerificationScreen(email, username) {
        pendingVerificationEmail = email;
        pendingVerificationUsername = username || '';
        if (verifyEmailDisplay) verifyEmailDisplay.textContent = email;
        if (verifyCodeInput) {
            verifyCodeInput.value = '';
            setTimeout(() => verifyCodeInput.focus(), 150);
        }
        toggleAuth('verify');
        startResendCountdown(60);
    }

    function startResendCountdown(seconds = 60) {
        if (resendCountdownTimer) clearInterval(resendCountdownTimer);
        let remaining = seconds;
        if (btnResendCode) {
            btnResendCode.disabled = true;
            if (resendCountdown) resendCountdown.textContent = remaining;
        }

        resendCountdownTimer = setInterval(() => {
            remaining--;
            if (resendCountdown) resendCountdown.textContent = remaining;
            if (remaining <= 0) {
                clearInterval(resendCountdownTimer);
                resendCountdownTimer = null;
                if (btnResendCode) {
                    btnResendCode.disabled = false;
                    btnResendCode.textContent = 'Tekrar Gönder';
                }
            }
        }, 1000);
    }

    if (btnResendCode) {
        safeOn(btnResendCode, 'click', async () => {
            if (!pendingVerificationEmail) return;
            btnResendCode.disabled = true;
            btnResendCode.textContent = 'Gönderiliyor...';
            try {
                const res = await fetch('/api/resend-verification', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: pendingVerificationEmail })
                });
                const data = await res.json();
                if (data.success) {
                    showFloatingToast('✉️ Yeni doğrulama kodu contact@example.com tarafından gönderildi.');
                    startResendCountdown(60);
                } else {
                    if (verifyError) verifyError.textContent = data.message || 'Kod gönderilemedi.';
                    btnResendCode.disabled = false;
                    btnResendCode.textContent = 'Tekrar Gönder';
                }
            } catch (err) {
                if (verifyError) verifyError.textContent = 'Bağlantı hatası oluştu.';
                btnResendCode.disabled = false;
                btnResendCode.textContent = 'Tekrar Gönder';
            }
        });
    }

    // Quick Demo Account Buttons
    safeOn(document.getElementById('btn-demo-user1'), 'click', () => {
        document.getElementById('login-username').value = 'The_kodak';
        document.getElementById('login-password').value = '1234';
    });
    safeOn(document.getElementById('btn-demo-user2'), 'click', () => {
        document.getElementById('login-username').value = 'thekodak';
        document.getElementById('login-password').value = '1234';
    });

    // 1. Login Form Submit
    safeOn(loginForm, 'submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('login-username').value.trim();
        const password = document.getElementById('login-password').value;
        const remember = loginRemember ? loginRemember.checked : true;
        const loginBtn = document.getElementById('btn-login-submit');

        if (loginBtn) {
            loginBtn.disabled = true;
            loginBtn.textContent = 'Giriş Yapılıyor...';
        }

        try {
            const res = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password, remember })
            });
            const data = await res.json();

            if (data.requires_2fa) {
                // Transition to 2FA Prompt Form
                pending2faTempToken = data.temp_token;
                loginForm.style.display = 'none';
                login2faForm.style.display = 'block';
                is2faRecoveryMode = false;
                twofaCodeLabel.textContent = '6 Haneli Authenticator Kodu';
                login2faCodeInput.placeholder = '• • • • • •';
                login2faCodeInput.value = '';
                login2faCodeInput.focus();
            } else if (data.requires_verification) {
                showVerificationScreen(data.email, data.username || username);
                if (verifyError) verifyError.textContent = data.message;
            } else if (data.success) {
                if (remember) {
                    try { localStorage.setItem('astral_remember_user', username); } catch (e) {}
                } else {
                    try { localStorage.removeItem('astral_remember_user'); } catch (e) {}
                }
                initApp(data.user);
            } else {
                document.getElementById('login-error').textContent = data.message || 'Giriş yapılamadı.';
            }
        } catch (err) {
            document.getElementById('login-error').textContent = 'Sunucuya bağlanılamadı.';
        } finally {
            if (loginBtn) {
                loginBtn.disabled = false;
                loginBtn.textContent = 'Giriş Yap';
            }
        }
    });

    // 2. 2FA Form Submit
    if (login2faForm) {
        safeOn(btnToggleRecoveryMode, 'click', (e) => {
            e.preventDefault();
            is2faRecoveryMode = !is2faRecoveryMode;
            if (is2faRecoveryMode) {
                twofaCodeLabel.textContent = 'Tek Kullanımlık Kurtarma Kodu';
                login2faCodeInput.placeholder = 'XXXX-XXXX';
                btnToggleRecoveryMode.textContent = 'Authenticator Kodu Kullan';
            } else {
                twofaCodeLabel.textContent = '6 Haneli Authenticator Kodu';
                login2faCodeInput.placeholder = '• • • • • •';
                btnToggleRecoveryMode.textContent = 'Kurtarma Kodu Kullan';
            }
            login2faCodeInput.value = '';
            login2faCodeInput.focus();
        });

        safeOn(btnBackFrom2fa, 'click', (e) => {
            e.preventDefault();
            login2faForm.style.display = 'none';
            loginForm.style.display = 'block';
            document.getElementById('login-2fa-error').textContent = '';
        });

        safeOn(login2faForm, 'submit', async (e) => {
            e.preventDefault();
            const code = login2faCodeInput.value.trim();
            const trustDevice = document.getElementById('login-trust-device').checked;
            const submitBtn = document.getElementById('btn-login-2fa-submit');

            if (!code) {
                document.getElementById('login-2fa-error').textContent = 'Lütfen doğrulama kodunu girin.';
                return;
            }

            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = 'Doğrulanıyor...';
            }

            try {
                const res = await fetch('/api/login/2fa', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        temp_token: pending2faTempToken,
                        code: code,
                        trust_device: trustDevice
                    })
                });
                const data = await res.json();
                if (data.success) {
                    showFloatingToast('✓ 2FA Doğrulandı! Giriş başarılı.');
                    initApp(data.user);
                } else {
                    document.getElementById('login-2fa-error').textContent = data.message || 'Geçersiz 2FA kodu.';
                }
            } catch (err) {
                document.getElementById('login-2fa-error').textContent = 'Bağlantı hatası oluştu.';
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Doğrula ve Giriş Yap';
                }
            }
        });
    }

    // 3. Register Form Submit
    safeOn(registerForm, 'submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('register-email').value.trim();
        const username = document.getElementById('register-username').value.trim();
        const displayName = document.getElementById('register-displayname').value.trim();
        const password = document.getElementById('register-password').value;
        const passwordConfirm = document.getElementById('register-password-confirm').value;
        const regBtn = document.getElementById('btn-register-submit');

        if (password !== passwordConfirm) {
            document.getElementById('register-error').textContent = 'Parolalar birbiriyle eşleşmiyor.';
            return;
        }

        if (regBtn) {
            regBtn.disabled = true;
            regBtn.textContent = 'Kayıt Yapılıyor...';
        }

        try {
            const res = await fetch('/api/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email,
                    username,
                    display_name: displayName,
                    password,
                    password_confirm: passwordConfirm
                })
            });
            const data = await res.json();
            if (data.requires_verification) {
                showVerificationScreen(data.email, data.username || username);
                showFloatingToast('✉️ Doğrulama kodu contact@example.com tarafından e-postanıza iletildi.');
            } else if (data.success) {
                initApp(data.user);
            } else {
                document.getElementById('register-error').textContent = data.message || 'Kayıt başarısız.';
            }
        } catch (err) {
            document.getElementById('register-error').textContent = 'Sunucuya bağlanılamadı.';
        } finally {
            if (regBtn) {
                regBtn.disabled = false;
                regBtn.textContent = 'Kayıt Ol ve Doğrula';
            }
        }
    });

    // 4. Verification Form Submit
    if (verifyForm) {
        safeOn(verifyForm, 'submit', async (e) => {
            e.preventDefault();
            const code = verifyCodeInput ? verifyCodeInput.value.trim() : '';
            const remember = loginRemember ? loginRemember.checked : true;
            const submitBtn = document.getElementById('btn-verify-submit');

            if (!code || code.length !== 6) {
                if (verifyError) verifyError.textContent = 'Lütfen 6 haneli doğrulama kodunu eksiksiz girin.';
                return;
            }

            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = 'Doğrulanıyor...';
            }

            try {
                const res = await fetch('/api/verify-email', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: pendingVerificationEmail, code, remember })
                });
                const data = await res.json();
                if (data.success) {
                    if (verifySuccess) {
                        verifySuccess.textContent = '✓ ' + (data.message || 'E-posta doğrulandı! Giriş yapılıyor...');
                        verifySuccess.style.display = 'block';
                    }
                    if (verifyError) verifyError.textContent = '';
                    if (remember && pendingVerificationUsername) {
                        try { localStorage.setItem('astral_remember_user', pendingVerificationUsername); } catch (e) {}
                    }
                    AudioEngine.play('call_connected');
                    setTimeout(() => {
                        initApp(data.user);
                    }, 500);
                } else {
                    if (verifyError) verifyError.textContent = data.message || 'Geçersiz doğrulama kodu.';
                    if (verifySuccess) verifySuccess.style.display = 'none';
                    AudioEngine.play('error_buzzer');
                }
            } catch (err) {
                if (verifyError) verifyError.textContent = 'Bağlantı hatası oluştu.';
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Doğrula ve Giriş Yap';
                }
            }
        });
    }

    // 5. Forgot Password Form Submit
    if (forgotPasswordForm) {
        safeOn(forgotPasswordForm, 'submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('forgot-email').value.trim();
            const submitBtn = document.getElementById('btn-forgot-submit');
            const errEl = document.getElementById('forgot-error');
            const succEl = document.getElementById('forgot-success');

            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = 'Gönderiliyor...';
            }

            try {
                const res = await fetch('/api/forgot-password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email })
                });
                const data = await res.json();
                errEl.textContent = '';
                succEl.textContent = '✓ ' + data.message;
                succEl.style.display = 'block';
            } catch (err) {
                errEl.textContent = 'Bağlantı hatası oluştu.';
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Sıfırlama Bağlantısı Gönder';
                }
            }
        });
    }

    // 6. Reset Password Form Submit
    if (resetPasswordForm) {
        safeOn(resetPasswordForm, 'submit', async (e) => {
            e.preventDefault();
            const token = document.getElementById('reset-token-input').value;
            const password = document.getElementById('reset-password').value;
            const passwordConfirm = document.getElementById('reset-password-confirm').value;
            const submitBtn = document.getElementById('btn-reset-submit');
            const errEl = document.getElementById('reset-error');
            const succEl = document.getElementById('reset-success');

            if (password !== passwordConfirm) {
                errEl.textContent = 'Parolalar birbiriyle eşleşmiyor.';
                return;
            }

            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = 'Güncelleniyor...';
            }

            try {
                const res = await fetch('/api/reset-password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        token: token,
                        password: password,
                        password_confirm: passwordConfirm
                    })
                });
                const data = await res.json();
                if (data.success) {
                    errEl.textContent = '';
                    succEl.textContent = '✓ ' + data.message;
                    succEl.style.display = 'block';
                    setTimeout(() => {
                        toggleAuth('login');
                    }, 2000);
                } else {
                    errEl.textContent = data.message || 'Şifre güncellenemedi.';
                }
            } catch (err) {
                errEl.textContent = 'Bağlantı hatası oluştu.';
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Şifremi Güncelle';
                }
            }
        });
    }

    async function handleLogout() {
        try {
            await fetch('/api/logout', { method: 'POST' });
        } catch (e) {}

        if (socket) {
            try { socket.disconnect(); } catch (e) {}
            socket = null;
        }

        currentUser = null;
        currentTargetId = null;
        currentServerId = null;
        currentChannelId = null;

        // Smooth transition to auth screen
        appScreen.classList.add('hidden');
        appScreen.style.display = 'none';
        authScreen.classList.remove('hidden');
        authScreen.style.display = 'flex';
        toggleAuth('login');
        loadRememberedUser();
    }

    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) safeOn(logoutBtn, 'click', handleLogout);

    const settingsLogoutBtn = document.getElementById('settings-logout-btn');
    if (settingsLogoutBtn) safeOn(settingsLogoutBtn, 'click', () => {
        if (settingsModal) settingsModal.style.display = 'none';
        handleLogout();
    });

    const btnDockLogout = document.getElementById('btn-dock-logout');
    if (btnDockLogout) safeOn(btnDockLogout, 'click', handleLogout);

    async function checkAuth() {
        const res = await fetch('/api/auth/status');
        const data = await res.json();
        if (data.logged_in) {
            initApp(data.user);
        } else {
            authScreen.classList.remove('hidden');
            authScreen.style.display = 'flex';
            appScreen.classList.add('hidden');
            appScreen.style.display = 'none';
        }
    }

    function initApp(user) {
        currentUser = user;
        authScreen.classList.add('hidden');
        authScreen.style.display = 'none';
        appScreen.classList.remove('hidden');
        appScreen.style.display = 'flex';

        // Update User UI in Dock
        document.getElementById('my-username').textContent = user.display_name || user.username;
        const myAvatar = document.getElementById('my-avatar');
        if (user.avatar) {
            myAvatar.style.backgroundImage = `url(${user.avatar})`;
            myAvatar.style.backgroundColor = 'transparent';
            myAvatar.textContent = '';
        } else {
            myAvatar.style.backgroundImage = 'none';
            myAvatar.style.backgroundColor = user.color || '#8b5cf6';
            myAvatar.textContent = (user.display_name || user.username).charAt(0).toUpperCase();
        }
        
        const myCustomStatus = document.getElementById('my-custom-status');
        if (myCustomStatus) {
            const statusText = user.custom_status ? `${user.custom_status_emoji || ''} ${user.custom_status}` : '✨ AstralPaws';
            myCustomStatus.textContent = statusText.trim();
        }

        // Account Pending Deletion Banner Check
        const statusBanner = document.getElementById('account-status-banner');
        if (statusBanner) {
            if (user.is_pending_deletion) {
                statusBanner.style.display = 'block';
                const schedDate = user.deletion_scheduled_for ? new Date(user.deletion_scheduled_for).toLocaleDateString('tr-TR') : '14 gün sonra';
                document.getElementById('account-status-banner-text').textContent = `⚠️ Hesabınız silinmek üzere planlanmıştır (${schedDate}). Dilediğiniz zaman iptal edebilirsiniz.`;
            } else {
                statusBanner.style.display = 'none';
            }
        }

        // Connect Socket.IO
        socket = io();
        setupSocketListeners();

        // Load initial data
        loadFriends();
        loadConversations();
        loadServers();
        switchToHome();
        initEmojiPicker();
        initSoundboard();
        initSettingsDashboard();
        initMessagingModals();
    }

    // --- Real-Time Socket Event Listeners ---
    function setupSocketListeners() {
        socket.on('receive_message', (msg) => {
            const isRelevant =
                (msg.conversation_id && msg.conversation_id === currentConversationId) ||
                (msg.channel_id && msg.channel_id === currentChannelId) ||
                (!msg.conversation_id && !msg.channel_id && (
                    (msg.receiver_id === currentTargetId && msg.sender_id === currentUser.id) ||
                    (msg.receiver_id === currentUser.id && msg.sender_id === currentTargetId) ||
                    (currentTargetId === null && msg.receiver_id === null)
                ));

            if (isRelevant) {
                appendMessage(msg);
                scrollToBottom();
                if (msg.sender_id !== currentUser.id) {
                    AudioEngine.play('message_incoming');
                }
            }

            // Update conversation list sidebar unread / last message
            if (msg.conversation_id) {
                loadConversations();
            }
        });

        socket.on('conversation_updated', () => {
            loadConversations();
        });

        socket.on('message_edited', ({ message_id, text, is_edited }) => {
            const textEl = document.getElementById(`msg-text-${message_id}`);
            if (textEl) {
                textEl.innerHTML = parseMarkdown(text);
                const editedBadge = document.getElementById(`msg-edited-${message_id}`);
                if (editedBadge) editedBadge.style.display = 'inline';
            }
        });

        socket.on('message_deleted', ({ message_id, is_deleted_everyone, text }) => {
            const msgEl = document.getElementById(`msg-${message_id}`);
            if (msgEl) {
                if (is_deleted_everyone) {
                    const textEl = document.getElementById(`msg-text-${message_id}`);
                    if (textEl) textEl.innerHTML = `<span class="deleted-msg-text">${text || '🚫 Bu mesaj silindi.'}</span>`;
                    const attEl = msgEl.querySelector('.msg-attachment-wrap');
                    if (attEl) attEl.remove();
                    const actionMenu = msgEl.querySelector('.msg-action-menu');
                    if (actionMenu) actionMenu.remove();
                    msgEl.classList.add('msg-deleted-everyone');
                } else {
                    msgEl.style.opacity = '0';
                    setTimeout(() => msgEl.remove(), 200);
                }
            }
        });

        socket.on('message_hidden_for_me', ({ message_id }) => {
            const msgEl = document.getElementById(`msg-${message_id}`);
            if (msgEl) {
                msgEl.style.opacity = '0';
                setTimeout(() => msgEl.remove(), 200);
            }
        });

        socket.on('reaction_updated', ({ message_id, reactions }) => {
            updateMessageReactions(message_id, reactions);
        });

        const handleTypingEvent = ({ username, display_name, conversation_id, channel_id, target_id }) => {
            const isRelevant =
                (conversation_id && conversation_id === currentConversationId) ||
                (channel_id && channel_id === currentChannelId) ||
                (target_id && target_id === currentUser?.id);

            if (isRelevant) {
                const typingEl = document.getElementById('typing-indicator');
                const typingTxt = document.getElementById('typing-text');
                if (typingTxt) typingTxt.textContent = `${display_name || username} yazıyor...`;
                if (typingEl) typingEl.style.display = 'flex';
            }
        };

        const handleStopTypingEvent = () => {
            const typingEl = document.getElementById('typing-indicator');
            if (typingEl) typingEl.style.display = 'none';
        };

        socket.on('user_typing', handleTypingEvent);
        socket.on('typing', handleTypingEvent);
        socket.on('user_stop_typing', handleStopTypingEvent);
        socket.on('stop_typing', handleStopTypingEvent);

        socket.on('soundboard_triggered', ({ sound_key, username }) => {
            AudioEngine.playSoundboard(sound_key);
            showFloatingToast(`🎵 ${username} played ${sound_key}!`);
        });

        socket.on('channel_created', (ch) => {
            if (currentServerId === ch.server_id) {
                appendChannelToSidebar(ch);
            }
        });

        socket.on('channel_deleted', ({ channel_id, server_id }) => {
            if (currentServerId === server_id) {
                const el = document.getElementById(`channel-${channel_id}`);
                if (el) el.remove();
                if (currentChannelId === channel_id) switchToHome();
            }
        });

        socket.on('canvas_stroke', handleCanvasRemoteStroke);
        socket.on('canvas_cleared', () => {
            const canvas = document.getElementById('collab-canvas');
            if (canvas) {
                const ctx = canvas.getContext('2d');
                ctx.clearRect(0, 0, canvas.width, canvas.height);
            }
        });

        socket.on('game_update', handleRemoteGameUpdate);

        // Real-time friend requests & server events
        socket.on('friend_request_received', (data) => {
            AudioEngine.play('friend_request');
            showFloatingToast(`👋 @${data.from_username} sana arkadaşlık isteği gönderdi!`);
            loadFriends();
        });

        socket.on('friend_request_accepted', (data) => {
            AudioEngine.play('friend_request');
            showFloatingToast(`🎉 @${data.username} arkadaşlık isteğini kabul etti!`);
            loadFriends();
        });

        socket.on('user_status_updated', () => {
            loadFriends();
            if (currentServerId) {
                fetch(`/api/servers/${currentServerId}/members`).then(r => r.json()).then(d => {
                    if (d.members) renderServerMembers(d.members);
                });
            }
        });

        socket.on('member_joined_server', (data) => {
            if (currentServerId === data.server_id) {
                fetch(`/api/servers/${currentServerId}/members`).then(r => r.json()).then(d => {
                    if (d.members) renderServerMembers(d.members);
                });
            }
        });

        socket.on('server_deleted', (data) => {
            loadServers();
            if (currentServerId === data.server_id) switchToHome();
        });

        // Direct 1-on-1 Voice Call Signaling Events
        socket.on('call_incoming', handleIncomingCall);
        socket.on('call_response', handleCallResponse);
        socket.on('call_ended', handleCallEnded);
        socket.on('call_signal', handleCallSignal);

        // WebRTC Voice Channel Signaling
        socket.on('user_joined_voice', handleUserJoinedVoice);
        socket.on('user_left_voice', handleUserLeftVoice);
        socket.on('webrtc_offer', handleWebrtcOffer);
        socket.on('webrtc_answer', handleWebrtcAnswer);
        socket.on('webrtc_ice_candidate', handleWebrtcIceCandidate);
        socket.on('user_speaking_state', ({ user_id, is_speaking }) => {
            const tile = document.getElementById(`participant-${user_id}`);
            if (tile) tile.classList.toggle('speaking', is_speaking);
            if (directCallState.active && directCallState.peerId === user_id) {
                const wave = document.getElementById('active-call-wave-visualizer');
                if (wave) wave.style.opacity = is_speaking ? '1' : '0.4';
            }
        });
    }

    // --- Navigation & View Switching ---

    safeOn(navHome, 'click', switchToHome);
    safeOn(document.getElementById('nav-friends-tab'), 'click', switchToHome);

    safeOn(navAiBot, 'click', () => {
        switchChat(null, 'Astral AI', '<i data-lucide="bot" class="icon-sm"></i>', null, true);
    });

    safeOn(document.getElementById('nav-ai-chat-tab'), 'click', () => {
        switchChat(null, 'Astral AI', '<i data-lucide="bot" class="icon-sm"></i>', null, true);
    });

    function switchToHome() {
        currentServerId = null;
        currentTargetId = null;
        if (btnStartDmVoiceCall) btnStartDmVoiceCall.style.display = 'none';
        if (currentChannelId && socket) {
            socket.emit('leave_chat_channel', { channel_id: currentChannelId });
            socket.emit('leave_canvas', { channel_id: currentChannelId });
            currentChannelId = null;
        }

        document.querySelectorAll('.server-icon').forEach(el => el.classList.remove('active'));
        if (navHome) navHome.classList.add('active');

        if (homeView) homeView.style.display = 'flex';
        if (serverView) serverView.style.display = 'none';
        if (sidebarTitle) sidebarTitle.textContent = 'AstralPaws';
        const srvHdr = document.getElementById('server-header-actions');
        if (srvHdr) srvHdr.style.display = 'none';
        const srvBdg = document.getElementById('sidebar-server-badge');
        if (srvBdg) srvBdg.style.display = 'none';
        const sidebarChevron = document.getElementById('sidebar-chevron');
        if (sidebarChevron) sidebarChevron.style.display = 'none';

        if (activitySidebar) activitySidebar.style.display = 'none';

        const friendsDash = document.getElementById('friends-dashboard');
        const chatPane = document.getElementById('chat-messages-pane');
        const canvasPane = document.getElementById('canvas-pane');
        const voicePane = document.getElementById('voice-pane');

        if (friendsDash) friendsDash.style.display = 'flex';
        if (chatPane) chatPane.style.display = 'none';
        if (canvasPane) canvasPane.style.display = 'none';
        if (voicePane) voicePane.style.display = 'none';

        if (chatTargetIcon) chatTargetIcon.innerHTML = '<i data-lucide="users" class="icon-sm"></i>';
        if (chatTargetName) chatTargetName.textContent = 'Arkadaşlar';
        if (chatTargetSub) chatTargetSub.textContent = 'AstralPaws Arkadaş Listesi & Direkt Mesajlar';

        document.querySelectorAll('#sidebar-dm-list .friend-item, .nav-item').forEach(el => el.classList.remove('active'));
        const fTab = document.getElementById('nav-friends-tab');
        if (fTab) fTab.classList.add('active');

        loadFriends();
        renderLucideIcons();
    }

    async function switchToServer(serverId, serverName) {
        currentServerId = serverId;
        currentTargetId = null;
        if (currentChannelId && socket) {
            socket.emit('leave_chat_channel', { channel_id: currentChannelId });
            socket.emit('leave_canvas', { channel_id: currentChannelId });
            currentChannelId = null;
        }

        document.querySelectorAll('.server-icon').forEach(el => el.classList.remove('active'));
        const srvIcon = document.getElementById(`server-icon-${serverId}`);
        if (srvIcon) srvIcon.classList.add('active');

        if (homeView) homeView.style.display = 'none';
        if (serverView) serverView.style.display = 'flex';
        if (sidebarTitle) sidebarTitle.textContent = serverName;
        const srvHdr = document.getElementById('server-header-actions');
        if (srvHdr) srvHdr.style.display = 'flex';
        const srvBdg = document.getElementById('sidebar-server-badge');
        if (srvBdg) srvBdg.style.display = 'inline';
        const sidebarChevron = document.getElementById('sidebar-chevron');
        if (sidebarChevron) sidebarChevron.style.display = 'inline';

        if (activitySidebar) activitySidebar.style.display = 'flex';

        const friendsDash = document.getElementById('friends-dashboard');
        const chatPane = document.getElementById('chat-messages-pane');
        const canvasPane = document.getElementById('canvas-pane');
        const voicePane = document.getElementById('voice-pane');

        if (friendsDash) friendsDash.style.display = 'none';
        if (chatPane) chatPane.style.display = 'flex';
        if (canvasPane) canvasPane.style.display = 'none';
        if (voicePane) voicePane.style.display = 'none';

        const channelListEl = document.getElementById('channel-list');
        if (channelListEl) channelListEl.innerHTML = '';

        // Fetch channels & members
        const [cRes, mRes] = await Promise.all([
            fetch(`/api/servers/${serverId}/channels`),
            fetch(`/api/servers/${serverId}/members`)
        ]);
        const cData = await cRes.json();
        const mData = await mRes.json();

        let firstTextChannel = null;
        if (cData.channels) {
            cData.channels.forEach(ch => {
                appendChannelToSidebar(ch);
                if (ch.type === 'text' && !firstTextChannel) firstTextChannel = ch;
            });
        }

        if (mData.members) {
            renderServerMembers(mData.members);
        }

        // Fetch invite code
        const sRes = await fetch('/api/servers');
        const sData = await sRes.json();
        const srv = sData.servers ? sData.servers.find(s => s.id === serverId) : null;
        if (srv && currentServerInvite) currentServerInvite.textContent = srv.invite_code;

        if (firstTextChannel) {
            switchToChannel(firstTextChannel.id, firstTextChannel.name, firstTextChannel.type);
        }
        renderLucideIcons();
    }

    async function switchToChannel(channelId, channelName, type = 'text') {
        if (currentChannelId && socket) {
            socket.emit('leave_chat_channel', { channel_id: currentChannelId });
            socket.emit('leave_canvas', { channel_id: currentChannelId });
        }

        currentChannelId = channelId;
        currentChannelType = type;
        currentTargetId = null;

        document.querySelectorAll('.channel-item').forEach(el => el.classList.remove('active'));
        const chEl = document.getElementById(`channel-${channelId}`);
        if (chEl) chEl.classList.add('active');

        const friendsDash = document.getElementById('friends-dashboard');
        const chatPane = document.getElementById('chat-messages-pane');
        const canvasPane = document.getElementById('canvas-pane');
        const voicePane = document.getElementById('voice-pane');

        if (friendsDash) friendsDash.style.display = 'none';

        if (type === 'canvas') {
            if (chatPane) chatPane.style.display = 'none';
            if (voicePane) voicePane.style.display = 'none';
            if (canvasPane) canvasPane.style.display = 'flex';
            if (chatTargetName) chatTargetName.textContent = `# ${channelName}`;
            if (chatTargetIcon) chatTargetIcon.innerHTML = '<i data-lucide="palette" class="icon-sm"></i>';
            if (chatTargetSub) chatTargetSub.textContent = `Canlı İşbirlikli Çizim Tuvali`;
            if (socket) socket.emit('join_canvas', { channel_id: channelId });
            initCollaborativeCanvas();
            renderLucideIcons();
            return;
        }

        if (canvasPane) canvasPane.style.display = 'none';
        if (voicePane) voicePane.style.display = 'none';
        if (chatPane) chatPane.style.display = 'flex';

        if (socket) socket.emit('join_chat_channel', { channel_id: channelId });
        if (chatTargetName) chatTargetName.textContent = `# ${channelName}`;
        if (chatTargetIcon) chatTargetIcon.innerHTML = '<i data-lucide="hash" class="icon-sm"></i>';
        if (chatTargetSub) chatTargetSub.textContent = `#${channelName} kanalına hoş geldiniz!`;
        if (messageInput) messageInput.placeholder = `#${channelName} kanalına mesaj yazın...`;

        if (chatHistory) chatHistory.innerHTML = '';
        const res = await fetch(`/api/messages/channel/${channelId}`);
        const data = await res.json();
        if (data.messages) {
            data.messages.forEach(msg => appendMessage(msg));
        }
        scrollToBottom();
        renderLucideIcons();
    }

    // ===================================================================
    // CONVERSATIONS & MESSAGING SYSTEM (DMs, Groups, Rich Media, Voice)
    // ===================================================================

    async function loadConversations() {
        try {
            const res = await fetch('/api/conversations');
            if (!res.ok) return;
            const data = await res.json();
            cachedConversations = data.conversations || [];
            renderConversations(cachedConversations);
        } catch (err) {
            console.error("Error loading conversations:", err);
        }
    }

    function renderConversations(conversations) {
        const dmList = document.getElementById('sidebar-dm-list');
        const groupList = document.getElementById('sidebar-group-list');
        if (!dmList) return;

        const dms = conversations.filter(c => c.type === 'direct');
        const groups = conversations.filter(c => c.type === 'group');

        // Render DMs
        dmList.innerHTML = '';
        if (dms.length === 0) {
            dmList.innerHTML = '<div class="empty-state-small">Henüz bir özel sohbet yok</div>';
        } else {
            dms.forEach(c => {
                const item = document.createElement('div');
                item.className = `group-chat-item ${currentConversationId === c.id ? 'active' : ''}`;
                item.id = `conv-item-${c.id}`;

                const unreadHtml = c.unread_count > 0 ? `<span class="unread-msg-badge">${c.unread_count}</span>` : '';
                const lastMsgText = c.last_message ? (c.last_message.text || '📎 Dosya / Medya') : 'Sohbet başlatın...';

                item.innerHTML = `
                    <div class="avatar-wrap">
                        <div class="avatar" style="background-color: ${c.icon_color || '#8b5cf6'}; width: 32px; height: 32px; font-size: 13px;">
                            ${(c.display_name || 'U').charAt(0).toUpperCase()}
                        </div>
                        <div class="status-dot status-${c.peer_status || 'offline'}"></div>
                    </div>
                    <div class="group-info-wrap">
                        <div class="group-title-row">
                            <span class="group-name-text">${escapeHTML(c.display_name)}</span>
                            ${unreadHtml}
                        </div>
                        <span class="group-member-count-sub">${escapeHTML(lastMsgText)}</span>
                    </div>
                `;

                item.onclick = () => switchConversation(c.id, c.display_name, c.icon_color, false, 2);
                dmList.appendChild(item);
            });
        }

        // Render Group Chats
        if (groupList) {
            groupList.innerHTML = '';
            if (groups.length === 0) {
                groupList.innerHTML = '<div class="empty-state-small">Henüz bir grup sohbeti yok</div>';
            } else {
                groups.forEach(c => {
                    const item = document.createElement('div');
                    item.className = `group-chat-item ${currentConversationId === c.id ? 'active' : ''}`;
                    item.id = `conv-item-${c.id}`;

                    const unreadHtml = c.unread_count > 0 ? `<span class="unread-msg-badge">${c.unread_count}</span>` : '';
                    const lastMsgText = c.last_message ? (c.last_message.text || '📎 Dosya / Medya') : `${c.member_count || 0} üye`;

                    item.innerHTML = `
                        <div class="group-avatar-badge" style="background: ${c.icon_color || 'linear-gradient(135deg, #6366f1, #8b5cf6)'}">
                            ${(c.name || 'G').charAt(0).toUpperCase()}
                        </div>
                        <div class="group-info-wrap">
                            <div class="group-title-row">
                                <span class="group-name-text">${escapeHTML(c.name)}</span>
                                ${unreadHtml}
                            </div>
                            <span class="group-member-count-sub">${escapeHTML(lastMsgText)}</span>
                        </div>
                    `;

                    item.onclick = () => switchConversation(c.id, c.name, c.icon_color, true, c.member_count);
                    groupList.appendChild(item);
                });
            }
        }
    }

    async function switchConversation(convId, convTitle, iconColor, isGroup = false, memberCount = 2) {
        if (currentConversationId && socket && currentConversationId !== convId) {
            socket.emit('leave_conversation', { conversation_id: currentConversationId });
        }

        currentConversationId = convId;
        currentTargetId = null;
        currentChannelId = null;
        currentServerId = null;
        currentChannelType = 'text';

        if (socket) {
            socket.emit('join_conversation', { conversation_id: convId });
        }

        const friendsDash = document.getElementById('friends-dashboard');
        const chatPane = document.getElementById('chat-messages-pane');
        const canvasPane = document.getElementById('canvas-pane');
        const voicePane = document.getElementById('voice-pane');
        const btnGroupInfo = document.getElementById('btn-group-info');

        if (friendsDash) friendsDash.style.display = 'none';
        if (canvasPane) canvasPane.style.display = 'none';
        if (voicePane) voicePane.style.display = 'none';
        if (chatPane) chatPane.style.display = 'flex';
        if (activitySidebar) activitySidebar.style.display = 'none';

        if (btnGroupInfo) {
            btnGroupInfo.style.display = isGroup ? 'inline-flex' : 'none';
        }

        if (btnStartDmVoiceCall) {
            btnStartDmVoiceCall.style.display = !isGroup ? 'inline-flex' : 'none';
        }

        if (chatTargetName) chatTargetName.textContent = isGroup ? convTitle : `@${convTitle}`;
        if (chatTargetIcon) {
            chatTargetIcon.innerHTML = isGroup 
                ? '<i data-lucide="users" class="icon-sm"></i>' 
                : '<i data-lucide="message-square" class="icon-sm"></i>';
        }
        if (chatTargetSub) {
            chatTargetSub.textContent = isGroup ? `${memberCount} Üyeli Grup Sohbeti` : 'Birebir Özel Mesajlaşma';
        }
        if (messageInput) {
            messageInput.placeholder = isGroup ? `${convTitle} grubuna mesaj yazın...` : `@${convTitle} kullanıcısına mesaj yazın...`;
        }

        document.querySelectorAll('.group-chat-item, .friend-item, .nav-item').forEach(el => el.classList.remove('active'));
        const activeItem = document.getElementById(`conv-item-${convId}`);
        if (activeItem) activeItem.classList.add('active');

        if (chatHistory) chatHistory.innerHTML = '';

        try {
            const res = await fetch(`/api/conversations/${convId}/messages`);
            if (res.ok) {
                const data = await res.json();
                if (data.messages) {
                    data.messages.forEach(msg => appendMessage(msg));
                }
                scrollToBottom();
            }
        } catch (err) {
            console.error("Error loading conversation messages:", err);
        }

        renderLucideIcons();
    }

    async function switchChat(targetId, targetName, iconHtml, channelId = null, isAi = false, color = '#8b5cf6') {
        if (isAi) {
            currentConversationId = null;
            currentTargetId = null;
            currentChannelId = null;
            currentChannelType = 'text';

            const friendsDash = document.getElementById('friends-dashboard');
            const chatPane = document.getElementById('chat-messages-pane');
            const canvasPane = document.getElementById('canvas-pane');
            const voicePane = document.getElementById('voice-pane');

            if (friendsDash) friendsDash.style.display = 'none';
            if (canvasPane) canvasPane.style.display = 'none';
            if (voicePane) voicePane.style.display = 'none';
            if (chatPane) chatPane.style.display = 'flex';
            if (activitySidebar) activitySidebar.style.display = 'none';

            if (chatTargetName) chatTargetName.textContent = 'Astral AI';
            if (chatTargetIcon) chatTargetIcon.innerHTML = '<i data-lucide="bot" class="icon-sm"></i>';
            if (chatTargetSub) chatTargetSub.textContent = 'Yapay Zeka Asistanı';
            if (messageInput) messageInput.placeholder = 'Astral AI ile sohbet edin... (Örn: kod yaz, soru sor)';

            if (btnStartDmVoiceCall) btnStartDmVoiceCall.style.display = 'none';
            const btnGroupInfo = document.getElementById('btn-group-info');
            if (btnGroupInfo) btnGroupInfo.style.display = 'none';

            document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
            const aiTab = document.getElementById('nav-ai-chat-tab');
            if (aiTab) aiTab.classList.add('active');

            if (chatHistory) chatHistory.innerHTML = '';
            appendMessage({
                id: 'ai_welcome',
                sender_id: 0,
                username: 'Astral AI',
                color: '#8b5cf6',
                badges: ['🤖 AI Asistan', '⚡ Llama 3'],
                text: "✨ **Astral AI Asistanı Hazır!**\nSana kodlama, çeviri, sohbet, fikir geliştirme veya her türlü teknik sorunda yardımcı olabilirim. Ne hakkında konuşmak istersin?",
                timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                reactions: {}
            });
            renderLucideIcons();
            return;
        }

        if (channelId) {
            currentConversationId = null;
            currentTargetId = null;
            currentChannelId = channelId;
            currentChannelType = 'text';

            const friendsDash = document.getElementById('friends-dashboard');
            const chatPane = document.getElementById('chat-messages-pane');
            const canvasPane = document.getElementById('canvas-pane');
            const voicePane = document.getElementById('voice-pane');

            if (friendsDash) friendsDash.style.display = 'none';
            if (canvasPane) canvasPane.style.display = 'none';
            if (voicePane) voicePane.style.display = 'none';
            if (chatPane) chatPane.style.display = 'flex';

            if (chatTargetName) chatTargetName.textContent = `# ${targetName}`;
            if (chatTargetIcon) chatTargetIcon.innerHTML = '<i data-lucide="hash" class="icon-sm"></i>';
            if (chatTargetSub) chatTargetSub.textContent = `#${targetName} kanalına hoş geldiniz!`;
            if (messageInput) messageInput.placeholder = `#${targetName} kanalına mesaj yazın...`;

            if (btnStartDmVoiceCall) btnStartDmVoiceCall.style.display = 'none';
            const btnGroupInfo = document.getElementById('btn-group-info');
            if (btnGroupInfo) btnGroupInfo.style.display = 'none';

            if (socket) socket.emit('join_chat_channel', { channel_id: channelId });

            if (chatHistory) chatHistory.innerHTML = '';
            const res = await fetch(`/api/messages/channel/${channelId}`);
            const data = await res.json();
            if (data.messages) {
                data.messages.forEach(msg => appendMessage(msg));
            }
            scrollToBottom();
            renderLucideIcons();
            return;
        }

        if (targetId) {
            // Direct Message -> Resolve/Create Conversation
            try {
                const res = await fetch('/api/conversations/direct', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ target_id: targetId })
                });
                const data = await res.json();
                if (data.success && data.conversation) {
                    await loadConversations();
                    switchConversation(data.conversation.id, data.conversation.display_name, data.conversation.icon_color, false, 2);
                    return;
                }
            } catch (err) {
                console.error("Error creating direct conversation:", err);
            }
        }
    }

    function appendChannelToSidebar(ch) {
        const channelListEl = document.getElementById('channel-list');
        if (!channelListEl) return;
        const div = document.createElement('div');
        div.className = `channel-item ${ch.type}`;
        div.id = `channel-${ch.id}`;

        let icon = '<i data-lucide="hash" class="icon-xs"></i>';
        if (ch.type === 'canvas') icon = '<i data-lucide="palette" class="icon-xs"></i>';
        else if (ch.type === 'voice') icon = '<i data-lucide="volume-2" class="icon-xs"></i>';

        div.innerHTML = `<span class="channel-hash">${icon}</span> <span>${escapeHTML(ch.name)}</span>`;

        div.onclick = () => {
            if (ch.type === 'voice') {
                joinVoiceChannel(ch.id, ch.name);
            } else {
                switchToChannel(ch.id, ch.name, ch.type);
            }
        };

        channelListEl.appendChild(div);
        renderLucideIcons();
    }

    async function loadServers() {
        const res = await fetch('/api/servers');
        const data = await res.json();
        serverList.innerHTML = '';
        data.servers.forEach(s => {
            const div = document.createElement('div');
            div.className = 'server-icon';
            div.id = `server-icon-${s.id}`;
            div.style.backgroundColor = s.icon_color;
            div.textContent = s.name.charAt(0).toUpperCase();
            div.title = s.name;
            div.innerHTML = `<span>${s.name.charAt(0).toUpperCase()}</span><div class="server-active-pill"></div>`;
            div.onclick = () => switchToServer(s.id, s.name);
            serverList.appendChild(div);
        });
    }

    function renderServerMembers(members) {
        serverMembersList.innerHTML = '';
        serverMembersCount.textContent = members.length;

        const roles = [
            { key: 'owner', label: '👑 Sunucu Sahibi', items: [] },
            { key: 'admin', label: '🛡️ Yöneticiler', items: [] },
            { key: 'online', label: '🟢 Çevrimiçi Üyeler', items: [] },
            { key: 'offline', label: '⚫ Çevrimdışı', items: [] }
        ];

        members.forEach(m => {
            if (m.role === 'owner') roles[0].items.push(m);
            else if (m.role === 'admin') roles[1].items.push(m);
            else if (m.status_mode === 'offline') roles[3].items.push(m);
            else roles[2].items.push(m);
        });

        roles.forEach(r => {
            if (r.items.length > 0) {
                const title = document.createElement('div');
                title.className = 'member-category-title';
                title.textContent = `${r.label} — ${r.items.length}`;
                serverMembersList.appendChild(title);

                r.items.forEach(m => {
                    const item = document.createElement('div');
                    item.className = 'member-item';
                    item.innerHTML = `
                        <div class="avatar-wrap">
                            <div class="avatar" style="background-color: ${m.color}; width: 32px; height: 32px; font-size: 13px;">${m.username.charAt(0).toUpperCase()}</div>
                            <div class="status-dot status-${m.status_mode}"></div>
                        </div>
                        <div class="friend-info">
                            <div class="friend-name">${escapeHTML(m.username)}</div>
                            <div class="friend-status-sub">${escapeHTML(m.custom_status || '')}</div>
                        </div>
                    `;
                    item.onclick = () => openUserProfileModal(m.id);
                    serverMembersList.appendChild(item);
                });
            }
        });
    }

    // --- Message Sending & Rendering Engine ---

    function scrollToBottom() {
        const historyEl = document.getElementById('chat-history');
        if (historyEl) historyEl.scrollTop = historyEl.scrollHeight;
    }

    async function sendMessage(attachment = null) {
        if (!currentUser) return;
        const input = document.getElementById('message-input');
        let text = input ? input.value.trim() : '';

        if (!text && !attachment) return;

        // Apply spoiler mode if toggled and text is present
        if (text && isSpoilerActive && !text.startsWith('||') && !text.endsWith('||')) {
            text = `||${text}||`;
        }

        const replyToId = activeReplyMessage ? activeReplyMessage.id : null;

        // 1. If inside an AI Chat tab:
        if (!currentConversationId && !currentChannelId && (currentTargetId === 'ai' || document.getElementById('nav-ai-chat-tab')?.classList.contains('active'))) {
            if (input) input.value = '';
            cancelReply();

            // Append user's message locally
            const userMsg = {
                id: `user_${Date.now()}`,
                sender_id: currentUser.id,
                username: currentUser.username,
                display_name: currentUser.display_name || currentUser.username,
                color: currentUser.color || '#8b5cf6',
                avatar: currentUser.avatar,
                text: text,
                timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                reactions: {}
            };
            appendMessage(userMsg);
            scrollToBottom();
            AudioEngine.play('message_sent');

            // Show typing indicator
            const typingEl = document.getElementById('typing-indicator');
            if (typingEl) {
                const typingTextEl = document.getElementById('typing-text');
                if (typingTextEl) typingTextEl.textContent = 'Astral AI düşünüyor...';
                typingEl.style.display = 'flex';
            }

            try {
                const res = await fetch('/api/ai/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: text })
                });
                const data = await res.json();
                if (typingEl) typingEl.style.display = 'none';

                if (data.reply) {
                    appendMessage({
                        id: `ai_${Date.now()}`,
                        sender_id: 0,
                        username: 'Astral AI',
                        display_name: 'Astral AI',
                        color: '#8b5cf6',
                        badges: ['🤖 AI Asistan', '⚡ Llama 3'],
                        text: data.reply,
                        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                        reactions: {}
                    });
                    scrollToBottom();
                    AudioEngine.play('message_incoming');
                }
            } catch (err) {
                if (typingEl) typingEl.style.display = 'none';
                showFloatingToast("Astral AI yanıt veremedi");
            }
            return;
        }

        // 2. If in a Conversation (DM or Group):
        if (currentConversationId) {
            const payload = {
                conversation_id: currentConversationId,
                text: text || (attachment ? (attachment.name || 'Ekli dosya') : ''),
                reply_to_id: replyToId,
                attachment_url: attachment ? (attachment.url || attachment.file_url) : null,
                attachment_type: attachment ? (attachment.type || attachment.file_type) : null,
                attachment_name: attachment ? (attachment.name || attachment.file_name) : null,
                attachments: attachment ? [{
                    file_url: attachment.url || attachment.file_url,
                    file_name: attachment.name || attachment.file_name || 'file',
                    file_size: attachment.size || attachment.file_size || 0,
                    file_type: attachment.type || attachment.file_type || 'file',
                    mime_type: attachment.mime_type || null,
                    is_spoiler: Boolean(attachment.is_spoiler || isSpoilerActive)
                }] : []
            };

            if (input) input.value = '';
            cancelReply();
            AudioEngine.play('message_sent');

            // Send via Socket.IO if connected, else via REST API fallback
            if (socket && socket.connected) {
                socket.emit('send_message', payload);
            } else {
                try {
                    const res = await fetch(`/api/conversations/${currentConversationId}/messages`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                    const data = await res.json();
                    if (data.success && data.message) {
                        appendMessage(data.message);
                        scrollToBottom();
                    } else if (!data.success) {
                        showFloatingToast(data.message || "Mesaj gönderilemedi");
                    }
                } catch (e) {
                    showFloatingToast("Bağlantı hatası: Mesaj gönderilemedi");
                }
            }
            return;
        }

        // 3. If in a Server Channel:
        if (currentChannelId) {
            const payload = {
                channel_id: currentChannelId,
                text: text || (attachment ? (attachment.name || 'Ekli dosya') : ''),
                reply_to_id: replyToId,
                attachment_url: attachment ? (attachment.url || attachment.file_url) : null,
                attachment_type: attachment ? (attachment.type || attachment.file_type) : null,
                attachment_name: attachment ? (attachment.name || attachment.file_name) : null
            };

            if (input) input.value = '';
            cancelReply();
            AudioEngine.play('message_sent');

            if (socket && socket.connected) {
                socket.emit('send_message', payload);
            } else {
                try {
                    const res = await fetch(`/api/messages/channel/${currentChannelId}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                    const data = await res.json();
                    if (data.success && data.message) {
                        appendMessage(data.message);
                        scrollToBottom();
                    }
                } catch (e) {
                    showFloatingToast("Bağlantı hatası");
                }
            }
            return;
        }

        // 4. If currentTargetId (legacy DM target)
        if (currentTargetId) {
            const payload = {
                target_id: currentTargetId,
                text: text,
                reply_to_id: replyToId,
                attachment_url: attachment ? (attachment.url || attachment.file_url) : null,
                attachment_type: attachment ? (attachment.type || attachment.file_type) : null,
                attachment_name: attachment ? (attachment.name || attachment.file_name) : null
            };

            if (input) input.value = '';
            cancelReply();
            AudioEngine.play('message_sent');

            if (socket && socket.connected) {
                socket.emit('send_message', payload);
            }
            return;
        }

        showFloatingToast("Lütfen bir sohbet veya kanal seçin.");
    }

    function appendMessage(msg) {
        const historyEl = document.getElementById('chat-history');
        if (!historyEl || !msg) return;

        // Check if message already rendered
        const existingEl = document.getElementById(`msg-${msg.id}`);
        if (existingEl) {
            const textEl = document.getElementById(`msg-text-${msg.id}`);
            if (textEl && !msg.is_deleted_everyone) {
                textEl.innerHTML = parseMarkdown(msg.text);
            }
            updateMessageReactions(msg.id, msg.reactions);
            return;
        }

        const isMine = currentUser && (msg.sender_id === currentUser.id);
        const msgDiv = document.createElement('div');
        msgDiv.className = `message-item ${isMine ? 'mine' : ''} ${msg.is_deleted_everyone ? 'msg-deleted-everyone' : ''}`;
        msgDiv.id = `msg-${msg.id}`;

        const senderName = msg.display_name || msg.username || 'Kullanıcı';
        const senderColor = msg.color || '#8b5cf6';
        const avatarInitial = senderName.charAt(0).toUpperCase();
        const avatarHtml = msg.avatar
            ? `<img src="${msg.avatar}" class="avatar" style="width: 38px; height: 38px;" alt="${senderName}">`
            : `<div class="avatar" style="background-color: ${senderColor}; width: 38px; height: 38px;">${avatarInitial}</div>`;

        // Badges HTML
        let badgesHtml = '';
        if (Array.isArray(msg.badges)) {
            badgesHtml = msg.badges.map(b => `<span class="badge-tag">${escapeHTML(b)}</span>`).join('');
        } else if (typeof msg.badges === 'string' && msg.badges) {
            badgesHtml = msg.badges.split(',').filter(b => b.trim()).map(b => `<span class="badge-tag">${escapeHTML(b.trim())}</span>`).join('');
        }

        // Forward badge HTML
        const forwardBadge = msg.forwarded_from
            ? `<div class="forwarded-badge">↗️ <strong>@${escapeHTML(msg.forwarded_from.username || 'Kullanıcı')}</strong> tarafından iletildi</div>`
            : '';

        // Reply quote HTML
        const replyQuote = msg.reply_to
            ? `<div class="reply-quote-bubble" onclick="jumpToMessage(${msg.reply_to.id})">
                <span class="reply-quote-user">↩️ @${escapeHTML(msg.reply_to.username || 'Kullanıcı')}:</span>
                <span class="reply-quote-snippet">${escapeHTML((msg.reply_to.text || '').substring(0, 80))}</span>
               </div>`
            : '';

        // Message text
        const isDeleted = Boolean(msg.is_deleted_everyone);
        const editedBadge = msg.is_edited ? `<span class="edited-badge" id="msg-edited-${msg.id}" title="Düzenlendi">(düzenlendi)</span>` : `<span class="edited-badge" id="msg-edited-${msg.id}" style="display: none;">(düzenlendi)</span>`;
        const contentHtml = isDeleted
            ? `<span class="deleted-msg-text">🚫 Bu mesaj silindi.</span>`
            : parseMarkdown(msg.text);

        // Attachments HTML
        let attachmentsHtml = '';
        const allAtts = (msg.attachments && msg.attachments.length > 0)
            ? msg.attachments
            : (msg.attachment_url ? [{
                file_url: msg.attachment_url,
                file_type: msg.attachment_type || 'file',
                file_name: msg.attachment_name || 'Dosya',
                is_spoiler: false
            }] : []);

        if (allAtts.length > 0 && !isDeleted) {
            attachmentsHtml = '<div class="msg-attachments-container">';
            allAtts.forEach(att => {
                const url = att.file_url || att.url;
                const fType = att.file_type || att.type || 'file';
                const fName = att.file_name || att.name || 'Dosya';
                const spoilerClass = att.is_spoiler ? 'spoiler-media' : '';

                if (fType === 'image' || url.match(/\.(jpeg|jpg|gif|png|webp|svg)($|\?)/i)) {
                    attachmentsHtml += `
                        <div class="msg-attachment-wrap ${spoilerClass}">
                            <img src="${url}" class="msg-media-img" alt="${escapeHTML(fName)}" onclick="openLightbox('${url}')" loading="lazy">
                            ${att.is_spoiler ? '<div class="spoiler-media-overlay" onclick="this.parentElement.classList.remove(\'spoiler-media\')"><span>⚠️ SPOILER (Görmek için tıklayın)</span></div>' : ''}
                        </div>
                    `;
                } else if (fType === 'video' || url.match(/\.(mp4|webm|ogg|mov)($|\?)/i)) {
                    attachmentsHtml += `
                        <div class="msg-attachment-wrap ${spoilerClass}">
                            <video src="${url}" controls class="msg-media-video"></video>
                        </div>
                    `;
                } else if (fType === 'voice_memo' || fType === 'audio' || url.match(/\.(mp3|wav|ogg|webm|m4a)($|\?)/i)) {
                    attachmentsHtml += `
                        <div class="voice-memo-card">
                            <div class="voice-memo-icon">🎤</div>
                            <audio src="${url}" controls class="voice-memo-audio"></audio>
                        </div>
                    `;
                } else if (fType === 'sticker') {
                    attachmentsHtml += `
                        <div class="msg-sticker-wrap">
                            <img src="${url}" class="msg-sticker-img" alt="${escapeHTML(fName)}">
                        </div>
                    `;
                } else {
                    attachmentsHtml += `
                        <div class="msg-file-card">
                            <div class="file-card-icon"><i data-lucide="file" class="icon-md"></i></div>
                            <div class="file-card-info">
                                <span class="file-card-name">${escapeHTML(fName)}</span>
                                <a href="${url}" target="_blank" download class="file-download-link"><i data-lucide="download" class="icon-xs"></i> İndir</a>
                            </div>
                        </div>
                    `;
                }
            });
            attachmentsHtml += '</div>';
        }

        // Action Toolbar
        const actionMenuHtml = isDeleted ? '' : `
            <div class="msg-action-menu">
                <button type="button" class="msg-action-btn" title="Tepki Ekle" onclick="openReactionPicker(${msg.id}, event)"><i data-lucide="smile" class="icon-xs"></i></button>
                <button type="button" class="msg-action-btn" title="Yanıtla" onclick="setReplyTarget(${msg.id}, '${escapeHTML(senderName)}', '${escapeHTML((msg.text || '').replace(/'/g, "\\'"))}')"><i data-lucide="reply" class="icon-xs"></i></button>
                <button type="button" class="msg-action-btn" title="İlet" onclick="openForwardModal(${msg.id}, '${escapeHTML(senderName)}', '${escapeHTML((msg.text || '').replace(/'/g, "\\'"))}')"><i data-lucide="forward" class="icon-xs"></i></button>
                <button type="button" class="msg-action-btn" title="Sabitle" onclick="togglePinMessage(${msg.id})"><i data-lucide="pin" class="icon-xs"></i></button>
                ${isMine ? `<button type="button" class="msg-action-btn" title="Düzenle" onclick="startEditMessage(${msg.id})"><i data-lucide="edit-2" class="icon-xs"></i></button>` : ''}
                <button type="button" class="msg-action-btn btn-danger-hover" title="Sil" onclick="openDeleteMessageModal(${msg.id}, ${isMine})"><i data-lucide="trash-2" class="icon-xs"></i></button>
            </div>
        `;

        const timestampStr = msg.timestamp || (msg.created_at ? new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '');

        msgDiv.innerHTML = `
            ${avatarHtml}
            <div class="msg-body">
                <div class="msg-header">
                    <span class="msg-author" onclick="openUserProfileModal('${msg.sender_public_id || msg.sender_id}')" style="cursor: pointer;">${escapeHTML(senderName)}</span>
                    ${badgesHtml}
                    <span class="msg-time">${timestampStr}</span>
                    ${editedBadge}
                </div>
                ${forwardBadge}
                ${replyQuote}
                <div class="msg-text" id="msg-text-${msg.id}">${contentHtml}</div>
                ${attachmentsHtml}
                <div class="reactions-row" id="reactions-row-${msg.id}">
                    ${renderReactionsHtml(msg.id, msg.reactions)}
                </div>
                <div class="link-previews-container" id="link-previews-${msg.id}"></div>
            </div>
            ${actionMenuHtml}
        `;

        historyEl.appendChild(msgDiv);
        renderLucideIcons();

        // Async Link Preview Scraper check
        if (msg.text && !isDeleted) {
            const urlMatches = msg.text.match(/(https?:\/\/[^\s]+)/g);
            if (urlMatches && urlMatches.length > 0) {
                const targetUrl = urlMatches[0];
                fetch('/api/messages/link-preview', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: targetUrl })
                })
                .then(r => r.json())
                .then(d => {
                    if (d.success && d.preview) {
                        const previewContainer = document.getElementById(`link-previews-${msg.id}`);
                        if (previewContainer && (d.preview.title || d.preview.description)) {
                            previewContainer.innerHTML = `
                                <a href="${escapeHTML(d.preview.url || targetUrl)}" target="_blank" rel="noopener noreferrer" class="link-preview-card">
                                    <div class="preview-info">
                                        <span class="preview-domain">${escapeHTML(d.preview.domain || '')}</span>
                                        <strong class="preview-title">${escapeHTML(d.preview.title || '')}</strong>
                                        <p class="preview-desc">${escapeHTML(d.preview.description || '')}</p>
                                    </div>
                                    ${d.preview.image ? `<img src="${d.preview.image}" class="preview-thumbnail" alt="preview" loading="lazy">` : ''}
                                </a>
                            `;
                        }
                    }
                })
                .catch(() => {});
            }
        }
    }

    safeOn(chatForm, 'submit', (e) => {
        e.preventDefault();
        sendMessage();
    });

    safeOn(document.getElementById('btn-send-message'), 'click', (e) => {
        e.preventDefault();
        sendMessage();
    });

    safeOn(messageInput, 'keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Typing Indicators
    safeOn(messageInput, 'input', () => {
        if (!socket) return;
        socket.emit('typing', { 
            conversation_id: currentConversationId,
            channel_id: currentChannelId, 
            target_id: currentTargetId 
        });
        clearTimeout(typingTimeout);
        typingTimeout = setTimeout(() => {
            socket.emit('stop_typing', { 
                conversation_id: currentConversationId,
                channel_id: currentChannelId, 
                target_id: currentTargetId 
            });
        }, 2000);
    });

    // Markdown Parser with Code Block Runner, Custom Emojis & Spoilers
    function parseMarkdown(text) {
        if (!text) return '';
        let html = escapeHTML(text);

        // Code blocks: ```language ... ```
        html = html.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
            const cleanLang = lang || 'code';
            const codeId = `code_${Math.random().toString(36).substr(2, 9)}`;
            const isJs = cleanLang.toLowerCase() === 'js' || cleanLang.toLowerCase() === 'javascript';
            const runBtnHtml = isJs ? `<button type="button" class="code-btn" onclick="runJsCode('${codeId}')">▶ Çalıştır</button>` : '';

            return `
                <div class="code-block-card">
                    <div class="code-header">
                        <span>${cleanLang.toUpperCase()}</span>
                        <div class="code-btn-group">
                            <button type="button" class="code-btn" onclick="copyCodeText('${codeId}')">📋 Kopyala</button>
                            ${runBtnHtml}
                        </div>
                    </div>
                    <pre class="code-content" id="${codeId}">${code}</pre>
                    <div class="code-output-terminal" id="out_${codeId}" style="display: none;"></div>
                </div>
            `;
        });

        // Inline code: `code`
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

        // Headers
        html = html.replace(/^### (.*$)/gm, '<h4 class="md-heading-3">$1</h4>');
        html = html.replace(/^## (.*$)/gm, '<h3 class="md-heading-2">$1</h3>');
        html = html.replace(/^# (.*$)/gm, '<h2 class="md-heading-1">$1</h2>');

        // Spoilers: ||text||
        html = html.replace(/\|\|(.*?)\|\|/g, '<span class="spoiler" onclick="this.classList.toggle(\'revealed\')">$1</span>');

        // Custom Emojis :name:
        html = html.replace(/:([a-zA-Z0-9_]+):/g, (match, code) => {
            return `<span class="custom-emoji-token" title=":${code}:">:${code}:</span>`;
        });

        // Bold: **text**
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

        // Italic: *text*
        html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');

        // Strikethrough: ~~text~~
        html = html.replace(/~~(.*?)~~/g, '<del>$1</del>');

        // Blockquote: > text
        html = html.replace(/^&gt;\s(.*)$/gm, '<blockquote>$1</blockquote>');

        // URLs
        html = html.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer" style="color: var(--primary-light);">$1</a>');

        // Bullet points
        html = html.replace(/^\s*-\s+(.*)$/gm, '• $1');

        // Line breaks
        html = html.replace(/\n/g, '<br>');

        return html;
    }

    // --- Message Reactions & Actions ---

    function renderReactionsHtml(msgId, reactions = {}) {
        if (!reactions || Object.keys(reactions).length === 0) return '';
        return Object.entries(reactions).map(([emoji, users]) => {
            const hasReacted = users.includes(currentUser.id);
            return `
                <div class="reaction-chip ${hasReacted ? 'reacted' : ''}" onclick="toggleReaction(${msgId}, '${emoji}')">
                    <span>${emoji}</span>
                    <span>${users.length}</span>
                </div>
            `;
        }).join('');
    }

    function updateMessageReactions(msgId, reactions) {
        const row = document.getElementById(`reactions-row-${msgId}`);
        if (row) {
            row.innerHTML = renderReactionsHtml(msgId, reactions);
        }
    }

    window.toggleReaction = (msgId, emoji) => {
        AudioEngine.playChime('pop');
        if (socket) {
            socket.emit('message_reaction', { message_id: msgId, emoji });
        } else {
            fetch(`/api/messages/${msgId}/reaction`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ emoji })
            });
        }
    };

    window.openReactionPicker = (msgId, event) => {
        const rect = event.target.getBoundingClientRect();
        const popover = document.getElementById('emoji-picker-popover');
        if (popover) {
            popover.style.top = `${Math.max(10, rect.top - 280)}px`;
            popover.style.left = `${Math.max(10, rect.left - 150)}px`;
            popover.style.display = 'flex';
            popover.dataset.targetMsgId = msgId;
        }
    };

    window.setReplyTarget = (msgId, username, textSnippet) => {
        activeReplyMessage = { id: msgId, username, text: textSnippet };
        if (replyToUser) replyToUser.textContent = `@${username}`;
        if (replyToSnippet) replyToSnippet.textContent = textSnippet.substring(0, 60) + (textSnippet.length > 60 ? '...' : '');
        if (replyPreviewBar) replyPreviewBar.style.display = 'flex';
        if (messageInput) messageInput.focus();
    };

    safeOn(btnCancelReply, 'click', cancelReply);
    function cancelReply() {
        activeReplyMessage = null;
        if (replyPreviewBar) replyPreviewBar.style.display = 'none';
    }

    window.togglePinMessage = async (msgId) => {
        try {
            const res = await fetch(`/api/messages/${msgId}/pin`, { method: 'POST' });
            const data = await res.json();
            showFloatingToast(data.is_pinned ? '📌 Mesaj sabitlendi!' : 'Mesaj sabitlemesi kaldırıldı');
        } catch (e) {
            showFloatingToast("İşlem gerçekleştirilemedi");
        }
    };

    window.startEditMessage = (msgId) => {
        const textEl = document.getElementById(`msg-text-${msgId}`);
        if (!textEl) return;
        const currentText = textEl.innerText.trim();
        const newText = prompt("Mesajı Düzenleyin:", currentText);
        if (newText !== null && newText.trim() !== '' && newText.trim() !== currentText) {
            if (socket) {
                socket.emit('edit_message', { message_id: msgId, text: newText.trim() });
            } else {
                fetch(`/api/messages/${msgId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: newText.trim() })
                });
            }
        }
    };

    // --- Message Deletion Modal Logic ---
    window.openDeleteMessageModal = (msgId, isAuthor) => {
        activePendingDeleteMsgId = msgId;
        activePendingDeleteIsMine = isAuthor;
        const modal = document.getElementById('delete-message-modal');
        const btnEveryone = document.getElementById('btn-delete-for-everyone');
        if (modal) {
            if (btnEveryone) {
                btnEveryone.style.display = isAuthor ? 'flex' : 'none';
            }
            modal.style.display = 'flex';
        }
    };

    function confirmDeleteMessage(forEveryone = false) {
        if (!activePendingDeleteMsgId) return;
        const msgId = activePendingDeleteMsgId;
        const modal = document.getElementById('delete-message-modal');
        if (modal) modal.style.display = 'none';

        if (socket) {
            socket.emit('delete_message', { 
                message_id: msgId, 
                delete_for_everyone: forEveryone 
            });
        } else {
            fetch(`/api/messages/${msgId}`, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    delete_for_everyone: forEveryone,
                    delete_for_me: !forEveryone
                })
            });
        }
        activePendingDeleteMsgId = null;
    }

    // --- Message Forwarding Modal Logic ---
    window.openForwardModal = (msgId, authorName, textSnippet) => {
        activeForwardMsgId = msgId;
        const modal = document.getElementById('forward-message-modal');
        const authorEl = document.getElementById('forward-preview-author');
        const textEl = document.getElementById('forward-preview-text');
        const targetList = document.getElementById('forward-conversations-target-list');
        const btnConfirm = document.getElementById('btn-confirm-forward');
        const errEl = document.getElementById('forward-error');

        if (authorEl) authorEl.textContent = `@${authorName}`;
        if (textEl) textEl.textContent = textSnippet || 'Ekli dosya/medya';
        if (errEl) errEl.textContent = '';
        if (btnConfirm) btnConfirm.disabled = true;

        if (targetList) {
            targetList.innerHTML = '';
            cachedConversations.forEach(c => {
                const item = document.createElement('div');
                item.className = 'forward-conv-item';
                item.dataset.convId = c.id;
                const iconBadge = c.type === 'group' ? '👥' : '💬';
                item.innerHTML = `
                    <span style="font-size: 16px;">${iconBadge}</span>
                    <strong style="color: var(--text-main); font-size: 13px;">${escapeHTML(c.display_name || c.name)}</strong>
                `;
                item.onclick = () => {
                    document.querySelectorAll('.forward-conv-item').forEach(i => i.classList.remove('selected'));
                    item.classList.add('selected');
                    if (btnConfirm) btnConfirm.disabled = false;
                };
                targetList.appendChild(item);
            });
        }

        if (modal) modal.style.display = 'flex';
    };

    async function submitForwardMessage() {
        if (!activeForwardMsgId) return;
        const selectedItem = document.querySelector('.forward-conv-item.selected');
        const errEl = document.getElementById('forward-error');
        if (!selectedItem) {
            if (errEl) errEl.textContent = 'Lütfen iletmek için bir hedef sohbet seçin.';
            return;
        }

        const targetConvId = parseInt(selectedItem.dataset.convId);
        try {
            const res = await fetch(`/api/messages/${activeForwardMsgId}/forward`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target_conversation_id: targetConvId })
            });
            const data = await res.json();
            if (data.success) {
                showFloatingToast("↗️ Mesaj başarıyla iletildi!");
                const modal = document.getElementById('forward-message-modal');
                if (modal) modal.style.display = 'none';
            } else {
                if (errEl) errEl.textContent = data.message || 'İletme başarısız';
            }
        } catch (e) {
            if (errEl) errEl.textContent = 'Sunucuya bağlanılamadı';
        }
    }

    window.jumpToMessage = (msgId) => {
        const el = document.getElementById(`msg-${msgId}`);
        if (el) {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            el.classList.add('highlight-flash');
            setTimeout(() => el.classList.remove('highlight-flash'), 2000);
        }
    };

    // Code Sandbox Runner
    window.runJsCode = (codeId) => {
        const codeEl = document.getElementById(codeId);
        const outEl = document.getElementById(`out_${codeId}`);
        if (!codeEl || !outEl) return;

        outEl.style.display = 'block';
        outEl.innerHTML = '<span style="color: var(--text-dim);">Çalıştırılıyor...</span>';

        try {
            const logs = [];
            const customConsole = {
                log: (...args) => logs.push(args.map(a => typeof a === 'object' ? JSON.stringify(a) : a).join(' ')),
                error: (...args) => logs.push(`❌ ${args.join(' ')}`),
                warn: (...args) => logs.push(`⚠️ ${args.join(' ')}`)
            };
            const runner = new Function('console', codeEl.textContent);
            runner(customConsole);
            outEl.innerHTML = logs.length > 0 ? logs.join('<br>') : '✓ Kod başarıyla tamamlandı.';
        } catch (err) {
            outEl.innerHTML = `<span style="color: var(--danger);">Hata: ${escapeHTML(err.message)}</span>`;
        }
    };

    window.copyCodeText = (codeId) => {
        const codeEl = document.getElementById(codeId);
        if (codeEl) {
            navigator.clipboard.writeText(codeEl.textContent);
            showFloatingToast("📋 Kod panoya kopyalandı!");
        }
    };

    // Audio Playback in Chat
    let currentPlayingAudio = null;
    window.toggleAudioPlayback = (url, containerId) => {
        const container = document.getElementById(containerId);
        if (!container) return;
        const btn = container.querySelector('.btn-play-voice');

        if (currentPlayingAudio && currentPlayingAudio.src === url) {
            if (currentPlayingAudio.paused) {
                currentPlayingAudio.play();
                if (btn) btn.textContent = '⏸';
                container.classList.add('playing');
            } else {
                currentPlayingAudio.pause();
                if (btn) btn.textContent = '▶';
                container.classList.remove('playing');
            }
            return;
        }

        if (currentPlayingAudio) {
            currentPlayingAudio.pause();
            document.querySelectorAll('.voice-note-player').forEach(p => {
                p.classList.remove('playing');
                const b = p.querySelector('.btn-play-voice');
                if (b) b.textContent = '▶';
            });
        }

        currentPlayingAudio = new Audio(url);
        currentPlayingAudio.play();
        if (btn) btn.textContent = '⏸';
        container.classList.add('playing');

        currentPlayingAudio.onended = () => {
            if (btn) btn.textContent = '▶';
            container.classList.remove('playing');
        };
    };

    // --- Group Management Logic ---

    async function openCreateGroupModal() {
        const modal = document.getElementById('create-group-modal');
        const checklist = document.getElementById('create-group-friends-checklist');
        const countSpan = document.getElementById('create-group-selected-count');
        const errEl = document.getElementById('create-group-error');
        const nameInput = document.getElementById('group-name-input');

        if (nameInput) nameInput.value = '';
        if (errEl) errEl.textContent = '';
        if (countSpan) countSpan.textContent = '0';

        if (checklist) {
            checklist.innerHTML = '<div class="empty-state-small">Arkadaşlar yükleniyor...</div>';
            try {
                const res = await fetch('/api/friends');
                const data = await res.json();
                const friends = data.friends || [];

                checklist.innerHTML = '';
                if (friends.length === 0) {
                    checklist.innerHTML = '<div class="empty-state-small">Gruba ekleyecek arkadaş bulunamadı.</div>';
                } else {
                    friends.forEach(f => {
                        const row = document.createElement('label');
                        row.className = 'friend-check-item';
                        row.innerHTML = `
                            <input type="checkbox" name="group_member" value="${f.id}">
                            <div class="avatar" style="background-color: ${f.color || '#8b5cf6'}; width: 28px; height: 28px; font-size: 12px;">
                                ${(f.display_name || f.username).charAt(0).toUpperCase()}
                            </div>
                            <span style="font-size: 13px; color: var(--text-main); font-weight: 500;">${escapeHTML(f.display_name || f.username)}</span>
                        `;
                        row.querySelector('input').addEventListener('change', () => {
                            const checked = checklist.querySelectorAll('input[type="checkbox"]:checked').length;
                            if (countSpan) countSpan.textContent = checked;
                        });
                        checklist.appendChild(row);
                    });
                }
            } catch (e) {
                checklist.innerHTML = '<div class="empty-state-small">Arkadaş listesi alınamadı.</div>';
            }
        }

        if (modal) modal.style.display = 'flex';
    }

    async function submitCreateGroup(e) {
        if (e) e.preventDefault();
        const nameInput = document.getElementById('group-name-input');
        const errEl = document.getElementById('create-group-error');
        const checklist = document.getElementById('create-group-friends-checklist');

        const groupName = nameInput ? nameInput.value.trim() : '';
        if (!groupName) {
            if (errEl) errEl.textContent = 'Lütfen bir grup adı girin.';
            return;
        }

        const checkedBoxes = checklist ? checklist.querySelectorAll('input[type="checkbox"]:checked') : [];
        const memberIds = Array.from(checkedBoxes).map(cb => parseInt(cb.value));

        try {
            const res = await fetch('/api/conversations/group', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: groupName,
                    member_ids: memberIds
                })
            });
            const data = await res.json();
            if (data.success && data.conversation) {
                showFloatingToast(`🎉 "${groupName}" grubu oluşturuldu!`);
                const modal = document.getElementById('create-group-modal');
                if (modal) modal.style.display = 'none';
                await loadConversations();
                switchConversation(data.conversation.id, data.conversation.name, data.conversation.icon_color, true, data.conversation.member_count);
            } else {
                if (errEl) errEl.textContent = data.message || 'Grup oluşturulamadı.';
            }
        } catch (err) {
            if (errEl) errEl.textContent = 'Sunucuya bağlanılamadı.';
        }
    }

    async function openGroupMembersModal() {
        if (!currentConversationId) return;
        const modal = document.getElementById('group-members-modal');
        const titleEl = document.getElementById('group-modal-title');
        const subEl = document.getElementById('group-modal-sub');
        const membersList = document.getElementById('group-members-list-body');
        const addFriendSelect = document.getElementById('group-add-friend-select');
        const editBox = document.getElementById('group-settings-edit-box');
        const editNameInput = document.getElementById('edit-group-name-input');

        try {
            const res = await fetch(`/api/conversations/${currentConversationId}`);
            const data = await res.json();
            if (!data.success || !data.conversation) return;
            const conv = data.conversation;

            if (titleEl) titleEl.textContent = conv.name;
            if (subEl) subEl.textContent = `${conv.members ? conv.members.length : 0} Katılımcı`;
            if (editNameInput) editNameInput.value = conv.name;

            const myMembership = (conv.members || []).find(m => m.user_id === currentUser.id);
            const isOwnerOrAdmin = myMembership && (myMembership.role === 'owner' || myMembership.role === 'admin');

            if (editBox) editBox.style.display = isOwnerOrAdmin ? 'block' : 'none';

            // Populate members
            if (membersList) {
                membersList.innerHTML = '';
                (conv.members || []).forEach(m => {
                    const row = document.createElement('div');
                    row.className = 'group-member-row';
                    const isSelf = m.user_id === currentUser.id;
                    const canKick = isOwnerOrAdmin && !isSelf && m.role !== 'owner';

                    const roleBadge = m.role === 'owner' 
                        ? '<span class="member-role-badge owner">👑 Kurucu</span>' 
                        : (m.role === 'admin' ? '<span class="member-role-badge admin">🛡️ Yönetici</span>' : '<span class="member-role-badge">Üye</span>');

                    const kickBtn = canKick ? `<button type="button" class="btn-danger-subtle btn-xs" onclick="removeGroupMember(${m.user_id})">Çıkar</button>` : '';

                    row.innerHTML = `
                        <div class="group-member-info">
                            <div class="avatar" style="background-color: ${m.color || '#8b5cf6'}; width: 30px; height: 30px; font-size: 12px;">
                                ${(m.display_name || m.username).charAt(0).toUpperCase()}
                            </div>
                            <div>
                                <strong style="font-size: 13px; color: var(--text-main);">${escapeHTML(m.display_name || m.username)}</strong>
                                ${roleBadge}
                            </div>
                        </div>
                        ${kickBtn}
                    `;
                    membersList.appendChild(row);
                });
            }

            // Populate friends to add
            if (addFriendSelect) {
                addFriendSelect.innerHTML = '<option value="">Arkadaş seçin...</option>';
                const existingMemberIds = (conv.members || []).map(m => m.user_id);
                try {
                    const fRes = await fetch('/api/friends');
                    const fData = await fRes.json();
                    (fData.friends || []).forEach(f => {
                        if (!existingMemberIds.includes(f.id)) {
                            const opt = document.createElement('option');
                            opt.value = f.id;
                            opt.textContent = f.display_name || f.username;
                            addFriendSelect.appendChild(opt);
                        }
                    });
                } catch (e) {}
            }

            if (modal) modal.style.display = 'flex';
        } catch (e) {
            console.error("Error opening group modal:", e);
        }
    }

    async function confirmAddGroupMember() {
        if (!currentConversationId) return;
        const select = document.getElementById('group-add-friend-select');
        const userId = select ? select.value : null;
        if (!userId) {
            showFloatingToast("Lütfen eklenecek arkadaşı seçin.");
            return;
        }

        try {
            const res = await fetch(`/api/conversations/${currentConversationId}/members`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_ids: [parseInt(userId)] })
            });
            const data = await res.json();
            if (data.success) {
                showFloatingToast("✓ Üye gruba eklendi!");
                openGroupMembersModal();
                loadConversations();
            } else {
                showFloatingToast(data.message || "Üye eklenemedi");
            }
        } catch (e) {
            showFloatingToast("Bağlantı hatası");
        }
    }

    window.removeGroupMember = async (userId) => {
        if (!currentConversationId) return;
        if (!confirm("Bu üyeyi gruptan çıkarmak istediğinize emin misiniz?")) return;

        try {
            const res = await fetch(`/api/conversations/${currentConversationId}/members/${userId}`, {
                method: 'DELETE'
            });
            const data = await res.json();
            if (data.success) {
                showFloatingToast("✓ Üye gruptan çıkarıldı.");
                openGroupMembersModal();
                loadConversations();
            } else {
                showFloatingToast(data.message || "İşlem başarısız");
            }
        } catch (e) {
            showFloatingToast("Bağlantı hatası");
        }
    };

    async function leaveCurrentGroup() {
        if (!currentConversationId) return;
        if (!confirm("Gruptan ayrılmak istediğinize emin misiniz?")) return;

        try {
            const res = await fetch(`/api/conversations/${currentConversationId}/members/${currentUser.id}`, {
                method: 'DELETE'
            });
            const data = await res.json();
            if (data.success) {
                showFloatingToast("Gruptan ayrıldınız.");
                const modal = document.getElementById('group-members-modal');
                if (modal) modal.style.display = 'none';
                await loadConversations();
                switchToHome();
            } else {
                showFloatingToast(data.message || "Ayrılma işlemi başarısız");
            }
        } catch (e) {
            showFloatingToast("Bağlantı hatası");
        }
    }

    async function saveGroupName() {
        if (!currentConversationId) return;
        const input = document.getElementById('edit-group-name-input');
        const newName = input ? input.value.trim() : '';
        if (!newName) return;

        try {
            const res = await fetch(`/api/conversations/${currentConversationId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: newName })
            });
            const data = await res.json();
            if (data.success) {
                showFloatingToast("✓ Grup adı güncellendi!");
                if (chatTargetName) chatTargetName.textContent = newName;
                openGroupMembersModal();
                loadConversations();
            }
        } catch (e) {
            showFloatingToast("Güncelleme başarısız");
        }
    }

    // --- Voice Recording Live Dock Engine ---
    let liveVoiceRecorder = null;
    let liveVoiceChunks = [];
    let liveVoiceTimer = null;
    let liveVoiceSecs = 0;

    async function startVoiceRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            liveVoiceChunks = [];
            liveVoiceRecorder = new MediaRecorder(stream);

            liveVoiceRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) liveVoiceChunks.push(e.data);
            };

            liveVoiceRecorder.start();
            liveVoiceSecs = 0;
            const timerEl = document.getElementById('voice-record-timer');
            const dock = document.getElementById('voice-recording-dock');
            if (timerEl) timerEl.textContent = '00:00';
            if (dock) dock.style.display = 'flex';

            liveVoiceTimer = setInterval(() => {
                liveVoiceSecs++;
                const mins = String(Math.floor(liveVoiceSecs / 60)).padStart(2, '0');
                const secs = String(liveVoiceSecs % 60).padStart(2, '0');
                if (timerEl) timerEl.textContent = `${mins}:${secs}`;
            }, 1000);
        } catch (err) {
            alert("Mikrofona erişilemedi. Lütfen mikrofon izinlerinizi kontrol edin.");
        }
    }

    function cancelVoiceRecording() {
        clearInterval(liveVoiceTimer);
        if (liveVoiceRecorder && liveVoiceRecorder.state !== 'inactive') {
            liveVoiceRecorder.stop();
            liveVoiceRecorder.stream.getTracks().forEach(t => t.stop());
        }
        liveVoiceChunks = [];
        const dock = document.getElementById('voice-recording-dock');
        if (dock) dock.style.display = 'none';
    }

    async function sendVoiceRecording() {
        if (!liveVoiceRecorder || liveVoiceRecorder.state === 'inactive') return;
        clearInterval(liveVoiceTimer);

        liveVoiceRecorder.onstop = async () => {
            const audioBlob = new Blob(liveVoiceChunks, { type: 'audio/webm' });
            const formData = new FormData();
            formData.append('file', audioBlob, `voice_memo_${Date.now()}.webm`);

            showFloatingToast("🎤 Ses kaydı yükleniyor...");
            try {
                const res = await fetch('/api/upload', { method: 'POST', body: formData });
                const data = await res.json();
                if (data.success) {
                    sendMessage({
                        url: data.url,
                        type: 'voice_memo',
                        name: 'Sesli Mesaj',
                        mime_type: 'audio/webm'
                    });
                } else {
                    alert(data.message);
                }
            } catch (e) {
                showFloatingToast("Ses kaydı gönderilemedi.");
            }
            liveVoiceChunks = [];
            liveVoiceRecorder.stream.getTracks().forEach(t => t.stop());
            const dock = document.getElementById('voice-recording-dock');
            if (dock) dock.style.display = 'none';
        };

        liveVoiceRecorder.stop();
    }

    // --- Code Snippet Modal Engine ---
    function openCodeSnippetModal() {
        const modal = document.getElementById('code-snippet-modal');
        const textarea = document.getElementById('code-snippet-body');
        if (textarea) textarea.value = '';
        if (modal) modal.style.display = 'flex';
    }

    function confirmInsertCodeSnippet() {
        const langSelect = document.getElementById('code-snippet-lang');
        const textarea = document.getElementById('code-snippet-body');
        const lang = langSelect ? langSelect.value : 'javascript';
        const code = textarea ? textarea.value : '';

        if (!code.trim()) {
            showFloatingToast("Lütfen kod içeriğini girin.");
            return;
        }

        const formatted = `\`\`\`${lang}\n${code}\n\`\`\``;
        if (messageInput) {
            messageInput.value += (messageInput.value ? '\n' : '') + formatted;
            messageInput.focus();
        }

        const modal = document.getElementById('code-snippet-modal');
        if (modal) modal.style.display = 'none';
    }

    // --- Popover Tabs & Custom Emojis / Stickers / GIFs Engine ---
    let currentEmojiTab = 'standard';

    async function loadEmojiTab(tabName) {
        currentEmojiTab = tabName;
        const grid = document.getElementById('emoji-grid-container');
        const subCats = document.getElementById('emoji-sub-cats');
        const searchWrap = document.getElementById('popover-search-wrap');
        const popover = document.getElementById('emoji-picker-popover');
        if (!grid) return;

        if (tabName === 'standard') {
            if (subCats) subCats.style.display = 'flex';
            if (searchWrap) searchWrap.style.display = 'none';
            loadEmojiCategory('smileys');
        } else if (tabName === 'custom') {
            if (subCats) subCats.style.display = 'none';
            if (searchWrap) searchWrap.style.display = 'none';
            grid.innerHTML = '<div class="empty-state-small">Özel emojiler yükleniyor...</div>';
            try {
                const res = await fetch('/api/emojis/custom');
                const data = await res.json();
                grid.innerHTML = '';
                (data.emojis || []).forEach(em => {
                    const item = document.createElement('div');
                    item.className = 'emoji-item';
                    item.title = `:${em.name}:`;
                    item.innerHTML = `<img src="${em.image_url}" class="custom-emoji-img" alt="${em.name}">`;
                    item.onclick = () => {
                        if (messageInput) {
                            messageInput.value += `:${em.name}: `;
                            messageInput.focus();
                        }
                        if (popover) popover.style.display = 'none';
                    };
                    grid.appendChild(item);
                });
            } catch (e) {
                grid.innerHTML = '<div class="empty-state-small">Özel emoji bulunamadı.</div>';
            }
        } else if (tabName === 'stickers') {
            if (subCats) subCats.style.display = 'none';
            if (searchWrap) searchWrap.style.display = 'none';
            grid.innerHTML = '<div class="empty-state-small">Stickerlar yükleniyor...</div>';
            try {
                const res = await fetch('/api/stickers');
                const data = await res.json();
                grid.innerHTML = '';
                grid.className = 'sticker-grid';
                (data.stickers || []).forEach(st => {
                    const item = document.createElement('div');
                    item.className = 'sticker-item';
                    item.title = st.name;
                    item.innerHTML = `<img src="${st.image_url}" alt="${st.name}"><span style="font-size: 10px; color: var(--text-dim); margin-top: 4px;">${escapeHTML(st.name)}</span>`;
                    item.onclick = () => {
                        sendMessage({
                            url: st.image_url,
                            type: 'sticker',
                            name: st.name
                        });
                        if (popover) popover.style.display = 'none';
                    };
                    grid.appendChild(item);
                });
            } catch (e) {
                grid.innerHTML = '<div class="empty-state-small">Sticker bulunamadı.</div>';
            }
        } else if (tabName === 'gifs') {
            if (subCats) subCats.style.display = 'none';
            if (searchWrap) searchWrap.style.display = 'block';
            loadGifs('');
        }
    }

    async function loadGifs(query = '') {
        const grid = document.getElementById('emoji-grid-container');
        const popover = document.getElementById('emoji-picker-popover');
        if (!grid) return;
        grid.className = 'gif-grid';
        grid.innerHTML = '<div class="empty-state-small">GIF\'ler aranıyor...</div>';

        try {
            const res = await fetch(`/api/gifs/search?q=${encodeURIComponent(query)}`);
            const data = await res.json();
            grid.innerHTML = '';
            (data.gifs || []).forEach(g => {
                const item = document.createElement('div');
                item.className = 'gif-item';
                item.title = g.title;
                item.innerHTML = `<img src="${g.url}" alt="${g.title}">`;
                item.onclick = () => {
                    sendMessage({
                        url: g.url,
                        type: 'image',
                        name: g.title
                    });
                    if (popover) popover.style.display = 'none';
                };
                grid.appendChild(item);
            });
        } catch (e) {
            grid.innerHTML = '<div class="empty-state-small">GIF bulunamadı.</div>';
        }
    }

    // --- Bind All Messaging Modals and Tools ---
    function initMessagingModals() {
        // Create Group
        safeOn(document.getElementById('btn-create-group'), 'click', openCreateGroupModal);
        safeOn(document.getElementById('create-group-form'), 'submit', submitCreateGroup);

        // Group Members & Details
        safeOn(document.getElementById('btn-group-info'), 'click', openGroupMembersModal);
        safeOn(document.getElementById('btn-confirm-add-group-member'), 'click', confirmAddGroupMember);
        safeOn(document.getElementById('btn-leave-group-action'), 'click', leaveCurrentGroup);
        safeOn(document.getElementById('btn-save-group-name'), 'click', saveGroupName);

        // Forward Message
        safeOn(document.getElementById('btn-confirm-forward'), 'click', submitForwardMessage);

        // Delete Message Choices
        safeOn(document.getElementById('btn-delete-for-me'), 'click', () => confirmDeleteMessage(false));
        safeOn(document.getElementById('btn-delete-for-everyone'), 'click', () => confirmDeleteMessage(true));

        // Code Snippet Inserter
        safeOn(document.getElementById('btn-insert-code'), 'click', openCodeSnippetModal);
        safeOn(document.getElementById('btn-insert-code-confirm'), 'click', confirmInsertCodeSnippet);

        // Voice Memo Recording
        safeOn(document.getElementById('btn-voice-memo'), 'click', startVoiceRecording);
        safeOn(document.getElementById('btn-send-voice-record'), 'click', sendVoiceRecording);
        safeOn(document.getElementById('btn-cancel-voice-record'), 'click', cancelVoiceRecording);

        // Spoiler Toggle Button
        safeOn(document.getElementById('btn-toggle-spoiler'), 'click', (e) => {
            isSpoilerActive = !isSpoilerActive;
            e.currentTarget.classList.toggle('active', isSpoilerActive);
            showFloatingToast(isSpoilerActive ? "⚠️ Spoiler Modu Açık (||metin||)" : "Spoiler Modu Kapalı");
        });

        // Popover Tabs (Standard, Custom, Stickers, GIFs)
        document.querySelectorAll('.emoji-tabs .emoji-tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.emoji-tabs .emoji-tab-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                loadEmojiTab(btn.dataset.tab);
            });
        });

        // Popover GIF/Sticker Search Input
        const popoverSearch = document.getElementById('popover-search-input');
        if (popoverSearch) {
            popoverSearch.addEventListener('input', (e) => {
                if (currentEmojiTab === 'gifs') {
                    loadGifs(e.target.value.trim());
                }
            });
        }
    }

    // --- File Upload & Voice Note Recording ---

    safeOn(btnAttachFile, 'click', () => fileUploadInput.click());
    safeOn(fileUploadInput, 'change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append('file', file);

        showFloatingToast(`Uploading ${file.name}...`);
        const res = await fetch('/api/upload', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.success) {
            sendMessage({ url: data.url, type: data.type, name: data.name });
        } else {
            alert(data.message);
        }
        fileUploadInput.value = '';
    });

    // Voice Note MediaRecorder
    let voiceMediaRecorder = null;
    let voiceAudioChunks = [];
    let voiceTimerInterval = null;
    let voiceSeconds = 0;

    safeOn(btnRecordVoiceNote, 'click', async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            voiceAudioChunks = [];
            voiceMediaRecorder = new MediaRecorder(stream);

            voiceMediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) voiceAudioChunks.push(e.data);
            };

            voiceMediaRecorder.start();
            voiceRecordBar.style.display = 'flex';
            voiceSeconds = 0;
            voiceRecordTimer.textContent = '00:00';
            voiceTimerInterval = setInterval(() => {
                voiceSeconds++;
                const mins = String(Math.floor(voiceSeconds / 60)).padStart(2, '0');
                const secs = String(voiceSeconds % 60).padStart(2, '0');
                voiceRecordTimer.textContent = `${mins}:${secs}`;
            }, 1000);

        } catch (err) {
            console.error(err);
            alert("Microphone access is required for voice notes.");
        }
    });

    safeOn(btnCancelVoice, 'click', () => {
        stopVoiceRecording(false);
    });

    safeOn(btnSendVoice, 'click', () => {
        stopVoiceRecording(true);
    });

    function stopVoiceRecording(shouldSend) {
        if (!voiceMediaRecorder) return;
        clearInterval(voiceTimerInterval);
        voiceRecordBar.style.display = 'none';

        voiceMediaRecorder.onstop = async () => {
            if (shouldSend && voiceAudioChunks.length > 0) {
                const audioBlob = new Blob(voiceAudioChunks, { type: 'audio/webm' });
                const file = new File([audioBlob], `voice_memo_${Date.now()}.webm`, { type: 'audio/webm' });
                const formData = new FormData();
                formData.append('file', file);
                formData.append('is_voice_memo', 'true');

                const res = await fetch('/api/upload', { method: 'POST', body: formData });
                const data = await res.json();
                if (data.success) {
                    sendMessage({ url: data.url, type: 'voice_memo', name: 'Voice Memo' });
                }
            }
            voiceAudioChunks = [];
        };

        voiceMediaRecorder.stop();
        voiceMediaRecorder.stream.getTracks().forEach(t => t.stop());
    }

    // --- Collaborative Whiteboard (HTML5 Canvas + Real-Time WebSocket) ---

    let wbCanvas = null;
    let wbCtx = null;
    let wbDrawing = false;
    let wbColor = '#8b5cf6';
    let wbSize = 4;
    let wbTool = 'pen'; // 'pen', 'eraser'

    function initCollaborativeCanvas() {
        wbCanvas = document.getElementById('collab-canvas');
        if (!wbCanvas) return;
        wbCtx = wbCanvas.getContext('2d');
        wbCtx.lineCap = 'round';
        wbCtx.lineJoin = 'round';

        let lastX = 0, lastY = 0;

        const getPos = (e) => {
            const rect = wbCanvas.getBoundingClientRect();
            const scaleX = wbCanvas.width / rect.width;
            const scaleY = wbCanvas.height / rect.height;
            return {
                x: (e.clientX - rect.left) * scaleX,
                y: (e.clientY - rect.top) * scaleY
            };
        };

        wbCanvas.onmousedown = (e) => {
            wbDrawing = true;
            const p = getPos(e);
            lastX = p.x;
            lastY = p.y;
        };

        wbCanvas.onmousemove = (e) => {
            if (!wbDrawing) return;
            const p = getPos(e);
            const strokeColor = wbTool === 'eraser' ? '#0d131f' : wbColor;
            const strokeSize = wbTool === 'eraser' ? wbSize * 3 : wbSize;

            wbCtx.strokeStyle = strokeColor;
            wbCtx.lineWidth = strokeSize;
            wbCtx.beginPath();
            wbCtx.moveTo(lastX, lastY);
            wbCtx.lineTo(p.x, p.y);
            wbCtx.stroke();

            // Broadcast stroke
            if (socket) {
                socket.emit('canvas_draw', {
                    channel_id: currentChannelId,
                    x0: lastX, y0: lastY,
                    x1: p.x, y1: p.y,
                    color: strokeColor,
                    size: strokeSize
                });
            }

            lastX = p.x;
            lastY = p.y;
        };

        const colorPicker = document.getElementById('canvas-color-picker');
        if (colorPicker) {
            wbColor = colorPicker.value;
            colorPicker.oninput = (e) => wbColor = e.target.value;
        }

        const sizeSlider = document.getElementById('canvas-size-slider');
        if (sizeSlider) {
            wbSize = parseInt(sizeSlider.value) || 4;
            sizeSlider.oninput = (e) => wbSize = parseInt(e.target.value) || 4;
        }

        const btnClear = document.getElementById('btn-clear-canvas');
        if (btnClear) {
            btnClear.onclick = () => {
                if (wbCtx && wbCanvas) wbCtx.clearRect(0, 0, wbCanvas.width, wbCanvas.height);
                if (socket && currentChannelId) socket.emit('canvas_clear', { channel_id: currentChannelId });
                showFloatingToast("🎨 Tuval temizlendi.");
            };
        }

        window.onmouseup = () => wbDrawing = false;
    }

    function handleCanvasRemoteStroke(data) {
        if (!wbCtx || data.channel_id !== currentChannelId) return;
        wbCtx.strokeStyle = data.color;
        wbCtx.lineWidth = data.size;
        wbCtx.beginPath();
        wbCtx.moveTo(data.x0, data.y0);
        wbCtx.lineTo(data.x1, data.y1);
        wbCtx.stroke();
    }

    // Whiteboard Toolbar Controls
    document.querySelectorAll('.color-swatch').forEach(swatch => {
        swatch.addEventListener('click', () => {
            document.querySelectorAll('.color-swatch').forEach(s => s.classList.remove('active'));
            swatch.classList.add('active');
            wbColor = swatch.dataset.color;
            wbTool = 'pen';
            const penBtn = document.getElementById('wb-tool-pen');
            const eraserBtn = document.getElementById('wb-tool-eraser');
            if (penBtn) penBtn.classList.add('active');
            if (eraserBtn) eraserBtn.classList.remove('active');
        });
    });

    safeOn(document.getElementById('wb-brush-size'), 'input', (e) => {
        wbSize = parseInt(e.target.value);
    });

    safeOn(document.getElementById('wb-tool-pen'), 'click', () => {
        wbTool = 'pen';
        const penBtn = document.getElementById('wb-tool-pen');
        const eraserBtn = document.getElementById('wb-tool-eraser');
        if (penBtn) penBtn.classList.add('active');
        if (eraserBtn) eraserBtn.classList.remove('active');
    });

    safeOn(document.getElementById('wb-tool-eraser'), 'click', () => {
        wbTool = 'eraser';
        const penBtn = document.getElementById('wb-tool-pen');
        const eraserBtn = document.getElementById('wb-tool-eraser');
        if (eraserBtn) eraserBtn.classList.add('active');
        if (penBtn) penBtn.classList.remove('active');
    });

    safeOn(document.getElementById('wb-tool-clear'), 'click', () => {
        if (confirm("Clear the entire canvas for everyone?")) {
            if (wbCtx && wbCanvas) wbCtx.clearRect(0, 0, wbCanvas.width, wbCanvas.height);
            socket.emit('canvas_clear', { channel_id: currentChannelId });
        }
    });

    safeOn(document.getElementById('wb-tool-download'), 'click', () => {
        if (wbCanvas) {
            const link = document.createElement('a');
            link.download = `neon_artwork_${Date.now()}.png`;
            link.href = wbCanvas.toDataURL();
            link.click();
        }
    });

    safeOn(document.getElementById('wb-close-btn'), 'click', switchToHome);

    // --- Interactive Mini-Games (Tic-Tac-Toe & Rock-Paper-Scissors) ---

    let tttBoardState = Array(9).fill(null);
    let tttTurn = 'X';
    let tttVsAi = true;

    safeOn(document.getElementById('btn-open-games'), 'click', () => {
        gamesModal.style.display = 'flex';
    });
    safeOn(document.getElementById('nav-games-tab'), 'click', () => {
        switchDashboardTab('dashboard-content-games');
    });
    safeOn(document.getElementById('btn-start-tictactoe'), 'click', () => {
        gamesModal.style.display = 'flex';
        document.getElementById('tictactoe-screen').style.display = 'block';
        document.getElementById('rps-screen').style.display = 'none';
        resetTttGame();
    });
    safeOn(document.getElementById('btn-start-rps'), 'click', () => {
        gamesModal.style.display = 'flex';
        document.getElementById('tictactoe-screen').style.display = 'none';
        document.getElementById('rps-screen').style.display = 'block';
    });

    document.querySelectorAll('.ttt-cell').forEach(cell => {
        cell.addEventListener('click', () => {
            const idx = parseInt(cell.dataset.index);
            if (tttBoardState[idx] || checkTttWinner()) return;

            makeTttMove(idx, 'X');

            if (tttVsAi && !checkTttWinner()) {
                setTimeout(() => {
                    const aiIdx = getAiTttMove();
                    if (aiIdx !== null) makeTttMove(aiIdx, 'O');
                }, 300);
            }
        });
    });

    function makeTttMove(idx, player, broadcast = true) {
        tttBoardState[idx] = player;
        const cell = document.querySelector(`.ttt-cell[data-index="${idx}"]`);
        if (cell) {
            cell.textContent = player;
            cell.classList.add(player === 'X' ? 'x-cell' : 'o-cell');
        }
        AudioEngine.play('reaction_pop');

        const winner = checkTttWinner();
        const statusEl = document.getElementById('ttt-status');
        if (winner) {
            statusEl.textContent = winner === 'draw' ? "Berabere! 🤝" : `Kazanan: ${winner}! 🎉`;
            AudioEngine.playSoundboard('victory');
        } else {
            statusEl.textContent = `Sıra: ${player === 'X' ? 'O' : 'X'}`;
        }

        if (broadcast && socket && (currentChannelId || currentTargetId)) {
            socket.emit('game_move', {
                game: 'ttt',
                idx: idx,
                player: player,
                channel_id: currentChannelId,
                target_id: currentTargetId
            });
        }
    }

    function checkTttWinner() {
        const wins = [
            [0, 1, 2], [3, 4, 5], [6, 7, 8],
            [0, 3, 6], [1, 4, 7], [2, 5, 8],
            [0, 4, 8], [2, 4, 6]
        ];
        for (let w of wins) {
            if (tttBoardState[w[0]] && tttBoardState[w[0]] === tttBoardState[w[1]] && tttBoardState[w[0]] === tttBoardState[w[2]]) {
                return tttBoardState[w[0]];
            }
        }
        if (tttBoardState.every(c => c !== null)) return 'draw';
        return null;
    }

    function getAiTttMove() {
        const empty = tttBoardState.map((val, idx) => val === null ? idx : null).filter(val => val !== null);
        return empty.length > 0 ? empty[Math.floor(Math.random() * empty.length)] : null;
    }

    function resetTttGame(broadcast = true) {
        tttBoardState = Array(9).fill(null);
        document.querySelectorAll('.ttt-cell').forEach(c => {
            c.textContent = '';
            c.classList.remove('x-cell', 'o-cell');
        });
        document.getElementById('ttt-status').textContent = "Sıranız: ❌ (Oyuncu 1)";
        if (broadcast && socket && (currentChannelId || currentTargetId)) {
            socket.emit('game_move', {
                game: 'ttt',
                action: 'reset',
                channel_id: currentChannelId,
                target_id: currentTargetId
            });
        }
    }

    safeOn(document.getElementById('btn-ttt-restart'), 'click', () => resetTttGame(true));
    safeOn(document.getElementById('btn-ttt-ai-mode'), 'click', () => {
        tttVsAi = !tttVsAi;
        showFloatingToast(`AI Rakip: ${tttVsAi ? 'Aktif' : 'Pasif'}`);
    });

    // Rock-Paper-Scissors
    document.querySelectorAll('.rps-card').forEach(card => {
        card.addEventListener('click', () => {
            const userChoice = card.dataset.choice;
            const choices = ['rock', 'paper', 'scissors'];
            const aiChoice = choices[Math.floor(Math.random() * 3)];
            const resEl = document.getElementById('rps-result');

            let outcome = '';
            if (userChoice === aiChoice) outcome = "Berabere! 🤝";
            else if (
                (userChoice === 'rock' && aiChoice === 'scissors') ||
                (userChoice === 'paper' && aiChoice === 'rock') ||
                (userChoice === 'scissors' && aiChoice === 'paper')
            ) {
                outcome = `Kazandınız! 🎉 (${userChoice} vs ${aiChoice})`;
                AudioEngine.playSoundboard('victory');
            } else {
                outcome = `AI Kazandı! 🤖 (${aiChoice} vs ${userChoice})`;
                AudioEngine.play('error_buzzer');
            }
            resEl.innerHTML = `<strong>Siz:</strong> ${userChoice.toUpperCase()} vs <strong>AI:</strong> ${aiChoice.toUpperCase()}<br><span style="color: var(--primary-light); font-size: 18px;">${outcome}</span>`;
        });
    });

    function handleRemoteGameUpdate(data) {
        if (data.game === 'ttt') {
            if (data.action === 'reset') {
                resetTttGame(false);
            } else if (data.idx !== undefined && data.player) {
                makeTttMove(data.idx, data.player, false);
            }
        }
    }

    // --- Search & Pinned Messages ---

    safeOn(chatSearchInput, 'input', async (e) => {
        const q = e.target.value.trim();
        chatSearchClear.style.display = q ? 'block' : 'none';
        if (!q) {
            chatHistory.innerHTML = '';
            const url = currentChannelId ? `/api/messages/channel/${currentChannelId}` : `/api/messages/${currentTargetId}`;
            const res = await fetch(url);
            const data = await res.json();
            data.messages.forEach(msg => appendMessage(msg));
            scrollToBottom();
            return;
        }

        const res = await fetch(`/api/messages/search?q=${encodeURIComponent(q)}&channel_id=${currentChannelId || ''}&target_id=${currentTargetId || ''}`);
        const data = await res.json();
        chatHistory.innerHTML = `<div style="text-align: center; color: var(--text-dim); margin-bottom: 10px;">Found ${data.messages.length} matching messages</div>`;
        data.messages.forEach(msg => appendMessage(msg));
    });

    safeOn(chatSearchClear, 'click', () => {
        chatSearchInput.value = '';
        chatSearchInput.dispatchEvent(new Event('input'));
    });

    safeOn(document.getElementById('btn-open-pins'), 'click', async () => {
        pinsModal.style.display = 'flex';
        const list = document.getElementById('pins-list-container');
        list.innerHTML = '<div style="color: var(--text-dim); text-align: center; padding: 20px;">Sabitlenmiş mesajlar yükleniyor...</div>';

        const res = await fetch(`/api/messages/pins?channel_id=${currentChannelId || ''}&target_id=${currentTargetId || ''}`);
        const data = await res.json();
        list.innerHTML = '';

        if (!data.pins || data.pins.length === 0) {
            list.innerHTML = `
                <div class="empty-state-wrap">
                    <div style="margin-bottom: 6px;"><i data-lucide="pin" class="icon-xl" style="color: var(--primary);"></i></div>
                    <div style="color: var(--text-muted); font-size: 13.5px;">Bu sohbette henüz sabitlenmiş mesaj yok.</div>
                </div>
            `;
            renderLucideIcons();
            return;
        }

        data.pins.forEach(pin => {
            const card = document.createElement('div');
            card.className = 'pin-card';
            card.innerHTML = `
                <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                    <strong>@${escapeHTML(pin.username)}</strong>
                    <span style="font-size: 11px; color: var(--text-dim);">${pin.timestamp}</span>
                </div>
                <div style="font-size: 13.5px; color: var(--text-main);">${escapeHTML(pin.text)}</div>
            `;
            card.onclick = () => {
                pinsModal.style.display = 'none';
                jumpToMessage(pin.id);
            };
            list.appendChild(card);
        });
        renderLucideIcons();
    });

    // --- Soundboard System ---

    function initSoundboard() {
        document.querySelectorAll('.sound-pad').forEach(pad => {
            pad.addEventListener('click', () => {
                const key = pad.dataset.sound;
                AudioEngine.playSoundboard(key);
                if (socket) {
                    socket.emit('soundboard_play', {
                        sound_key: key,
                        channel_id: currentChannelId,
                        target_id: currentTargetId
                    });
                }
            });
        });
    }

    safeOn(navSoundboardBtn, 'click', () => soundboardModal.style.display = 'flex');
    safeOn(document.getElementById('btn-open-soundboard'), 'click', () => soundboardModal.style.display = 'flex');
    safeOn(document.getElementById('btn-voice-soundboard'), 'click', () => soundboardModal.style.display = 'flex');

    // --- Toast Notification System ---
    function showFloatingToast(message) {
        let toastContainer = document.getElementById('toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'toast-container';
            toastContainer.className = 'toast-container';
            document.body.appendChild(toastContainer);
        }

        const toast = document.createElement('div');
        toast.className = 'toast-item';
        toast.textContent = message;
        toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(10px)';
            toast.style.transition = 'all 0.25s ease';
            setTimeout(() => toast.remove(), 250);
        }, 3500);
    }
    window.showFloatingToast = showFloatingToast;

    // --- User Profile & Settings Modal Controller ---

    safeOn(document.getElementById('btn-open-my-profile'), 'click', () => {
        if (currentUser) openUserProfileModal(currentUser.public_id || currentUser.id);
    });

    async function openUserProfileModal(identifier) {
        let pData = null;
        try {
            const res = await fetch(`/api/profile/${identifier}`);
            const data = await res.json();
            if (data.success) pData = data;
        } catch (e) {}

        if (!pData) {
            showFloatingToast('❌ Profil bilgileri yüklenemedi.');
            return;
        }

        const u = pData.user;
        const isSelf = pData.is_self;

        // 1. Dynamic Card Theme and Accent Color
        const modalContainer = document.getElementById('profile-modal-card-container');
        if (modalContainer) {
            modalContainer.className = `modal-content profile-modal-card theme-${u.profile_card_theme || 'cyber-glass'}`;
            const accent = u.profile_accent_color || '#8b5cf6';
            modalContainer.style.setProperty('--profile-accent', accent);
            const hexClean = accent.replace('#', '');
            if (hexClean.length === 6) {
                const r = parseInt(hexClean.substring(0, 2), 16);
                const g = parseInt(hexClean.substring(2, 4), 16);
                const b = parseInt(hexClean.substring(4, 6), 16);
                modalContainer.style.setProperty('--profile-accent-rgb', `${r}, ${g}, ${b}`);
            }
        }

        // 2. Banner
        const bannerEl = document.getElementById('modal-profile-banner');
        if (u.banner) {
            bannerEl.style.backgroundImage = `url(${u.banner})`;
            bannerEl.style.backgroundColor = 'transparent';
        } else {
            bannerEl.style.backgroundImage = 'none';
            bannerEl.style.backgroundColor = u.banner_color || u.profile_accent_color || '#8b5cf6';
        }

        // 3. Avatar & Presence
        const av = document.getElementById('modal-profile-avatar');
        if (u.avatar) {
            av.style.backgroundImage = `url(${u.avatar})`;
            av.style.backgroundColor = 'transparent';
            av.textContent = '';
        } else {
            av.style.backgroundImage = 'none';
            av.style.backgroundColor = u.color || '#8b5cf6';
            av.textContent = (u.display_name || u.username).charAt(0).toUpperCase();
        }

        const statusDot = document.getElementById('modal-profile-status-dot');
        if (statusDot) {
            statusDot.className = `status-dot-large status-${u.presence_status || u.status_mode || 'online'}`;
        }

        // 4. Header Badges Row
        const badgeWrap = document.getElementById('modal-profile-badges');
        if (badgeWrap) {
            const bList = pData.badges || [];
            badgeWrap.innerHTML = bList.slice(0, 4).map(b => `
                <span class="badge-chip category-${b.category || 'special'}" title="${escapeHTML(b.description || b.name)}">
                    <i data-lucide="${b.icon || 'award'}" class="icon-xs"></i> ${escapeHTML(b.name)}
                </span>
            `).join('');
        }

        // 5. Basic Info (Display name, Username, Age badge, Public ID, Custom Status)
        document.getElementById('modal-profile-displayname').textContent = u.display_name || u.username;
        document.getElementById('modal-profile-username').textContent = `@${u.username}`;
        document.getElementById('modal-profile-public-id').textContent = u.public_id || `astral_${u.id}`;
        document.getElementById('modal-profile-custom-status').textContent = u.custom_status || '✨ AstralPaws';

        const ageBadgeEl = document.getElementById('modal-profile-age-badge');
        if (ageBadgeEl && u.account_age_badge) {
            ageBadgeEl.innerHTML = `<i data-lucide="${u.account_age_badge.icon || 'shield-check'}" class="icon-xs"></i> <span>${escapeHTML(u.account_age_badge.name)}</span>`;
            ageBadgeEl.title = u.account_age_badge.description || '';
        }

        const statusModeEl = document.getElementById('modal-profile-status-mode');
        if (statusModeEl) {
            statusModeEl.textContent = (u.presence_status || u.status_mode || 'online').toUpperCase();
        }

        // Copy Astral ID
        const btnProfileCopyId = document.getElementById('btn-profile-copy-id');
        if (btnProfileCopyId) {
            btnProfileCopyId.onclick = () => {
                navigator.clipboard.writeText(u.public_id || `astral_${u.id}`);
                btnProfileCopyId.innerHTML = '<i data-lucide="check" class="icon-xs"></i>';
                renderLucideIcons();
                showFloatingToast('📋 Astral ID kopyalandı!');
                setTimeout(() => {
                    btnProfileCopyId.innerHTML = '<i data-lucide="copy" class="icon-xs"></i>';
                    renderLucideIcons();
                }, 2000);
            };
        }

        // 6. Tab 1: Overview (Bio, Links, Detailed Badges, Achievements, Joined Date)
        document.getElementById('modal-profile-bio').textContent = u.bio || 'Henüz bir biyografi yazılmadı.';
        document.getElementById('modal-profile-joined-date').textContent = u.created_at || '2026-08-28';

        // Links
        const linksWrap = document.getElementById('modal-profile-links-wrap');
        const linksSec = document.getElementById('modal-profile-links-section');
        const linksList = pData.links || [];
        if (linksList.length > 0) {
            if (linksSec) linksSec.style.display = 'block';
            linksWrap.innerHTML = linksList.map(l => `
                <a href="${escapeHTML(l.url)}" target="_blank" rel="noopener noreferrer" class="profile-link-chip">
                    <i data-lucide="${l.icon || 'globe'}" class="icon-xs"></i> ${escapeHTML(l.title)}
                </a>
            `).join('');
        } else {
            if (linksSec) linksSec.style.display = 'none';
        }

        // Detailed Badges Tab Section
        const badgesDetail = document.getElementById('modal-profile-badges-detail');
        if (badgesDetail) {
            const allBadges = pData.badges || [];
            if (allBadges.length > 0) {
                badgesDetail.innerHTML = allBadges.map(b => `
                    <div class="profile-badge-card">
                        <div class="badge-card-icon"><i data-lucide="${b.icon || 'award'}" class="icon-sm"></i></div>
                        <div class="badge-card-info">
                            <h5>${escapeHTML(b.name)}</h5>
                            <p>${escapeHTML(b.description || '')}</p>
                        </div>
                    </div>
                `).join('');
            } else {
                badgesDetail.innerHTML = '<div style="color: var(--text-dim); font-size: 12px;">Henüz rozet bulunmuyor.</div>';
            }
        }

        // Achievements Section
        const achWrap = document.getElementById('modal-profile-achievements-wrap');
        if (achWrap) {
            const achList = pData.achievements || [];
            if (achList.length > 0) {
                achWrap.innerHTML = achList.map(a => `
                    <div class="profile-achievement-card">
                        <div class="achievement-card-icon"><i data-lucide="${a.icon || 'sparkles'}" class="icon-sm"></i></div>
                        <div class="achievement-card-info">
                            <h5>${escapeHTML(a.name)}</h5>
                            <p>${escapeHTML(a.description || '')}</p>
                            ${a.earned_at ? `<span class="achievement-card-date">Kazanıldı: ${escapeHTML(a.earned_at)}</span>` : ''}
                        </div>
                    </div>
                `).join('');
            } else {
                achWrap.innerHTML = '<div style="color: var(--text-dim); font-size: 12px;">Henüz kazanılmış bir başarım yok.</div>';
            }
        }

        // 7. Tab 2: Projects & Portfolio
        const projects = pData.projects || [];
        const portfolio = pData.portfolio || {};
        document.getElementById('modal-profile-proj-count').textContent = projects.length;

        const portHeader = document.getElementById('modal-profile-portfolio-info');
        if (portfolio.enabled) {
            if (portHeader) {
                portHeader.style.display = 'block';
                document.getElementById('modal-profile-portfolio-title').textContent = portfolio.title || 'Portföyüm';
                document.getElementById('modal-profile-portfolio-desc').textContent = portfolio.description || '';
            }
        } else {
            if (portHeader) portHeader.style.display = 'none';
        }

        const projGrid = document.getElementById('modal-profile-projects-grid');
        if (projGrid) {
            if (projects.length > 0) {
                projGrid.innerHTML = projects.map(pr => `
                    <div class="profile-project-card">
                        ${pr.image_url ? `<div class="project-card-image" style="background-image: url('${escapeHTML(pr.image_url)}');"></div>` : ''}
                        <div class="project-card-body">
                            <h5>${escapeHTML(pr.title)}</h5>
                            ${pr.description ? `<p>${escapeHTML(pr.description)}</p>` : ''}
                            ${pr.url ? `<a href="${escapeHTML(pr.url)}" target="_blank" rel="noopener noreferrer" class="btn-project-link"><i data-lucide="external-link" class="icon-xs"></i> Projeyi İncele</a>` : ''}
                        </div>
                    </div>
                `).join('');
            } else {
                projGrid.innerHTML = `
                    <div class="empty-state-wrap" style="grid-column: 1 / -1; padding: 25px 0;">
                        <i data-lucide="folder-git-2" class="icon-xl" style="color: var(--text-dim); margin-bottom: 6px;"></i>
                        <div style="color: var(--text-muted); font-size: 13px;">Henüz sergilenen bir proje yok.</div>
                    </div>
                `;
            }
        }

        // 8. Tab 3: Communities (Created + Mutual)
        const createdServers = pData.created_servers || [];
        const mutualServers = pData.mutual_servers || [];
        const totalComm = createdServers.length + mutualServers.length;
        document.getElementById('modal-profile-comm-count').textContent = totalComm;
        document.getElementById('modal-created-servers-count').textContent = createdServers.length;
        document.getElementById('modal-mutual-servers-count').textContent = mutualServers.length;

        const createdGrid = document.getElementById('modal-profile-created-servers');
        if (createdGrid) {
            if (createdServers.length > 0) {
                createdGrid.innerHTML = createdServers.map(s => `
                    <div class="profile-server-card">
                        <div class="server-card-icon" style="background-color: ${s.icon_color || '#8b5cf6'};">${escapeHTML(s.name.charAt(0).toUpperCase())}</div>
                        <div class="server-card-info">
                            <h5>${escapeHTML(s.name)}</h5>
                            <span>👑 Kurucu</span>
                        </div>
                    </div>
                `).join('');
            } else {
                createdGrid.innerHTML = '<div style="color: var(--text-dim); font-size: 12px;">Oluşturulmuş bir topluluk yok.</div>';
            }
        }

        const mutualGrid = document.getElementById('modal-profile-mutual-servers');
        if (mutualGrid) {
            if (mutualServers.length > 0) {
                mutualGrid.innerHTML = mutualServers.map(s => `
                    <div class="profile-server-card">
                        <div class="server-card-icon" style="background-color: ${s.icon_color || '#8b5cf6'};">${escapeHTML(s.name.charAt(0).toUpperCase())}</div>
                        <div class="server-card-info">
                            <h5>${escapeHTML(s.name)}</h5>
                            <span>Ortak Topluluk</span>
                        </div>
                    </div>
                `).join('');
            } else {
                mutualGrid.innerHTML = '<div style="color: var(--text-dim); font-size: 12px;">Ortak topluluk bulunamadı.</div>';
            }
        }

        // 9. Tab 4: Mutual Friends
        const mutualFriends = pData.mutual_friends || [];
        document.getElementById('modal-profile-mutuals-count').textContent = pData.mutual_friends_count || 0;
        const mutualFriendsList = document.getElementById('modal-profile-mutual-friends-list');
        if (mutualFriendsList) {
            if (mutualFriends.length > 0) {
                mutualFriendsList.innerHTML = mutualFriends.map(mf => `
                    <div class="mutual-friend-item">
                        <div class="avatar-circle" style="background-color: ${mf.color || '#8b5cf6'};">${escapeHTML((mf.display_name || mf.username).charAt(0).toUpperCase())}</div>
                        <div class="mutual-friend-info">
                            <h5>${escapeHTML(mf.display_name || mf.username)}</h5>
                            <span>@${escapeHTML(mf.username)}</span>
                        </div>
                        <button type="button" class="btn btn-small btn-secondary" onclick="document.getElementById('user-profile-modal').style.display='none'; switchChat(${mf.id}, '${escapeHTML(mf.username)}', '<div class=\\'avatar\\' style=\\'background-color: ${mf.color}; width: 24px; height: 24px; font-size: 11px;\\'>${escapeHTML((mf.display_name || mf.username).charAt(0).toUpperCase())}</div>', null, false, '${mf.color}');" title="Mesaj Gönder"><i data-lucide="message-square" class="icon-xs"></i></button>
                    </div>
                `).join('');
            } else {
                mutualFriendsList.innerHTML = '<div style="color: var(--text-dim); font-size: 12px;">Ortak arkadaşınız bulunmuyor.</div>';
            }
        }

        // 10. Tab Navigation Event Listeners
        document.querySelectorAll('#user-profile-modal .profile-tab-btn').forEach(btn => {
            btn.onclick = () => {
                const targetTab = btn.dataset.profileTab;
                document.querySelectorAll('#user-profile-modal .profile-tab-btn').forEach(b => b.classList.remove('active'));
                document.querySelectorAll('#user-profile-modal .profile-tab-content').forEach(c => c.style.display = 'none');
                btn.classList.add('active');
                const targetContent = document.getElementById(targetTab);
                if (targetContent) targetContent.style.display = 'block';
                renderLucideIcons();
            };
        });

        // Reset to Overview Tab on open
        document.querySelectorAll('#user-profile-modal .profile-tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('#user-profile-modal .profile-tab-content').forEach(c => c.style.display = 'none');
        const defaultTabBtn = document.querySelector('#user-profile-modal .profile-tab-btn[data-profile-tab="tab-prof-overview"]');
        if (defaultTabBtn) defaultTabBtn.classList.add('active');
        const defaultTabContent = document.getElementById('tab-prof-overview');
        if (defaultTabContent) defaultTabContent.style.display = 'block';

        // 11. Private Note on Profile (if friend note exists)
        const notePreviewEl = document.getElementById('modal-profile-note-preview');
        const noteTextEl = document.getElementById('modal-profile-note-text');
        const editNoteInlineBtn = document.getElementById('btn-profile-edit-note-inline');

        if (notePreviewEl && noteTextEl) {
            if (!isSelf && pData.friend_note) {
                noteTextEl.textContent = pData.friend_note;
                notePreviewEl.style.display = 'block';
                if (editNoteInlineBtn) {
                    editNoteInlineBtn.onclick = () => {
                        openFriendNoteModal(u.id, u.display_name || u.username, pData.friend_note || '');
                    };
                }
            } else {
                notePreviewEl.style.display = 'none';
            }
        }

        // 12. Bottom Action Buttons & Friendship Toolbar
        const actionsWrap = document.getElementById('modal-profile-actions');
        if (isSelf) {
            actionsWrap.innerHTML = `
                <div class="profile-actions-main">
                    <button class="btn primary-btn btn-glow" id="btn-modal-edit-profile"><i data-lucide="user-pen" class="icon-sm"></i> Profilimi Düzenle</button>
                </div>
            `;
            const editBtn = document.getElementById('btn-modal-edit-profile');
            if (editBtn) {
                editBtn.onclick = () => {
                    userProfileModal.style.display = 'none';
                    settingsModal.style.display = 'flex';
                    switchSettingsTab('tab-settings-profile');
                };
            }
        } else {
            const status = pData.friendship_status;
            let mainBtnsHTML = '';
            let secondaryToolbarHTML = '';

            if (status === 'blocked_by_me') {
                mainBtnsHTML = `<button class="btn btn-secondary" onclick="unblockUser(${u.id})"><i data-lucide="shield-check" class="icon-sm"></i> Engeli Kaldır</button>`;
            } else if (status === 'blocked_me') {
                mainBtnsHTML = `<span class="badge-chip"><i data-lucide="shield-alert" class="icon-xs"></i> Bu kullanıcıyla iletişim kurulamaz</span>`;
            } else if (status === 'friends') {
                mainBtnsHTML = `
                    <button class="btn primary-btn btn-glow" id="btn-modal-dm-user"><i data-lucide="message-square" class="icon-sm"></i> Mesaj Gönder</button>
                    <button class="btn btn-danger-subtle btn-small" onclick="removeFriend(${u.id})" title="Arkadaşlıktan Çıkar"><i data-lucide="user-x" class="icon-xs"></i> Çıkar</button>
                `;
                secondaryToolbarHTML = `
                    <div class="profile-actions-secondary">
                        <button class="icon-btn action-toggle-btn ${pData.friend_note ? 'active-state-star' : ''}" onclick="openFriendNoteModal(${u.id}, '${escapeHTML(u.display_name || u.username)}', '${escapeHTML(pData.friend_note || '')}')" title="Özel Not"><i data-lucide="file-pen-line"></i></button>
                        <button class="icon-btn action-toggle-btn ${pData.is_close_friend ? 'active-state-heart' : ''}" onclick="toggleCloseFriend(${u.id})" title="Yakın Arkadaş"><i data-lucide="heart"></i></button>
                        <button class="icon-btn action-toggle-btn ${pData.is_favorite ? 'active-state-star' : ''}" onclick="toggleFavoriteFriend(${u.id})" title="Favori"><i data-lucide="star"></i></button>
                        <button class="icon-btn action-toggle-btn ${pData.notify_on_online ? 'active-state-bell' : ''}" onclick="toggleOnlineNotify(${u.id})" title="Çevrimiçi Bildirim"><i data-lucide="bell"></i></button>
                        <button class="icon-btn action-toggle-btn btn-danger-hover" onclick="blockUser(${u.id})" title="Engelle"><i data-lucide="shield-ban"></i></button>
                    </div>
                `;
            } else if (status === 'pending_sent') {
                mainBtnsHTML = `
                    <span class="badge-chip"><i data-lucide="clock" class="icon-xs"></i> İstek Gönderildi</span>
                    <button class="btn btn-card-cancel btn-small" onclick="cancelFriendRequest(${pData.friendship_id})"><i data-lucide="x" class="icon-xs"></i> İptal Et</button>
                `;
            } else if (status === 'pending_received') {
                mainBtnsHTML = `
                    <button class="btn btn-card-accept btn-small" onclick="acceptFriend(${pData.friendship_id})"><i data-lucide="check" class="icon-xs"></i> Kabul Et</button>
                    <button class="btn btn-card-reject btn-small" onclick="rejectFriend(${pData.friendship_id})"><i data-lucide="x" class="icon-xs"></i> Reddet</button>
                `;
            } else {
                // none
                mainBtnsHTML = `
                    <button class="btn btn-secondary" onclick="sendFriendRequestById(${u.id})"><i data-lucide="user-plus" class="icon-sm"></i> Arkadaş Ekle</button>
                    <button class="btn btn-danger-subtle btn-small" onclick="blockUser(${u.id})" title="Engelle"><i data-lucide="shield-ban" class="icon-xs"></i> Engelle</button>
                `;
            }

            actionsWrap.innerHTML = `
                <div class="profile-actions-main">
                    ${mainBtnsHTML}
                </div>
                ${secondaryToolbarHTML}
            `;

            const dmBtn = document.getElementById('btn-modal-dm-user');
            if (dmBtn) {
                dmBtn.onclick = () => {
                    userProfileModal.style.display = 'none';
                    switchChat(u.id, u.username, `<div class="avatar" style="background-color: ${u.color}; width: 24px; height: 24px; font-size: 11px;">${(u.display_name || u.username).charAt(0).toUpperCase()}</div>`, null, false, u.color);
                };
            }
        }

        userProfileModal.style.display = 'flex';
        renderLucideIcons();
    }

    // Expose functions globally for inline HTML event handlers
    window.openUserProfileModal = openUserProfileModal;

    // --- Settings Dashboard System ---
    function initSettingsDashboard() {
        // Open Settings Button
        const openSettingsBtn = document.getElementById('open-settings-btn');
        if (openSettingsBtn) {
            openSettingsBtn.addEventListener('click', () => {
                if (settingsModal) settingsModal.style.display = 'flex';
                renderMyAccountTab();
                switchSettingsTab('tab-settings-account');
            });
        }

        // Close modal handlers
        safeOn(document.getElementById('settings-close-btn'), 'click', () => {
            if (settingsModal) settingsModal.style.display = 'none';
        });
        safeOn(document.getElementById('settings-top-close-btn'), 'click', () => {
            if (settingsModal) settingsModal.style.display = 'none';
        });
        safeOn(document.getElementById('btn-close-2fa-setup'), 'click', () => {
            if (twofaSetupModal) twofaSetupModal.style.display = 'none';
        });
        safeOn(document.getElementById('btn-close-recovery-modal'), 'click', () => {
            if (recoveryCodesModal) recoveryCodesModal.style.display = 'none';
        });
        safeOn(document.getElementById('btn-close-recovery-codes'), 'click', () => {
            if (recoveryCodesModal) recoveryCodesModal.style.display = 'none';
        });
        safeOn(document.getElementById('btn-close-danger-modal'), 'click', () => {
            if (dangerConfirmModal) dangerConfirmModal.style.display = 'none';
        });
        safeOn(document.getElementById('btn-close-user-profile'), 'click', () => {
            if (userProfileModal) userProfileModal.style.display = 'none';
        });
        safeOn(document.getElementById('settings-logout-btn'), 'click', () => {
            if (settingsModal) settingsModal.style.display = 'none';
            handleLogout();
        });

        // Tab Navigation click handlers
        document.querySelectorAll('.settings-nav-item[data-settings-tab]').forEach(item => {
            item.addEventListener('click', () => {
                const tabId = item.dataset.settingsTab;
                switchSettingsTab(tabId);
            });
        });

        // Bio character counter
        const editBio = document.getElementById('edit-bio');
        const bioCharCount = document.getElementById('bio-char-count');
        if (editBio && bioCharCount) {
            editBio.addEventListener('input', () => {
                bioCharCount.textContent = editBio.value.length;
            });
        }

        // Copy Public ID
        const btnCopyId = document.getElementById('btn-copy-public-id');
        if (btnCopyId) {
            btnCopyId.addEventListener('click', () => {
                if (currentUser && currentUser.public_id) {
                    navigator.clipboard.writeText(currentUser.public_id).then(() => {
                        btnCopyId.innerHTML = '<i data-lucide="check" class="icon-xs"></i> Kopyalandı!';
                        renderLucideIcons();
                        showFloatingToast('📋 Astral ID panoya kopyalandı.');
                        setTimeout(() => {
                            btnCopyId.innerHTML = '<i data-lucide="copy" class="icon-xs"></i> Kopyala';
                            renderLucideIcons();
                        }, 2000);
                    });
                }
            });
        }

        // Quick edit profile button inside My Account
        const btnQuickEdit = document.getElementById('btn-quick-edit-profile');
        if (btnQuickEdit) {
            btnQuickEdit.addEventListener('click', () => switchSettingsTab('tab-settings-profile'));
        }

        // Avatar Upload & Remove Handlers
        const avatarFileInput = document.getElementById('avatar-file-input');
        if (avatarFileInput) {
            avatarFileInput.addEventListener('change', async () => {
                if (!avatarFileInput.files.length) return;
                const formData = new FormData();
                formData.append('file', avatarFileInput.files[0]);

                try {
                    const res = await fetch('/api/profile/avatar', { method: 'POST', body: formData });
                    const data = await res.json();
                    if (data.success) {
                        currentUser = data.user;
                        updateLivePreviews();
                        showFloatingToast('✓ Profil fotoğrafı güncellendi!');
                    } else {
                        showFloatingToast(`❌ ${data.message || 'Yükleme başarısız.'}`);
                    }
                } catch (e) {
                    showFloatingToast('❌ Dosya yüklenirken hata oluştu.');
                }
            });
        }

        const btnRemoveAvatar = document.getElementById('btn-remove-avatar');
        if (btnRemoveAvatar) {
            btnRemoveAvatar.addEventListener('click', async () => {
                try {
                    const res = await fetch('/api/profile/avatar/remove', { method: 'POST' });
                    const data = await res.json();
                    if (data.success) {
                        currentUser = data.user;
                        updateLivePreviews();
                        showFloatingToast('✓ Profil fotoğrafı kaldırıldı.');
                    }
                } catch (e) {}
            });
        }

        // Banner Upload & Remove Handlers
        const bannerFileInput = document.getElementById('banner-file-input');
        if (bannerFileInput) {
            bannerFileInput.addEventListener('change', async () => {
                if (!bannerFileInput.files.length) return;
                const formData = new FormData();
                formData.append('file', bannerFileInput.files[0]);

                try {
                    const res = await fetch('/api/profile/banner', { method: 'POST', body: formData });
                    const data = await res.json();
                    if (data.success) {
                        currentUser = data.user;
                        updateLivePreviews();
                        showFloatingToast('✓ Banner görseli güncellendi!');
                    } else {
                        showFloatingToast(`❌ ${data.message || 'Yükleme başarısız.'}`);
                    }
                } catch (e) {
                    showFloatingToast('❌ Dosya yüklenirken hata oluştu.');
                }
            });
        }

        const btnRemoveBanner = document.getElementById('btn-remove-banner');
        if (btnRemoveBanner) {
            btnRemoveBanner.addEventListener('click', async () => {
                try {
                    const res = await fetch('/api/profile/banner/remove', { method: 'POST' });
                    const data = await res.json();
                    if (data.success) {
                        currentUser = data.user;
                        updateLivePreviews();
                        showFloatingToast('✓ Banner görseli kaldırıldı.');
                    }
                } catch (e) {}
            });
        }

        // Edit Profile Form Submit
        const editProfileForm = document.getElementById('edit-profile-form');
        if (editProfileForm) {
            editProfileForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const displayName = document.getElementById('edit-displayname').value.trim();
                const bio = document.getElementById('edit-bio').value.trim();
                const color = document.getElementById('edit-avatar-color').value;
                const bannerColor = document.getElementById('edit-banner-color').value;
                const accentColor = document.getElementById('edit-profile-accent-color') ? document.getElementById('edit-profile-accent-color').value : '#8b5cf6';
                const activeThemeCard = document.querySelector('.theme-select-card.active');
                const cardTheme = activeThemeCard ? activeThemeCard.dataset.theme : 'cyber-glass';

                const portEnabled = document.getElementById('toggle-portfolio-enabled') ? document.getElementById('toggle-portfolio-enabled').checked : false;
                const portTitle = document.getElementById('portfolio-title-input') ? document.getElementById('portfolio-title-input').value.trim() : '';
                const portDesc = document.getElementById('portfolio-desc-input') ? document.getElementById('portfolio-desc-input').value.trim() : '';

                const errEl = document.getElementById('edit-profile-error');
                const succEl = document.getElementById('edit-profile-success');

                try {
                    // Update main profile
                    const res = await fetch('/api/profile/update', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            display_name: displayName,
                            bio: bio,
                            color: color,
                            banner_color: bannerColor
                        })
                    });
                    const data = await res.json();
                    
                    // Update theme & accent
                    await fetch('/api/profile/theme', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            accent_color: accentColor,
                            card_theme: cardTheme
                        })
                    });

                    // Update portfolio settings
                    await fetch('/api/profile/portfolio', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            enabled: portEnabled,
                            title: portTitle,
                            description: portDesc
                        })
                    });

                    if (data.success) {
                        currentUser = data.user;
                        currentUser.profile_accent_color = accentColor;
                        currentUser.profile_card_theme = cardTheme;
                        currentUser.portfolio_enabled = portEnabled;
                        currentUser.portfolio_title = portTitle;
                        currentUser.portfolio_description = portDesc;

                        errEl.textContent = '';
                        succEl.textContent = '✓ Tüm profil ayarları başarıyla kaydedildi!';
                        succEl.style.display = 'block';
                        updateLivePreviews();
                        showFloatingToast('✓ Profil ve tema ayarları kaydedildi!');
                        setTimeout(() => succEl.style.display = 'none', 3000);
                    } else {
                        errEl.textContent = data.message || 'Güncelleme başarısız.';
                    }
                } catch (err) {
                    errEl.textContent = 'Bağlantı hatası oluştu.';
                }
            });
        }

        // Color Chip Click Handlers
        document.querySelectorAll('.color-chip-btn').forEach(chip => {
            chip.addEventListener('click', () => {
                const col = chip.dataset.color;
                const picker = document.getElementById('edit-profile-accent-color');
                if (picker && col) picker.value = col;
            });
        });

        // Theme Card Selectors
        document.querySelectorAll('.theme-select-card').forEach(card => {
            card.addEventListener('click', () => {
                document.querySelectorAll('.theme-select-card').forEach(c => c.classList.remove('active'));
                card.classList.add('active');
            });
        });

        // Add Profile Link Button
        const btnAddProfileLink = document.getElementById('btn-add-profile-link');
        if (btnAddProfileLink) {
            btnAddProfileLink.addEventListener('click', async () => {
                const platform = document.getElementById('link-platform-select').value;
                const title = document.getElementById('link-title-input').value.trim();
                const url = document.getElementById('link-url-input').value.trim();

                if (!title || !url) {
                    showFloatingToast('❌ Lütfen başlık ve geçerli bir URL girin.');
                    return;
                }

                try {
                    const res = await fetch('/api/profile/links', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ platform, title, url })
                    });
                    const data = await res.json();
                    if (data.success) {
                        document.getElementById('link-title-input').value = '';
                        document.getElementById('link-url-input').value = '';
                        showFloatingToast('✓ Bağlantı eklendi!');
                        loadSettingsProfileLinks();
                    } else {
                        showFloatingToast(`❌ ${data.message || 'Eklenemedi.'}`);
                    }
                } catch (e) {
                    showFloatingToast('❌ Bağlantı eklenirken hata oluştu.');
                }
            });
        }

        // Add Profile Project Button
        const btnAddProfileProject = document.getElementById('btn-add-profile-project');
        if (btnAddProfileProject) {
            btnAddProfileProject.addEventListener('click', async () => {
                const title = document.getElementById('proj-title-input').value.trim();
                const url = document.getElementById('proj-url-input').value.trim();
                const desc = document.getElementById('proj-desc-input').value.trim();
                const img = document.getElementById('proj-image-input').value.trim();

                if (!title) {
                    showFloatingToast('❌ Proje başlığı zorunludur.');
                    return;
                }

                try {
                    const res = await fetch('/api/profile/projects', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ title, url, description: desc, image_url: img })
                    });
                    const data = await res.json();
                    if (data.success) {
                        document.getElementById('proj-title-input').value = '';
                        document.getElementById('proj-url-input').value = '';
                        document.getElementById('proj-desc-input').value = '';
                        document.getElementById('proj-image-input').value = '';
                        showFloatingToast('✓ Proje portföye eklendi!');
                        loadSettingsProfileProjects();
                    } else {
                        showFloatingToast(`❌ ${data.message || 'Eklenemedi.'}`);
                    }
                } catch (e) {
                    showFloatingToast('❌ Proje eklenirken hata oluştu.');
                }
            });
        }

        // Change Username Button
        const btnSaveUsername = document.getElementById('btn-save-username');
        if (btnSaveUsername) {
            btnSaveUsername.addEventListener('click', async () => {
                const newUsername = document.getElementById('edit-username-input').value.trim();
                const errEl = document.getElementById('edit-username-error');
                const succEl = document.getElementById('edit-username-success');

                if (!newUsername) {
                    errEl.textContent = 'Lütfen yeni kullanıcı adını girin.';
                    return;
                }

                try {
                    const res = await fetch('/api/profile/username', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ username: newUsername })
                    });
                    const data = await res.json();
                    if (data.success) {
                        currentUser = data.user;
                        errEl.textContent = '';
                        succEl.textContent = '✓ ' + data.message;
                        succEl.style.display = 'block';
                        renderMyAccountTab();
                        showFloatingToast('✓ Kullanıcı adı güncellendi!');
                        setTimeout(() => succEl.style.display = 'none', 3000);
                    } else {
                        errEl.textContent = data.message || 'Kullanıcı adı değiştirilemedi.';
                    }
                } catch (err) {
                    errEl.textContent = 'Bağlantı hatası oluştu.';
                }
            });
        }

        // Presence Status Cards Click Handlers
        document.querySelectorAll('.status-card-opt').forEach(card => {
            card.addEventListener('click', async () => {
                const status = card.dataset.status;
                document.querySelectorAll('.status-card-opt').forEach(c => c.classList.remove('active'));
                card.classList.add('active');

                try {
                    const res = await fetch('/api/profile/update', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ presence_status: status })
                    });
                    const data = await res.json();
                    if (data.success) {
                        currentUser = data.user;
                        showFloatingToast(`✓ Durum '${status.toUpperCase()}' olarak ayarlandı.`);
                    }
                } catch (e) {}
            });
        });

        // Custom Status Form Submit
        const customStatusForm = document.getElementById('custom-status-form');
        if (customStatusForm) {
            customStatusForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const text = document.getElementById('custom-status-text-input').value.trim();
                const emoji = document.getElementById('custom-status-emoji-input').value.trim();
                const expiresIn = document.getElementById('custom-status-duration').value;
                const errEl = document.getElementById('custom-status-error');
                const succEl = document.getElementById('custom-status-success');

                try {
                    const res = await fetch('/api/profile/custom-status', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ text, emoji, expires_in: expiresIn })
                    });
                    const data = await res.json();
                    if (data.success) {
                        currentUser = data.user;
                        errEl.textContent = '';
                        succEl.textContent = '✓ Özel durum kaydedildi!';
                        succEl.style.display = 'block';
                        const myCustomStatus = document.getElementById('my-custom-status');
                        if (myCustomStatus) {
                            myCustomStatus.textContent = text ? `${emoji} ${text}`.trim() : '✨ AstralPaws';
                        }
                        showFloatingToast('✓ Özel durum kaydedildi!');
                        setTimeout(() => succEl.style.display = 'none', 3000);
                    } else {
                        errEl.textContent = data.message || 'Kaydedilemedi.';
                    }
                } catch (err) {
                    errEl.textContent = 'Bağlantı hatası.';
                }
            });
        }

        // Clear Custom Status Button
        const btnClearCustomStatus = document.getElementById('btn-clear-custom-status');
        if (btnClearCustomStatus) {
            btnClearCustomStatus.addEventListener('click', async () => {
                document.getElementById('custom-status-text-input').value = '';
                document.getElementById('custom-status-emoji-input').value = '';
                try {
                    const res = await fetch('/api/profile/custom-status', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ text: '', emoji: '', expires_in: 'never' })
                    });
                    const data = await res.json();
                    if (data.success) {
                        currentUser = data.user;
                        document.getElementById('my-custom-status').textContent = '✨ AstralPaws';
                        showFloatingToast('✓ Özel durum temizlendi.');
                    }
                } catch (e) {}
            });
        }

        // Change Password Form Submit
        const changePasswordForm = document.getElementById('change-password-form');
        if (changePasswordForm) {
            changePasswordForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const currentPassword = document.getElementById('change-pwd-current').value;
                const newPassword = document.getElementById('change-pwd-new').value;
                const newPasswordConfirm = document.getElementById('change-pwd-confirm').value;
                const logoutOthers = document.getElementById('change-pwd-logout-others').checked;
                const errEl = document.getElementById('change-pwd-error');
                const succEl = document.getElementById('change-pwd-success');

                if (newPassword !== newPasswordConfirm) {
                    errEl.textContent = 'Yeni parola tekrarı eşleşmiyor.';
                    return;
                }

                try {
                    const res = await fetch('/api/account/change-password', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            current_password: currentPassword,
                            new_password: newPassword,
                            new_password_confirm: newPasswordConfirm,
                            logout_other_devices: logoutOthers
                        })
                    });
                    const data = await res.json();
                    if (data.success) {
                        errEl.textContent = '';
                        succEl.textContent = '✓ ' + data.message;
                        succEl.style.display = 'block';
                        changePasswordForm.reset();
                        showFloatingToast('✓ Şifreniz başarıyla değiştirildi!');
                        setTimeout(() => succEl.style.display = 'none', 4000);
                    } else {
                        errEl.textContent = data.message || 'Şifre değiştirilemedi.';
                    }
                } catch (err) {
                    errEl.textContent = 'Bağlantı hatası.';
                }
            });
        }

        // 2FA Setup Flow
        const btnStart2fa = document.getElementById('btn-start-2fa-setup');
        if (btnStart2fa) {
            btnStart2fa.addEventListener('click', async () => {
                try {
                    const res = await fetch('/api/security/2fa/setup', { method: 'POST' });
                    const data = await res.json();
                    if (data.success) {
                        document.getElementById('twofa-qr-image').src = data.qr_code;
                        document.getElementById('twofa-secret-display').textContent = data.secret;
                        document.getElementById('twofa-setup-code').value = '';
                        document.getElementById('twofa-setup-error').textContent = '';
                        twofaSetupModal.style.display = 'flex';
                    }
                } catch (e) {
                    showFloatingToast('❌ 2FA kurulumu başlatılamadı.');
                }
            });
        }

        // 2FA Verify & Enable Form Submit
        const twofaVerifySetupForm = document.getElementById('twofa-verify-setup-form');
        if (twofaVerifySetupForm) {
            twofaVerifySetupForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const code = document.getElementById('twofa-setup-code').value.trim();
                const errEl = document.getElementById('twofa-setup-error');

                try {
                    const res = await fetch('/api/security/2fa/enable', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ code })
                    });
                    const data = await res.json();
                    if (data.success) {
                        twofaSetupModal.style.display = 'none';
                        currentUser.two_factor_enabled = true;
                        renderSecurityTab();
                        renderRecoveryCodes(data.recovery_codes);
                        recoveryCodesModal.style.display = 'flex';
                        showFloatingToast('✓ 2FA başarıyla aktifleştirildi!');
                    } else {
                        errEl.textContent = data.message || 'Geçersiz 2FA kodu.';
                    }
                } catch (err) {
                    errEl.textContent = 'Bağlantı hatası.';
                }
            });
        }

        // 2FA Disable Prompt
        const btnDisable2faPrompt = document.getElementById('btn-disable-2fa-prompt');
        if (btnDisable2faPrompt) {
            btnDisable2faPrompt.addEventListener('click', () => {
                openDangerConfirmModal(
                    'İki Aşamalı Doğrulamayı Devre Dışı Bırak',
                    '2FA korumasını kapatmak için lütfen mevcut şifrenizi girin:',
                    async (password) => {
                        const res = await fetch('/api/security/2fa/disable', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ password })
                        });
                        const data = await res.json();
                        if (data.success) {
                            currentUser.two_factor_enabled = false;
                            renderSecurityTab();
                            showFloatingToast('✓ 2FA devre dışı bırakıldı.');
                            return true;
                        } else {
                            throw new Error(data.message || 'İşlem başarısız.');
                        }
                    }
                );
            });
        }

        // Recovery codes modal triggers
        const btnOpenRecoveryModal = document.getElementById('btn-open-recovery-modal');
        if (btnOpenRecoveryModal) {
            btnOpenRecoveryModal.addEventListener('click', () => {
                openDangerConfirmModal(
                    'Yeni Kurtarma Kodları Üret',
                    'Kurtarma kodlarını yenilemek için lütfen şifrenizi girin. Eski kodlarınız geçersiz olacaktır:',
                    async (password) => {
                        const res = await fetch('/api/security/2fa/recovery-codes/regenerate', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ password })
                        });
                        const data = await res.json();
                        if (data.success) {
                            renderRecoveryCodes(data.recovery_codes);
                            recoveryCodesModal.style.display = 'flex';
                            renderSecurityTab();
                            showFloatingToast('✓ Yeni kurtarma kodları oluşturuldu!');
                            return true;
                        } else {
                            throw new Error(data.message || 'Hata oluştu.');
                        }
                    }
                );
            });
        }

        // Download Recovery Codes as text file
        const btnDownloadRecovery = document.getElementById('btn-download-recovery-codes');
        if (btnDownloadRecovery) {
            btnDownloadRecovery.addEventListener('click', () => {
                const chips = Array.from(document.querySelectorAll('.recovery-code-chip')).map(c => c.textContent);
                if (!chips.length) return;
                const text = `AstralPaws İki Aşamalı Doğrulama Kurtarma Kodları\nOluşturulma: ${new Date().toLocaleString('tr-TR')}\n\n` + chips.join('\n') + `\n\nHer kod tek kullanımlıktır.`;
                const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
                const link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                link.download = `astralpaws_recovery_codes_${Date.now()}.txt`;
                link.click();
            });
        }

        // Copy Recovery Codes
        const btnCopyRecovery = document.getElementById('btn-copy-recovery-codes');
        if (btnCopyRecovery) {
            btnCopyRecovery.addEventListener('click', () => {
                const chips = Array.from(document.querySelectorAll('.recovery-code-chip')).map(c => c.textContent);
                if (!chips.length) return;
                navigator.clipboard.writeText(chips.join('\n')).then(() => {
                    btnCopyRecovery.innerHTML = '<i data-lucide="check" class="icon-xs"></i> Kopyalandı!';
                    renderLucideIcons();
                    showFloatingToast('📋 Kurtarma kodları panoya kopyalandı.');
                    setTimeout(() => {
                        btnCopyRecovery.innerHTML = '<i data-lucide="copy" class="icon-xs"></i> Kopyala';
                        renderLucideIcons();
                    }, 2000);
                });
            });
        }

        // Revoke other sessions button
        const btnRevokeOthers = document.getElementById('btn-revoke-other-sessions');
        if (btnRevokeOthers) {
            btnRevokeOthers.addEventListener('click', async () => {
                try {
                    const res = await fetch('/api/account/sessions/revoke-others', { method: 'POST' });
                    const data = await res.json();
                    if (data.success) {
                        showFloatingToast('✓ Diğer tüm oturumlar kapatıldı.');
                        loadActiveSessions();
                    }
                } catch (e) {}
            });
        }

        // Revoke all trusted devices button
        const btnRevokeAllTrusted = document.getElementById('btn-revoke-all-trusted');
        if (btnRevokeAllTrusted) {
            btnRevokeAllTrusted.addEventListener('click', async () => {
                try {
                    const res = await fetch('/api/security/trusted-devices/revoke-all', { method: 'POST' });
                    const data = await res.json();
                    if (data.success) {
                        showFloatingToast('✓ Tüm güvenilir cihazlar kaldırıldı.');
                        loadTrustedDevices();
                    }
                } catch (e) {}
            });
        }

        // Save Privacy settings
        const btnSavePrivacy = document.getElementById('btn-save-privacy');
        if (btnSavePrivacy) {
            btnSavePrivacy.addEventListener('click', async () => {
                const selected = document.querySelector('input[name="last_seen_privacy"]:checked');
                const hideComm = document.getElementById('privacy-hide-communities') ? document.getElementById('privacy-hide-communities').checked : false;
                const succEl = document.getElementById('privacy-success');

                try {
                    const res = await fetch('/api/profile/privacy-settings', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            last_seen_privacy: selected ? selected.value : 'everyone',
                            hide_communities: hideComm
                        })
                    });
                    const data = await res.json();
                    if (data.success) {
                        currentUser.last_seen_privacy = data.last_seen_privacy;
                        currentUser.hide_communities = data.hide_communities;
                        if (succEl) {
                            succEl.textContent = '✓ Gizlilik ayarları başarıyla kaydedildi.';
                            succEl.style.display = 'block';
                            setTimeout(() => succEl.style.display = 'none', 3000);
                        }
                        showFloatingToast('✓ Gizlilik ayarları kaydedildi!');
                    }
                } catch (e) {
                    showFloatingToast('❌ Gizlilik ayarları kaydedilemedi.');
                }
            });
        }

        // Disable Account prompt
        const btnPromptDisable = document.getElementById('btn-prompt-disable-account');
        if (btnPromptDisable) {
            btnPromptDisable.addEventListener('click', () => {
                openDangerConfirmModal(
                    'Hesabı Devre Dışı Bırak',
                    'Hesabınızı geçici olarak dondurmak istediğinize emin misiniz? Lütfen şifrenizi girin:',
                    async (password) => {
                        const res = await fetch('/api/account/disable', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ password })
                        });
                        const data = await res.json();
                        if (data.success) {
                            settingsModal.style.display = 'none';
                            handleLogout();
                            showFloatingToast(data.message);
                            return true;
                        } else {
                            throw new Error(data.message || 'İşlem başarısız.');
                        }
                    }
                );
            });
        }

        // Delete Account prompt (14 day grace period)
        const btnPromptDelete = document.getElementById('btn-prompt-delete-account');
        if (btnPromptDelete) {
            btnPromptDelete.addEventListener('click', () => {
                openDangerConfirmModal(
                    'Hesabı Kalıcı Olarak Sil',
                    'Hesabınız 14 günlük geri dönüş süresiyle silinmek üzere planlanacaktır. Lütfen şifrenizi onaylayın:',
                    async (password) => {
                        const res = await fetch('/api/account/delete-request', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ password })
                        });
                        const data = await res.json();
                        if (data.success) {
                            settingsModal.style.display = 'none';
                            currentUser.is_pending_deletion = true;
                            currentUser.deletion_scheduled_for = data.deletion_scheduled_for;
                            const statusBanner = document.getElementById('account-status-banner');
                            if (statusBanner) {
                                statusBanner.style.display = 'block';
                                document.getElementById('account-status-banner-text').textContent = `⚠️ Hesabınız silinmek üzere planlanmıştır (${new Date(data.deletion_scheduled_for).toLocaleDateString('tr-TR')}).`;
                            }
                            showFloatingToast('⚠️ Hesap silme talebi alındı (14 gün süre).');
                            return true;
                        } else {
                            throw new Error(data.message || 'Silme işlemi başlatılamadı.');
                        }
                    }
                );
            });
        }

        // Appearance & Themes Tab Handlers
        document.querySelectorAll('.theme-card').forEach(card => {
            card.addEventListener('click', () => {
                const theme = card.dataset.theme;
                if (!theme) return;
                document.querySelectorAll('.theme-card').forEach(c => c.classList.remove('active'));
                card.classList.add('active');
                document.documentElement.setAttribute('data-theme', theme);
                document.body.className = `theme-${theme}`;
                try {
                    localStorage.setItem('astral_theme', theme);
                } catch (e) {}
                const title = card.querySelector('h4') ? card.querySelector('h4').textContent : theme;
                showFloatingToast(`🎨 Tema uygulandı: ${title}`);
            });
        });
    }

    function switchSettingsTab(tabId) {
        document.querySelectorAll('.settings-nav-item').forEach(n => n.classList.remove('active'));
        document.querySelectorAll('.settings-tab-pane').forEach(p => p.style.display = 'none');

        const nav = document.querySelector(`[data-settings-tab="${tabId}"]`);
        if (nav) nav.classList.add('active');
        const pane = document.getElementById(tabId);
        if (pane) pane.style.display = 'block';

        // Tab-specific loaders
        if (tabId === 'tab-settings-account') renderMyAccountTab();
        else if (tabId === 'tab-settings-profile') renderEditProfileTab();
        else if (tabId === 'tab-settings-security') renderSecurityTab();
        else if (tabId === 'tab-settings-sessions') loadActiveSessions();
        else if (tabId === 'tab-settings-trusted') loadTrustedDevices();
        else if (tabId === 'tab-settings-privacy') loadPrivacySettings();
    }

    function renderMyAccountTab() {
        if (!currentUser) return;
        document.getElementById('acc-card-displayname').textContent = currentUser.display_name || currentUser.username;
        document.getElementById('acc-card-username').textContent = `@${currentUser.username}`;
        document.getElementById('acc-card-public-id').textContent = currentUser.public_id || `astral_${currentUser.id}`;
        document.getElementById('acc-card-email').textContent = currentUser.email || 'user@example.com';
        document.getElementById('acc-card-created-date').textContent = currentUser.created_at || '2026-08-28';

        const bannerEl = document.getElementById('acc-card-banner');
        if (currentUser.banner) {
            bannerEl.style.backgroundImage = `url(${currentUser.banner})`;
            bannerEl.style.backgroundColor = 'transparent';
        } else {
            bannerEl.style.backgroundImage = 'none';
            bannerEl.style.backgroundColor = currentUser.banner_color || '#8b5cf6';
        }

        const avatarEl = document.getElementById('acc-card-avatar');
        if (currentUser.avatar) {
            avatarEl.style.backgroundImage = `url(${currentUser.avatar})`;
            avatarEl.style.backgroundColor = 'transparent';
            avatarEl.textContent = '';
        } else {
            avatarEl.style.backgroundImage = 'none';
            avatarEl.style.backgroundColor = currentUser.color || '#8b5cf6';
            avatarEl.textContent = (currentUser.display_name || currentUser.username).charAt(0).toUpperCase();
        }

        const pill2fa = document.getElementById('acc-card-2fa-pill');
        if (currentUser.two_factor_enabled) {
            pill2fa.innerHTML = '<i data-lucide="shield-check" class="icon-xs"></i> Etkin';
            pill2fa.className = 'status-pill verified';
        } else {
            pill2fa.textContent = 'Devre Dışı';
            pill2fa.className = 'status-pill';
        }
        renderLucideIcons();
    }

    function renderEditProfileTab() {
        if (!currentUser) return;
        document.getElementById('edit-displayname').value = currentUser.display_name || currentUser.username;
        document.getElementById('edit-bio').value = currentUser.bio || '';
        document.getElementById('bio-char-count').textContent = (currentUser.bio || '').length;
        document.getElementById('edit-username-input').value = currentUser.username;
        document.getElementById('edit-avatar-color').value = currentUser.color || '#8b5cf6';
        document.getElementById('edit-banner-color').value = currentUser.banner_color || '#6366f1';

        // Custom profile theme settings
        const accentInput = document.getElementById('edit-profile-accent-color');
        if (accentInput) accentInput.value = currentUser.profile_accent_color || '#8b5cf6';

        const themeCards = document.querySelectorAll('.theme-select-card');
        themeCards.forEach(c => {
            if (c.dataset.theme === (currentUser.profile_card_theme || 'cyber-glass')) {
                c.classList.add('active');
            } else {
                c.classList.remove('active');
            }
        });

        // Portfolio settings
        const portToggle = document.getElementById('toggle-portfolio-enabled');
        if (portToggle) portToggle.checked = Boolean(currentUser.portfolio_enabled);
        const portTitleInput = document.getElementById('portfolio-title-input');
        if (portTitleInput) portTitleInput.value = currentUser.portfolio_title || 'Öne Çıkan Çalışmalarım';
        const portDescInput = document.getElementById('portfolio-desc-input');
        if (portDescInput) portDescInput.value = currentUser.portfolio_description || '';

        // Load dynamic links & projects lists
        loadSettingsProfileLinks();
        loadSettingsProfileProjects();

        updateLivePreviews();
        renderLucideIcons();
    }

    function updateLivePreviews() {
        if (!currentUser) return;
        const avPreview = document.getElementById('avatar-live-preview');
        if (currentUser.avatar) {
            avPreview.style.backgroundImage = `url(${currentUser.avatar})`;
            avPreview.style.backgroundColor = 'transparent';
            avPreview.textContent = '';
        } else {
            avPreview.style.backgroundImage = 'none';
            avPreview.style.backgroundColor = currentUser.color || '#8b5cf6';
            avPreview.textContent = (currentUser.display_name || currentUser.username).charAt(0).toUpperCase();
        }

        const bannerPreview = document.getElementById('banner-live-preview');
        if (currentUser.banner) {
            bannerPreview.style.backgroundImage = `url(${currentUser.banner})`;
            bannerPreview.style.backgroundColor = 'transparent';
        } else {
            bannerPreview.style.backgroundImage = 'none';
            bannerPreview.style.backgroundColor = currentUser.banner_color || '#6366f1';
        }
    }

    async function renderSecurityTab() {
        if (!currentUser) return;
        const is2fa = Boolean(currentUser.two_factor_enabled);
        const pill = document.getElementById('security-2fa-status-pill');
        const disabledView = document.getElementById('twofa-disabled-view');
        const enabledView = document.getElementById('twofa-enabled-view');

        if (is2fa) {
            pill.innerHTML = '<i data-lucide="shield-check" class="icon-xs"></i> Etkin';
            pill.className = 'status-pill verified';
            disabledView.style.display = 'none';
            enabledView.style.display = 'block';

            // Load remaining recovery codes count
            try {
                const res = await fetch('/api/security/2fa/recovery-codes');
                const data = await res.json();
                if (data.success) {
                    document.getElementById('recovery-codes-count').textContent = data.remaining;
                }
            } catch (e) {}
        } else {
            pill.textContent = 'Devre Dışı';
            pill.className = 'status-pill';
            disabledView.style.display = 'block';
            enabledView.style.display = 'none';
        }
        renderLucideIcons();
    }

    function renderRecoveryCodes(codes) {
        const grid = document.getElementById('recovery-codes-grid');
        grid.innerHTML = '';
        (codes || []).forEach(c => {
            const chip = document.createElement('div');
            chip.className = 'recovery-code-chip';
            chip.textContent = c;
            grid.appendChild(chip);
        });
    }

    async function loadActiveSessions() {
        const list = document.getElementById('active-sessions-list');
        list.innerHTML = '<div style="color: var(--text-dim); text-align: center; padding: 20px;">Oturumlar yükleniyor...</div>';
        try {
            const res = await fetch('/api/account/sessions');
            const data = await res.json();
            list.innerHTML = '';
            if (!data.sessions || !data.sessions.length) {
                list.innerHTML = '<div style="color: var(--text-dim); text-align: center;">Aktif oturum bulunamadı.</div>';
                return;
            }
            data.sessions.forEach(s => {
                const card = document.createElement('div');
                card.className = `session-item-card ${s.is_current ? 'current-session' : ''}`;
                
                const isMobile = (s.os || '').toLowerCase().includes('android') || (s.os || '').toLowerCase().includes('ios');
                const deviceIcon = isMobile ? '<i data-lucide="smartphone" class="icon-lg"></i>' : '<i data-lucide="laptop" class="icon-lg"></i>';
                const currentBadge = s.is_current ? '<span class="status-pill active" style="font-size: 11px;">Mevcut Cihaz</span>' : '';
                const revokeBtn = s.is_current ? '' : `<button type="button" class="btn btn-small btn-danger-outline" onclick="revokeSession(${s.id})"><i data-lucide="log-out" class="icon-xs"></i> Sonlandır</button>`;

                card.innerHTML = `
                    <div class="session-item-left">
                        <div class="session-device-icon">${deviceIcon}</div>
                        <div class="session-info-text">
                            <h4>${escapeHTML(s.device_name)} ${currentBadge}</h4>
                            <div class="session-meta">
                                <i data-lucide="globe" class="icon-xs"></i> IP: ${escapeHTML(s.ip_address)} • Son Aktivite: ${new Date(s.last_active_at).toLocaleString('tr-TR')}
                            </div>
                        </div>
                    </div>
                    <div>${revokeBtn}</div>
                `;
                list.appendChild(card);
            });
            renderLucideIcons();
        } catch (e) {
            list.innerHTML = '<div style="color: var(--danger); text-align: center;">Oturumlar yüklenemedi.</div>';
        }
    }
    window.revokeSession = async (sessionId) => {
        try {
            const res = await fetch('/api/account/sessions/revoke', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId })
            });
            const data = await res.json();
            if (data.success) {
                showFloatingToast('✓ Oturum sonlandırıldı.');
                loadActiveSessions();
            }
        } catch (e) {}
    };

    async function loadTrustedDevices() {
        const list = document.getElementById('trusted-devices-list');
        list.innerHTML = '<div style="color: var(--text-dim); text-align: center; padding: 20px;">Güvenilir cihazlar yükleniyor...</div>';
        try {
            const res = await fetch('/api/security/trusted-devices');
            const data = await res.json();
            list.innerHTML = '';
            if (!data.devices || !data.devices.length) {
                list.innerHTML = '<div style="color: var(--text-dim); text-align: center; padding: 20px;">Kayıtlı güvenilir cihaz bulunmamaktadır.</div>';
                return;
            }
            data.devices.forEach(d => {
                const card = document.createElement('div');
                card.className = 'session-item-card';
                card.innerHTML = `
                    <div class="session-item-left">
                        <div class="session-device-icon"><i data-lucide="shield-check" class="icon-lg"></i></div>
                        <div class="session-info-text">
                            <h4>${escapeHTML(d.device_name)}</h4>
                            <div class="session-meta">
                                Geçerlilik: ${escapeHTML(d.expires_at)} • Son Kullanım: ${new Date(d.last_used_at).toLocaleDateString('tr-TR')}
                            </div>
                        </div>
                    </div>
                    <button type="button" class="btn btn-small btn-danger-outline" onclick="revokeTrustedDevice(${d.id})"><i data-lucide="trash-2" class="icon-xs"></i> Kaldır</button>
                `;
                list.appendChild(card);
            });
            renderLucideIcons();
        } catch (e) {
            list.innerHTML = '<div style="color: var(--danger); text-align: center;">Yüklenemedi.</div>';
        }
    }
    window.revokeTrustedDevice = async (deviceId) => {
        try {
            const res = await fetch('/api/security/trusted-devices/revoke', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ device_id: deviceId })
            });
            const data = await res.json();
            if (data.success) {
                showFloatingToast('✓ Güvenilir cihaz kaldırıldı.');
                loadTrustedDevices();
            }
        } catch (e) {}
    };

    function loadPrivacySettings() {
        if (!currentUser) return;
        const currentSetting = currentUser.last_seen_privacy || 'everyone';
        const radio = document.querySelector(`input[name="last_seen_privacy"][value="${currentSetting}"]`);
        if (radio) radio.checked = true;

        const hideComm = document.getElementById('privacy-hide-communities');
        if (hideComm) hideComm.checked = Boolean(currentUser.hide_communities);
    }

    async function loadSettingsProfileLinks() {
        const list = document.getElementById('profile-links-edit-list');
        if (!list) return;
        try {
            const res = await fetch('/api/profile/links');
            const data = await res.json();
            if (data.success && data.links) {
                if (data.links.length === 0) {
                    list.innerHTML = '<div style="color: var(--text-dim); font-size: 12px; padding: 4px 0;">Henüz eklenmiş bağlantı yok.</div>';
                    return;
                }
                list.innerHTML = data.links.map(l => `
                    <div class="link-manager-item">
                        <div class="item-title"><i data-lucide="${l.icon || 'link'}" class="icon-xs"></i> ${escapeHTML(l.title)}</div>
                        <div class="item-url">${escapeHTML(l.url)}</div>
                        <button type="button" class="btn btn-small btn-danger-outline" onclick="deleteProfileLink(${l.id})"><i data-lucide="trash-2" class="icon-xs"></i> Sil</button>
                    </div>
                `).join('');
                renderLucideIcons();
            }
        } catch (e) {}
    }
    window.deleteProfileLink = async (id) => {
        try {
            const res = await fetch('/api/profile/links', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id })
            });
            const data = await res.json();
            if (data.success) {
                showFloatingToast('✓ Bağlantı silindi.');
                loadSettingsProfileLinks();
            }
        } catch (e) {}
    };

    async function loadSettingsProfileProjects() {
        const list = document.getElementById('profile-projects-edit-list');
        if (!list) return;
        try {
            const res = await fetch('/api/profile/projects');
            const data = await res.json();
            if (data.success && data.projects) {
                if (data.projects.length === 0) {
                    list.innerHTML = '<div style="color: var(--text-dim); font-size: 12px; padding: 4px 0;">Henüz eklenmiş proje yok.</div>';
                    return;
                }
                list.innerHTML = data.projects.map(p => `
                    <div class="project-manager-item">
                        <div class="item-title"><i data-lucide="folder-git-2" class="icon-xs"></i> ${escapeHTML(p.title)}</div>
                        <div class="item-url">${escapeHTML(p.url || p.description || '')}</div>
                        <button type="button" class="btn btn-small btn-danger-outline" onclick="deleteProfileProject(${p.id})"><i data-lucide="trash-2" class="icon-xs"></i> Sil</button>
                    </div>
                `).join('');
                renderLucideIcons();
            }
        } catch (e) {}
    }
    window.deleteProfileProject = async (id) => {
        try {
            const res = await fetch('/api/profile/projects', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id })
            });
            const data = await res.json();
            if (data.success) {
                showFloatingToast('✓ Proje silindi.');
                loadSettingsProfileProjects();
            }
        } catch (e) {}
    };

    function openDangerConfirmModal(title, desc, onConfirmAsync) {
        document.getElementById('danger-modal-title').textContent = title;
        document.getElementById('danger-modal-desc').textContent = desc;
        document.getElementById('danger-pwd-input').value = '';
        document.getElementById('danger-modal-error').textContent = '';
        dangerConfirmModal.style.display = 'flex';
        dangerActionCallback = onConfirmAsync;
    }

    const dangerActionForm = document.getElementById('danger-action-form');
    if (dangerActionForm) {
        dangerActionForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const password = document.getElementById('danger-pwd-input').value;
            const errEl = document.getElementById('danger-modal-error');
            const submitBtn = document.getElementById('btn-danger-modal-confirm');

            if (!password) {
                errEl.textContent = 'Parola gereklidir.';
                return;
            }

            if (dangerActionCallback) {
                submitBtn.disabled = true;
                submitBtn.textContent = 'İşleniyor...';
                try {
                    await dangerActionCallback(password);
                    dangerConfirmModal.style.display = 'none';
                } catch (err) {
                    errEl.textContent = err.message || 'İşlem başarısız.';
                } finally {
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Onayla';
                }
            }
        });
    }

    const btnDangerCancel = document.getElementById('btn-danger-modal-cancel');
    if (btnDangerCancel) {
        btnDangerCancel.addEventListener('click', () => {
            dangerConfirmModal.style.display = 'none';
        });
    }


    // Sound Settings
    safeOn(document.getElementById('setting-sound-effects'), 'change', (e) => {
        soundEffectsEnabled = e.target.checked;
    });
    safeOn(document.getElementById('setting-soundboard-vol'), 'input', (e) => {
        soundboardVolume = parseInt(e.target.value) / 100;
    });
    safeOn(document.getElementById('btn-test-sound'), 'click', () => {
        AudioEngine.playChime('ping');
    });

    // --- Emoji Picker Popover ---
    function initEmojiPicker() {
        const popover = document.getElementById('emoji-picker-popover');
        if (!popover) return;
        loadEmojiCategory('smileys');

        document.querySelectorAll('.sub-cat-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                document.querySelectorAll('.sub-cat-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                loadEmojiCategory(btn.dataset.cat);
            });
        });

        safeOn(document.getElementById('btn-open-emojis'), 'click', (e) => {
            e.stopPropagation();
            const isVisible = popover.style.display === 'flex';
            popover.style.display = isVisible ? 'none' : 'flex';
            delete popover.dataset.targetMsgId;
        });
    }

    function loadEmojiCategory(cat) {
        const grid = document.getElementById('emoji-grid-container');
        const popover = document.getElementById('emoji-picker-popover');
        if (!grid) return;
        grid.innerHTML = '';
        (EMOJI_DATABASE[cat] || []).forEach(em => {
            const item = document.createElement('div');
            item.className = 'emoji-item';
            item.textContent = em;
            item.onclick = (e) => {
                e.stopPropagation();
                const targetMsgId = popover ? popover.dataset.targetMsgId : null;
                if (targetMsgId) {
                    toggleReaction(parseInt(targetMsgId), em);
                } else if (messageInput) {
                    messageInput.value += em;
                    messageInput.focus();
                }
                if (popover) popover.style.display = 'none';
            };
            grid.appendChild(item);
        });
    }

    // Close emoji picker on outside click
    document.addEventListener('click', (e) => {
        const popover = document.getElementById('emoji-picker-popover');
        if (!popover) return;
        if (!popover.contains(e.target) && !e.target.closest('#btn-open-emojis') && !e.target.closest('.msg-action-btn')) {
            popover.style.display = 'none';
        }
    });

    // --- Lightbox Media Viewer ---
    window.openLightbox = (imgUrl) => {
        document.getElementById('lightbox-img').src = imgUrl;
        document.getElementById('lightbox-download-link').href = imgUrl;
        lightboxModal.style.display = 'flex';
    };
    safeOn(document.getElementById('lightbox-close'), 'click', () => {
        lightboxModal.style.display = 'none';
    });

    // --- Friends & Dashboard Logic ---
    // --- Friends & Dashboard System ---
    let currentFriendTab = 'online';
    let cachedFriendsData = null;

    async function loadFriends() {
        try {
            const res = await fetch('/api/friends');
            const data = await res.json();
            if (!data.success && !data.friends) return;

            cachedFriendsData = data;
            renderFriends(data);
        } catch (e) {
            console.error("Error loading friends:", e);
        }
    }

    function renderFriends(data) {
        if (!data) return;
        const friends = data.friends || [];
        const pendingIn = data.pending_incoming || [];
        const pendingOut = data.pending_outgoing || [];
        const closeList = data.close_friends || [];
        const favList = data.favorites || [];
        const blockedList = data.blocked || [];
        const counts = data.counts || {
            all: friends.length,
            online: friends.filter(f => f.status_mode && f.status_mode !== 'offline').length,
            pending_in: pendingIn.length,
            pending_out: pendingOut.length,
            close: closeList.length,
            favorites: favList.length,
            blocked: blockedList.length
        };

        // 1. Update Tab Badges
        const setBadge = (id, count, hideIfZero = false) => {
            const el = document.getElementById(id);
            if (el) {
                el.textContent = count;
                if (hideIfZero) {
                    el.style.display = count > 0 ? 'inline-flex' : 'none';
                }
            }
        };

        setBadge('tab-cnt-online', counts.online);
        setBadge('tab-cnt-all', counts.all);
        setBadge('tab-cnt-pending-in', counts.pending_in, true);
        setBadge('tab-cnt-pending-out', counts.pending_out, true);
        setBadge('tab-cnt-close', counts.close);
        setBadge('tab-cnt-favorites', counts.favorites);
        setBadge('tab-cnt-blocked', counts.blocked);

        const sidebarPendingBadge = document.getElementById('pending-badge');
        if (sidebarPendingBadge) {
            if (counts.pending_in > 0) {
                sidebarPendingBadge.textContent = counts.pending_in;
                sidebarPendingBadge.style.display = 'inline-block';
            } else {
                sidebarPendingBadge.style.display = 'none';
            }
        }

        // 2. Populate Sidebar DMs List
        const sidebarDms = document.getElementById('sidebar-dm-list');
        if (sidebarDms) {
            sidebarDms.innerHTML = '';
            if (friends.length === 0) {
                sidebarDms.innerHTML = '<div style="padding: 12px 16px; color: var(--text-dim); font-size: 12px;">Henüz arkadaşınız yok.</div>';
            } else {
                // Sort favorites and close friends first in sidebar
                const sortedFriends = [...friends].sort((a, b) => {
                    const aScore = (a.is_favorite ? 2 : 0) + (a.is_close_friend ? 1 : 0);
                    const bScore = (b.is_favorite ? 2 : 0) + (b.is_close_friend ? 1 : 0);
                    return bScore - aScore;
                });

                sortedFriends.forEach(f => {
                    const sItem = document.createElement('div');
                    sItem.className = 'friend-item';
                    sItem.id = `sidebar-dm-${f.user_id}`;
                    const initial = (f.display_name || f.username || '?').charAt(0).toUpperCase();
                    const avatarHTML = f.avatar 
                        ? `<div class="avatar" style="background-image: url('${f.avatar}'); width: 34px; height: 34px;"></div>`
                        : `<div class="avatar" style="background-color: ${f.color || '#8b5cf6'}; width: 34px; height: 34px;">${escapeHTML(initial)}</div>`;

                    sItem.innerHTML = `
                        <div class="avatar-wrap">
                            ${avatarHTML}
                            <div class="status-dot status-${f.status_mode || 'offline'}"></div>
                        </div>
                        <div class="friend-info">
                            <div class="friend-name">
                                <span>${escapeHTML(f.display_name || f.username)}</span>
                                ${f.is_favorite ? '<i data-lucide="star" class="icon-xs" style="color: #f59e0b; width: 12px; height: 12px;"></i>' : ''}
                                ${f.is_close_friend ? '<i data-lucide="heart" class="icon-xs" style="color: #ec4899; width: 12px; height: 12px;"></i>' : ''}
                            </div>
                            <div class="friend-status-sub">${escapeHTML(f.custom_status || (f.status_mode === 'offline' ? 'Çevrimdışı' : 'Çevrimiçi'))}</div>
                        </div>
                    `;
                    sItem.onclick = () => {
                        switchChat(f.user_id, f.username, avatarHTML, null, false, f.color);
                    };
                    sidebarDms.appendChild(sItem);
                });
            }
        }

        // 3. Pane Visibility
        const friendsPane = document.getElementById('dash-pane-friends');
        const reqsPane = document.getElementById('dash-pane-requests');
        const suggPane = document.getElementById('dash-pane-suggestions');
        const blockedPane = document.getElementById('dash-pane-blocked');
        const addPane = document.getElementById('dash-pane-add');
        const filterBar = document.getElementById('friends-filter-bar');

        if (friendsPane) friendsPane.style.display = 'none';
        if (reqsPane) reqsPane.style.display = 'none';
        if (suggPane) suggPane.style.display = 'none';
        if (blockedPane) blockedPane.style.display = 'none';
        if (addPane) addPane.style.display = 'none';
        if (filterBar) filterBar.style.display = (currentFriendTab === 'add') ? 'none' : 'block';

        if (['online', 'all', 'close', 'favorites'].includes(currentFriendTab)) {
            if (friendsPane) friendsPane.style.display = 'block';
            renderFriendsTabPane(friends);
        } else if (['pending_in', 'pending_out'].includes(currentFriendTab)) {
            if (reqsPane) reqsPane.style.display = 'block';
            renderRequestsTabPane(pendingIn, pendingOut);
        } else if (currentFriendTab === 'suggestions') {
            if (suggPane) suggPane.style.display = 'block';
            renderSuggestionsTabPane();
        } else if (currentFriendTab === 'blocked') {
            if (blockedPane) blockedPane.style.display = 'block';
            renderBlockedTabPane(blockedList);
        } else if (currentFriendTab === 'add') {
            if (addPane) addPane.style.display = 'block';
        }

        renderLucideIcons();
    }

    function renderFriendsTabPane(allFriends) {
        const listEl = document.getElementById('dashboard-friend-list');
        const titleEl = document.getElementById('friends-pane-section-title');
        const countEl = document.getElementById('friends-pane-count');
        if (!listEl) return;
        listEl.innerHTML = '';

        let filtered = [];
        let sectionTitle = 'TÜM ARKADAŞLAR';

        if (currentFriendTab === 'online') {
            filtered = allFriends.filter(f => f.status_mode && f.status_mode !== 'offline');
            sectionTitle = 'ÇEVRİMİÇİ ARKADAŞLAR';
        } else if (currentFriendTab === 'close') {
            filtered = allFriends.filter(f => f.is_close_friend);
            sectionTitle = 'YAKIN ARKADAŞLAR';
        } else if (currentFriendTab === 'favorites') {
            filtered = allFriends.filter(f => f.is_favorite);
            sectionTitle = 'FAVORİ KİŞİLER';
        } else {
            filtered = [...allFriends];
            sectionTitle = 'TÜM ARKADAŞLAR';
        }

        if (titleEl) titleEl.textContent = `${sectionTitle} — `;
        if (countEl) countEl.textContent = filtered.length;

        if (filtered.length === 0) {
            let emptyMsg = 'Henüz arkadaş listeniz boş.';
            if (currentFriendTab === 'online') emptyMsg = 'Şu anda çevrimiçi arkadaşınız bulunmuyor.';
            else if (currentFriendTab === 'close') emptyMsg = 'Henüz yakın arkadaş olarak işaretlenmiş birisi yok.';
            else if (currentFriendTab === 'favorites') emptyMsg = 'Henüz favorilere eklenmiş bir arkadaşınız yok.';

            listEl.innerHTML = `
                <div class="empty-state-wrap">
                    <div style="margin-bottom: 8px;"><i data-lucide="sparkles" class="icon-2xl" style="color: var(--primary);"></i></div>
                    <div style="color: var(--text-muted); font-size: 13.5px;">${emptyMsg}</div>
                </div>
            `;
            return;
        }

        filtered.forEach(f => {
            const initial = (f.display_name || f.username || '?').charAt(0).toUpperCase();
            const avatarHTML = f.avatar
                ? `<div class="avatar" style="background-image: url('${f.avatar}');"></div>`
                : `<div class="avatar" style="background-color: ${f.color || '#8b5cf6'};">${escapeHTML(initial)}</div>`;

            const card = document.createElement('div');
            card.className = `dashboard-friend-card ${f.is_favorite ? 'card-favorite' : ''} ${f.is_close_friend ? 'card-close-friend' : ''}`;
            card.innerHTML = `
                <div class="card-left" onclick="openUserProfileModal(${f.user_id})">
                    <div class="avatar-wrap">
                        ${avatarHTML}
                        <div class="status-dot status-${f.status_mode || 'offline'}"></div>
                    </div>
                    <div class="card-user-info">
                        <div class="card-username">
                            <span>${escapeHTML(f.display_name || f.username)}</span>
                            <span class="user-handle">@${escapeHTML(f.username)}</span>
                            ${f.is_favorite ? '<span class="card-rel-tag tag-favorite"><i data-lucide="star" class="icon-xs"></i> Favori</span>' : ''}
                            ${f.is_close_friend ? '<span class="card-rel-tag tag-close"><i data-lucide="heart" class="icon-xs"></i> Yakın Arkadaş</span>' : ''}
                        </div>
                        <div class="friend-status-sub">${escapeHTML(f.custom_status || (f.status_mode === 'offline' ? 'Çevrimdışı' : 'Çevrimiçi'))}</div>
                        ${f.note ? `<div class="card-note-chip"><i data-lucide="sticky-note" class="icon-xs"></i> ${escapeHTML(f.note)}</div>` : ''}
                    </div>
                </div>
                <div class="card-actions">
                    <button class="btn primary-btn btn-small btn-glow" onclick="switchChat(${f.user_id}, '${escapeHTML(f.username)}', null, null, false, '${f.color}')" title="Mesaj Gönder"><i data-lucide="message-square" class="icon-xs"></i> Mesaj</button>
                    <button class="btn-card-icon ${f.note ? 'active-star' : ''}" onclick="openFriendNoteModal(${f.user_id}, '${escapeHTML(f.display_name || f.username)}', '${escapeHTML(f.note || '')}')" title="Özel Not"><i data-lucide="file-pen-line" class="icon-xs"></i>${f.note ? '<span class="note-has-dot"></span>' : ''}</button>
                    <button class="btn-card-icon ${f.is_favorite ? 'active-star' : ''}" onclick="toggleFavoriteFriend(${f.user_id})" title="${f.is_favorite ? 'Favorilerden Çıkar' : 'Favorilere Ekle'}"><i data-lucide="star" class="icon-xs"></i></button>
                    <button class="btn-card-icon ${f.is_close_friend ? 'active-heart' : ''}" onclick="toggleCloseFriend(${f.user_id})" title="${f.is_close_friend ? 'Yakın Arkadaşlardan Çıkar' : 'Yakın Arkadaşlara Ekle'}"><i data-lucide="heart" class="icon-xs"></i></button>
                    <button class="btn-card-icon ${f.notify_on_online ? 'active-bell' : ''}" onclick="toggleOnlineNotify(${f.user_id})" title="${f.notify_on_online ? 'Çevrimiçi Bildirimini Kapat' : 'Çevrimiçi Bildirimini Aç'}"><i data-lucide="bell" class="icon-xs"></i></button>
                    <button class="btn-card-icon btn-danger-hover" onclick="removeFriend(${f.user_id})" title="Arkadaşlıktan Çıkar"><i data-lucide="user-x" class="icon-xs"></i></button>
                </div>
            `;
            listEl.appendChild(card);
        });
    }

    function renderRequestsTabPane(pendingIn, pendingOut) {
        const listEl = document.getElementById('dashboard-request-list');
        const titleEl = document.getElementById('requests-pane-section-title');
        const countEl = document.getElementById('requests-pane-count');
        if (!listEl) return;
        listEl.innerHTML = '';

        const isIncoming = currentFriendTab === 'pending_in';
        const requests = isIncoming ? pendingIn : pendingOut;

        if (titleEl) titleEl.textContent = isIncoming ? 'GELEN ARKADAŞLIK İSTEKLERİ — ' : 'GİDEN ARKADAŞLIK İSTEKLERİ — ';
        if (countEl) countEl.textContent = requests.length;

        if (requests.length === 0) {
            listEl.innerHTML = `
                <div class="empty-state-wrap">
                    <div style="margin-bottom: 8px;"><i data-lucide="inbox" class="icon-2xl" style="color: var(--primary);"></i></div>
                    <div style="color: var(--text-muted); font-size: 13.5px;">${isIncoming ? 'Bekleyen gelen istek bulunmuyor.' : 'Bekleyen giden istek bulunmuyor.'}</div>
                </div>
            `;
            return;
        }

        requests.forEach(r => {
            const initial = (r.display_name || r.username || '?').charAt(0).toUpperCase();
            const avatarHTML = r.avatar
                ? `<div class="avatar" style="background-image: url('${r.avatar}');"></div>`
                : `<div class="avatar" style="background-color: ${r.color || '#8b5cf6'};">${escapeHTML(initial)}</div>`;

            const card = document.createElement('div');
            card.className = 'dashboard-friend-card';
            card.innerHTML = `
                <div class="card-left" onclick="openUserProfileModal(${r.user_id})">
                    <div class="avatar-wrap">
                        ${avatarHTML}
                        <div class="status-dot status-${r.status_mode || 'offline'}"></div>
                    </div>
                    <div class="card-user-info">
                        <div class="card-username">
                            <span>${escapeHTML(r.display_name || r.username)}</span>
                            <span class="user-handle">@${escapeHTML(r.username)}</span>
                        </div>
                        <div class="friend-status-sub">${isIncoming ? 'Size arkadaşlık isteği gönderdi' : 'Yanıt bekleniyor...'}</div>
                    </div>
                </div>
                <div class="card-actions">
                    ${isIncoming ? `
                        <button class="btn-card-action btn-card-accept" onclick="acceptFriend(${r.friendship_id})"><i data-lucide="check" class="icon-xs"></i> Kabul Et</button>
                        <button class="btn-card-action btn-card-reject" onclick="rejectFriend(${r.friendship_id})"><i data-lucide="x" class="icon-xs"></i> Reddet</button>
                    ` : `
                        <button class="btn-card-action btn-card-cancel" onclick="cancelFriendRequest(${r.friendship_id})"><i data-lucide="x" class="icon-xs"></i> İptal Et</button>
                    `}
                </div>
            `;
            listEl.appendChild(card);
        });
    }

    async function renderSuggestionsTabPane() {
        const listEl = document.getElementById('dashboard-suggestions-list');
        const countEl = document.getElementById('suggestions-pane-count');
        if (!listEl) return;
        listEl.innerHTML = '<div style="padding: 20px; text-align: center; color: var(--text-dim);"><i data-lucide="loader-2" class="icon-spin"></i> Öneriler yükleniyor...</div>';
        renderLucideIcons();

        try {
            const res = await fetch('/api/friends/suggestions');
            const data = await res.json();
            const suggestions = data.suggestions || [];

            if (countEl) countEl.textContent = suggestions.length;
            listEl.innerHTML = '';

            if (suggestions.length === 0) {
                listEl.innerHTML = `
                    <div class="empty-state-wrap">
                        <div style="margin-bottom: 8px;"><i data-lucide="sparkles" class="icon-2xl" style="color: var(--primary);"></i></div>
                        <div style="color: var(--text-muted); font-size: 13.5px;">Şu anda önerilecek yeni arkadaş bulunmuyor.</div>
                    </div>
                `;
                return;
            }

            suggestions.forEach(s => {
                const initial = (s.display_name || s.username || '?').charAt(0).toUpperCase();
                const avatarHTML = s.avatar
                    ? `<div class="avatar" style="background-image: url('${s.avatar}');"></div>`
                    : `<div class="avatar" style="background-color: ${s.color || '#8b5cf6'};">${escapeHTML(initial)}</div>`;

                let mutualInfo = '';
                if (s.mutual_friends_count > 0) {
                    const sample = (s.mutual_friends_sample || []).join(', ');
                    mutualInfo = `<div class="suggestion-mutual-pill"><i data-lucide="users" class="icon-xs"></i> <strong>${s.mutual_friends_count} Ortak Arkadaş</strong> ${sample ? `(${escapeHTML(sample)})` : ''}</div>`;
                } else if (s.mutual_servers_count > 0) {
                    mutualInfo = `<div class="suggestion-mutual-pill"><i data-lucide="globe" class="icon-xs"></i> <strong>${s.mutual_servers_count} Ortak Topluluk</strong></div>`;
                }

                const card = document.createElement('div');
                card.className = 'dashboard-friend-card';
                card.innerHTML = `
                    <div class="card-left" onclick="openUserProfileModal(${s.user_id})">
                        <div class="avatar-wrap">
                            ${avatarHTML}
                            <div class="status-dot status-${s.status_mode || 'offline'}"></div>
                        </div>
                        <div class="card-user-info">
                            <div class="card-username">
                                <span>${escapeHTML(s.display_name || s.username)}</span>
                                <span class="user-handle">@${escapeHTML(s.username)}</span>
                            </div>
                            ${mutualInfo}
                        </div>
                    </div>
                    <div class="card-actions">
                        <button class="btn primary-btn btn-small btn-glow" onclick="sendFriendRequestById(${s.user_id})"><i data-lucide="user-plus" class="icon-xs"></i> Ekle</button>
                    </div>
                `;
                listEl.appendChild(card);
            });
            renderLucideIcons();
        } catch (e) {
            listEl.innerHTML = '<div style="color: var(--danger); font-size: 13px;">Öneriler alınamadı.</div>';
        }
    }

    function renderBlockedTabPane(blockedList) {
        const listEl = document.getElementById('dashboard-blocked-list');
        const countEl = document.getElementById('blocked-pane-count');
        if (!listEl) return;
        listEl.innerHTML = '';

        if (countEl) countEl.textContent = blockedList.length;

        if (blockedList.length === 0) {
            listEl.innerHTML = `
                <div class="empty-state-wrap">
                    <div style="margin-bottom: 8px;"><i data-lucide="shield-check" class="icon-2xl" style="color: #22c55e;"></i></div>
                    <div style="color: var(--text-muted); font-size: 13.5px;">Engellenen kullanıcı bulunmuyor.</div>
                </div>
            `;
            return;
        }

        blockedList.forEach(b => {
            const initial = (b.display_name || b.username || '?').charAt(0).toUpperCase();
            const avatarHTML = b.avatar
                ? `<div class="avatar" style="background-image: url('${b.avatar}');"></div>`
                : `<div class="avatar" style="background-color: ${b.color || '#8b5cf6'};">${escapeHTML(initial)}</div>`;

            const card = document.createElement('div');
            card.className = 'dashboard-friend-card';
            card.innerHTML = `
                <div class="card-left">
                    <div class="avatar-wrap">
                        ${avatarHTML}
                    </div>
                    <div class="card-user-info">
                        <div class="card-username">
                            <span>${escapeHTML(b.display_name || b.username)}</span>
                            <span class="user-handle">@${escapeHTML(b.username)}</span>
                        </div>
                        <div class="friend-status-sub">${b.reason ? escapeHTML(b.reason) : 'Engellendi'}</div>
                    </div>
                </div>
                <div class="card-actions">
                    <button class="btn btn-secondary btn-small" onclick="unblockUser(${b.blocked_id})"><i data-lucide="shield-check" class="icon-xs"></i> Engeli Kaldır</button>
                </div>
            `;
            listEl.appendChild(card);
        });
    }

    // --- Action Handlers Exposed to Window ---

    window.sendFriendRequestById = async (userId) => {
        try {
            const res = await fetch('/api/friends/request', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId })
            });
            const data = await res.json();
            if (data.success) {
                showFloatingToast('✓ ' + (data.message || 'İstek gönderildi!'));
                loadFriends();
                if (document.getElementById('user-profile-modal').style.display !== 'none') {
                    openUserProfileModal(userId);
                }
            } else {
                showFloatingToast(`❌ ${data.message || 'İstek gönderilemedi.'}`);
            }
        } catch (e) {
            showFloatingToast('❌ Bağlantı hatası.');
        }
    };

    window.acceptFriend = async (friendshipId) => {
        try {
            const res = await fetch(`/api/friends/requests/${friendshipId}/accept`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ friendship_id: friendshipId })
            });
            const data = await res.json();
            if (data.success) {
                showFloatingToast('✓ Arkadaşlık isteği kabul edildi!');
                loadFriends();
                if (document.getElementById('user-profile-modal').style.display !== 'none') {
                    document.getElementById('user-profile-modal').style.display = 'none';
                }
            } else {
                showFloatingToast(`❌ ${data.message || 'İstek kabul edilemedi.'}`);
            }
        } catch (e) {
            showFloatingToast('❌ İşlem tamamlanamadı.');
        }
    };

    window.rejectFriend = async (friendshipId) => {
        try {
            const res = await fetch(`/api/friends/requests/${friendshipId}/reject`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ friendship_id: friendshipId })
            });
            const data = await res.json();
            if (data.success) {
                showFloatingToast('✓ İstek reddedildi.');
                loadFriends();
                if (document.getElementById('user-profile-modal').style.display !== 'none') {
                    document.getElementById('user-profile-modal').style.display = 'none';
                }
            }
        } catch (e) {
            showFloatingToast('❌ İşlem tamamlanamadı.');
        }
    };

    window.cancelFriendRequest = async (friendshipId) => {
        try {
            const res = await fetch(`/api/friends/requests/${friendshipId}/cancel`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ friendship_id: friendshipId })
            });
            const data = await res.json();
            if (data.success) {
                showFloatingToast('✓ Arkadaşlık isteği iptal edildi.');
                loadFriends();
                if (document.getElementById('user-profile-modal').style.display !== 'none') {
                    document.getElementById('user-profile-modal').style.display = 'none';
                }
            }
        } catch (e) {
            showFloatingToast('❌ İşlem tamamlanamadı.');
        }
    };

    window.removeFriend = async (friendId) => {
        if (!confirm('Bu kullanıcıyı arkadaş listenizden kaldırmak istediğinize emin misiniz?')) return;
        try {
            const res = await fetch(`/api/friends/${friendId}`, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ friend_id: friendId })
            });
            const data = await res.json();
            if (data.success) {
                showFloatingToast('✓ Arkadaş listenizden kaldırıldı.');
                loadFriends();
                if (document.getElementById('user-profile-modal').style.display !== 'none') {
                    openUserProfileModal(friendId);
                }
            }
        } catch (e) {
            showFloatingToast('❌ İşlem tamamlanamadı.');
        }
    };

    window.blockUser = async (userId) => {
        if (!confirm('Bu kullanıcıyı engellemek istediğinize emin misiniz? Mevcut arkadaşlık ve mesajlaşma sonlandırılacaktır.')) return;
        try {
            const res = await fetch(`/api/friends/${userId}/block`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target_user_id: userId })
            });
            const data = await res.json();
            if (data.success) {
                showFloatingToast('✓ Kullanıcı engellendi.');
                loadFriends();
                if (document.getElementById('user-profile-modal').style.display !== 'none') {
                    openUserProfileModal(userId);
                }
            }
        } catch (e) {
            showFloatingToast('❌ İşlem tamamlanamadı.');
        }
    };

    window.unblockUser = async (userId) => {
        try {
            const res = await fetch(`/api/friends/${userId}/unblock`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target_user_id: userId })
            });
            const data = await res.json();
            if (data.success) {
                showFloatingToast('✓ Kullanıcının engeli kaldırıldı.');
                loadFriends();
                if (document.getElementById('user-profile-modal').style.display !== 'none') {
                    openUserProfileModal(userId);
                }
            }
        } catch (e) {
            showFloatingToast('❌ İşlem tamamlanamadı.');
        }
    };

    window.toggleCloseFriend = async (friendId) => {
        try {
            const res = await fetch(`/api/friends/${friendId}/toggle-close`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const data = await res.json();
            if (data.success) {
                showFloatingToast(data.is_close_friend ? '💖 Yakın arkadaşlara eklendi.' : 'Yakın arkadaşlardan çıkarıldı.');
                loadFriends();
                if (document.getElementById('user-profile-modal').style.display !== 'none') {
                    openUserProfileModal(friendId);
                }
            }
        } catch (e) {
            showFloatingToast('❌ Güncellenemedi.');
        }
    };

    window.toggleFavoriteFriend = async (friendId) => {
        try {
            const res = await fetch(`/api/friends/${friendId}/toggle-favorite`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const data = await res.json();
            if (data.success) {
                showFloatingToast(data.is_favorite ? '⭐ Favorilere eklendi.' : 'Favorilerden çıkarıldı.');
                loadFriends();
                if (document.getElementById('user-profile-modal').style.display !== 'none') {
                    openUserProfileModal(friendId);
                }
            }
        } catch (e) {
            showFloatingToast('❌ Güncellenemedi.');
        }
    };

    window.toggleOnlineNotify = async (friendId) => {
        try {
            const res = await fetch(`/api/friends/${friendId}/toggle-online-notify`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const data = await res.json();
            if (data.success) {
                showFloatingToast(data.notify_on_online ? '🔔 Çevrimiçi bildirimi açıldı.' : '🔕 Çevrimiçi bildirimi kapatıldı.');
                loadFriends();
                if (document.getElementById('user-profile-modal').style.display !== 'none') {
                    openUserProfileModal(friendId);
                }
            }
        } catch (e) {
            showFloatingToast('❌ Güncellenemedi.');
        }
    };

    // --- Friend Note Modal Wiring ---
    const friendNoteModal = document.getElementById('friend-note-modal');
    const friendNoteTextarea = document.getElementById('friend-note-textarea');
    const friendNoteTargetId = document.getElementById('friend-note-target-id');
    const friendNoteSubtitle = document.getElementById('friend-note-subtitle');

    window.openFriendNoteModal = (friendId, friendName, currentNote = '') => {
        if (!friendNoteModal) return;
        if (friendNoteTargetId) friendNoteTargetId.value = friendId;
        if (friendNoteSubtitle) friendNoteSubtitle.textContent = `${friendName} hakkında özel notunuz. Sadece siz görebilirsiniz.`;
        if (friendNoteTextarea) friendNoteTextarea.value = currentNote || '';
        friendNoteModal.style.display = 'flex';
        if (friendNoteTextarea) friendNoteTextarea.focus();
        renderLucideIcons();
    };

    safeOn(document.getElementById('btn-cancel-friend-note'), 'click', () => {
        if (friendNoteModal) friendNoteModal.style.display = 'none';
    });

    safeOn(document.getElementById('btn-clear-friend-note'), 'click', async () => {
        const targetId = friendNoteTargetId ? friendNoteTargetId.value : null;
        if (!targetId) return;

        try {
            const res = await fetch(`/api/friends/${targetId}/note`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ note: '' })
            });
            const data = await res.json();
            if (data.success) {
                showFloatingToast('✓ Özel not silindi.');
                if (friendNoteModal) friendNoteModal.style.display = 'none';
                loadFriends();
                if (document.getElementById('user-profile-modal').style.display !== 'none') {
                    openUserProfileModal(targetId);
                }
            }
        } catch (e) {
            showFloatingToast('❌ Not silinemedi.');
        }
    });

    safeOn(document.getElementById('btn-save-friend-note'), 'click', async () => {
        const targetId = friendNoteTargetId ? friendNoteTargetId.value : null;
        const noteText = friendNoteTextarea ? friendNoteTextarea.value.trim() : '';
        if (!targetId) return;

        try {
            const res = await fetch(`/api/friends/${targetId}/note`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ note: noteText })
            });
            const data = await res.json();
            if (data.success) {
                showFloatingToast('✓ Özel arkadaş notu kaydedildi!');
                if (friendNoteModal) friendNoteModal.style.display = 'none';
                loadFriends();
                if (document.getElementById('user-profile-modal').style.display !== 'none') {
                    openUserProfileModal(targetId);
                }
            } else {
                showFloatingToast(`❌ ${data.message || 'Not kaydedilemedi.'}`);
            }
        } catch (e) {
            showFloatingToast('❌ Not kaydedilemedi.');
        }
    });

    // Live search filter across cards in active dashboard pane
    const filterFriendsInput = document.getElementById('filter-friends-input');
    const clearFriendsSearchBtn = document.getElementById('btn-clear-friends-search');

    if (filterFriendsInput) {
        safeOn(filterFriendsInput, 'input', (e) => {
            const query = e.target.value.toLowerCase().trim();
            if (clearFriendsSearchBtn) {
                clearFriendsSearchBtn.style.display = query ? 'inline-flex' : 'none';
            }

            document.querySelectorAll('.dashboard-friend-card').forEach(card => {
                const name = card.querySelector('.card-username')?.textContent.toLowerCase() || '';
                const status = card.querySelector('.friend-status-sub')?.textContent.toLowerCase() || '';
                const note = card.querySelector('.card-note-chip')?.textContent.toLowerCase() || '';
                card.style.display = (name.includes(query) || status.includes(query) || note.includes(query)) ? 'flex' : 'none';
            });
        });
    }

    if (clearFriendsSearchBtn) {
        safeOn(clearFriendsSearchBtn, 'click', () => {
            if (filterFriendsInput) {
                filterFriendsInput.value = '';
                filterFriendsInput.dispatchEvent(new Event('input'));
            }
        });
    }

    // Dashboard Tabs Binding
    document.querySelectorAll('.dash-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.dash-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const tabName = tab.dataset.tab;
            currentFriendTab = tabName;

            if (filterFriendsInput) {
                filterFriendsInput.value = '';
                if (clearFriendsSearchBtn) clearFriendsSearchBtn.style.display = 'none';
            }

            loadFriends();
        });
    });

    safeOn(document.getElementById('add-friend-btn'), 'click', () => {
        switchToHome();
        const addTab = document.querySelector('.dash-tab[data-tab="add"]');
        if (addTab) addTab.click();
    });

    // Add Friend Request Handler
    safeOn(document.getElementById('btn-send-friend-req'), 'click', async () => {
        const input = document.getElementById('add-friend-username-input');
        const errEl = document.getElementById('add-friend-error');
        const succEl = document.getElementById('add-friend-success');
        if (!input) return;

        const username = input.value.trim();
        if (!username) {
            if (errEl) errEl.textContent = 'Lütfen bir kullanıcı adı veya ID girin.';
            return;
        }

        if (errEl) errEl.textContent = '';
        if (succEl) succEl.style.display = 'none';

        try {
            const res = await fetch('/api/friends/request', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username })
            });
            const data = await res.json();
            if (data.success) {
                if (succEl) {
                    succEl.textContent = '✓ ' + (data.message || 'Arkadaşlık isteği başarıyla gönderildi!');
                    succEl.style.display = 'block';
                }
                input.value = '';
                showFloatingToast('✓ İstek gönderildi!');
                loadFriends();
                setTimeout(() => { if (succEl) succEl.style.display = 'none'; }, 3500);
            } else {
                if (errEl) errEl.textContent = data.message || 'İstek gönderilemedi.';
            }
        } catch (e) {
            if (errEl) errEl.textContent = 'Bağlantı hatası oluştu.';
        }
    });

    // Copy Invite
    safeOn(btnCopyInvite, 'click', () => {
        navigator.clipboard.writeText(currentServerInvite.textContent);
        btnCopyInvite.innerHTML = '<i data-lucide="check" class="icon-xs"></i>';
        renderLucideIcons();
        showFloatingToast("📋 Davet kodu kopyalandı!");
        setTimeout(() => {
            btnCopyInvite.innerHTML = '<i data-lucide="copy" class="icon-xs"></i>';
            renderLucideIcons();
        }, 2000);
    });

    // --- Server & Channel Creation Modals ---

    safeOn(addServerBtn, 'click', () => addServerModal.style.display = 'flex');

    safeOn(document.getElementById('tab-create-server'), 'click', () => {
        document.getElementById('tab-create-server').classList.add('active');
        document.getElementById('tab-join-server').classList.remove('active');
        document.getElementById('create-server-view').style.display = 'block';
        document.getElementById('join-server-view').style.display = 'none';
    });

    safeOn(document.getElementById('tab-join-server'), 'click', () => {
        document.getElementById('tab-join-server').classList.add('active');
        document.getElementById('tab-create-server').classList.remove('active');
        document.getElementById('join-server-view').style.display = 'block';
        document.getElementById('create-server-view').style.display = 'none';
    });

    safeOn(document.getElementById('submit-create-server-btn'), 'click', async () => {
        const name = document.getElementById('create-server-input').value.trim();
        if (!name) return;
        const res = await fetch('/api/servers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        const data = await res.json();
        if (data.success) {
            addServerModal.style.display = 'none';
            await loadServers();
            switchToServer(data.server.id, data.server.name);
            showFloatingToast(`🎉 "${data.server.name}" sunucusu oluşturuldu!`);
        } else {
            document.getElementById('create-server-msg').textContent = data.message;
        }
    });

    safeOn(document.getElementById('submit-join-server-btn'), 'click', async () => {
        const code = document.getElementById('join-server-input').value.trim();
        if (!code) return;
        const res = await fetch('/api/servers/join', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ invite_code: code })
        });
        const data = await res.json();
        if (data.success) {
            addServerModal.style.display = 'none';
            await loadServers();
            switchToServer(data.server.id, data.server.name);
            showFloatingToast(`🎉 "${data.server.name}" sunucusuna katıldınız!`);
        } else {
            document.getElementById('join-server-msg').textContent = data.message;
        }
    });

    // Create Channel Buttons
    safeOn(document.getElementById('add-channel-btn'), 'click', () => {
        addChannelModal.style.display = 'flex';
    });

    safeOn(document.getElementById('submit-create-channel-btn'), 'click', async () => {
        const name = document.getElementById('create-channel-input').value.trim();
        const type = document.getElementById('create-channel-type').value;
        if (!name || !currentServerId) return;

        const res = await fetch(`/api/servers/${currentServerId}/channels`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, type })
        });
        const data = await res.json();
        if (data.success) {
            addChannelModal.style.display = 'none';
            document.getElementById('create-channel-input').value = '';
            showFloatingToast(`✓ #${name} kanalı oluşturuldu!`);
            // Refresh channels
            const cRes = await fetch(`/api/servers/${currentServerId}/channels`);
            const cData = await cRes.json();
            const channelListEl = document.getElementById('channel-list');
            if (channelListEl) {
                channelListEl.innerHTML = '';
                cData.channels.forEach(ch => appendChannelToSidebar(ch));
            }
        } else {
            document.getElementById('create-channel-msg').textContent = data.message;
        }
    });

    // Close Modals
    document.querySelectorAll('.close-modal-btn, .modal-close-corner').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const overlay = e.target.closest('.modal-overlay');
            if (overlay) overlay.style.display = 'none';
        });
    });

    document.querySelectorAll('.modal-overlay').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.style.display = 'none';
            }
        });
    });

    window.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal-overlay').forEach(m => m.style.display = 'none');
            if (emojiPickerPopover) emojiPickerPopover.style.display = 'none';
        }
    });

    // --- WebRTC Real-Time Voice & Video ---

    let localStream = null;
    let screenStream = null;
    let isVideoOn = false;
    let isMicOn = true;
    let peerConnections = {};
    const rtcConfig = { 'iceServers': [{ 'urls': 'stun:stun.l.google.com:19302' }] };

    const localVideo = document.getElementById('local-video');
    const voiceGrid = document.getElementById('voice-grid');

    async function joinVoiceChannel(channelId, channelName) {
        currentVoiceChannelId = channelId;
        document.getElementById('voice-channel-name').textContent = channelName;

        mainChatArea.style.display = 'none';
        mainWhiteboardArea.style.display = 'none';
        mainVoiceArea.style.display = 'flex';

        try {
            localStream = await navigator.mediaDevices.getUserMedia({ video: isVideoOn, audio: isMicOn });
            localVideo.srcObject = localStream;
            socket.emit('join_voice', { channel_id: channelId });
            AudioEngine.playChime('join');

            // Speaking detector
            setupSpeakingDetector(localStream, (isSpeaking) => {
                const myTile = document.getElementById('participant-me');
                if (myTile) myTile.classList.toggle('speaking', isSpeaking);
                socket.emit('webrtc_speaking', { channel_id: channelId, is_speaking: isSpeaking });
            });

        } catch (err) {
            console.error('Media devices error:', err);
            showFloatingToast("Mic permissions needed for voice channel");
        }
    }

    function setupSpeakingDetector(stream, callback) {
        try {
            const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            const source = audioCtx.createMediaStreamSource(stream);
            const analyser = audioCtx.createAnalyser();
            analyser.fftSize = 512;
            source.connect(analyser);
            const dataArray = new Uint8Array(analyser.frequencyBinCount);

            setInterval(() => {
                analyser.getByteFrequencyData(dataArray);
                let sum = 0;
                for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
                const avg = sum / dataArray.length;
                callback(avg > 15);
            }, 200);
        } catch (e) { }
    }

    safeOn(document.getElementById('leave-voice-btn'), 'click', leaveVoiceChannel);

    function leaveVoiceChannel() {
        if (!currentVoiceChannelId) return;
        socket.emit('leave_voice', { channel_id: currentVoiceChannelId });
        for (let id in peerConnections) {
            peerConnections[id].close();
            const el = document.getElementById(`participant-${id}`);
            if (el) el.remove();
        }
        peerConnections = {};

        if (localStream) {
            localStream.getTracks().forEach(t => t.stop());
            localStream = null;
        }
        currentVoiceChannelId = null;
        mainVoiceArea.style.display = 'none';
        mainChatArea.style.display = 'flex';
    }

    safeOn(document.getElementById('toggle-mic-btn'), 'click', () => {
        if (!localStream) return;
        isMicOn = !isMicOn;
        localStream.getAudioTracks()[0].enabled = isMicOn;
        document.getElementById('toggle-mic-btn').classList.toggle('active', isMicOn);
    });

    safeOn(document.getElementById('toggle-video-btn'), 'click', async () => {
        isVideoOn = !isVideoOn;
        document.getElementById('toggle-video-btn').classList.toggle('active', isVideoOn);
        if (isVideoOn) {
            try {
                const vidStream = await navigator.mediaDevices.getUserMedia({ video: true });
                const track = vidStream.getVideoTracks()[0];
                localStream.addTrack(track);
                localVideo.srcObject = localStream;
            } catch (e) { isVideoOn = false; }
        } else {
            const track = localStream.getVideoTracks()[0];
            if (track) { track.stop(); localStream.removeTrack(track); }
        }
    });

    safeOn(document.getElementById('toggle-screen-btn'), 'click', async () => {
        try {
            if (!screenStream) {
                screenStream = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: 60 } });
                localVideo.srcObject = screenStream;
                document.getElementById('toggle-screen-btn').classList.add('active');
                screenStream.getVideoTracks()[0].onended = () => {
                    localVideo.srcObject = localStream;
                    screenStream = null;
                    document.getElementById('toggle-screen-btn').classList.remove('active');
                };
            } else {
                screenStream.getTracks().forEach(t => t.stop());
                screenStream = null;
                localVideo.srcObject = localStream;
                document.getElementById('toggle-screen-btn').classList.remove('active');
            }
        } catch (e) { console.warn(e); }
    });

    function createPeerConnection(targetId) {
        const pc = new RTCPeerConnection(rtcConfig);
        peerConnections[targetId] = pc;
        if (localStream) {
            localStream.getTracks().forEach(t => pc.addTrack(t, localStream));
        }
        pc.onicecandidate = (e) => {
            if (e.candidate) socket.emit('webrtc_ice_candidate', { target_id: targetId, candidate: e.candidate });
        };
        pc.ontrack = (e) => {
            let partDiv = document.getElementById(`participant-${targetId}`);
            if (!partDiv) {
                partDiv = document.createElement('div');
                partDiv.className = 'voice-participant';
                partDiv.id = `participant-${targetId}`;
                partDiv.innerHTML = `
                    <video autoplay playsinline></video>
                    <div class="participant-footer">
                        <span class="participant-name">User ${targetId}</span>
                    </div>
                `;
                voiceGrid.appendChild(partDiv);
            }
            partDiv.querySelector('video').srcObject = e.streams[0];
        };
        return pc;
    }

    async function handleUserJoinedVoice(data) {
        const pc = createPeerConnection(data.user_id);
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        socket.emit('webrtc_offer', { target_id: data.user_id, sdp: pc.localDescription });
    }

    async function handleWebrtcOffer(data) {
        const pc = createPeerConnection(data.sender_id);
        await pc.setRemoteDescription(new RTCSessionDescription(data.sdp));
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        socket.emit('webrtc_answer', { target_id: data.sender_id, sdp: pc.localDescription });
    }

    async function handleWebrtcAnswer(data) {
        const pc = peerConnections[data.sender_id];
        if (pc) await pc.setRemoteDescription(new RTCSessionDescription(data.sdp));
    }

    function handleWebrtcIceCandidate(data) {
        const pc = peerConnections[data.sender_id];
        if (pc) pc.addIceCandidate(new RTCIceCandidate(data.candidate)).catch(e => console.warn(e));
    }

    function handleUserLeftVoice(data) {
        const pc = peerConnections[data.user_id];
        if (pc) { pc.close(); delete peerConnections[data.user_id]; }
        const el = document.getElementById(`participant-${data.user_id}`);
        if (el) el.remove();
    }

    // --- Direct 1-on-1 Sesli Arama (Voice Calling) System ---

    function initDirectCallingHandlers() {
        // Direct call modal action buttons
        const btnAccept = document.getElementById('btn-incoming-call-accept');
        if (btnAccept) btnAccept.onclick = acceptIncomingCall;

        const btnDecline = document.getElementById('btn-incoming-call-decline');
        if (btnDecline) btnDecline.onclick = declineIncomingCall;

        const btnCancelOutgoing = document.getElementById('btn-outgoing-call-cancel');
        if (btnCancelOutgoing) btnCancelOutgoing.onclick = cancelOutgoingCall;

        const btnEndActive = document.getElementById('btn-active-call-end');
        if (btnEndActive) btnEndActive.onclick = () => endActiveCall(true);

        const btnActiveMic = document.getElementById('btn-active-call-mic');
        if (btnActiveMic) {
            btnActiveMic.onclick = () => {
                if (directCallState.localStream) {
                    const track = directCallState.localStream.getAudioTracks()[0];
                    if (track) {
                        track.enabled = !track.enabled;
                        directCallState.isMicMuted = !track.enabled;
                        btnActiveMic.classList.toggle('active', track.enabled);
                        AudioEngine.play(track.enabled ? 'mic_unmute' : 'mic_mute');
                        showFloatingToast(track.enabled ? "🎤 Mikrofon açıldı" : "🎤 Mikrofon susturuldu");
                    }
                }
            };
        }

        const btnActiveDeafen = document.getElementById('btn-active-call-deafen');
        if (btnActiveDeafen) {
            btnActiveDeafen.onclick = () => {
                if (directCallState.remoteAudio) {
                    directCallState.isDeafened = !directCallState.isDeafened;
                    directCallState.remoteAudio.muted = directCallState.isDeafened;
                    btnActiveDeafen.classList.toggle('active', !directCallState.isDeafened);
                    AudioEngine.play(directCallState.isDeafened ? 'deafen' : 'undeafen');
                    showFloatingToast(directCallState.isDeafened ? "🎧 Ses sağırlaştırıldı" : "🎧 Ses açıldı");
                }
            };
        }

        if (btnStartDmVoiceCall) {
            btnStartDmVoiceCall.onclick = () => {
                if (currentTargetId && currentTargetName) {
                    startVoiceCall(currentTargetId, currentTargetName, currentTargetColor);
                }
            };
        }
    }

    async function startVoiceCall(targetId, targetName, targetColor) {
        if (directCallState.active) {
            showFloatingToast("Zaten aktif bir görüşmedesiniz!");
            return;
        }
        if (currentVoiceChannelId) {
            leaveVoiceChannel();
        }

        directCallState.active = true;
        directCallState.isCaller = true;
        directCallState.peerId = targetId;
        directCallState.peerName = targetName;
        directCallState.peerColor = targetColor || '#8b5cf6';
        directCallState.seconds = 0;

        document.getElementById('outgoing-call-username').textContent = targetName;
        const av = document.getElementById('outgoing-call-avatar');
        av.textContent = targetName.charAt(0).toUpperCase();
        av.style.backgroundColor = targetColor || '#8b5cf6';
        document.getElementById('outgoing-call-status').textContent = 'Aranıyor...';
        outgoingCallModal.style.display = 'flex';

        AudioEngine.startOutgoingRing();
        socket.emit('call_user', { target_id: targetId, call_type: 'audio' });
    }

    function handleIncomingCall(data) {
        if (directCallState.active) {
            socket.emit('call_response', { caller_id: data.caller_id, accepted: false });
            return;
        }

        directCallState.active = true;
        directCallState.isCaller = false;
        directCallState.peerId = data.caller_id;
        directCallState.peerName = data.caller_name;
        directCallState.peerColor = data.caller_color || '#8b5cf6';
        directCallState.seconds = 0;

        document.getElementById('incoming-call-username').textContent = data.caller_name;
        const av = document.getElementById('incoming-call-avatar');
        av.textContent = (data.caller_avatar || data.caller_name.charAt(0)).toUpperCase();
        av.style.backgroundColor = data.caller_color || '#8b5cf6';
        document.getElementById('incoming-call-status').textContent = 'Gelen Sesli Arama...';
        incomingCallModal.style.display = 'flex';

        AudioEngine.startIncomingRing();
    }

    async function acceptIncomingCall() {
        AudioEngine.stopIncomingRing();
        incomingCallModal.style.display = 'none';

        try {
            directCallState.localStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (err) {
            console.warn('Microphone error:', err);
            showFloatingToast("Mikrofon erişimi gerekli!");
        }

        setupDirectPeerConnection();
        socket.emit('call_response', { caller_id: directCallState.peerId, accepted: true });
        startActiveCallUI();
        AudioEngine.play('call_connected');
    }

    function declineIncomingCall() {
        AudioEngine.stopIncomingRing();
        incomingCallModal.style.display = 'none';
        if (directCallState.peerId) {
            socket.emit('call_response', { caller_id: directCallState.peerId, accepted: false });
        }
        AudioEngine.play('call_ended');
        resetDirectCallState();
    }

    function cancelOutgoingCall() {
        AudioEngine.stopOutgoingRing();
        outgoingCallModal.style.display = 'none';
        if (directCallState.peerId) {
            socket.emit('call_end', { target_id: directCallState.peerId });
        }
        AudioEngine.play('call_ended');
        resetDirectCallState();
    }

    async function handleCallResponse(data) {
        AudioEngine.stopOutgoingRing();
        outgoingCallModal.style.display = 'none';

        if (data.accepted) {
            AudioEngine.play('call_connected');
            try {
                directCallState.localStream = await navigator.mediaDevices.getUserMedia({ audio: true });
            } catch (err) {
                console.warn('Microphone error:', err);
            }

            setupDirectPeerConnection();
            startActiveCallUI();

            if (directCallState.pc) {
                const offer = await directCallState.pc.createOffer();
                await directCallState.pc.setLocalDescription(offer);
                socket.emit('call_signal', {
                    target_id: data.receiver_id,
                    signal: { type: 'offer', sdp: directCallState.pc.localDescription }
                });
            }
        } else {
            AudioEngine.play('call_ended');
            showFloatingToast(`📞 @${directCallState.peerName} aramayı reddetti veya meşgul.`);
            resetDirectCallState();
        }
    }

    function setupDirectPeerConnection() {
        const pc = new RTCPeerConnection(rtcConfig);
        directCallState.pc = pc;

        if (directCallState.localStream) {
            directCallState.localStream.getTracks().forEach(t => pc.addTrack(t, directCallState.localStream));
        }

        pc.onicecandidate = (e) => {
            if (e.candidate && directCallState.peerId) {
                socket.emit('call_signal', {
                    target_id: directCallState.peerId,
                    signal: { type: 'candidate', candidate: e.candidate }
                });
            }
        };

        pc.ontrack = (e) => {
            if (!directCallState.remoteAudio) {
                directCallState.remoteAudio = new Audio();
                directCallState.remoteAudio.autoplay = true;
            }
            directCallState.remoteAudio.srcObject = e.streams[0];
        };

        if (directCallState.localStream) {
            setupSpeakingDetector(directCallState.localStream, (isSpeaking) => {
                socket.emit('webrtc_speaking', { target_id: directCallState.peerId, is_speaking: isSpeaking });
            });
        }
    }

    async function handleCallSignal(data) {
        if (!directCallState.pc) setupDirectPeerConnection();
        const pc = directCallState.pc;
        const sig = data.signal;

        if (sig.type === 'offer') {
            await pc.setRemoteDescription(new RTCSessionDescription(sig.sdp));
            const answer = await pc.createAnswer();
            await pc.setLocalDescription(answer);
            socket.emit('call_signal', {
                target_id: data.sender_id,
                signal: { type: 'answer', sdp: pc.localDescription }
            });
        } else if (sig.type === 'answer') {
            await pc.setRemoteDescription(new RTCSessionDescription(sig.sdp));
        } else if (sig.type === 'candidate' && sig.candidate) {
            pc.addIceCandidate(new RTCIceCandidate(sig.candidate)).catch(e => console.warn(e));
        }
    }

    function handleCallEnded(data) {
        showFloatingToast(`📞 Arama sonlandırıldı (@${data.by_username}).`);
        endActiveCall(false);
    }

    function endActiveCall(notifyPeer = true) {
        if (notifyPeer && directCallState.peerId) {
            socket.emit('call_end', { target_id: directCallState.peerId });
        }
        AudioEngine.stopIncomingRing();
        AudioEngine.stopOutgoingRing();
        AudioEngine.play('call_ended');
        resetDirectCallState();
    }

    function resetDirectCallState() {
        if (directCallState.timerInterval) {
            clearInterval(directCallState.timerInterval);
            directCallState.timerInterval = null;
        }
        if (directCallState.localStream) {
            directCallState.localStream.getTracks().forEach(t => t.stop());
            directCallState.localStream = null;
        }
        if (directCallState.pc) {
            directCallState.pc.close();
            directCallState.pc = null;
        }
        if (directCallState.remoteAudio) {
            directCallState.remoteAudio.pause();
            directCallState.remoteAudio.srcObject = null;
            directCallState.remoteAudio = null;
        }
        if (activeCallDock) activeCallDock.style.display = 'none';
        if (incomingCallModal) incomingCallModal.style.display = 'none';
        if (outgoingCallModal) outgoingCallModal.style.display = 'none';

        directCallState.active = false;
        directCallState.peerId = null;
        directCallState.peerName = null;
        directCallState.peerColor = null;
        directCallState.seconds = 0;
    }

    function startActiveCallUI() {
        if (activeCallDock) {
            document.getElementById('active-call-peer-name').textContent = `@${directCallState.peerName}`;
            document.getElementById('active-call-duration').textContent = '00:00';
            activeCallDock.style.display = 'flex';
        }
        directCallState.seconds = 0;
        if (directCallState.timerInterval) clearInterval(directCallState.timerInterval);
        directCallState.timerInterval = setInterval(() => {
            directCallState.seconds++;
            const mins = String(Math.floor(directCallState.seconds / 60)).padStart(2, '0');
            const secs = String(directCallState.seconds % 60).padStart(2, '0');
            const durEl = document.getElementById('active-call-duration');
            if (durEl) durEl.textContent = `${mins}:${secs}`;
        }, 1000);
    }

    // --- Web Speech API Sesli Arama & Dikte Engine ---

    function initVoiceRecognitionSystem() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

        const bindVoiceSearch = (btn, input, onDone, isDictate = false) => {
            if (!btn || !input) return;
            if (!SpeechRecognition) {
                btn.addEventListener('click', () => {
                    AudioEngine.play('error_buzzer');
                    showFloatingToast("Tarayıcınız Web Speech API sesli aramayı desteklemiyor.");
                });
                return;
            }

            let recognition = null;
            let isListening = false;

            btn.addEventListener('click', () => {
                if (isListening && recognition) {
                    recognition.stop();
                    return;
                }

                try {
                    recognition = new SpeechRecognition();
                    recognition.lang = 'tr-TR';
                    recognition.interimResults = false;
                    recognition.maxAlternatives = 1;

                    recognition.onstart = () => {
                        isListening = true;
                        btn.classList.add('listening');
                        AudioEngine.play('voice_search_start');
                        showFloatingToast("🎙️ Dinleniyor... Konuşun.");
                    };

                    recognition.onresult = (e) => {
                        const transcript = e.results[0][0].transcript;
                        if (isDictate) {
                            input.value = (input.value ? input.value + ' ' : '') + transcript;
                        } else {
                            input.value = transcript;
                        }
                        input.dispatchEvent(new Event('input'));
                        AudioEngine.play('voice_search_success');
                        if (onDone) onDone(transcript);
                    };

                    recognition.onerror = (e) => {
                        console.warn('Speech recognition error:', e);
                        isListening = false;
                        btn.classList.remove('listening');
                        AudioEngine.play('error_buzzer');
                    };

                    recognition.onend = () => {
                        isListening = false;
                        btn.classList.remove('listening');
                    };

                    recognition.start();
                } catch (err) {
                    console.warn('SpeechRecognition start error:', err);
                    isListening = false;
                    btn.classList.remove('listening');
                }
            });
        };

        const btnVoiceSearchChat = document.getElementById('btn-voice-search-chat');
        const btnVoiceSearchFriends = document.getElementById('btn-voice-search-friends');
        const btnVoiceSearchMembers = document.getElementById('btn-voice-search-members');
        const btnVoiceDictate = document.getElementById('btn-voice-dictate');

        if (btnVoiceSearchChat) {
            bindVoiceSearch(btnVoiceSearchChat, chatSearchInput, (txt) => {
                showFloatingToast(`🔍 Sesli arandı: "${txt}"`);
            });
        }

        if (btnVoiceSearchFriends) {
            bindVoiceSearch(btnVoiceSearchFriends, document.getElementById('filter-friends-input'), (txt) => {
                showFloatingToast(`👥 Arkadaş arandı: "${txt}"`);
            });
        }

        if (btnVoiceSearchMembers) {
            bindVoiceSearch(btnVoiceSearchMembers, document.getElementById('members-filter-input'), (txt) => {
                showFloatingToast(`👥 Üye arandı: "${txt}"`);
            });
        }

        if (btnVoiceDictate) {
            bindVoiceSearch(btnVoiceDictate, messageInput, (txt) => {
                showFloatingToast(`🗣️ Dikte eklendi: "${txt}"`);
            }, true);
        }
    }

    // --- Quick Action Buttons & Status Toggles ---

    function initQuickButtonListeners() {
        const btnQuickAi = document.getElementById('btn-quick-ai-prompt');
        if (btnQuickAi) {
            safeOn(btnQuickAi, 'click', () => {
                messageInput.value = '@ai ';
                messageInput.focus();
            });
        }

        const btnQuickAddFriend = document.getElementById('btn-quick-add-friend');
        if (btnQuickAddFriend) {
            safeOn(btnQuickAddFriend, 'click', () => {
                switchToHome();
                const addTab = document.getElementById('tab-add-friend');
                if (addTab) addTab.click();
            });
        }

        const serverSettingsBtn = document.getElementById('server-settings-btn');
        if (serverSettingsBtn) {
            serverSettingsBtn.addEventListener('click', () => {
                if (currentServerInvite && currentServerInvite.textContent) {
                    navigator.clipboard.writeText(currentServerInvite.textContent);
                    showFloatingToast(`📋 Sunucu davet kodu kopyalandı: ${currentServerInvite.textContent}`);
                } else {
                    showFloatingToast("Sunucu ayarları");
                }
            });
        }

        const userMicToggle = document.getElementById('user-mic-toggle');
        if (userMicToggle) {
            safeOn(userMicToggle, 'click', () => {
                globalMicMuted = !globalMicMuted;
                userMicToggle.classList.toggle('active', !globalMicMuted);
                AudioEngine.play(globalMicMuted ? 'mic_mute' : 'mic_unmute');
                showFloatingToast(globalMicMuted ? "🎤 Mikrofon kapatıldı" : "🎤 Mikrofon açıldı");
            });
        }

        const userDeafenToggle = document.getElementById('user-deafen-toggle');
        if (userDeafenToggle) {
            safeOn(userDeafenToggle, 'click', () => {
                globalDeafened = !globalDeafened;
                userDeafenToggle.classList.toggle('active', !globalDeafened);
                AudioEngine.play(globalDeafened ? 'deafen' : 'undeafen');
                showFloatingToast(globalDeafened ? "🎧 Kulaklık sağırlaştırıldı" : "🎧 Kulaklık sesi açıldı");
            });
        }

        const btnToggleMembers = document.getElementById('btn-toggle-members');
        if (btnToggleMembers) {
            safeOn(btnToggleMembers, 'click', () => {
                const actSidebar = document.getElementById('activity-sidebar');
                if (actSidebar) {
                    const isHidden = actSidebar.style.display === 'none';
                    actSidebar.style.display = isHidden ? 'flex' : 'none';
                    showFloatingToast(isHidden ? "👥 Üye listesi açıldı" : "👥 Üye listesi gizlendi");
                }
            });
        }

        const btnOpenWhiteboard = document.getElementById('btn-open-whiteboard');
        if (btnOpenWhiteboard) {
            safeOn(btnOpenWhiteboard, 'click', () => {
                mainChatArea.style.display = 'none';
                mainVoiceArea.style.display = 'none';
                mainWhiteboardArea.style.display = 'flex';
                initCollaborativeCanvas();
            });
        }
    }

    // --- Floating Toast Notifications ---
    function showFloatingToast(msg) {
        const toast = document.createElement('div');
        toast.style.cssText = `
            position: fixed;
            bottom: 24px;
            right: 24px;
            padding: 10px 18px;
            background: rgba(18, 24, 38, 0.95);
            border: 1px solid var(--primary);
            border-radius: 12px;
            color: #fff;
            font-size: 13px;
            font-weight: 600;
            box-shadow: 0 10px 30px var(--primary-glow);
            z-index: 9999;
            animation: fadeIn 0.2s ease;
        `;
        toast.textContent = msg;
        document.body.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    // Helpers
    function escapeHTML(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
});

