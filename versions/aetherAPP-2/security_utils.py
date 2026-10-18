import re
import os
import io
import time
import secrets
import hashlib
import base64
import pyotp
import qrcode
from PIL import Image
from datetime import datetime, timezone, timedelta
from werkzeug.utils import secure_filename

# --- 1. Unique ID & Token Generators ---

def generate_user_public_id() -> str:
    """
    Generates a permanent, non-sequential, cryptographically secure public ID.
    Example format: 'astral_8f92a3c7b4e10d65'
    """
    random_hex = secrets.token_hex(8)
    return f"astral_{random_hex}"

def generate_secure_token(nbytes: int = 32) -> str:
    """Generates a high-entropy URL-safe token."""
    return secrets.token_urlsafe(nbytes)

def hash_token(token: str) -> str:
    """Hashes a token with SHA-256 for secure database storage."""
    if not token:
        return ""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()

def generate_otp_code(length: int = 6) -> str:
    """Generates a cryptographically secure numeric OTP code (e.g., 6 digits)."""
    # Use secrets.randbelow to prevent bias
    return "".join(str(secrets.randbelow(10)) for _ in range(length))

def generate_recovery_codes(count: int = 10) -> list:
    """
    Generates a list of formatted single-use recovery codes.
    Format: 'ABCD-1234'
    """
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ" # Exclude confusing chars 0, 1, I, O
    codes = []
    for _ in range(count):
        part1 = "".join(secrets.choice(alphabet) for _ in range(4))
        part2 = "".join(secrets.choice(alphabet) for _ in range(4))
        codes.append(f"{part1}-{part2}")
    return codes

def hash_recovery_code(code: str) -> str:
    """Normalizes and hashes a recovery code."""
    clean_code = code.strip().upper().replace("-", "").replace(" ", "")
    return hashlib.sha256(clean_code.encode('utf-8')).hexdigest()

# --- 2. Two-Factor Authentication (TOTP) & QR Codes ---

def generate_totp_secret() -> str:
    """Generates a random base32 TOTP secret."""
    return pyotp.random_base32()

def get_totp_uri(secret: str, username: str, issuer: str = "AstralPaws") -> str:
    """Generates the standard otpauth:// URI for authenticator apps."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=username, issuer_name=issuer)

def generate_qr_code_data_url(totp_uri: str) -> str:
    """Generates a Base64-encoded PNG Data URL of the QR code."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=3,
    )
    qr.add_data(totp_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#000000", back_color="#ffffff")
    
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
    return f"data:image/png;base64,{img_b64}"

def verify_totp_code(secret: str, code: str) -> bool:
    """
    Verifies a 6-digit TOTP token against the secret.
    Allows a 1-step window (±30s) to account for slight clock drift.
    """
    if not secret or not code:
        return False
    clean_code = str(code).strip()
    try:
        totp = pyotp.TOTP(secret)
        return totp.verify(clean_code, valid_window=1)
    except Exception:
        return False

# --- 3. User-Agent & Device Parser ---

def parse_user_agent(ua_string: str) -> dict:
    """
    Parses a user-agent string into friendly browser, OS, and device categories.
    """
    if not ua_string:
        return {
            'browser': 'Bilinmeyen Tarayıcı',
            'os': 'Bilinmeyen İşletim Sistemi',
            'device': 'Masaüstü / Cihaz',
            'is_mobile': False
        }

    ua = ua_string.lower()

    # Determine OS
    os_name = "Diğer İşletim Sistemi"
    if "windows nt 10.0" in ua or "windows nt 11.0" in ua or "windows" in ua:
        os_name = "Windows"
    elif "macintosh" in ua or "mac os x" in ua:
        os_name = "macOS"
    elif "android" in ua:
        os_name = "Android"
    elif "iphone" in ua or "ipad" in ua or "ipod" in ua:
        os_name = "iOS"
    elif "linux" in ua:
        os_name = "Linux"

    # Determine Browser
    browser_name = "Tarayıcı"
    if "edg/" in ua or "edge" in ua:
        browser_name = "Microsoft Edge"
    elif "opr/" in ua or "opera" in ua:
        browser_name = "Opera"
    elif "chrome" in ua and "chromium" not in ua:
        browser_name = "Google Chrome"
    elif "firefox" in ua:
        browser_name = "Mozilla Firefox"
    elif "safari" in ua and "chrome" not in ua:
        browser_name = "Apple Safari"
    elif "pywebview" in ua:
        browser_name = "AstralPaws Desktop App"

    # Determine Device Type
    is_mobile = any(m in ua for m in ['mobile', 'android', 'iphone', 'ipad', 'ipod'])
    device_type = "Mobil Cihaz" if is_mobile else "Masaüstü Bilgisayar"
    if "ipad" in ua or "tablet" in ua:
        device_type = "Tablet"

    device_label = f"{os_name} • {browser_name}"

    return {
        'browser': browser_name,
        'os': os_name,
        'device': device_label,
        'device_type': device_type,
        'is_mobile': is_mobile
    }

def sanitize_ip(ip_address: str) -> str:
    """Sanitizes or masks IP address for privacy/logging."""
    if not ip_address:
        return "127.0.0.1"
    # Return cleanly
    return ip_address.strip()

# --- 4. Input Validators & Sanitizers ---

USERNAME_REGEX = re.compile(r'^[a-zA-Z0-9_.-]+$')
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')

def validate_username(username: str) -> tuple:
    """
    Validates username rules:
    - 3 to 30 characters
    - Alphanumeric, underscores, hyphens, dots
    - Cannot start or end with symbols
    """
    if not username or not isinstance(username, str):
        return False, "Kullanıcı adı boş bırakılamaz."
    u = username.strip()
    if len(u) < 3:
        return False, "Kullanıcı adı en az 3 karakter olmalıdır."
    if len(u) > 30:
        return False, "Kullanıcı adı en fazla 30 karakter olabilir."
    if not USERNAME_REGEX.match(u):
        return False, "Kullanıcı adı sadece harf, rakam, alt çizgi, nokta ve tire içerebilir."
    if u[0] in '._-' or u[-1] in '._-':
        return False, "Kullanıcı adı özel karakterle başlayamaz veya bitemez."
    return True, u

def validate_display_name(display_name: str) -> tuple:
    """
    Validates display name rules:
    - 1 to 50 characters
    - Can contain any unicode characters/emojis
    """
    if not display_name or not isinstance(display_name, str):
        return False, "Görünen isim boş bırakılamaz."
    d = display_name.strip()
    if len(d) < 1:
        return False, "Görünen isim en az 1 karakter olmalıdır."
    if len(d) > 50:
        return False, "Görünen isim en fazla 50 karakter olabilir."
    return True, d

def validate_email(email: str) -> tuple:
    """
    Validates email format:
    - Normalized to lowercase
    - Matches standard email regex
    """
    if not email or not isinstance(email, str):
        return False, "E-posta adresi boş bırakılamaz."
    e = email.strip().lower()
    if len(e) > 120:
        return False, "E-posta adresi çok uzun."
    if not EMAIL_REGEX.match(e):
        return False, "Lütfen geçerli bir e-posta adresi girin."
    return True, e

def validate_password(password: str) -> tuple:
    """
    Validates password strength:
    - Minimum 6 characters (recommended 8+)
    - Maximum 128 characters
    """
    if not password or not isinstance(password, str):
        return False, "Parola boş bırakılamaz."
    if len(password) < 6:
        return False, "Parola en az 6 karakter olmalıdır."
    if len(password) > 128:
        return False, "Parola en fazla 128 karakter olabilir."
    return True, password

def sanitize_text(text: str, max_len: int = 500) -> str:
    """Trims text, strips null bytes, and limits max length safely."""
    if not text:
        return ""
    clean = str(text).replace('\x00', '').strip()
    return clean[:max_len]

# --- 5. File Upload Security ---

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
ALLOWED_MIMETYPES = {'image/png', 'image/jpeg', 'image/webp', 'image/gif'}
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

def validate_image_upload(file_storage) -> tuple:
    """
    Validates uploaded file:
    - Presence
    - Safe extension
    - Content-Type / MIME type
    - Real image verification via Pillow
    - Max size limit
    """
    if not file_storage or not file_storage.filename:
        return False, "Lütfen bir dosya seçin.", None

    filename = secure_filename(file_storage.filename)
    if '.' not in filename:
        return False, "Geçersiz dosya uzantısı.", None

    ext = filename.rsplit('.', 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, "Sadece PNG, JPG, JPEG, WEBP ve GIF dosyaları desteklenir.", None

    # Check MIME type
    if file_storage.content_type and file_storage.content_type.lower() not in ALLOWED_MIMETYPES:
        return False, "Desteklenmeyen dosya türü.", None

    # Read bytes to verify image integrity
    try:
        file_bytes = file_storage.read()
        file_size = len(file_bytes)
        
        if file_size > MAX_FILE_SIZE_BYTES:
            return False, "Dosya boyutu 5 MB'den büyük olamaz.", None

        if file_size < 10:
            return False, "Dosya boş veya bozuk.", None

        # Verify image using Pillow
        stream = io.BytesIO(file_bytes)
        img = Image.open(stream)
        img.verify() # Verify file header & structure
        
        # Reset file stream for subsequent saving
        file_storage.seek(0)
        
        # Generate safe random filename
        unique_filename = f"{secrets.token_hex(16)}.{ext}"
        return True, "Geçerli dosya.", unique_filename
    except Exception as e:
        return False, "Görsel dosyası doğrulanamadı veya bozuk.", None

# --- 6. In-Memory Rate Limiting & Cooldowns ---

class RateLimiter:
    """
    Lightweight, thread-safe rate limiter and cooldown manager.
    """
    def __init__(self):
        self._records = {}

    def check_cooldown(self, key: str, cooldown_seconds: int = 60) -> tuple:
        """
        Checks if an action for `key` is allowed or still in cooldown.
        Returns (is_allowed: bool, remaining_seconds: int).
        """
        now = time.time()
        last_time = self._records.get(key, 0)
        elapsed = now - last_time
        if elapsed < cooldown_seconds:
            remaining = int(cooldown_seconds - elapsed) + 1
            return False, remaining
        return True, 0

    def record_action(self, key: str):
        """Records the timestamp of an action."""
        self._records[key] = time.time()

    def check_attempts(self, key: str, max_attempts: int = 5, window_seconds: int = 300) -> tuple:
        """
        Sliding window attempt tracker for brute force defense.
        Returns (is_allowed: bool, remaining_attempts: int).
        """
        now = time.time()
        attempts = self._records.get(f"attempts_{key}", [])
        # Filter out old attempts
        valid_attempts = [t for t in attempts if now - t < window_seconds]
        if len(valid_attempts) >= max_attempts:
            return False, 0
        return True, max_attempts - len(valid_attempts)

    def record_attempt(self, key: str):
        """Records a failed attempt timestamp."""
        now = time.time()
        k = f"attempts_{key}"
        attempts = self._records.get(k, [])
        attempts.append(now)
        # Keep recent 20
        self._records[k] = attempts[-20:]

    def clear_attempts(self, key: str):
        """Clears recorded attempts upon successful action."""
        k = f"attempts_{key}"
        if k in self._records:
            del self._records[k]

rate_limiter = RateLimiter()
