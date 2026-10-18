import os
import ssl
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

# --- SMTP Configuration from Environment Variables ---
SMTP_HOST = os.getenv('SMTP_HOST') or os.getenv('SMTP_SERVER', 'mail.astralpaws.com.tr')
SMTP_PORT = int(os.getenv('SMTP_PORT', 465))
SMTP_SECURE = os.getenv('SMTP_SECURE', 'ssl').lower() # 'ssl' or 'tls' / 'starttls'
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
MAIL_FROM = os.getenv("MAIL_FROM", SMTP_USER)
SENDER_NAME = os.getenv('SMTP_SENDER_NAME', 'AstralPaws')
APP_BASE_URL = os.getenv('APP_BASE_URL', 'http://127.0.0.1:5000').rstrip('/')

def _build_base_email_html(title: str, subtitle: str, body_html: str, footer_text: str = None) -> str:
    """Wraps body content in a Cyber-Luxe AstralPaws dark-mode responsive template."""
    default_footer = footer_text or "Eğer bu işlemi siz başlatmadıysanız lütfen bu e-postayı güvenle göz ardı edin."
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
</head>
<body style="margin:0; padding:0; background-color:#06080e; font-family:'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color:#f8fafc;">
    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color:#06080e; padding:36px 12px;">
        <tr>
            <td align="center">
                <table width="100%" max-width="540px" border="0" cellspacing="0" cellpadding="0" style="max-width:540px; background:linear-gradient(150deg, #101423, #0b0e18); border:1px solid rgba(139,92,246,0.35); border-radius:20px; box-shadow:0 18px 50px rgba(0,0,0,0.7); overflow:hidden;">
                    
                    <!-- Header -->
                    <tr>
                        <td align="center" style="padding:32px 24px 20px; background:linear-gradient(180deg, rgba(139,92,246,0.22) 0%, rgba(139,92,246,0) 100%);">
                            <div style="font-size:38px; line-height:1; margin-bottom:12px;">🐾✨</div>
                            <h1 style="margin:0; font-size:24px; font-weight:800; letter-spacing:1px; color:#ffffff;">
                                ASTRAL<span style="background:linear-gradient(135deg, #6366f1, #8b5cf6, #d946ef); padding:3px 10px; border-radius:8px; font-size:13px; vertical-align:middle; color:#fff; margin-left:6px;">PAWS</span>
                            </h1>
                            <p style="margin:8px 0 0; font-size:12px; color:#a78bfa; letter-spacing:0.8px; font-weight:600; text-transform:uppercase;">
                                {subtitle}
                            </p>
                        </td>
                    </tr>

                    <!-- Body Content -->
                    <tr>
                        <td style="padding:24px 36px 32px; text-align:center;">
                            {body_html}
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding:22px 30px; background-color:rgba(7, 9, 16, 0.96); border-top:1px solid rgba(255,255,255,0.06); text-align:center;">
                            <p style="margin:0 0 6px; font-size:12px; color:#64748b; line-height:1.5;">
                                {default_footer}
                            </p>
                            <p style="margin:0 0 4px; font-size:11px; color:#475569;">
                                Bu e-posta <strong>{MAIL_FROM}</strong> adresi üzerinden otomatik olarak iletilmiştir.
                            </p>
                            <p style="margin:0; font-size:11px; color:#334155;">
                                &copy; 2026 AstralPaws Platform. Tüm hakları saklıdır.
                            </p>
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""

# --- Email Content Builders ---

def build_verification_email_html(username: str, otp_code: str, token: str = None) -> tuple:
    """Generates verification email HTML and plain text."""
    verify_url = f"{APP_BASE_URL}/verify-email?token={token}" if token else f"{APP_BASE_URL}/"

    body = f"""
    <h2 style="margin:0 0 12px; font-size:20px; font-weight:700; color:#ffffff;">
        AstralPaws'a Hoş Geldin, <span style="color:#a78bfa;">{username}</span>! 👋
    </h2>
    <p style="margin:0 0 24px; font-size:14px; line-height:1.6; color:#94a3b8;">
        Hesabını aktifleştirmek ve topluluğumuza katılmak için e-posta adresini doğrula.
    </p>

    <!-- 6-digit OTP Code -->
    <div style="margin:0 auto 20px; padding:18px 26px; background:rgba(12, 16, 28, 0.95); border:2px dashed #8b5cf6; border-radius:14px; display:inline-block;">
        <div style="font-size:11px; font-weight:700; letter-spacing:1px; color:#a78bfa; margin-bottom:6px; text-transform:uppercase;">6 HANELİ DOĞRULAMA KODU</div>
        <span style="font-family:'Courier New', Courier, monospace; font-size:36px; font-weight:800; letter-spacing:8px; color:#ffffff; text-shadow:0 0 14px rgba(139,92,246,0.85);">{otp_code}</span>
    </div>

    <!-- Direct Verify Button -->
    <div style="margin:16px 0 24px;">
        <a href="{verify_url}" style="display:inline-block; padding:14px 34px; background:linear-gradient(135deg, #6366f1, #8b5cf6); color:#ffffff; text-decoration:none; font-weight:700; font-size:15px; border-radius:12px; box-shadow:0 6px 20px rgba(99,102,241,0.45);">
            ✨ E-postamı Doğrula
        </a>
    </div>

    <p style="margin:0 0 6px; font-size:13px; color:#64748b;">
        ⏱️ Bu doğrulama kodu <strong>15 dakika</strong> boyunca geçerlidir.
    </p>
    """

    plain = f"""Merhaba {username},

AstralPaws'a Hoş Geldin!

Hesabını aktifleştirmek için 6 haneli doğrulama kodunuz: {otp_code}
Veya bağlantıyı tarayıcınızda açın: {verify_url}

Bu kod 15 dakika boyunca geçerlidir.
Eğer bu hesabı sen oluşturmadıysan bu e-postayı görmezden gelebilirsin.

AstralPaws Sistemi
{MAIL_FROM}
"""
    html = _build_base_email_html("AstralPaws'a Hoş Geldin!", "GÜVENLİ E-POSTA DOĞRULAMA", body)
    return html, plain

def build_password_reset_email_html(username: str, reset_token: str) -> tuple:
    """Generates password reset email HTML and plain text."""
    reset_url = f"{APP_BASE_URL}/reset-password?token={reset_token}"

    body = f"""
    <h2 style="margin:0 0 12px; font-size:20px; font-weight:700; color:#ffffff;">
        Şifre Sıfırlama Talebi, <span style="color:#a78bfa;">{username}</span> 🔒
    </h2>
    <p style="margin:0 0 24px; font-size:14px; line-height:1.6; color:#94a3b8;">
        AstralPaws hesabınız için şifre sıfırlama talebinde bulundunuz. Yeni şifrenizi belirlemek için aşağıdaki butona tıklayın:
    </p>

    <!-- Reset Button -->
    <div style="margin:20px 0 28px;">
        <a href="{reset_url}" style="display:inline-block; padding:14px 34px; background:linear-gradient(135deg, #ec4899, #8b5cf6); color:#ffffff; text-decoration:none; font-weight:700; font-size:15px; border-radius:12px; box-shadow:0 6px 20px rgba(236,72,153,0.45);">
            🔑 Şifremi Sıfırla
        </a>
    </div>

    <p style="margin:0 0 6px; font-size:13px; color:#64748b;">
        ⏱️ Bu bağlantı <strong>1 saat</strong> boyunca geçerlidir ve yalnızca tek bir kez kullanılabilir.
    </p>
    <p style="margin:0; font-size:12px; color:#475569;">
        Eğer şifre sıfırlama talebinde bulunmadıysanız hesabınız güvendedir, hiçbir işlem yapmanıza gerek yoktur.
    </p>
    """

    plain = f"""Merhaba {username},

AstralPaws hesabınız için şifre sıfırlama bağlantısı:
{reset_url}

Bu bağlantı 1 saat boyunca geçerlidir ve tek kullanımlıktır.
Talebi siz yapmadıysanız bu e-postayı dikkate almayın.

AstralPaws Güvenlik Ekibi
{MAIL_FROM}
"""
    html = _build_base_email_html("Şifre Sıfırlama Talebi", "HESAP GÜVENLİĞİ", body)
    return html, plain

def build_password_changed_email_html(username: str, ip_address: str, device_info: str) -> tuple:
    """Generates password changed notification email."""
    body = f"""
    <h2 style="margin:0 0 12px; font-size:20px; font-weight:700; color:#ffffff;">
        Şifreniz Değiştirildi 🛡️
    </h2>
    <p style="margin:0 0 20px; font-size:14px; line-height:1.6; color:#94a3b8;">
        <strong>{username}</strong>, AstralPaws hesabınızın şifresi az önce başarıyla güncellendi.
    </p>

    <div style="margin:0 auto 20px; padding:16px 22px; background:rgba(12, 16, 28, 0.9); border:1px solid rgba(255,255,255,0.08); border-radius:12px; text-align:left; font-size:13px; color:#cbd5e1; max-width:380px;">
        <div style="margin-bottom:6px;">📱 <strong>Cihaz / Tarayıcı:</strong> {device_info}</div>
        <div>🌐 <strong>IP Adresi:</strong> {ip_address}</div>
    </div>

    <p style="margin:0; font-size:12px; color:#ef4444; font-weight:600;">
        ⚠️ Bu işlemi siz gerçekleştirmediyseniz lütfen derhal şifrenizi sıfırlayın veya destek ile iletişime geçin.
    </p>
    """

    plain = f"""Merhaba {username},

AstralPaws hesabınızın şifresi güncellendi.
Cihaz: {device_info}
IP: {ip_address}

Bu işlemi siz yapmadıysanız lütfen hemen şifrenizi sıfırlayın.

AstralPaws Güvenlik Ekibi
"""
    html = _build_base_email_html("Şifreniz Değiştirildi", "GÜVENLİK BİLDİRİMİ", body)
    return html, plain

def build_suspicious_login_email_html(username: str, device_info: str, ip_address: str, timestamp_str: str) -> tuple:
    """Generates new/suspicious login alert email."""
    body = f"""
    <h2 style="margin:0 0 12px; font-size:20px; font-weight:700; color:#ffffff;">
        Yeni Cihaz Girişi Bildirimi 🔍
    </h2>
    <p style="margin:0 0 20px; font-size:14px; line-height:1.6; color:#94a3b8;">
        <strong>{username}</strong>, hesabınıza yeni veya alışılmadık bir cihazdan başarılı giriş yapıldı.
    </p>

    <div style="margin:0 auto 20px; padding:16px 22px; background:rgba(12, 16, 28, 0.9); border:1px solid rgba(255,255,255,0.08); border-radius:12px; text-align:left; font-size:13px; color:#cbd5e1; max-width:380px;">
        <div style="margin-bottom:6px;">💻 <strong>Cihaz / Tarayıcı:</strong> {device_info}</div>
        <div style="margin-bottom:6px;">🌐 <strong>IP Adresi:</strong> {ip_address}</div>
        <div>⏱️ <strong>Zaman:</strong> {timestamp_str}</div>
    </div>

    <p style="margin:0; font-size:12px; color:#94a3b8;">
        Bu giriş size aitse hiçbir işlem yapmanıza gerek yoktur. Size ait değilse, hesap ayarlarından <strong>"Diğer tüm cihazlardan çıkış yap"</strong> seçeneğini kullanın ve şifrenizi değiştirin.
    </p>
    """

    plain = f"""Merhaba {username},

AstralPaws hesabınıza yeni bir cihazdan giriş yapıldı:
Cihaz: {device_info}
IP: {ip_address}
Zaman: {timestamp_str}

Giriş size ait değilse lütfen hesap ayarlarından diğer oturumları sonlandırıp şifrenizi değiştirin.

AstralPaws Güvenlik Ekibi
"""
    html = _build_base_email_html("Yeni Cihaz Girişi", "GÜVENLİK UYARISI", body)
    return html, plain

def build_deletion_notice_email_html(username: str, scheduled_date_str: str) -> tuple:
    """Generates account deletion grace period notice email."""
    body = f"""
    <h2 style="margin:0 0 12px; font-size:20px; font-weight:700; color:#ef4444;">
        Hesap Silme Talebi Alındı ⚠️
    </h2>
    <p style="margin:0 0 20px; font-size:14px; line-height:1.6; color:#94a3b8;">
        <strong>{username}</strong>, AstralPaws hesabınızı silme talebiniz işleme alınmıştır.
    </p>

    <div style="margin:0 auto 20px; padding:16px 22px; background:rgba(239, 68, 68, 0.08); border:1px solid rgba(239, 68, 68, 0.3); border-radius:12px; font-size:13px; color:#fca5a5; max-width:380px;">
        📅 <strong>Planlanan Kalıcı Silme Tarihi:</strong><br>
        <span style="font-size:15px; font-weight:700; color:#ffffff;">{scheduled_date_str}</span>
    </div>

    <p style="margin:0 0 12px; font-size:13px; color:#94a3b8; line-height:1.6;">
        Bu süre zarfında hesabınıza tekrar giriş yaparak silme talebini dilediğiniz zaman <strong>iptal edebilir</strong> ve hesabınızı anında kullanmaya devam edebilirsiniz.
    </p>
    """

    plain = f"""Merhaba {username},

AstralPaws hesabınızı silme talebiniz alındı.
Kalıcı silme tarihi: {scheduled_date_str}

Bu tarihe kadar hesabınıza giriş yaparak silme talebini iptal edebilirsiniz.

AstralPaws Ekibi
"""
    html = _build_base_email_html("Hesap Silme Talebi", "HESAP İŞLEMLERİ", body)
    return html, plain

# --- Core SMTP Dispatcher ---

def _try_smtp_login(server, user: str, primary_pwd: str):
    """Tries primary password and smart case variations (e.g. configured SMTP password / Fatih2641)."""
    passwords_to_try = []
    if primary_pwd and primary_pwd not in ('your_password_here', 'your_secure_smtp_password_here'):
        passwords_to_try.append(primary_pwd)
        if primary_pwd.capitalize() not in passwords_to_try:
            passwords_to_try.append(primary_pwd.capitalize())
        if primary_pwd.lower() not in passwords_to_try:
            passwords_to_try.append(primary_pwd.lower())
    
    logged_in = False
    last_err = None
    for p in passwords_to_try:
        try:
            server.login(user, p)
            logged_in = True
            break
        except Exception as err:
            last_err = err
    if not logged_in and last_err:
        raise last_err

def _send_smtp_email(to_email: str, subject: str, html_content: str, text_content: str) -> bool:
    """
    Sends an email using configured SMTP server with SSL/TLS support and automatic fallback.
    """
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{SENDER_NAME} <{MAIL_FROM}>"
        msg['To'] = to_email

        msg.attach(MIMEText(text_content, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))

        print(f"[EmailService] Dispatching email to <{to_email}> Subject: '{subject}' via {SMTP_HOST}:{SMTP_PORT} ({SMTP_SECURE})...", flush=True)

        # Create SSL context suitable for cPanel/NBThost servers
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        sent = False
        # Try Primary Configured Mode (Port 465 SSL)
        if SMTP_PORT == 465 or SMTP_SECURE == 'ssl':
            try:
                with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10, context=ssl_ctx) as server:
                    _try_smtp_login(server, SMTP_USER, SMTP_PASSWORD)
                    server.send_message(msg)
                    sent = True
            except Exception as ssl_err:
                print(f"[EmailService] Port {SMTP_PORT} SSL attempt notice: {ssl_err}. Trying Port 587 STARTTLS fallback...", flush=True)
                try:
                    with smtplib.SMTP(SMTP_HOST, 587, timeout=10) as server:
                        server.ehlo()
                        server.starttls(context=ssl_ctx)
                        server.ehlo()
                        _try_smtp_login(server, SMTP_USER, SMTP_PASSWORD)
                        server.send_message(msg)
                        sent = True
                except Exception as fallback_err:
                    print(f"[EmailService] Fallback to 587 failed: {fallback_err}", flush=True)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                server.ehlo()
                try:
                    server.starttls(context=ssl_ctx)
                    server.ehlo()
                except Exception as tls_err:
                    print(f"[EmailService] Notice on STARTTLS: {tls_err}", flush=True)
                _try_smtp_login(server, SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
                sent = True

        if sent:
            print(f"[EmailService] Email successfully delivered to {to_email} from {MAIL_FROM}.", flush=True)
            return True
        return False
    except Exception as e:
        print(f"[EmailService] Notice: Could not deliver email via SMTP to {to_email}: {e}", flush=True)
        return False

# --- Public Async Senders ---

def send_verification_email_async(to_email: str, username: str, otp_code: str, token: str = None):
    """Dispatches account verification email in background daemon thread."""
    html, plain = build_verification_email_html(username, otp_code, token)
    subject = f"{otp_code} - AstralPaws E-posta Doğrulama Kodu"
    
    print(f"\n=======================================================", flush=True)
    print(f"[EmailService] Dogrulama Kodu -> Alici: {to_email} ({username})", flush=True)
    print(f"[EmailService] 6 Haneli OTP Kod: [{otp_code}]", flush=True)
    if token:
        print(f"[EmailService] Dogrulama Linki: {APP_BASE_URL}/verify-email?token={token}", flush=True)
    print(f"=======================================================\n", flush=True)
    
    thread = threading.Thread(
        target=_send_smtp_email,
        args=(to_email, subject, html, plain),
        daemon=True
    )
    thread.start()
    return thread

def send_password_reset_email_async(to_email: str, username: str, reset_token: str):
    """Dispatches password reset email in background daemon thread."""
    html, plain = build_password_reset_email_html(username, reset_token)
    subject = "AstralPaws Şifre Sıfırlama Bağlantısı"
    
    print(f"[EmailService DEV LOG] Password Reset Link for {to_email} ({username}): {APP_BASE_URL}/reset-password?token={reset_token}")
    
    thread = threading.Thread(
        target=_send_smtp_email,
        args=(to_email, subject, html, plain),
        daemon=True
    )
    thread.start()
    return thread

def send_password_changed_email_async(to_email: str, username: str, ip_address: str, device_info: str):
    """Dispatches password changed security notice."""
    html, plain = build_password_changed_email_html(username, ip_address, device_info)
    subject = "AstralPaws Şifreniz Değiştirildi"
    
    thread = threading.Thread(
        target=_send_smtp_email,
        args=(to_email, subject, html, plain),
        daemon=True
    )
    thread.start()
    return thread

def send_suspicious_login_email_async(to_email: str, username: str, device_info: str, ip_address: str, timestamp_str: str):
    """Dispatches suspicious/new device login alert."""
    html, plain = build_suspicious_login_email_html(username, device_info, ip_address, timestamp_str)
    subject = "AstralPaws Hesabınıza Yeni Bir Cihazdan Giriş Yapıldı"
    
    thread = threading.Thread(
        target=_send_smtp_email,
        args=(to_email, subject, html, plain),
        daemon=True
    )
    thread.start()
    return thread

def send_deletion_notice_email_async(to_email: str, username: str, scheduled_date_str: str):
    """Dispatches account deletion grace period notice."""
    html, plain = build_deletion_notice_email_html(username, scheduled_date_str)
    subject = "AstralPaws Hesap Silme Talebiniz Alındı"
    
    thread = threading.Thread(
        target=_send_smtp_email,
        args=(to_email, subject, html, plain),
        daemon=True
    )
    thread.start()
    return thread
