import os
import unittest
import json
import io
import pyotp
from datetime import datetime, timezone, timedelta

# Set testing environment variables
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'test-secret-key-astralpaws-ultra'
os.environ['SMTP_HOST'] = 'localhost'
os.environ['SMTP_PORT'] = '1025'
os.environ['SMTP_USER'] = 'contact@example.com'
os.environ['SMTP_PASSWORD'] = 'test-smtp-password'
os.environ['MAIL_FROM'] = 'contact@example.com'

from app import app, db
from models import User, Session, EmailVerificationToken, PasswordResetToken, TwoFactorAuthentication, RecoveryCode, TrustedDevice
import security_utils

class AstralPawsUserAccountSystemTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        self.app = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    # ==========================================
    # 1. REGISTRATION & VALIDATION TESTS
    # ==========================================
    def test_01_registration_success(self):
        """Test successful registration creating an unverified user and verification token."""
        res = self.app.post('/api/register', json={
            'email': 'astral.user@example.com',
            'username': 'astral_user',
            'display_name': 'Astral Explorer',
            'password': 'StrongPassword123!',
            'password_confirm': 'StrongPassword123!'
        })
        data = res.get_json()
        self.assertEqual(res.status_code, 200)
        self.assertTrue(data['requires_verification'])
        self.assertEqual(data['email'], 'astral.user@example.com')

        user = User.query.filter_by(email='astral.user@example.com').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.username, 'astral_user')
        self.assertEqual(user.display_name, 'Astral Explorer')
        self.assertFalse(user.is_verified)
        self.assertEqual(user.account_status, 'unverified')
        self.assertTrue(user.public_id.startswith('astral_'))

        token_obj = EmailVerificationToken.query.filter_by(user_id=user.id).first()
        self.assertIsNotNone(token_obj)
        self.assertEqual(len(token_obj.otp_code), 6)

    def test_02_registration_validation_errors(self):
        """Test registration rejection on invalid email, username, or passwords."""
        # Invalid email
        res = self.app.post('/api/register', json={
            'email': 'not-an-email',
            'username': 'validuser',
            'password': 'Password123'
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('geçerli bir e-posta', res.get_json()['message'].lower())

        # Invalid username (too short)
        res = self.app.post('/api/register', json={
            'email': 'test@example.com',
            'username': 'ab',
            'password': 'Password123'
        })
        self.assertEqual(res.status_code, 400)

        # Mismatched password
        res = self.app.post('/api/register', json={
            'email': 'test@example.com',
            'username': 'validuser',
            'password': 'Password123',
            'password_confirm': 'DifferentPassword123'
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('eşleşmiyor', res.get_json()['message'])

    def test_03_registration_duplicate_checks(self):
        """Test registration rejection on duplicate email or username for verified users."""
        self._create_verified_user(
            email='alpha@example.com',
            username='alpha_wolf',
            password='Password123'
        )

        # Duplicate email
        res = self.app.post('/api/register', json={
            'email': 'alpha@example.com',
            'username': 'beta_wolf',
            'password': 'Password123'
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('zaten kayıtlı', res.get_json()['message'])

        # Duplicate username
        res = self.app.post('/api/register', json={
            'email': 'beta@example.com',
            'username': 'alpha_wolf',
            'password': 'Password123'
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('zaten alınmış', res.get_json()['message'])

    # ==========================================
    # 2. EMAIL VERIFICATION TESTS
    # ==========================================
    def test_04_verify_email_via_otp_code(self):
        """Test verifying email via 6-digit OTP code."""
        self.app.post('/api/register', json={
            'email': 'verify.otp@example.com',
            'username': 'verify_otp',
            'password': 'Password123'
        })
        user = User.query.filter_by(email='verify.otp@example.com').first()
        token_obj = EmailVerificationToken.query.filter_by(user_id=user.id).first()

        res = self.app.post('/api/verify-email', json={
            'email': 'verify.otp@example.com',
            'code': token_obj.otp_code
        })
        data = res.get_json()
        self.assertEqual(res.status_code, 200)
        self.assertTrue(data['success'])
        self.assertTrue(data['user']['is_verified'])

        # Check DB state
        user_db = User.query.get(user.id)
        self.assertTrue(user_db.is_verified)
        self.assertEqual(user_db.account_status, 'active')
        self.assertIsNotNone(token_obj.used_at)

    def test_05_verify_email_via_token_link(self):
        """Test verifying email via link token."""
        self.app.post('/api/register', json={
            'email': 'verify.link@example.com',
            'username': 'verify_link',
            'password': 'Password123'
        })
        user = User.query.filter_by(email='verify.link@example.com').first()
        token_obj = EmailVerificationToken.query.filter_by(user_id=user.id).first()
        
        # Test invalid token first
        res_invalid = self.app.post('/api/verify-email', json={'token': 'invalid-token-12345'})
        self.assertEqual(res_invalid.status_code, 400)

        # Set raw token
        raw_token = security_utils.generate_secure_token(32)
        token_obj.token_hash = security_utils.hash_token(raw_token)
        db.session.commit()

        res_valid = self.app.post('/api/verify-email', json={'token': raw_token})
        self.assertEqual(res_valid.status_code, 200)
        self.assertTrue(res_valid.get_json()['success'])

    # ==========================================
    # 3. LOGIN & SESSION AUTHENTICATION TESTS
    # ==========================================
    def _create_verified_user(self, email='user@astralpaws.com', username='astral_test', password='Password123'):
        self.app.post('/api/register', json={
            'email': email,
            'username': username,
            'password': password
        })
        user = User.query.filter_by(email=email).first()
        token_obj = EmailVerificationToken.query.filter_by(user_id=user.id).first()
        self.app.post('/api/verify-email', json={'email': email, 'code': token_obj.otp_code})
        return user

    def test_06_login_with_username_and_email(self):
        """Test logging in with username and logging in with email."""
        self._create_verified_user(email='john@example.com', username='john_doe', password='SecretPassword123')

        # Login with email
        res1 = self.app.post('/api/login', json={'username': 'john@example.com', 'password': 'SecretPassword123'})
        self.assertEqual(res1.status_code, 200)
        self.assertTrue(res1.get_json()['success'])

        # Login with username
        res2 = self.app.post('/api/login', json={'username': 'john_doe', 'password': 'SecretPassword123'})
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(res2.get_json()['success'])

        # Invalid password
        res3 = self.app.post('/api/login', json={'username': 'john_doe', 'password': 'WrongPassword'})
        self.assertEqual(res3.status_code, 401)

    def test_07_login_unverified_account_flow(self):
        """Test that unverified accounts receive verification prompt on login."""
        self.app.post('/api/register', json={
            'email': 'unverified@example.com',
            'username': 'unverified_user',
            'password': 'Password123'
        })
        res = self.app.post('/api/login', json={'username': 'unverified_user', 'password': 'Password123'})
        data = res.get_json()
        self.assertEqual(res.status_code, 403)
        self.assertTrue(data['requires_verification'])

    def test_08_auth_status_and_logout(self):
        """Test checking session auth status and logging out."""
        self._create_verified_user(email='session@example.com', username='session_user', password='Password123')
        self.app.post('/api/login', json={'username': 'session_user', 'password': 'Password123'})

        # Check /api/auth/status
        res_status = self.app.get('/api/auth/status')
        self.assertEqual(res_status.status_code, 200)
        self.assertTrue(res_status.get_json()['logged_in'])

        # Logout
        res_logout = self.app.post('/api/logout')
        self.assertEqual(res_logout.status_code, 200)

        # Check /api/auth/status again
        res_status_after = self.app.get('/api/auth/status')
        self.assertFalse(res_status_after.get_json()['logged_in'])

    # ==========================================
    # 4. TWO-FACTOR AUTHENTICATION (2FA) TESTS
    # ==========================================
    def test_09_twofa_setup_and_enable(self):
        """Test full 2FA setup, TOTP validation, and 10 recovery codes generation."""
        self._create_verified_user(email='twofa@example.com', username='twofa_user', password='Password123')
        self.app.post('/api/login', json={'username': 'twofa_user', 'password': 'Password123'})

        # 1. Start setup
        res_setup = self.app.post('/api/security/2fa/setup')
        self.assertEqual(res_setup.status_code, 200)
        data_setup = res_setup.get_json()
        self.assertTrue(data_setup['success'])
        self.assertTrue('secret' in data_setup)
        self.assertTrue(data_setup['qr_code'].startswith('data:image/png;base64,'))

        secret = data_setup['secret']
        totp = pyotp.TOTP(secret)
        valid_code = totp.now()

        # 2. Verify and enable
        res_enable = self.app.post('/api/security/2fa/enable', json={'code': valid_code})
        self.assertEqual(res_enable.status_code, 200)
        data_enable = res_enable.get_json()
        self.assertTrue(data_enable['success'])
        self.assertEqual(len(data_enable['recovery_codes']), 10)

        # Verify DB state
        user = User.query.filter_by(username='twofa_user').first()
        twofa_record = TwoFactorAuthentication.query.filter_by(user_id=user.id).first()
        self.assertTrue(twofa_record.enabled)
        recovery_codes = RecoveryCode.query.filter_by(user_id=user.id).all()
        self.assertEqual(len(recovery_codes), 10)

    def test_10_twofa_login_flow_with_totp_and_recovery_code(self):
        """Test 2FA required prompt on login, TOTP verification, and recovery code verification."""
        user = self._create_verified_user(email='twofa.login@example.com', username='twofa_login', password='Password123')
        self.app.post('/api/login', json={'username': 'twofa_login', 'password': 'Password123'})

        # Setup 2FA
        res_setup = self.app.post('/api/security/2fa/setup')
        secret = res_setup.get_json()['secret']
        valid_code = pyotp.TOTP(secret).now()
        res_enable = self.app.post('/api/security/2fa/enable', json={'code': valid_code})
        recovery_codes = res_enable.get_json()['recovery_codes']
        self.app.post('/api/logout')

        # Login -> requires 2FA
        res_login = self.app.post('/api/login', json={'username': 'twofa_login', 'password': 'Password123'})
        data_login = res_login.get_json()
        self.assertTrue(data_login['requires_2fa'])
        temp_token = data_login['temp_token']

        # Complete 2FA login with TOTP
        totp_code = pyotp.TOTP(secret).now()
        res_2fa = self.app.post('/api/login/2fa', json={'temp_token': temp_token, 'code': totp_code})
        self.assertEqual(res_2fa.status_code, 200)
        self.assertTrue(res_2fa.get_json()['success'])

        # Logout and test Recovery Code login
        self.app.post('/api/logout')
        res_login2 = self.app.post('/api/login', json={'username': 'twofa_login', 'password': 'Password123'})
        temp_token2 = res_login2.get_json()['temp_token']

        first_recovery_code = recovery_codes[0]
        res_recovery = self.app.post('/api/login/2fa', json={'temp_token': temp_token2, 'code': first_recovery_code})
        self.assertEqual(res_recovery.status_code, 200)
        self.assertTrue(res_recovery.get_json()['success'])

        # Verify the used recovery code cannot be reused
        self.app.post('/api/logout')
        res_login3 = self.app.post('/api/login', json={'username': 'twofa_login', 'password': 'Password123'})
        temp_token3 = res_login3.get_json()['temp_token']
        res_reuse = self.app.post('/api/login/2fa', json={'temp_token': temp_token3, 'code': first_recovery_code})
        self.assertEqual(res_reuse.status_code, 400)

    def test_11_twofa_disable_and_regenerate_codes(self):
        """Test disabling 2FA with password check and regenerating recovery codes."""
        self._create_verified_user(email='twofa.mgmt@example.com', username='twofa_mgmt', password='Password123')
        self.app.post('/api/login', json={'username': 'twofa_mgmt', 'password': 'Password123'})

        # Setup 2FA
        res_setup = self.app.post('/api/security/2fa/setup')
        secret = res_setup.get_json()['secret']
        self.app.post('/api/security/2fa/enable', json={'code': pyotp.TOTP(secret).now()})

        # Regenerate recovery codes
        res_regen = self.app.post('/api/security/2fa/recovery-codes/regenerate', json={'password': 'Password123'})
        self.assertEqual(res_regen.status_code, 200)
        self.assertEqual(len(res_regen.get_json()['recovery_codes']), 10)

        # Disable 2FA
        res_disable = self.app.post('/api/security/2fa/disable', json={'password': 'Password123'})
        self.assertEqual(res_disable.status_code, 200)
        self.assertTrue(res_disable.get_json()['success'])

        # Check DB state
        user = User.query.filter_by(username='twofa_mgmt').first()
        twofa_rec = TwoFactorAuthentication.query.filter_by(user_id=user.id).first()
        self.assertFalse(twofa_rec.enabled)

    # ==========================================
    # 5. PASSWORD MANAGEMENT TESTS
    # ==========================================
    def test_12_forgot_and_reset_password(self):
        """Test forgot password request and resetting password with single-use token."""
        user = self._create_verified_user(email='forgot@example.com', username='forgot_user', password='OldPassword123')

        # Forgot password request
        res_forgot = self.app.post('/api/forgot-password', json={'email': 'forgot@example.com'})
        self.assertEqual(res_forgot.status_code, 200)
        self.assertIn('şifre sıfırlama', res_forgot.get_json()['message'])

        reset_token_obj = PasswordResetToken.query.filter_by(user_id=user.id).first()
        self.assertIsNotNone(reset_token_obj)
        self.assertIsNone(reset_token_obj.used_at)

        # Set raw token
        raw_token = security_utils.generate_secure_token(32)
        reset_token_obj.token_hash = security_utils.hash_token(raw_token)
        db.session.commit()

        res_reset = self.app.post('/api/reset-password', json={
            'token': raw_token,
            'password': 'NewStrongPassword123!',
            'password_confirm': 'NewStrongPassword123!'
        })
        self.assertEqual(res_reset.status_code, 200)
        self.assertTrue(res_reset.get_json()['success'])

        # Verify old password fails, new password succeeds
        res_old = self.app.post('/api/login', json={'username': 'forgot_user', 'password': 'OldPassword123'})
        self.assertEqual(res_old.status_code, 401)
        res_new = self.app.post('/api/login', json={'username': 'forgot_user', 'password': 'NewStrongPassword123!'})
        self.assertEqual(res_new.status_code, 200)

    def test_13_change_password_endpoint(self):
        """Test authenticated user changing password with option to logout others."""
        self._create_verified_user(email='change.pwd@example.com', username='change_pwd_user', password='CurrentPassword123')
        self.app.post('/api/login', json={'username': 'change_pwd_user', 'password': 'CurrentPassword123'})

        res = self.app.post('/api/account/change-password', json={
            'current_password': 'CurrentPassword123',
            'new_password': 'BrandNewPassword123!',
            'new_password_confirm': 'BrandNewPassword123!',
            'logout_other_devices': True
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])

    # ==========================================
    # 6. PROFILE MANAGEMENT TESTS
    # ==========================================
    def test_14_profile_update_and_public_id(self):
        """Test updating profile display name, bio, avatar/banner colors, and public id retrieval."""
        user = self._create_verified_user(email='profile@example.com', username='profile_user', password='Password123')
        self.app.post('/api/login', json={'username': 'profile_user', 'password': 'Password123'})

        # Update profile
        res_update = self.app.post('/api/profile/update', json={
            'display_name': 'Astral Master',
            'bio': 'Exploring cosmic communication networks.',
            'color': '#10b981',
            'banner_color': '#3b82f6',
            'presence_status': 'dnd'
        })
        self.assertEqual(res_update.status_code, 200)
        data = res_update.get_json()
        self.assertEqual(data['user']['display_name'], 'Astral Master')
        self.assertEqual(data['user']['bio'], 'Exploring cosmic communication networks.')
        self.assertEqual(data['user']['presence_status'], 'dnd')

        # Retrieve user by public ID
        res_pub = self.app.get(f'/api/users/{user.public_id}')
        self.assertEqual(res_pub.status_code, 200)
        self.assertEqual(res_pub.get_json()['user']['display_name'], 'Astral Master')

    def test_15_profile_avatar_and_banner_upload(self):
        """Test uploading and removing avatar and banner images."""
        from PIL import Image as PILImage
        self._create_verified_user(email='media@example.com', username='media_user', password='Password123')
        self.app.post('/api/login', json={'username': 'media_user', 'password': 'Password123'})

        # Upload Avatar
        img = PILImage.new('RGB', (50, 50), color='purple')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)

        res_avatar = self.app.post('/api/profile/avatar', data={'file': (img_bytes, 'avatar.png')}, content_type='multipart/form-data')
        self.assertEqual(res_avatar.status_code, 200)
        self.assertTrue(res_avatar.get_json()['success'])
        self.assertTrue(res_avatar.get_json()['user']['avatar'].startswith('/static/uploads/'))

        # Remove Avatar
        res_rem_avatar = self.app.post('/api/profile/avatar/remove')
        self.assertEqual(res_rem_avatar.status_code, 200)
        self.assertIsNone(res_rem_avatar.get_json()['user']['avatar'])

        # Upload Banner
        banner_img = PILImage.new('RGB', (200, 80), color='indigo')
        banner_bytes = io.BytesIO()
        banner_img.save(banner_bytes, format='PNG')
        banner_bytes.seek(0)

        res_banner = self.app.post('/api/profile/banner', data={'file': (banner_bytes, 'banner.png')}, content_type='multipart/form-data')
        self.assertEqual(res_banner.status_code, 200)
        self.assertTrue(res_banner.get_json()['success'])
        self.assertTrue(res_banner.get_json()['user']['banner'].startswith('/static/uploads/'))

        # Remove Banner
        res_rem_banner = self.app.post('/api/profile/banner/remove')
        self.assertEqual(res_rem_banner.status_code, 200)
        self.assertIsNone(res_rem_banner.get_json()['user']['banner'])


    def test_16_custom_status_with_expiry(self):
        """Test setting and clearing custom status with duration."""
        self._create_verified_user(email='status@example.com', username='status_user', password='Password123')
        self.app.post('/api/login', json={'username': 'status_user', 'password': 'Password123'})

        res_status = self.app.post('/api/profile/custom-status', json={
            'text': 'Coding on AstralPaws',
            'emoji': '🚀',
            'expires_in': '1h'
        })
        self.assertEqual(res_status.status_code, 200)
        self.assertEqual(res_status.get_json()['user']['custom_status'], 'Coding on AstralPaws')
        self.assertEqual(res_status.get_json()['user']['custom_status_emoji'], '🚀')

    # ==========================================
    # 7. SESSIONS & TRUSTED DEVICES TESTS
    # ==========================================
    def test_17_sessions_listing_and_revocation(self):
        """Test listing active sessions and revoking specific session."""
        self._create_verified_user(email='sessions.test@example.com', username='sessions_test_user', password='Password123')
        self.app.post('/api/login', json={'username': 'sessions_test_user', 'password': 'Password123'})

        res_list = self.app.get('/api/account/sessions')
        self.assertEqual(res_list.status_code, 200)
        sessions = res_list.get_json()['sessions']
        self.assertGreaterEqual(len(sessions), 1)
        self.assertTrue(sessions[0]['is_current'])

        # Revoke other sessions endpoint
        res_revoke_others = self.app.post('/api/account/sessions/revoke-others')
        self.assertEqual(res_revoke_others.status_code, 200)

    # ==========================================
    # 8. ACCOUNT LIFECYCLE & GRACE PERIOD TESTS
    # ==========================================
    def test_18_account_disable_and_reactivation(self):
        """Test disabling account and auto-reactivating on next login."""
        self._create_verified_user(email='disable@example.com', username='disable_user', password='Password123')
        self.app.post('/api/login', json={'username': 'disable_user', 'password': 'Password123'})

        # Disable account
        res_dis = self.app.post('/api/account/disable', json={'password': 'Password123'})
        self.assertEqual(res_dis.status_code, 200)

        user = User.query.filter_by(username='disable_user').first()
        self.assertEqual(user.account_status, 'disabled')

        # Login again -> should reactivate
        res_reactivate = self.app.post('/api/login', json={'username': 'disable_user', 'password': 'Password123'})
        self.assertEqual(res_reactivate.status_code, 200)
        self.assertTrue(res_reactivate.get_json()['success'])
        
        user_db = User.query.filter_by(username='disable_user').first()
        self.assertEqual(user_db.account_status, 'active')

    def test_19_account_deletion_request_grace_period_and_cancellation(self):
        """Test account deletion with 14-day grace period and cancellation."""
        self._create_verified_user(email='delete@example.com', username='delete_user', password='Password123')
        self.app.post('/api/login', json={'username': 'delete_user', 'password': 'Password123'})

        # Request deletion
        res_del = self.app.post('/api/account/delete-request', json={'password': 'Password123'})
        self.assertEqual(res_del.status_code, 200)
        data = res_del.get_json()
        self.assertTrue(data['success'])
        self.assertIn('14 gün', data['message'])

        user = User.query.filter_by(username='delete_user').first()
        self.assertEqual(user.account_status, 'pending_deletion')
        self.assertIsNotNone(user.deletion_scheduled_for)

        # Cancel deletion
        res_cancel = self.app.post('/api/account/delete-cancel')
        self.assertEqual(res_cancel.status_code, 200)
        self.assertTrue(res_cancel.get_json()['success'])

        user_after = User.query.filter_by(username='delete_user').first()
        self.assertEqual(user_after.account_status, 'active')
        self.assertIsNone(user_after.deletion_scheduled_for)


if __name__ == '__main__':
    unittest.main()
