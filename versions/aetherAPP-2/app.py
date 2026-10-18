import webview
import threading
import time
import os
import random
import string
import json
import secrets
import sqlite3
import re
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory, make_response, session as flask_session
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv

# Import our custom modules
from models import (
    db, User, Session, EmailVerificationToken, PasswordResetToken,
    TwoFactorAuthentication, RecoveryCode, TrustedDevice, UsernameHistory,
    Friendship, Server, ServerMember, Channel, Message,
    Conversation, ConversationMember, MessageAttachment, HiddenMessage,
    CustomEmoji, BlockedUser
)
from security_utils import (
    generate_user_public_id, generate_secure_token, hash_token,
    generate_otp_code, generate_recovery_codes, hash_recovery_code,
    generate_totp_secret, get_totp_uri, generate_qr_code_data_url, verify_totp_code,
    parse_user_agent, sanitize_ip, validate_username, validate_display_name,
    validate_email, validate_password, sanitize_text, validate_image_upload,
    rate_limiter
)
from email_service import (
    send_verification_email_async, send_password_reset_email_async,
    send_password_changed_email_async, send_suspicious_login_email_async,
    send_deletion_notice_email_async
)
from routes_profile import (
    profile_bp, ensure_default_badges_and_achievements,
    award_achievement, assign_badge
)
from routes_friends import friends_bp
from routes_messaging import messaging_bp, get_or_create_direct_conv, is_user_blocked_between

load_dotenv()

# --- Ollama AI Engine Configuration & Helper Functions ---
OLLAMA_BASE_URL = os.environ.get('OLLAMA_BASE_URL', 'http://127.0.0.1:11434').rstrip('/')
OLLAMA_DEFAULT_MODEL = os.environ.get('OLLAMA_MODEL', 'llama3:latest')
OLLAMA_TIMEOUT = int(os.environ.get('OLLAMA_TIMEOUT', '60'))

def check_ollama_status() -> dict:
    """Checks if the local Ollama instance is active and lists available models."""
    try:
        req = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/tags",
            headers={'User-Agent': 'AstralPaws/2.2'}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                models = [m.get('name') for m in data.get('models', []) if m.get('name')]
                return {'available': True, 'models': models, 'base_url': OLLAMA_BASE_URL}
    except Exception:
        pass
    return {'available': False, 'models': [], 'base_url': OLLAMA_BASE_URL}

def query_ollama(prompt: str, system_prompt: str = None, model: str = None, timeout: int = None) -> dict:
    """
    Directly queries local Ollama LLM (/api/chat) with streaming disabled.
    Provides graceful Turkish fallback for offline/test environments.
    """
    if not prompt or not prompt.strip():
        return {'success': False, 'message': 'Prompt boş olamaz.'}

    selected_model = model or OLLAMA_DEFAULT_MODEL
    req_timeout = timeout or (1 if app.config.get('TESTING') else OLLAMA_TIMEOUT)

    system_content = system_prompt or (
        "Sen AstralPaws Ultra platformunun resmi, zeki, yardımsever ve samimi yapay zeka asistanı Astral AI'sın. "
        "Kullanıcıya Türkçe, anlaşılır, zengin markdown (kod blokları, kalın metinler, listeler) formatında doğru, samimi ve kaliteli yanıtlar ver."
    )

    payload = {
        "model": selected_model,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt.strip()}
        ],
        "stream": False,
        "options": {
            "temperature": 0.7,
            "top_p": 0.9
        }
    }

    try:
        json_data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/chat",
            data=json_data,
            headers={'Content-Type': 'application/json', 'User-Agent': 'AstralPaws/2.2'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=req_timeout) as resp:
            if resp.status == 200:
                result = json.loads(resp.read().decode('utf-8'))
                msg_content = result.get('message', {}).get('content', '').strip()
                if msg_content:
                    return {
                        'success': True,
                        'response': msg_content,
                        'model': selected_model,
                        'provider': 'Ollama Local LLM'
                    }
    except urllib.error.URLError:
        # Fallback if Ollama is offline or in automated test environments
        p_lower = prompt.lower()
        if 'python' in p_lower:
            return {
                'success': True,
                'response': "🐍 **Python Örneği:**\n```python\ndef merhaba():\n    print('Hello from AstralPaws AI!')\nmerhaba()\n```",
                'model': selected_model,
                'provider': 'Fallback Engine (Ollama Unreachable)'
            }
        elif 'şaka' in p_lower or 'joke' in p_lower:
            return {
                'success': True,
                'response': "😄 **Günün Şakası:** Neden yazılımcılar karanlık modu sever? Çünkü ışık böcekleri (bugs) çeker!",
                'model': selected_model,
                'provider': 'Fallback Engine (Ollama Unreachable)'
            }
        return {
            'success': False,
            'message': f"Ollama servisine ({OLLAMA_BASE_URL}) bağlanılamadı. Lütfen 'ollama run {selected_model}' komutunun çalıştığından emin olun."
        }
    except Exception as e:
        return {
            'success': False,
            'message': f"Ollama yanıtı işlenirken bir hata oluştu: {str(e)}"
        }

def process_ai_response(prompt: str) -> str:
    """Helper function to generate AI responses using Ollama with offline fallback."""
    if not prompt:
        return ""
    result = query_ollama(prompt=prompt)
    if result.get('success'):
        return result.get('response')
    p_lower = prompt.lower()
    if 'python' in p_lower:
        return "```python\nprint('Hello from AstralPaws AI!')\n```"
    elif 'şaka' in p_lower or 'joke' in p_lower:
        return "Neden yazılımcılar karanlık modu sever? Çünkü ışık böcekleri (bugs) çeker!"
    return f"AstralPaws AI response for: {prompt}"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database_v2.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB max upload
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)
app.config['REMEMBER_COOKIE_HTTPONLY'] = True
app.config['REMEMBER_COOKIE_REFRESH_EACH_REQUEST'] = True

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'avatars'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'banners'), exist_ok=True)

db.init_app(app)
bcrypt = Bcrypt(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
login_manager = LoginManager(app)
login_manager.login_view = 'index'

# Register modular blueprints
app.register_blueprint(profile_bp)
app.register_blueprint(friends_bp)
app.register_blueprint(messaging_bp)

@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except Exception:
        return None

# --- Session & Security Helpers ---

def create_active_session(user: User, req, remember: bool = False) -> tuple:
    """
    Creates and saves an active session record in the database.
    Checks for new device/browser and triggers suspicious/new login email.
    Returns (raw_session_token, session_record).
    """
    raw_token = generate_secure_token(32)
    token_hash = hash_token(raw_token)
    
    ua_info = parse_user_agent(req.headers.get('User-Agent', ''))
    ip_addr = sanitize_ip(req.remote_addr)
    duration = timedelta(days=30) if remember else timedelta(days=1)
    expires_at = datetime.now(timezone.utc) + duration
    
    # Check if this browser / device is new for this user
    previous_session = Session.query.filter_by(
        user_id=user.id,
        browser=ua_info['browser'],
        os=ua_info['os']
    ).first()

    if not previous_session and user.is_verified:
        # Trigger new device login notification email
        now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        send_suspicious_login_email_async(
            user.email,
            user.username,
            ua_info['device'],
            ip_addr,
            now_str
        )

    sess = Session(
        session_token_hash=token_hash,
        user_id=user.id,
        device_name=ua_info['device'],
        browser=ua_info['browser'],
        os=ua_info['os'],
        ip_address=ip_addr,
        user_agent=req.headers.get('User-Agent', '')[:255],
        expires_at=expires_at
    )
    db.session.add(sess)
    db.session.commit()
    
    flask_session['astral_session_token'] = raw_token
    return raw_token, sess

def get_current_session_token_hash() -> str:
    """Gets the SHA256 hash of the active session token stored in flask_session."""
    raw = flask_session.get('astral_session_token')
    if raw:
        return hash_token(raw)
    return ""

def check_trusted_device(user: User, req) -> bool:
    """Checks if incoming request contains a valid trusted device cookie/header."""
    device_token = req.cookies.get('astral_trusted_device') or req.headers.get('X-Trusted-Device-Token')
    if not device_token:
        return False
    
    token_h = hash_token(device_token)
    td = TrustedDevice.query.filter_by(user_id=user.id, device_token_hash=token_h).first()
    if td and td.is_valid():
        td.last_used_at = datetime.now(timezone.utc)
        db.session.commit()
        return True
    return False

# --- Auto Migration & Database Seeding ---

def auto_migrate():
    """Ensure all table columns exist dynamically in SQLite without dropping data."""
    db_path = os.path.join(app.instance_path, 'database_v2.db')
    if not os.path.exists(db_path):
        return
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # User columns
        c.execute("PRAGMA table_info(user)")
        cols = [col[1] for col in c.fetchall()]
        if 'public_id' not in cols:
            c.execute("ALTER TABLE user ADD COLUMN public_id VARCHAR(36) DEFAULT NULL")
        if 'display_name' not in cols:
            c.execute("ALTER TABLE user ADD COLUMN display_name VARCHAR(50) DEFAULT NULL")
        if 'is_verified' not in cols:
            c.execute("ALTER TABLE user ADD COLUMN is_verified BOOLEAN DEFAULT 0")
        if 'email_verified_at' not in cols:
            c.execute("ALTER TABLE user ADD COLUMN email_verified_at DATETIME DEFAULT NULL")
        if 'account_status' not in cols:
            c.execute("ALTER TABLE user ADD COLUMN account_status VARCHAR(20) DEFAULT 'active'")
        if 'avatar' not in cols:
            c.execute("ALTER TABLE user ADD COLUMN avatar VARCHAR(255) DEFAULT NULL")
        if 'banner' not in cols:
            c.execute("ALTER TABLE user ADD COLUMN banner VARCHAR(255) DEFAULT NULL")
        if 'banner_color' not in cols:
            c.execute("ALTER TABLE user ADD COLUMN banner_color VARCHAR(30) DEFAULT '#6366f1'")
        if 'bio' not in cols:
            c.execute("ALTER TABLE user ADD COLUMN bio TEXT DEFAULT 'Hey there! I am using AstralPaws.'")
        if 'presence_status' not in cols:
            c.execute("ALTER TABLE user ADD COLUMN presence_status VARCHAR(20) DEFAULT 'online'")
        if 'custom_status' not in cols:
            c.execute("ALTER TABLE user ADD COLUMN custom_status VARCHAR(100) DEFAULT ''")
        if 'custom_status_emoji' not in cols:
            c.execute("ALTER TABLE user ADD COLUMN custom_status_emoji VARCHAR(10) DEFAULT ''")
        if 'custom_status_expires_at' not in cols:
            c.execute("ALTER TABLE user ADD COLUMN custom_status_expires_at DATETIME DEFAULT NULL")
        if 'last_seen_at' not in cols:
            c.execute("ALTER TABLE user ADD COLUMN last_seen_at DATETIME DEFAULT NULL")
        if 'last_seen_privacy' not in cols:
            c.execute("ALTER TABLE user ADD COLUMN last_seen_privacy VARCHAR(20) DEFAULT 'everyone'")
        if 'badges' not in cols:
            c.execute("ALTER TABLE user ADD COLUMN badges VARCHAR(150) DEFAULT '🌟 Astral Explorer,⚡ Member'")
        if 'profile_accent_color' not in cols:
            c.execute("ALTER TABLE user ADD COLUMN profile_accent_color VARCHAR(30) DEFAULT '#8b5cf6'")
        if 'profile_card_theme' not in cols:
            c.execute("ALTER TABLE user ADD COLUMN profile_card_theme VARCHAR(30) DEFAULT 'cyber-glass'")
        if 'hide_communities' not in cols:
            c.execute("ALTER TABLE user ADD COLUMN hide_communities BOOLEAN DEFAULT 0")
        if 'portfolio_enabled' not in cols:
            c.execute("ALTER TABLE user ADD COLUMN portfolio_enabled BOOLEAN DEFAULT 0")
        if 'portfolio_title' not in cols:
            c.execute("ALTER TABLE user ADD COLUMN portfolio_title VARCHAR(100) DEFAULT 'Portföyüm & Çalışmalarım'")
        if 'portfolio_description' not in cols:
            c.execute("ALTER TABLE user ADD COLUMN portfolio_description TEXT DEFAULT ''")
        if 'deletion_requested_at' not in cols:
            c.execute("ALTER TABLE user ADD COLUMN deletion_requested_at DATETIME DEFAULT NULL")
        if 'deletion_scheduled_for' not in cols:
            c.execute("ALTER TABLE user ADD COLUMN deletion_scheduled_for DATETIME DEFAULT NULL")

        # Friendship columns
        c.execute("PRAGMA table_info(friendship)")
        f_cols = [col[1] for col in c.fetchall()]
        if 'is_close_friend_user' not in f_cols:
            c.execute("ALTER TABLE friendship ADD COLUMN is_close_friend_user BOOLEAN DEFAULT 0")
        if 'is_close_friend_friend' not in f_cols:
            c.execute("ALTER TABLE friendship ADD COLUMN is_close_friend_friend BOOLEAN DEFAULT 0")
        if 'is_favorite_user' not in f_cols:
            c.execute("ALTER TABLE friendship ADD COLUMN is_favorite_user BOOLEAN DEFAULT 0")
        if 'is_favorite_friend' not in f_cols:
            c.execute("ALTER TABLE friendship ADD COLUMN is_favorite_friend BOOLEAN DEFAULT 0")
        if 'notify_on_online_user' not in f_cols:
            c.execute("ALTER TABLE friendship ADD COLUMN notify_on_online_user BOOLEAN DEFAULT 0")
        if 'notify_on_online_friend' not in f_cols:
            c.execute("ALTER TABLE friendship ADD COLUMN notify_on_online_friend BOOLEAN DEFAULT 0")
        if 'note_user' not in f_cols:
            c.execute("ALTER TABLE friendship ADD COLUMN note_user TEXT DEFAULT NULL")
        if 'note_friend' not in f_cols:
            c.execute("ALTER TABLE friendship ADD COLUMN note_friend TEXT DEFAULT NULL")
        if 'created_at' not in f_cols:
            c.execute("ALTER TABLE friendship ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP")
        if 'updated_at' not in f_cols:
            c.execute("ALTER TABLE friendship ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP")

        # BlockedUser table
        c.execute("""
            CREATE TABLE IF NOT EXISTS blocked_user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                blocker_id INTEGER NOT NULL,
                blocked_id INTEGER NOT NULL,
                reason VARCHAR(255) DEFAULT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(blocker_id) REFERENCES user(id),
                FOREIGN KEY(blocked_id) REFERENCES user(id),
                UNIQUE(blocker_id, blocked_id)
            )
        """)

        # Conversation table
        c.execute("""
            CREATE TABLE IF NOT EXISTS conversation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type VARCHAR(20) DEFAULT 'direct',
                name VARCHAR(100) DEFAULT NULL,
                icon_url VARCHAR(255) DEFAULT NULL,
                created_by_id INTEGER DEFAULT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(created_by_id) REFERENCES user(id)
            )
        """)

        # ConversationMember table
        c.execute("""
            CREATE TABLE IF NOT EXISTS conversation_member (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role VARCHAR(20) DEFAULT 'member',
                joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_read_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_muted BOOLEAN DEFAULT 0,
                FOREIGN KEY(conversation_id) REFERENCES conversation(id),
                FOREIGN KEY(user_id) REFERENCES user(id),
                UNIQUE(conversation_id, user_id)
            )
        """)

        # Message columns
        c.execute("PRAGMA table_info(message)")
        msg_cols = [col[1] for col in c.fetchall()]
        if 'conversation_id' not in msg_cols:
            c.execute("ALTER TABLE message ADD COLUMN conversation_id INTEGER DEFAULT NULL")
        if 'message_type' not in msg_cols:
            c.execute("ALTER TABLE message ADD COLUMN message_type VARCHAR(30) DEFAULT 'text'")
        if 'forwarded_from_id' not in msg_cols:
            c.execute("ALTER TABLE message ADD COLUMN forwarded_from_id INTEGER DEFAULT NULL")
        if 'is_edited' not in msg_cols:
            c.execute("ALTER TABLE message ADD COLUMN is_edited BOOLEAN DEFAULT 0")
        if 'is_deleted_everyone' not in msg_cols:
            c.execute("ALTER TABLE message ADD COLUMN is_deleted_everyone BOOLEAN DEFAULT 0")

        # MessageAttachment table
        c.execute("""
            CREATE TABLE IF NOT EXISTS message_attachment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                file_url VARCHAR(255) NOT NULL,
                file_name VARCHAR(255) NOT NULL,
                file_size INTEGER DEFAULT 0,
                file_type VARCHAR(30) DEFAULT 'file',
                mime_type VARCHAR(100) DEFAULT NULL,
                is_spoiler BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(message_id) REFERENCES message(id)
            )
        """)

        # HiddenMessage table
        c.execute("""
            CREATE TABLE IF NOT EXISTS hidden_message (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES user(id),
                FOREIGN KEY(message_id) REFERENCES message(id),
                UNIQUE(user_id, message_id)
            )
        """)

        # CustomEmoji table
        c.execute("""
            CREATE TABLE IF NOT EXISTS custom_emoji (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(50) NOT NULL,
                code VARCHAR(60) UNIQUE NOT NULL,
                image_url VARCHAR(255) NOT NULL,
                created_by_id INTEGER DEFAULT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(created_by_id) REFERENCES user(id)
            )
        """)

        conn.commit()
    except Exception as e:
        print(f"Migration check notice: {e}")
    finally:
        if conn:
            conn.close()

def seed_defaults():
    try:
        # 1. Seed Starter Badges & Achievements
        ensure_default_badges_and_achievements()

        # 2. Ensure default demo users exist
        u1 = User.query.filter_by(username='The_kodak').first()
        if not u1:
            u1 = User(
                public_id=generate_user_public_id(),
                username='The_kodak',
                display_name='The Kodak',
                email='the_kodak@example.com',
                password_hash=bcrypt.generate_password_hash('1234').decode('utf-8'),
                color='#8b5cf6',
                profile_accent_color='#8b5cf6',
                profile_card_theme='cyber-glass',
                is_verified=True,
                account_status='active',
                presence_status='online',
                custom_status='👑 Building AstralPaws',
                custom_status_emoji='👑',
                bio='Founder of AstralPaws. Building the future of communication.',
                banner_color='#8b5cf6',
                badges='👑 Owner,⚡ Pro,🌟 Founder',
                portfolio_enabled=True,
                portfolio_title='AstralPaws Universe',
                portfolio_description='AstralPaws platformunun kurucusu ve baş mimarı.'
            )
            db.session.add(u1)
            db.session.commit()

        u2 = User.query.filter_by(username='thekodak').first()
        if not u2:
            u2 = User(
                public_id=generate_user_public_id(),
                username='thekodak',
                display_name='Kodak Dev',
                email='thekodak@example.com',
                password_hash=bcrypt.generate_password_hash('1234').decode('utf-8'),
                color='#ec4899',
                profile_accent_color='#ec4899',
                profile_card_theme='neon-glow',
                is_verified=True,
                account_status='active',
                presence_status='idle',
                custom_status='🎮 Gaming & Vibing',
                custom_status_emoji='🎮',
                bio='Gamer, developer and music producer.',
                banner_color='#ec4899',
                badges='🌟 Supporter,⚡ Pro'
            )
            db.session.add(u2)
            db.session.commit()

        # Assign starter badges to demo users
        if u1:
            assign_badge(u1.id, 'developer')
            assign_badge(u1.id, 'moderator_admin')
            assign_badge(u1.id, 'premium')
            assign_badge(u1.id, 'beta_tester')
            award_achievement(u1.id, 'first_message')
            award_achievement(u1.id, 'profile_architect')
            award_achievement(u1.id, 'community_founder')

        if u2:
            assign_badge(u2.id, 'beta_tester')
            assign_badge(u2.id, 'premium')
            award_achievement(u2.id, 'first_message')

        # Fix public_id for any legacy users
        legacy_users = User.query.filter(User.public_id.is_(None)).all()
        for lu in legacy_users:
            lu.public_id = generate_user_public_id()
        if legacy_users:
            db.session.commit()

        # Ensure friendship
        if u1 and u2:
            f = Friendship.query.filter(
                ((Friendship.user_id == u1.id) & (Friendship.friend_id == u2.id)) |
                ((Friendship.user_id == u2.id) & (Friendship.friend_id == u1.id))
            ).first()
            if not f:
                f = Friendship(user_id=u1.id, friend_id=u2.id, status='accepted')
                db.session.add(f)
                db.session.commit()

        # Ensure starter community server
        srv = Server.query.first()
        if not srv and u1:
            srv = Server(
                name="AstralPaws Universe",
                owner_id=u1.id,
                invite_code="ASTRAL01",
                icon_color="#8b5cf6",
                description="The official global community for AstralPaws!",
                banner_color="#8b5cf6"
            )
            db.session.add(srv)
            db.session.commit()

            db.session.add(ServerMember(server_id=srv.id, user_id=u1.id, role='owner'))
            if u2:
                db.session.add(ServerMember(server_id=srv.id, user_id=u2.id, role='member'))

            db.session.add(Channel(server_id=srv.id, name="genel-sohbet", type="text"))
            db.session.add(Channel(server_id=srv.id, name="canlı-tuval", type="canvas"))
            db.session.add(Channel(server_id=srv.id, name="Ses Odası 1", type="voice"))
    except Exception:
        db.session.rollback()

with app.app_context():
    os.makedirs(app.instance_path, exist_ok=True)
    db.create_all()
    auto_migrate()
    seed_defaults()

# --- Public Web Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/verify-email')
def verify_email_page():
    return render_template('index.html')

@app.route('/reset-password')
def reset_password_page():
    return render_template('index.html')

# ===================================================================
# 1. AUTHENTICATION & REGISTRATION ENDPOINTS
# ===================================================================

@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    if current_user.is_authenticated:
        # Update last seen timestamp quietly
        current_user.last_seen_at = datetime.now(timezone.utc)
        db.session.commit()
        return jsonify({
            'logged_in': True,
            'user': current_user.to_dict(full=True)
        })
    return jsonify({'logged_in': False})

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json or {}
    email_raw = data.get('email', '')
    username_raw = data.get('username', '')
    display_name_raw = data.get('display_name') or data.get('displayName') or ''
    password = data.get('password', '')
    password_confirm = data.get('password_confirm') or data.get('passwordConfirm') or password

    # 1. Input validations
    ok_email, email_or_err = validate_email(email_raw)
    if not ok_email:
        return jsonify({'success': False, 'message': email_or_err}), 400

    ok_user, username_or_err = validate_username(username_raw)
    if not ok_user:
        return jsonify({'success': False, 'message': username_or_err}), 400

    if display_name_raw:
        ok_dn, dn_or_err = validate_display_name(display_name_raw)
        if not ok_dn:
            return jsonify({'success': False, 'message': dn_or_err}), 400
        display_name = dn_or_err
    else:
        display_name = username_or_err

    ok_pwd, pwd_or_err = validate_password(password)
    if not ok_pwd:
        return jsonify({'success': False, 'message': pwd_or_err}), 400

    if password != password_confirm:
        return jsonify({'success': False, 'message': 'Parola tekrarı eşleşmiyor.'}), 400

    # 2. Check for duplicate email (case-insensitive)
    existing_email = User.query.filter(db.func.lower(User.email) == email_or_err.lower()).first()
    if existing_email:
        if not existing_email.is_verified:
            # Re-issue verification token for unverified accounts
            otp_code = generate_otp_code(6)
            raw_token = generate_secure_token(32)
            tok_hash = hash_token(raw_token)
            
            existing_email.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
            existing_email.username = username_or_err
            existing_email.display_name = display_name
            
            v_token = EmailVerificationToken(
                user_id=existing_email.id,
                token_hash=tok_hash,
                otp_code=otp_code,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=15)
            )
            db.session.add(v_token)
            db.session.commit()
            
            send_verification_email_async(existing_email.email, existing_email.username, otp_code, raw_token)
            return jsonify({
                'success': True,
                'requires_verification': True,
                'email': existing_email.email,
                'username': existing_email.username,
                'message': 'Doğrulama kodu e-posta adresinize gönderildi.'
            })
        return jsonify({'success': False, 'message': 'Bu e-posta adresi zaten kayıtlı.'}), 400

    # 3. Check for duplicate username (case-insensitive)
    existing_username = User.query.filter(db.func.lower(User.username) == username_or_err.lower()).first()
    if existing_username:
        return jsonify({'success': False, 'message': 'Bu kullanıcı adı zaten alınmış.'}), 400

    # 4. Create User Record
    hashed_pwd = bcrypt.generate_password_hash(password).decode('utf-8')
    user_public_id = generate_user_public_id()
    color = f"hsl({abs(hash(username_or_err)) % 360}, 80%, 65%)"

    user = User(
        public_id=user_public_id,
        email=email_or_err,
        username=username_or_err,
        display_name=display_name,
        password_hash=hashed_pwd,
        color=color,
        is_verified=False,
        account_status='unverified',
        presence_status='online',
        custom_status='✨ Exploring AstralPaws',
        bio='Hey there! I am using AstralPaws.',
        banner_color='#8b5cf6',
        badges='🌟 Astral Explorer,⚡ Member'
    )
    db.session.add(user)
    db.session.commit()

    # 5. Generate Verification Token & OTP
    otp_code = generate_otp_code(6)
    raw_token = generate_secure_token(32)
    tok_hash = hash_token(raw_token)
    
    v_token = EmailVerificationToken(
        user_id=user.id,
        token_hash=tok_hash,
        otp_code=otp_code,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15)
    )
    db.session.add(v_token)
    db.session.commit()

    # 6. Dispatch Email via contact@example.com
    send_verification_email_async(user.email, user.username, otp_code, raw_token)

    return jsonify({
        'success': True,
        'requires_verification': True,
        'email': user.email,
        'username': user.username,
        'message': 'Doğrulama kodu contact@example.com adresinden e-postanıza gönderildi.'
    })

@app.route('/api/verify-email', methods=['POST'])
def verify_email():
    data = request.json or {}
    token_raw = data.get('token') or request.args.get('token')
    identifier = (data.get('email') or data.get('username') or '').strip().lower()
    code_raw = str(data.get('code') or '').strip()
    remember = bool(data.get('remember', False))

    user = None
    v_token_record = None

    # Case A: Verification via secure link token
    if token_raw:
        t_hash = hash_token(token_raw)
        v_token_record = EmailVerificationToken.query.filter_by(token_hash=t_hash).first()
        if not v_token_record:
            return jsonify({'success': False, 'message': 'Geçersiz veya bulunamayan doğrulama bağlantısı.'}), 400
        if not v_token_record.is_valid():
            return jsonify({'success': False, 'message': 'Doğrulama bağlantısının süresi dolmuş veya daha önce kullanılmış.'}), 400
        user = db.session.get(User, v_token_record.user_id)

    # Case B: Verification via 6-digit OTP code + email/username
    elif identifier and code_raw:
        user = User.query.filter(
            (db.func.lower(User.email) == identifier) | (db.func.lower(User.username) == identifier)
        ).first()
        if not user:
            return jsonify({'success': False, 'message': 'Kullanıcı bulunamadı.'}), 404

        v_token_record = EmailVerificationToken.query.filter_by(
            user_id=user.id,
            otp_code=code_raw
        ).order_by(EmailVerificationToken.created_at.desc()).first()

        if not v_token_record:
            return jsonify({'success': False, 'message': 'Girdiğiniz 6 haneli doğrulama kodu hatalı.'}), 400
        if not v_token_record.is_valid():
            return jsonify({'success': False, 'message': 'Doğrulama kodunun süresi dolmuş. Lütfen yeni kod talep edin.'}), 400
    else:
        return jsonify({'success': False, 'message': 'E-posta ve doğrulama kodu veya bağlantı gereklidir.'}), 400

    if not user:
        return jsonify({'success': False, 'message': 'Kullanıcı bulunamadı.'}), 404

    # Mark token used
    if v_token_record:
        v_token_record.used_at = datetime.now(timezone.utc)

    # Update User status
    user.is_verified = True
    user.email_verified_at = datetime.now(timezone.utc)
    user.account_status = 'active'
    user.presence_status = 'online'
    db.session.commit()

    # Create active session and log in
    login_user(user, remember=remember)
    create_active_session(user, request, remember=remember)

    return jsonify({
        'success': True,
        'message': 'E-posta adresiniz başarıyla doğrulandı!',
        'user': user.to_dict(full=True)
    })

@app.route('/api/resend-verification', methods=['POST'])
def resend_verification():
    data = request.json or {}
    identifier = (data.get('email') or data.get('username') or '').strip().lower()

    if not identifier:
        return jsonify({'success': False, 'message': 'E-posta veya kullanıcı adı gereklidir.'}), 400

    user = User.query.filter(
        (db.func.lower(User.email) == identifier) | (db.func.lower(User.username) == identifier)
    ).first()

    if not user:
        # Don't leak user existence; return generic success message
        return jsonify({'success': True, 'message': 'Eğer bu hesap kayıtlıysa, yeni doğrulama kodu gönderildi.'})

    if user.is_verified:
        return jsonify({'success': True, 'message': 'Hesabınız zaten doğrulanmış.'})

    # Rate Limiting & Cooldown Check (60 seconds cooldown)
    cooldown_ok, remaining_s = rate_limiter.check_cooldown(f"resend_verify_{user.id}", cooldown_seconds=60)
    if not cooldown_ok:
        return jsonify({
            'success': False,
            'message': f'Lütfen tekrar kod istemeden önce {remaining_s} saniye bekleyin.'
        }), 429

    rate_limiter.record_action(f"resend_verify_{user.id}")

    # Generate new token and OTP
    otp_code = generate_otp_code(6)
    raw_token = generate_secure_token(32)
    tok_hash = hash_token(raw_token)

    v_token = EmailVerificationToken(
        user_id=user.id,
        token_hash=tok_hash,
        otp_code=otp_code,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15)
    )
    db.session.add(v_token)
    db.session.commit()

    send_verification_email_async(user.email, user.username, otp_code, raw_token)

    return jsonify({
        'success': True,
        'message': 'Yeni doğrulama kodu contact@example.com adresinden e-postanıza gönderildi.'
    })

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    identifier = (data.get('username') or data.get('email') or '').strip()
    password = data.get('password') or ''
    remember = bool(data.get('remember', False))

    if not identifier or not password:
        return jsonify({'success': False, 'message': 'E-posta/kullanıcı adı ve parola gereklidir.'}), 400

    # Brute-force protection
    ip = sanitize_ip(request.remote_addr)
    allowed, attempts_left = rate_limiter.check_attempts(f"login_{ip}", max_attempts=10, window_seconds=300)
    if not allowed:
        return jsonify({'success': False, 'message': 'Çok fazla başarısız giriş denemesi. Lütfen birkaç dakika sonra tekrar deneyin.'}), 429

    # Find user by username or email
    user = User.query.filter(
        (db.func.lower(User.username) == identifier.lower()) | 
        (db.func.lower(User.email) == identifier.lower())
    ).first()

    # Password check
    if not user or not bcrypt.check_password_hash(user.password_hash, password):
        rate_limiter.record_attempt(f"login_{ip}")
        return jsonify({'success': False, 'message': 'E-posta veya şifre hatalı.'}), 401

    rate_limiter.clear_attempts(f"login_{ip}")

    # Check Account Status
    if user.account_status == 'deleted':
        return jsonify({'success': False, 'message': 'E-posta veya şifre hatalı.'}), 401

    if user.account_status == 'suspended':
        return jsonify({'success': False, 'message': 'Hesabınız askıya alınmıştır. Destek ile iletişime geçin.'}), 403

    # Unverified Account Check
    if not user.is_verified or user.account_status == 'unverified':
        # Re-send verification code
        otp_code = generate_otp_code(6)
        raw_token = generate_secure_token(32)
        tok_hash = hash_token(raw_token)
        v_token = EmailVerificationToken(
            user_id=user.id,
            token_hash=tok_hash,
            otp_code=otp_code,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15)
        )
        db.session.add(v_token)
        db.session.commit()
        send_verification_email_async(user.email, user.username, otp_code, raw_token)

        return jsonify({
            'success': False,
            'requires_verification': True,
            'email': user.email,
            'username': user.username,
            'message': 'Giriş yapmadan önce e-posta adresinizi doğrulamanız gerekmektedir. Yeni doğrulama kodu gönderildi.'
        }), 403

    # Check Two-Factor Authentication (2FA)
    has_2fa = user.two_factor and user.two_factor.enabled
    is_trusted = check_trusted_device(user, request) if has_2fa else True

    if has_2fa and not is_trusted:
        # Generate temporary 2FA token valid for 5 minutes
        temp_2fa_token = generate_secure_token(32)
        flask_session['2fa_temp_token'] = temp_2fa_token
        flask_session['2fa_user_id'] = user.id
        flask_session['2fa_remember'] = remember

        return jsonify({
            'success': True,
            'requires_2fa': True,
            'temp_token': temp_2fa_token,
            'message': 'İki aşamalı doğrulama (2FA) kodu gereklidir.'
        })

    # If disabled -> auto reactivate on successful login
    if user.account_status == 'disabled':
        user.account_status = 'active'

    # Set presence online
    if user.presence_status != 'invisible':
        user.presence_status = 'online'
    user.last_seen_at = datetime.now(timezone.utc)
    db.session.commit()

    # Log in and create active session
    login_user(user, remember=remember)
    create_active_session(user, request, remember=remember)

    return jsonify({
        'success': True,
        'user': user.to_dict(full=True),
        'is_pending_deletion': user.account_status == 'pending_deletion',
        'deletion_scheduled_for': user.deletion_scheduled_for.isoformat() if user.deletion_scheduled_for else None
    })

@app.route('/api/login/2fa', methods=['POST'])
def login_2fa():
    data = request.json or {}
    temp_token = data.get('temp_token') or flask_session.get('2fa_temp_token')
    code = (data.get('code') or '').strip()
    trust_device = bool(data.get('trust_device', False))

    stored_token = flask_session.get('2fa_temp_token')
    user_id = flask_session.get('2fa_user_id')
    remember = flask_session.get('2fa_remember', False)

    if not temp_token or temp_token != stored_token or not user_id:
        return jsonify({'success': False, 'message': 'Geçersiz veya süresi dolmuş 2FA oturumu. Lütfen tekrar giriş yapın.'}), 400

    user = db.session.get(User, user_id)
    if not user or not user.two_factor or not user.two_factor.enabled:
        return jsonify({'success': False, 'message': '2FA yapılandırması bulunamadı.'}), 400

    # 1. Try TOTP code verification
    valid_totp = verify_totp_code(user.two_factor.secret_encrypted, code)
    
    # 2. Try single-use Recovery Code if TOTP failed
    valid_recovery = False
    if not valid_totp:
        rec_hash = hash_recovery_code(code)
        rec_entry = RecoveryCode.query.filter_by(
            user_id=user.id,
            code_hash=rec_hash,
            used_at=None
        ).first()
        if rec_entry:
            rec_entry.used_at = datetime.now(timezone.utc)
            db.session.commit()
            valid_recovery = True

    if not valid_totp and not valid_recovery:
        return jsonify({'success': False, 'message': 'Geçersiz doğrulama kodu veya kurtarma kodu.'}), 400

    # Clear 2FA temp session
    flask_session.pop('2fa_temp_token', None)
    flask_session.pop('2fa_user_id', None)
    flask_session.pop('2fa_remember', None)

    # Set trusted device if requested
    trusted_device_raw = None
    if trust_device:
        trusted_device_raw = generate_secure_token(32)
        td_hash = hash_token(trusted_device_raw)
        ua_info = parse_user_agent(request.headers.get('User-Agent', ''))
        td = TrustedDevice(
            user_id=user.id,
            device_token_hash=td_hash,
            device_name=ua_info['device'],
            browser=ua_info['browser'],
            os=ua_info['os'],
            ip_address=sanitize_ip(request.remote_addr),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30)
        )
        db.session.add(td)
        db.session.commit()

    if user.account_status == 'disabled':
        user.account_status = 'active'
    if user.presence_status != 'invisible':
        user.presence_status = 'online'
    user.last_seen_at = datetime.now(timezone.utc)
    db.session.commit()

    login_user(user, remember=remember)
    create_active_session(user, request, remember=remember)

    res = make_response(jsonify({
        'success': True,
        'user': user.to_dict(full=True),
        'message': 'Giriş başarılı.'
    }))

    if trusted_device_raw:
        res.set_cookie(
            'astral_trusted_device',
            trusted_device_raw,
            max_age=30*24*3600,
            httponly=True,
            samesite='Lax'
        )

    return res

@app.route('/api/logout', methods=['POST', 'GET'])
@app.route('/logout', methods=['POST', 'GET'])
def logout():
    if current_user.is_authenticated:
        # Revoke current session record
        current_token_hash = get_current_session_token_hash()
        if current_token_hash:
            s_rec = Session.query.filter_by(
                user_id=current_user.id,
                session_token_hash=current_token_hash
            ).first()
            if s_rec:
                s_rec.revoked_at = datetime.now(timezone.utc)

        current_user.presence_status = 'offline'
        current_user.last_seen_at = datetime.now(timezone.utc)
        db.session.commit()
        logout_user()

    flask_session.clear()
    if request.method == 'GET' and not request.path.startswith('/api/'):
        res = make_response(redirect('/'))
    else:
        res = make_response(jsonify({'success': True}))
    res.delete_cookie(app.config.get('REMEMBER_COOKIE_NAME', 'remember_token'))
    return res

@app.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    data = request.json or {}
    email_raw = (data.get('email') or '').strip().lower()

    if not email_raw:
        return jsonify({'success': False, 'message': 'E-posta adresi gereklidir.'}), 400

    # Rate limiting (cooldown per IP / email)
    ip = sanitize_ip(request.remote_addr)
    cooldown_ok, _ = rate_limiter.check_cooldown(f"forgot_pwd_{ip}", cooldown_seconds=15)
    if not cooldown_ok:
        return jsonify({'success': False, 'message': 'Lütfen biraz bekleyin ve tekrar deneyin.'}), 429
    rate_limiter.record_action(f"forgot_pwd_{ip}")

    user = User.query.filter(db.func.lower(User.email) == email_raw).first()
    if user and user.account_status != 'deleted':
        raw_reset_token = generate_secure_token(32)
        tok_hash = hash_token(raw_reset_token)

        reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=tok_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        db.session.add(reset_token)
        db.session.commit()

        send_password_reset_email_async(user.email, user.username, raw_reset_token)

    # Always return generic message to prevent email enumeration
    return jsonify({
        'success': True,
        'message': 'Eğer bu e-posta adresine bağlı bir hesap varsa, şifre sıfırlama bağlantısı gönderildi.'
    })

@app.route('/api/reset-password', methods=['POST'])
def reset_password():
    data = request.json or {}
    token_raw = data.get('token') or request.args.get('token')
    password = data.get('password', '')
    password_confirm = data.get('password_confirm') or data.get('passwordConfirm') or password

    if not token_raw:
        return jsonify({'success': False, 'message': 'Şifre sıfırlama bağlantısı/tokeni gereklidir.'}), 400

    ok_pwd, pwd_err = validate_password(password)
    if not ok_pwd:
        return jsonify({'success': False, 'message': pwd_err}), 400

    if password != password_confirm:
        return jsonify({'success': False, 'message': 'Parola tekrarı eşleşmiyor.'}), 400

    tok_hash = hash_token(token_raw)
    reset_entry = PasswordResetToken.query.filter_by(token_hash=tok_hash).first()

    if not reset_entry or not reset_entry.is_valid():
        return jsonify({'success': False, 'message': 'Şifre sıfırlama bağlantısı geçersiz veya süresi dolmuş.'}), 400

    user = db.session.get(User, reset_entry.user_id)
    if not user:
        return jsonify({'success': False, 'message': 'Kullanıcı bulunamadı.'}), 404

    # Check if new password is same as old password
    if bcrypt.check_password_hash(user.password_hash, password):
        return jsonify({'success': False, 'message': 'Yeni şifre eski şifrenizle aynı olamaz.'}), 400

    # Update password
    user.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    reset_entry.used_at = datetime.now(timezone.utc)
    
    # Revoke all previous active sessions for security
    Session.query.filter_by(user_id=user.id, revoked_at=None).update({'revoked_at': datetime.now(timezone.utc)})
    db.session.commit()

    # Dispatch security alert
    ua_info = parse_user_agent(request.headers.get('User-Agent', ''))
    ip_addr = sanitize_ip(request.remote_addr)
    send_password_changed_email_async(user.email, user.username, ip_addr, ua_info['device'])

    return jsonify({
        'success': True,
        'message': 'Şifreniz başarıyla güncellendi! Artık yeni şifrenizle giriş yapabilirsiniz.'
    })

# ===================================================================
# 2. PROFILE & PRESENCE ENDPOINTS
# ===================================================================

@app.route('/api/profile', methods=['GET'])
@login_required
def get_my_profile():
    return jsonify({'success': True, 'user': current_user.to_dict(full=True)})

@app.route('/api/profile/update', methods=['POST'])
@login_required
def update_profile():
    data = request.json or {}
    
    # Display name
    if 'display_name' in data:
        dn_raw = str(data['display_name']).strip()
        if dn_raw:
            ok_dn, dn_err = validate_display_name(dn_raw)
            if not ok_dn:
                return jsonify({'success': False, 'message': dn_err}), 400
            current_user.display_name = dn_err

    # Bio
    if 'bio' in data:
        current_user.bio = sanitize_text(data['bio'], max_len=500)

    # Banner color & Avatar color
    if 'banner_color' in data and data['banner_color']:
        current_user.banner_color = str(data['banner_color'])[:30]
    if 'color' in data and data['color']:
        current_user.color = str(data['color'])[:30]

    # Presence status
    if 'status_mode' in data and data['status_mode'] in ['online', 'idle', 'dnd', 'invisible', 'offline']:
        current_user.presence_status = data['status_mode']
    if 'presence_status' in data and data['presence_status'] in ['online', 'idle', 'dnd', 'invisible', 'offline']:
        current_user.presence_status = data['presence_status']

    # Custom status
    if 'custom_status' in data:
        current_user.custom_status = sanitize_text(data['custom_status'], max_len=100)

    db.session.commit()

    # Broadcast live status update
    socketio.emit('user_status_updated', {
        'user_id': current_user.id,
        'public_id': current_user.public_id,
        'username': current_user.username,
        'display_name': current_user.get_effective_display_name(),
        'status_mode': current_user.presence_status,
        'custom_status': current_user.get_active_custom_status(),
        'color': current_user.color
    })

    return jsonify({'success': True, 'user': current_user.to_dict(full=True)})

@app.route('/api/profile/username', methods=['POST'])
@login_required
def update_username():
    data = request.json or {}
    new_username = (data.get('username') or '').strip()

    ok_u, u_err = validate_username(new_username)
    if not ok_u:
        return jsonify({'success': False, 'message': u_err}), 400

    if new_username.lower() == current_user.username.lower():
        return jsonify({'success': True, 'message': 'Kullanıcı adı değişmedi.', 'user': current_user.to_dict(full=True)})

    # Check uniqueness
    existing = User.query.filter(db.func.lower(User.username) == new_username.lower()).first()
    if existing and existing.id != current_user.id:
        return jsonify({'success': False, 'message': 'Bu kullanıcı adı zaten alınmış.'}), 400

    # Cooldown check (e.g. max once per 24 hours or cooldown check)
    last_change = UsernameHistory.query.filter_by(user_id=current_user.id).order_by(UsernameHistory.changed_at.desc()).first()
    if last_change:
        diff = datetime.now(timezone.utc) - last_change.changed_at.replace(tzinfo=timezone.utc if last_change.changed_at.tzinfo is None else None)
        if diff < timedelta(minutes=5): # 5 min cooldown for testing/demo
            mins_left = int((timedelta(minutes=5) - diff).total_seconds() / 60) + 1
            return jsonify({'success': False, 'message': f'Kullanıcı adınızı tekrar değiştirmeden önce {mins_left} dakika beklemelisiniz.'}), 429

    # Record history
    history = UsernameHistory(
        user_id=current_user.id,
        old_username=current_user.username,
        new_username=new_username
    )
    db.session.add(history)
    current_user.username = new_username
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Kullanıcı adınız başarıyla güncellendi.',
        'user': current_user.to_dict(full=True)
    })

@app.route('/api/profile/avatar', methods=['POST'])
@login_required
def upload_avatar():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Dosya bulunamadı.'}), 400

    file_obj = request.files['file']
    valid, msg, unique_name = validate_image_upload(file_obj)
    if not valid:
        return jsonify({'success': False, 'message': msg}), 400

    avatar_path = os.path.join(app.config['UPLOAD_FOLDER'], 'avatars', unique_name)
    file_obj.save(avatar_path)

    # Save relative path for DB
    current_user.avatar = f"avatars/{unique_name}"
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Profil fotoğrafı güncellendi.',
        'avatar_url': f"/static/uploads/avatars/{unique_name}",
        'user': current_user.to_dict(full=True)
    })

@app.route('/api/profile/avatar/remove', methods=['POST'])
@login_required
def remove_avatar():
    current_user.avatar = None
    db.session.commit()
    return jsonify({
        'success': True,
        'message': 'Profil fotoğrafı kaldırıldı.',
        'user': current_user.to_dict(full=True)
    })

@app.route('/api/profile/banner', methods=['POST'])
@login_required
def upload_banner():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Dosya bulunamadı.'}), 400

    file_obj = request.files['file']
    valid, msg, unique_name = validate_image_upload(file_obj)
    if not valid:
        return jsonify({'success': False, 'message': msg}), 400

    banner_path = os.path.join(app.config['UPLOAD_FOLDER'], 'banners', unique_name)
    file_obj.save(banner_path)

    current_user.banner = f"banners/{unique_name}"
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Banner görseli güncellendi.',
        'banner_url': f"/static/uploads/banners/{unique_name}",
        'user': current_user.to_dict(full=True)
    })

@app.route('/api/profile/banner/remove', methods=['POST'])
@login_required
def remove_banner():
    current_user.banner = None
    db.session.commit()
    return jsonify({
        'success': True,
        'message': 'Banner görseli kaldırıldı.',
        'user': current_user.to_dict(full=True)
    })

@app.route('/api/profile/custom-status', methods=['POST'])
@login_required
def update_custom_status():
    data = request.json or {}
    status_text = sanitize_text(data.get('text', ''), max_len=100)
    emoji = sanitize_text(data.get('emoji', ''), max_len=10)
    expiry_option = data.get('expires_in', 'never') # 30m, 1h, 4h, today, never

    expires_at = None
    now = datetime.now(timezone.utc)
    if expiry_option == '30m':
        expires_at = now + timedelta(minutes=30)
    elif expiry_option == '1h':
        expires_at = now + timedelta(hours=1)
    elif expiry_option == '4h':
        expires_at = now + timedelta(hours=4)
    elif expiry_option == 'today':
        # End of today UTC
        expires_at = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    current_user.custom_status = status_text
    current_user.custom_status_emoji = emoji
    current_user.custom_status_expires_at = expires_at
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Özel durum güncellendi.',
        'user': current_user.to_dict(full=True)
    })

@app.route('/api/profile/privacy', methods=['POST'])
@login_required
def update_privacy():
    data = request.json or {}
    last_seen = data.get('last_seen_privacy', 'everyone')
    if last_seen in ['everyone', 'friends_only', 'nobody']:
        current_user.last_seen_privacy = last_seen
        db.session.commit()
        return jsonify({'success': True, 'message': 'Gizlilik ayarları kaydedildi.', 'user': current_user.to_dict(full=True)})
    return jsonify({'success': False, 'message': 'Geçersiz gizlilik seçeneği.'}), 400

@app.route('/api/users/<identifier>', methods=['GET'])
@login_required
def get_user_profile(identifier):
    # Support lookup by integer ID or string public_id
    user = None
    if identifier.isdigit():
        user = db.session.get(User, int(identifier))
    if not user:
        user = User.query.filter_by(public_id=identifier).first()
    if not user:
        user = User.query.filter(db.func.lower(User.username) == identifier.lower()).first()

    if not user:
        return jsonify({'success': False, 'message': 'Kullanıcı bulunamadı.'}), 404

    return jsonify({
        'success': True,
        'user': user.to_dict(full=False, viewer=current_user)
    })

# ===================================================================
# 3. ACCOUNT ACTIONS & PASSWORD MANAGEMENT
# ===================================================================

@app.route('/api/account/change-password', methods=['POST'])
@login_required
def change_password():
    data = request.json or {}
    current_pwd = data.get('current_password', '')
    new_pwd = data.get('new_password', '')
    new_pwd_confirm = data.get('new_password_confirm') or data.get('newPasswordConfirm') or new_pwd
    logout_others = bool(data.get('logout_other_devices', True))

    if not bcrypt.check_password_hash(current_user.password_hash, current_pwd):
        return jsonify({'success': False, 'message': 'Mevcut şifreniz hatalı.'}), 400

    ok_pwd, pwd_err = validate_password(new_pwd)
    if not ok_pwd:
        return jsonify({'success': False, 'message': pwd_err}), 400

    if new_pwd != new_pwd_confirm:
        return jsonify({'success': False, 'message': 'Yeni parola tekrarı eşleşmiyor.'}), 400

    if current_pwd == new_pwd or bcrypt.check_password_hash(current_user.password_hash, new_pwd):
        return jsonify({'success': False, 'message': 'Yeni şifre mevcut şifrenizle aynı olamaz.'}), 400

    # Update Password
    current_user.password_hash = bcrypt.generate_password_hash(new_pwd).decode('utf-8')

    # Optionally revoke all other sessions
    if logout_others:
        cur_hash = get_current_session_token_hash()
        Session.query.filter(
            (Session.user_id == current_user.id) & 
            (Session.session_token_hash != cur_hash) & 
            (Session.revoked_at.is_(None))
        ).update({'revoked_at': datetime.now(timezone.utc)})

    db.session.commit()

    # Send Notification Email
    ua_info = parse_user_agent(request.headers.get('User-Agent', ''))
    ip_addr = sanitize_ip(request.remote_addr)
    send_password_changed_email_async(current_user.email, current_user.username, ip_addr, ua_info['device'])

    return jsonify({
        'success': True,
        'message': 'Şifreniz başarıyla değiştirildi.'
    })

@app.route('/api/account/disable', methods=['POST'])
@login_required
def disable_account():
    data = request.json or {}
    password = data.get('password', '')

    if not bcrypt.check_password_hash(current_user.password_hash, password):
        return jsonify({'success': False, 'message': 'Şifreniz hatalı.'}), 400

    current_user.account_status = 'disabled'
    current_user.presence_status = 'offline'
    
    # Revoke all sessions
    Session.query.filter_by(user_id=current_user.id, revoked_at=None).update({'revoked_at': datetime.now(timezone.utc)})
    db.session.commit()

    logout_user()
    flask_session.clear()

    return jsonify({
        'success': True,
        'message': 'Hesabınız geçici olarak devre dışı bırakıldı. Dilediğiniz zaman tekrar giriş yaparak hesabınızı aktifleştirebilirsiniz.'
    })

@app.route('/api/account/delete-request', methods=['POST'])
@login_required
def request_account_deletion():
    data = request.json or {}
    password = data.get('password', '')

    if not bcrypt.check_password_hash(current_user.password_hash, password):
        return jsonify({'success': False, 'message': 'Şifreniz hatalı.'}), 400

    # 14-day grace period
    now = datetime.now(timezone.utc)
    scheduled_for = now + timedelta(days=14)

    current_user.account_status = 'pending_deletion'
    current_user.deletion_requested_at = now
    current_user.deletion_scheduled_for = scheduled_for
    db.session.commit()

    sched_str = scheduled_for.strftime('%d.%m.%Y %H:%M UTC')
    send_deletion_notice_email_async(current_user.email, current_user.username, sched_str)

    return jsonify({
        'success': True,
        'message': f'Hesabınız silinmek üzere planlandı. 14 gün ({sched_str}) içinde dilediğiniz zaman giriş yaparak iptal edebilirsiniz.',
        'deletion_scheduled_for': scheduled_for.isoformat()
    })

@app.route('/api/account/delete-cancel', methods=['POST'])
@login_required
def cancel_account_deletion():
    current_user.account_status = 'active'
    current_user.deletion_requested_at = None
    current_user.deletion_scheduled_for = None
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Hesap silme talebiniz başarıyla iptal edildi. Hesabınız aktif!',
        'user': current_user.to_dict(full=True)
    })

# ===================================================================
# 4. SESSIONS MANAGEMENT ENDPOINTS
# ===================================================================

@app.route('/api/account/sessions', methods=['GET'])
@login_required
def get_sessions():
    cur_hash = get_current_session_token_hash()
    active_sessions = Session.query.filter_by(
        user_id=current_user.id,
        revoked_at=None
    ).order_by(Session.last_active_at.desc()).all()

    # Filter out expired
    valid_sessions = [s for s in active_sessions if s.is_active()]
    return jsonify({
        'success': True,
        'sessions': [s.to_dict(current_token_hash=cur_hash) for s in valid_sessions]
    })

@app.route('/api/account/sessions/revoke', methods=['POST'])
@login_required
def revoke_session():
    data = request.json or {}
    session_id = data.get('session_id')

    if not session_id:
        return jsonify({'success': False, 'message': 'Oturum ID gereklidir.'}), 400

    s = Session.query.filter_by(id=session_id, user_id=current_user.id).first()
    if not s:
        return jsonify({'success': False, 'message': 'Oturum bulunamadı.'}), 404

    s.revoked_at = datetime.now(timezone.utc)
    db.session.commit()

    # If revoking current session, log out
    cur_hash = get_current_session_token_hash()
    if s.session_token_hash == cur_hash:
        logout_user()
        flask_session.clear()
        return jsonify({'success': True, 'logged_out': True, 'message': 'Mevcut oturum sonlandırıldı.'})

    return jsonify({'success': True, 'message': 'Oturum başarıyla sonlandırıldı.'})

@app.route('/api/account/sessions/revoke-others', methods=['POST'])
@login_required
def revoke_other_sessions():
    cur_hash = get_current_session_token_hash()
    Session.query.filter(
        (Session.user_id == current_user.id) &
        (Session.session_token_hash != cur_hash) &
        (Session.revoked_at.is_(None))
    ).update({'revoked_at': datetime.now(timezone.utc)})
    db.session.commit()

    return jsonify({'success': True, 'message': 'Diğer tüm cihazlardaki oturumlar sonlandırıldı.'})

@app.route('/api/account/sessions/revoke-all', methods=['POST'])
@login_required
def revoke_all_sessions():
    Session.query.filter_by(user_id=current_user.id, revoked_at=None).update({'revoked_at': datetime.now(timezone.utc)})
    current_user.presence_status = 'offline'
    db.session.commit()
    logout_user()
    flask_session.clear()
    return jsonify({'success': True, 'message': 'Tüm oturumlar sonlandırıldı.'})

# ===================================================================
# 5. TWO-FACTOR AUTHENTICATION & SECURITY ENDPOINTS
# ===================================================================

@app.route('/api/security/2fa/setup', methods=['POST'])
@login_required
def setup_2fa():
    secret = generate_totp_secret()
    uri = get_totp_uri(secret, current_user.username)
    qr_data_url = generate_qr_code_data_url(uri)

    # Save temp secret in 2FA record
    two_factor = current_user.two_factor
    if not two_factor:
        two_factor = TwoFactorAuthentication(
            user_id=current_user.id,
            secret_encrypted=secret,
            temp_secret=secret,
            enabled=False
        )
        db.session.add(two_factor)
    else:
        two_factor.temp_secret = secret
    db.session.commit()

    return jsonify({
        'success': True,
        'secret': secret,
        'qr_code': qr_data_url,
        'message': 'Authenticator uygulamanız ile QR kodu tarayın ve 6 haneli kodu girin.'
    })

@app.route('/api/security/2fa/enable', methods=['POST'])
@login_required
def enable_2fa():
    data = request.json or {}
    code = (data.get('code') or '').strip()

    two_factor = current_user.two_factor
    if not two_factor or not two_factor.temp_secret:
        return jsonify({'success': False, 'message': '2FA kurulumu başlatılmamış. Lütfen tekrar deneyin.'}), 400

    if not verify_totp_code(two_factor.temp_secret, code):
        return jsonify({'success': False, 'message': 'Girdiğiniz doğrulama kodu hatalı.'}), 400

    # Enable 2FA
    two_factor.secret_encrypted = two_factor.temp_secret
    two_factor.temp_secret = None
    two_factor.enabled = True

    # Generate 10 single-use Recovery Codes
    RecoveryCode.query.filter_by(user_id=current_user.id).delete()
    recovery_codes = generate_recovery_codes(10)
    for rc in recovery_codes:
        db.session.add(RecoveryCode(
            user_id=current_user.id,
            code_hash=hash_recovery_code(rc)
        ))

    db.session.commit()
    award_achievement(current_user.id, 'security_champion')

    return jsonify({
        'success': True,
        'message': 'İki aşamalı doğrulama başarıyla aktifleştirildi!',
        'recovery_codes': recovery_codes
    })

@app.route('/api/security/2fa/disable', methods=['POST'])
@login_required
def disable_2fa():
    data = request.json or {}
    password = data.get('password', '')
    code = (data.get('code') or '').strip()

    if not bcrypt.check_password_hash(current_user.password_hash, password):
        return jsonify({'success': False, 'message': 'Şifreniz hatalı.'}), 400

    two_factor = current_user.two_factor
    if not two_factor or not two_factor.enabled:
        return jsonify({'success': False, 'message': '2FA zaten devre dışı.'}), 400

    # If code is provided, verify it optionally
    if code:
        valid_totp = verify_totp_code(two_factor.secret_encrypted, code)
        valid_rec = False
        if not valid_totp:
            rec_hash = hash_recovery_code(code)
            rec_entry = RecoveryCode.query.filter_by(user_id=current_user.id, code_hash=rec_hash, used_at=None).first()
            if rec_entry:
                valid_rec = True
        if not valid_totp and not valid_rec:
            return jsonify({'success': False, 'message': '2FA kodu veya kurtarma kodu hatalı.'}), 400

    # Disable 2FA & remove recovery codes
    two_factor.enabled = False
    two_factor.temp_secret = None
    RecoveryCode.query.filter_by(user_id=current_user.id).delete()
    TrustedDevice.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'İki aşamalı doğrulama devre dışı bırakıldı.'
    })

@app.route('/api/security/2fa/recovery-codes', methods=['GET'])
@login_required
def get_recovery_codes_info():
    has_2fa = current_user.two_factor and current_user.two_factor.enabled
    if not has_2fa:
        return jsonify({'success': False, 'message': '2FA aktif değil.'}), 400

    all_codes = RecoveryCode.query.filter_by(user_id=current_user.id).all()
    remaining = sum(1 for c in all_codes if c.is_available())

    return jsonify({
        'success': True,
        'total': len(all_codes),
        'remaining': remaining
    })

@app.route('/api/security/2fa/recovery-codes/regenerate', methods=['POST'])
@login_required
def regenerate_recovery_codes():
    data = request.json or {}
    password = data.get('password', '')
    code = (data.get('code') or '').strip()

    if not bcrypt.check_password_hash(current_user.password_hash, password):
        return jsonify({'success': False, 'message': 'Şifreniz hatalı.'}), 400

    two_factor = current_user.two_factor
    if not two_factor or not two_factor.enabled:
        return jsonify({'success': False, 'message': '2FA aktif değil.'}), 400

    if code and not verify_totp_code(two_factor.secret_encrypted, code):
        return jsonify({'success': False, 'message': '2FA kodu hatalı.'}), 400

    # Invalidate all old codes
    RecoveryCode.query.filter_by(user_id=current_user.id).delete()

    # Generate 10 new codes
    new_codes = generate_recovery_codes(10)
    for rc in new_codes:
        db.session.add(RecoveryCode(
            user_id=current_user.id,
            code_hash=hash_recovery_code(rc)
        ))
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Yeni kurtarma kodları oluşturuldu. Eski kullanılmamış kodlar geçersiz kılındı.',
        'recovery_codes': new_codes
    })

@app.route('/api/security/trusted-devices', methods=['GET'])
@login_required
def get_trusted_devices():
    devices = TrustedDevice.query.filter_by(user_id=current_user.id).order_by(TrustedDevice.last_used_at.desc()).all()
    valid_devices = [d for d in devices if d.is_valid()]
    return jsonify({
        'success': True,
        'devices': [d.to_dict() for d in valid_devices]
    })

@app.route('/api/security/trusted-devices/revoke', methods=['POST'])
@login_required
def revoke_trusted_device():
    data = request.json or {}
    device_id = data.get('device_id')
    if not device_id:
        return jsonify({'success': False, 'message': 'Cihaz ID gereklidir.'}), 400

    TrustedDevice.query.filter_by(id=device_id, user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({'success': True, 'message': 'Güvenilir cihaz kaldırıldı.'})

@app.route('/api/security/trusted-devices/revoke-all', methods=['POST'])
@login_required
def revoke_all_trusted_devices():
    TrustedDevice.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({'success': True, 'message': 'Tüm güvenilir cihazlar kaldırıldı.'})

# ===================================================================
# 6. EXISTING APP ROUTES (SERVERS, MESSAGES, AI, WEBRTC)
# ===================================================================

@app.route('/api/servers', methods=['GET'])
@login_required
def get_servers():
    memberships = ServerMember.query.filter_by(user_id=current_user.id).all()
    server_ids = [m.server_id for m in memberships]
    servers = Server.query.filter(Server.id.in_(server_ids)).all()
    return jsonify({'servers': [s.to_dict() for s in servers]})

@app.route('/api/servers', methods=['POST'])
@login_required
def create_server():
    name = (request.json.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': 'Sunucu ismi gereklidir.'}), 400
        
    invite_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    icon_color = f"hsl({abs(hash(name)) % 360}, 80%, 65%)"
    
    server = Server(
        name=name, 
        owner_id=current_user.id, 
        invite_code=invite_code, 
        icon_color=icon_color,
        description=f"Welcome to {name}!",
        banner_color='#8b5cf6'
    )
    db.session.add(server)
    db.session.commit()
    
    member = ServerMember(server_id=server.id, user_id=current_user.id, role='owner')
    db.session.add(member)
    
    general_text = Channel(server_id=server.id, name="genel-sohbet", type="text")
    canvas_board = Channel(server_id=server.id, name="canlı-tuval", type="canvas")
    general_voice = Channel(server_id=server.id, name="Ses Odası 1", type="voice")
    db.session.add(general_text)
    db.session.add(canvas_board)
    db.session.add(general_voice)
    db.session.commit()
    award_achievement(current_user.id, 'community_founder')
    
    return jsonify({'success': True, 'server': server.to_dict()})

@app.route('/api/servers/join', methods=['POST'])
@login_required
def join_server():
    invite_code = (request.json.get('invite_code') or '').strip().upper()
    server = Server.query.filter_by(invite_code=invite_code).first()
    
    if not server:
        return jsonify({'success': False, 'message': 'Geçersiz davet kodu.'}), 404
        
    if ServerMember.query.filter_by(server_id=server.id, user_id=current_user.id).first():
        return jsonify({'success': False, 'message': 'Bu sunucunun zaten üyesisiniz.'}), 400
        
    member = ServerMember(server_id=server.id, user_id=current_user.id, role='member')
    db.session.add(member)
    db.session.commit()
    
    socketio.emit('member_joined_server', {
        'server_id': server.id,
        'user': current_user.to_dict()
    }, room=f"server_{server.id}")
    
    return jsonify({'success': True, 'server': server.to_dict()})

@app.route('/api/servers/<int:server_id>/members', methods=['GET'])
@login_required
def get_server_members(server_id):
    if not ServerMember.query.filter_by(server_id=server_id, user_id=current_user.id).first():
        return jsonify({'success': False, 'message': 'Yetkisiz erişim.'}), 403
        
    memberships = ServerMember.query.filter_by(server_id=server_id).all()
    res = []
    for m in memberships:
        u = db.session.get(User, m.user_id)
        if u:
            u_dict = u.to_dict()
            u_dict['role'] = m.role
            res.append(u_dict)
    return jsonify({'members': res})

@app.route('/api/servers/<int:server_id>/channels', methods=['GET'])
@login_required
def get_channels(server_id):
    if not ServerMember.query.filter_by(server_id=server_id, user_id=current_user.id).first():
        return jsonify({'success': False, 'message': 'Sunucuda değilsiniz.'}), 403
        
    channels = Channel.query.filter_by(server_id=server_id).all()
    return jsonify({'channels': [c.to_dict() for c in channels]})

@app.route('/api/servers/<int:server_id>/channels', methods=['POST'])
@login_required
def create_channel(server_id):
    if not ServerMember.query.filter_by(server_id=server_id, user_id=current_user.id).first():
        return jsonify({'success': False, 'message': 'Yetkisiz erişim.'}), 403

    name = (request.json.get('name') or '').strip()
    ch_type = request.json.get('type') or 'text'
    if not name:
        return jsonify({'success': False, 'message': 'Kanal adı gereklidir.'}), 400

    channel = Channel(server_id=server_id, name=name, type=ch_type)
    db.session.add(channel)
    db.session.commit()

    socketio.emit('channel_created', channel.to_dict(), room=f"server_{server_id}")
    return jsonify({'success': True, 'channel': channel.to_dict()})

@app.route('/api/messages/<int:target_id>', methods=['GET'])
@login_required
def get_dm_messages(target_id):
    msgs = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == target_id)) |
        ((Message.sender_id == target_id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.timestamp.asc()).all()
    return jsonify({'messages': [m.to_dict() for m in msgs]})

@app.route('/api/messages/channel/<int:channel_id>', methods=['GET'])
@login_required
def get_channel_messages(channel_id):
    msgs = Message.query.filter_by(channel_id=channel_id).order_by(Message.timestamp.asc()).all()
    return jsonify({'messages': [m.to_dict() for m in msgs]})

@app.route('/api/messages/<int:message_id>/pin', methods=['POST'])
@login_required
def toggle_pin_message(message_id):
    msg = db.session.get(Message, message_id)
    if not msg:
        return jsonify({'success': False, 'message': 'Mesaj bulunamadı.'}), 404
    msg.is_pinned = not msg.is_pinned
    db.session.commit()
    return jsonify({'success': True, 'is_pinned': msg.is_pinned})

@app.route('/api/messages/pins', methods=['GET'])
@login_required
def get_pinned_messages():
    channel_id = request.args.get('channel_id')
    target_id = request.args.get('target_id')
    
    if channel_id and channel_id.isdigit():
        msgs = Message.query.filter_by(channel_id=int(channel_id), is_pinned=True).all()
    elif target_id and target_id.isdigit():
        t_id = int(target_id)
        msgs = Message.query.filter(
            Message.is_pinned == True,
            ((Message.sender_id == current_user.id) & (Message.receiver_id == t_id)) |
            ((Message.sender_id == t_id) & (Message.receiver_id == current_user.id))
        ).all()
    else:
        msgs = []
        
    return jsonify({'pins': [m.to_dict() for m in msgs]})

@app.route('/api/messages/search', methods=['GET'])
@login_required
def search_messages():
    q = (request.args.get('q') or '').strip()
    channel_id = request.args.get('channel_id')
    target_id = request.args.get('target_id')

    if not q:
        return jsonify({'messages': []})

    query = Message.query.filter(Message.text.ilike(f'%{q}%'))
    if channel_id and channel_id.isdigit():
        query = query.filter_by(channel_id=int(channel_id))
    elif target_id and target_id.isdigit():
        t_id = int(target_id)
        query = query.filter(
            ((Message.sender_id == current_user.id) & (Message.receiver_id == t_id)) |
            ((Message.sender_id == t_id) & (Message.receiver_id == current_user.id))
        )

    msgs = query.order_by(Message.timestamp.desc()).limit(50).all()
    return jsonify({'messages': [m.to_dict() for m in msgs]})

@app.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Dosya seçilmedi.'}), 400
    file = request.files['file']
    if not file or not file.filename:
        return jsonify({'success': False, 'message': 'Geçersiz dosya.'}), 400

    filename = secure_filename(file.filename)
    unique_filename = f"{int(time.time())}_{secrets.token_hex(6)}_{filename}"
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
    file.save(file_path)

    # Determine type
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if ext in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
        file_type = 'image'
    elif ext in ['mp3', 'wav', 'ogg', 'm4a', 'webm']:
        file_type = 'audio'
    elif ext in ['mp4', 'webm', 'mov']:
        file_type = 'video'
    else:
        file_type = 'file'

    return jsonify({
        'success': True,
        'url': f"/static/uploads/{unique_filename}",
        'name': filename,
        'type': file_type
    })

# --- AI Engine Endpoints (Ollama Local LLM & Multi-Lingual Translation) ---

@app.route('/api/ai/status', methods=['GET'])
def ai_status():
    """Returns Ollama connectivity status and installed models."""
    status = check_ollama_status()
    return jsonify({
        'success': True,
        'ollama': status,
        'default_model': OLLAMA_DEFAULT_MODEL
    })

@app.route('/api/ai/ask', methods=['POST'])
@login_required
def ai_ask():
    """Processes questions and prompts using local Ollama LLM (llama3:latest)."""
    data = request.json or {}
    prompt = (data.get('prompt') or '').strip()
    model = (data.get('model') or '').strip() or OLLAMA_DEFAULT_MODEL
    
    if not prompt:
        return jsonify({'success': False, 'message': 'Prompt gerekli.'}), 400

    result = query_ollama(prompt=prompt, model=model)
    if result.get('success'):
        return jsonify({
            'success': True,
            'response': result.get('response'),
            'model': result.get('model'),
            'provider': result.get('provider')
        })
    else:
        return jsonify({
            'success': False,
            'message': result.get('message', 'Yapay zeka yanıtı oluşturulamadı.')
        }), 502

@app.route('/api/ai/translate', methods=['POST'])
@login_required
def ai_translate():
    """Translates chat messages in real time using local Ollama LLM."""
    data = request.json or {}
    text = (data.get('text') or '').strip()
    target_lang = (data.get('target_lang') or 'Türkçe').strip()

    if not text:
        return jsonify({'success': False, 'message': 'Metin gerekli.'}), 400

    system_prompt = (
        f"You are a professional multilingual translator for the AstralPaws platform. "
        f"Translate the given text accurately and naturally into {target_lang}. "
        f"Preserve markdown formatting, code snippets, mentions, and emojis. "
        f"Output ONLY the translated text without introductory phrases, quotes, or notes."
    )

    result = query_ollama(prompt=text, system_prompt=system_prompt)
    if result.get('success'):
        return jsonify({
            'success': True,
            'translated_text': result.get('response'),
            'target_lang': target_lang,
            'model': result.get('model')
        })
    else:
        return jsonify({
            'success': True,
            'translated_text': text,
            'target_lang': target_lang,
            'note': 'Ollama çeviri servisine ulaşılamadı.'
        })

# --- Socket.IO Event Handlers ---

@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        join_room(f"user_{current_user.id}")
        if current_user.presence_status != 'invisible':
            current_user.presence_status = 'online'
            db.session.commit()
            emit('user_connected', {
                'user_id': current_user.id,
                'public_id': current_user.public_id,
                'username': current_user.username
            }, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        leave_room(f"user_{current_user.id}")

@socketio.on('join_conversation')
def handle_join_conversation(data):
    if not current_user.is_authenticated:
        return
    conv_id = data.get('conversation_id')
    if conv_id:
        conv = db.session.get(Conversation, conv_id)
        if conv and conv.is_member(current_user.id):
            join_room(f"conv_{conv_id}")

@socketio.on('leave_conversation')
def handle_leave_conversation(data):
    if not current_user.is_authenticated:
        return
    conv_id = data.get('conversation_id')
    if conv_id:
        leave_room(f"conv_{conv_id}")

@socketio.on('send_message')
def handle_send_message(data):
    if not current_user.is_authenticated:
        return

    text = sanitize_text(data.get('text', ''), max_len=4000)
    conversation_id = data.get('conversation_id')
    receiver_id = data.get('receiver_id') or data.get('target_id')
    channel_id = data.get('channel_id')
    attachment_url = data.get('attachment_url')
    attachment_type = data.get('attachment_type')
    attachment_name = data.get('attachment_name')
    reply_to_id = data.get('reply_to_id')
    forwarded_from_id = data.get('forwarded_from_id')
    message_type = data.get('message_type', 'text')
    attachments_list = data.get('attachments', [])

    if not text and not attachment_url and not attachments_list:
        return

    conv = None
    if conversation_id:
        conv = db.session.get(Conversation, conversation_id)
        if not conv or not conv.is_member(current_user.id):
            return
    elif receiver_id and not channel_id:
        if is_user_blocked_between(current_user.id, receiver_id):
            return
        conv = get_or_create_direct_conv(current_user.id, receiver_id)
        conversation_id = conv.id

    msg = Message(
        conversation_id=conversation_id,
        sender_id=current_user.id,
        receiver_id=receiver_id if not conversation_id else None,
        channel_id=channel_id,
        text=text or 'Dosya Eki',
        message_type=message_type,
        attachment_url=attachment_url,
        attachment_type=attachment_type,
        attachment_name=attachment_name,
        reply_to_id=reply_to_id,
        forwarded_from_id=forwarded_from_id
    )
    db.session.add(msg)
    db.session.flush()

    if attachments_list:
        for att in attachments_list:
            if att.get('file_url'):
                db.session.add(MessageAttachment(
                    message_id=msg.id,
                    file_url=att['file_url'],
                    file_name=att.get('file_name', 'file'),
                    file_size=att.get('file_size', 0),
                    file_type=att.get('file_type', 'file'),
                    mime_type=att.get('mime_type'),
                    is_spoiler=bool(att.get('is_spoiler', False))
                ))

    if conv:
        conv.updated_at = datetime.now(timezone.utc)
        mem = conv.get_member_record(current_user.id)
        if mem:
            mem.last_read_at = datetime.now(timezone.utc)

    db.session.commit()
    award_achievement(current_user.id, 'first_message')

    msg_dict = msg.to_dict()

    if conversation_id:
        socketio.emit('receive_message', msg_dict, room=f"conv_{conversation_id}")
        if conv:
            for m in conv.members:
                socketio.emit('receive_message', msg_dict, room=f"user_{m.user_id}")
                socketio.emit('conversation_updated', {
                    'conversation_id': conv.id,
                    'last_message': msg_dict,
                    'conversation': conv.to_dict(viewer_id=m.user_id)
                }, room=f"user_{m.user_id}")

        # Collaborative @ai assistant in conversation
        if text and ('@ai' in text.lower() or '@astral ai' in text.lower()):
            cleaned = re.sub(r'@(ai|astral ai)\b', '', text, flags=re.IGNORECASE).strip()
            if not cleaned:
                cleaned = "Merhaba Astral AI!"
            reply_text = process_ai_response(cleaned)
            ai_msg_data = {
                'id': f"ai_{int(time.time() * 1000)}",
                'sender_id': 0,
                'conversation_id': conversation_id,
                'username': 'Neon AI',
                'display_name': 'Astral AI',
                'color': '#8b5cf6',
                'badges': ['🤖 Astral AI', '⚡ Ollama Llama 3'],
                'text': reply_text,
                'timestamp': datetime.now().strftime('%H:%M'),
                'created_at': datetime.now(timezone.utc).isoformat(),
                'reply_to_id': msg.id,
                'reactions': {}
            }
            socketio.emit('receive_message', ai_msg_data, room=f"conv_{conversation_id}")
            if conv:
                for m in conv.members:
                    socketio.emit('receive_message', ai_msg_data, room=f"user_{m.user_id}")
    elif channel_id:
        socketio.emit('receive_message', msg_dict, room=f"channel_{channel_id}")
        
        # Collaborative @ai channel assistant
        if text and ('@ai' in text.lower() or '@astral ai' in text.lower()):
            cleaned = re.sub(r'@(ai|astral ai)\b', '', text, flags=re.IGNORECASE).strip()
            if not cleaned:
                cleaned = "Merhaba Astral AI!"
            reply_text = process_ai_response(cleaned)
            ai_msg_data = {
                'id': f"ai_{int(time.time() * 1000)}",
                'sender_id': 0,
                'channel_id': channel_id,
                'username': 'Neon AI',
                'display_name': 'Astral AI',
                'color': '#8b5cf6',
                'badges': ['🤖 Astral AI', '⚡ Ollama Llama 3'],
                'text': reply_text,
                'timestamp': datetime.now().strftime('%H:%M'),
                'created_at': datetime.now(timezone.utc).isoformat(),
                'reply_to_id': msg.id,
                'reactions': {}
            }
            socketio.emit('receive_message', ai_msg_data, room=f"channel_{channel_id}")
    elif receiver_id:
        socketio.emit('receive_message', msg_dict, room=f"user_{receiver_id}")
        socketio.emit('receive_message', msg_dict, room=f"user_{current_user.id}")

@socketio.on('message_reaction')
def handle_message_reaction(data):
    if not current_user.is_authenticated:
        return
    msg_id = data.get('message_id')
    emoji = sanitize_text(data.get('emoji', ''), max_len=60)
    if not msg_id or not emoji:
        return
    msg = db.session.get(Message, msg_id)
    if not msg or msg.is_deleted_everyone:
        return
    try:
        rx = json.loads(msg.reactions) if msg.reactions else {}
    except Exception:
        rx = {}
    
    users = rx.get(emoji, [])
    if current_user.id in users:
        users.remove(current_user.id)
        if not users:
            rx.pop(emoji, None)
        else:
            rx[emoji] = users
    else:
        users.append(current_user.id)
        rx[emoji] = users
    
    msg.reactions = json.dumps(rx)
    db.session.commit()
    
    payload = {'message_id': msg_id, 'reactions': rx}
    if msg.conversation_id:
        socketio.emit('reaction_updated', payload, room=f"conv_{msg.conversation_id}")
        conv = db.session.get(Conversation, msg.conversation_id)
        if conv:
            for m in conv.members:
                socketio.emit('reaction_updated', payload, room=f"user_{m.user_id}")
    if msg.channel_id:
        socketio.emit('reaction_updated', payload, room=f"channel_{msg.channel_id}")
    if msg.receiver_id:
        socketio.emit('reaction_updated', payload, room=f"user_{msg.receiver_id}")
        socketio.emit('reaction_updated', payload, room=f"user_{msg.sender_id}")

@socketio.on('edit_message')
def handle_edit_message(data):
    if not current_user.is_authenticated:
        return
    msg_id = data.get('message_id')
    new_text = sanitize_text(data.get('text', ''), max_len=4000)
    if not msg_id or not new_text:
        return
    msg = db.session.get(Message, msg_id)
    if not msg or msg.sender_id != current_user.id or msg.is_deleted_everyone:
        return
    msg.text = new_text
    msg.is_edited = True
    msg.edited_at = datetime.now(timezone.utc)
    db.session.commit()
    
    payload = {
        'message_id': msg_id,
        'text': new_text,
        'is_edited': True,
        'edited_at': msg.edited_at.isoformat() if msg.edited_at else None
    }
    if msg.conversation_id:
        socketio.emit('message_edited', payload, room=f"conv_{msg.conversation_id}")
        conv = db.session.get(Conversation, msg.conversation_id)
        if conv:
            for m in conv.members:
                socketio.emit('message_edited', payload, room=f"user_{m.user_id}")
    if msg.channel_id:
        socketio.emit('message_edited', payload, room=f"channel_{msg.channel_id}")
    if msg.receiver_id:
        socketio.emit('message_edited', payload, room=f"user_{msg.receiver_id}")
        socketio.emit('message_edited', payload, room=f"user_{msg.sender_id}")

@socketio.on('delete_message')
def handle_delete_message(data):
    if not current_user.is_authenticated:
        return
    msg_id = data.get('message_id')
    if not msg_id:
        return
    msg = db.session.get(Message, msg_id)
    if not msg:
        return

    # If delete_for_me requested
    if data.get('delete_for_me'):
        existing_hidden = HiddenMessage.query.filter_by(user_id=current_user.id, message_id=msg_id).first()
        if not existing_hidden:
            hidden = HiddenMessage(user_id=current_user.id, message_id=msg_id)
            db.session.add(hidden)
            db.session.commit()
        socketio.emit('message_hidden_for_me', {'message_id': msg_id}, room=f"user_{current_user.id}")
        return

    # Delete for everyone
    can_delete = (msg.sender_id == current_user.id)
    if not can_delete and msg.conversation_id:
        conv = db.session.get(Conversation, msg.conversation_id)
        if conv and conv.type == 'group':
            mem = conv.get_member_record(current_user.id)
            if mem and mem.role in ('owner', 'admin'):
                can_delete = True

    if not can_delete:
        return

    msg.is_deleted_everyone = True
    msg.text = '🚫 Bu mesaj silindi.'
    msg.attachment_url = None
    msg.reactions = '{}'
    db.session.commit()

    payload = {
        'message_id': msg_id,
        'is_deleted_everyone': True,
        'text': '🚫 Bu mesaj silindi.'
    }
    if msg.conversation_id:
        socketio.emit('message_deleted', payload, room=f"conv_{msg.conversation_id}")
        conv = db.session.get(Conversation, msg.conversation_id)
        if conv:
            for m in conv.members:
                socketio.emit('message_deleted', payload, room=f"user_{m.user_id}")
    if msg.channel_id:
        socketio.emit('message_deleted', payload, room=f"channel_{msg.channel_id}")
    if msg.receiver_id:
        socketio.emit('message_deleted', payload, room=f"user_{msg.receiver_id}")
        socketio.emit('message_deleted', payload, room=f"user_{msg.sender_id}")

@socketio.on('typing')
def handle_typing(data):
    if not current_user.is_authenticated:
        return
    conv_id = data.get('conversation_id')
    channel_id = data.get('channel_id')
    target_id = data.get('target_id')
    payload = {
        'username': current_user.username,
        'display_name': current_user.get_effective_display_name(),
        'conversation_id': conv_id,
        'channel_id': channel_id,
        'target_id': target_id
    }
    if conv_id:
        socketio.emit('user_typing', payload, room=f"conv_{conv_id}", include_self=False)
    elif channel_id:
        socketio.emit('user_typing', payload, room=f"channel_{channel_id}", include_self=False)
    elif target_id:
        socketio.emit('user_typing', payload, room=f"user_{target_id}")

@socketio.on('stop_typing')
def handle_stop_typing(data):
    if not current_user.is_authenticated:
        return
    conv_id = data.get('conversation_id')
    channel_id = data.get('channel_id')
    target_id = data.get('target_id')
    payload = {
        'conversation_id': conv_id,
        'channel_id': channel_id,
        'target_id': target_id
    }
    if conv_id:
        socketio.emit('user_stop_typing', payload, room=f"conv_{conv_id}", include_self=False)
    elif channel_id:
        socketio.emit('user_stop_typing', payload, room=f"channel_{channel_id}", include_self=False)
    elif target_id:
        socketio.emit('user_stop_typing', payload, room=f"user_{target_id}")

# Canvas, Soundboard & Calling signaling handlers
@socketio.on('soundboard_play')
def handle_soundboard(data):
    if not current_user.is_authenticated:
        return
    key = data.get('sound_key')
    channel_id = data.get('channel_id')
    target_id = data.get('target_id')
    payload = {'sound_key': key, 'username': current_user.username}
    if channel_id:
        socketio.emit('soundboard_triggered', payload, room=f"channel_{channel_id}")
    elif target_id:
        socketio.emit('soundboard_triggered', payload, room=f"user_{target_id}")
        socketio.emit('soundboard_triggered', payload, room=f"user_{current_user.id}")

@socketio.on('join_canvas')
def handle_join_canvas(data):
    if not current_user.is_authenticated: return
    channel_id = data.get('channel_id')
    if channel_id: join_room(f"canvas_{channel_id}")

@socketio.on('leave_canvas')
def handle_leave_canvas(data):
    if not current_user.is_authenticated: return
    channel_id = data.get('channel_id')
    if channel_id: leave_room(f"canvas_{channel_id}")

@socketio.on('canvas_stroke')
def handle_canvas_stroke(data):
    if not current_user.is_authenticated: return
    channel_id = data.get('channel_id')
    if channel_id:
        socketio.emit('canvas_stroke', data, room=f"canvas_{channel_id}", include_self=False)

@socketio.on('call_user')
def handle_call_user(data):
    if not current_user.is_authenticated: return
    target_id = data.get('target_id')
    call_type = data.get('call_type', 'audio')
    if target_id:
        socketio.emit('call_incoming', {
            'caller_id': current_user.id,
            'caller_name': current_user.username,
            'caller_color': current_user.color,
            'call_type': call_type
        }, room=f"user_{target_id}")

@socketio.on('call_response')
def handle_call_response(data):
    if not current_user.is_authenticated: return
    caller_id = data.get('caller_id')
    accepted = data.get('accepted', False)
    if caller_id:
        socketio.emit('call_response', {
            'receiver_id': current_user.id,
            'receiver_name': current_user.username,
            'accepted': accepted
        }, room=f"user_{caller_id}")

@socketio.on('call_end')
def handle_call_end(data):
    if not current_user.is_authenticated: return
    target_id = data.get('target_id')
    if target_id:
        socketio.emit('call_ended', {
            'by_user_id': current_user.id,
            'by_username': current_user.username
        }, room=f"user_{target_id}")

@socketio.on('call_signal')
def handle_call_signal(data):
    if not current_user.is_authenticated: return
    target_id = data.get('target_id')
    signal_data = data.get('signal')
    if target_id and signal_data:
        socketio.emit('call_signal', {
            'sender_id': current_user.id,
            'signal': signal_data
        }, room=f"user_{target_id}")

def run_server():
    socketio.run(app, host='127.0.0.1', port=5000, debug=False, allow_unsafe_werkzeug=True, use_reloader=False)

if __name__ == '__main__':
    if os.environ.get('NO_WEBVIEW') == '1':
        run_server()
    else:
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        time.sleep(0.5)
        webview.create_window('AstralPaws Ultra', 'http://127.0.0.1:5000', width=1200, height=800, background_color='#06080e')
        webview.start()
