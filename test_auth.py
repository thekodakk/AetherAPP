import unittest
import json
from datetime import datetime, timezone, timedelta
from app import app, db, User

class AuthTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        self.app = app
        self.client = app.test_client()

        with app.app_context():
            db.create_all()
            from flask_bcrypt import generate_password_hash
            # Verified test user
            u_verified = User(
                username='verified_user',
                email='verified@astralpaws.com.tr',
                password_hash=generate_password_hash('secret123').decode('utf-8'),
                color='#8b5cf6',
                is_verified=True,
                status_mode='online'
            )
            # Unverified test user
            u_unverified = User(
                username='unverified_user',
                email='unverified@astralpaws.com.tr',
                password_hash=generate_password_hash('secret123').decode('utf-8'),
                color='#ec4899',
                is_verified=False,
                verification_code='654321',
                verification_code_expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
                status_mode='offline'
            )
            db.session.add(u_verified)
            db.session.add(u_unverified)
            db.session.commit()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def test_register_flow(self):
        # 1. Register a new user
        res = self.client.post('/api/register', json={
            'username': 'newuser',
            'email': 'newuser@domain.com',
            'password': 'password123'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertTrue(data['requires_verification'])
        self.assertEqual(data['email'], 'newuser@domain.com')

        # Check in DB
        with app.app_context():
            user = User.query.filter_by(username='newuser').first()
            self.assertIsNotNone(user)
            self.assertFalse(user.is_verified)
            self.assertIsNotNone(user.verification_code)
            self.assertEqual(len(user.verification_code), 6)
            code = user.verification_code

        # 2. Verify with wrong code
        fail_res = self.client.post('/api/verify-email', json={
            'email': 'newuser@domain.com',
            'code': '000000'
        })
        self.assertEqual(fail_res.status_code, 400)
        self.assertFalse(fail_res.get_json()['success'])

        # 3. Verify with correct code
        ok_res = self.client.post('/api/verify-email', json={
            'email': 'newuser@domain.com',
            'code': code,
            'remember': True
        })
        self.assertEqual(ok_res.status_code, 200)
        self.assertTrue(ok_res.get_json()['success'])

        # Check DB updated
        with app.app_context():
            user = User.query.filter_by(username='newuser').first()
            self.assertTrue(user.is_verified)
            self.assertIsNone(user.verification_code)

    def test_login_unverified_user_blocked(self):
        # Attempt to login with unverified user -> Should fail with requires_verification
        res = self.client.post('/api/login', json={
            'username': 'unverified_user',
            'password': 'secret123'
        })
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertFalse(data['success'])
        self.assertTrue(data['requires_verification'])
        self.assertEqual(data['email'], 'unverified@astralpaws.com.tr')

    def test_login_verified_user_by_username_and_email(self):
        # Login with username
        res1 = self.client.post('/api/login', json={
            'username': 'verified_user',
            'password': 'secret123',
            'remember': True
        })
        self.assertEqual(res1.status_code, 200)
        self.assertTrue(res1.get_json()['success'])
        self.assertEqual(res1.get_json()['user']['username'], 'verified_user')

        # Logout
        self.client.post('/api/logout')

        # Login with email
        res2 = self.client.post('/api/login', json={
            'username': 'verified@astralpaws.com.tr',
            'password': 'secret123',
            'remember': False
        })
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(res2.get_json()['success'])
        self.assertEqual(res2.get_json()['user']['username'], 'verified_user')

    def test_resend_verification_code(self):
        res = self.client.post('/api/resend-verification', json={
            'email': 'unverified@astralpaws.com.tr'
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])

        with app.app_context():
            u = User.query.filter_by(username='unverified_user').first()
            self.assertIsNotNone(u.verification_code)
            self.assertEqual(len(u.verification_code), 6)

    def test_logout(self):
        # Login
        self.client.post('/api/login', json={
            'username': 'verified_user',
            'password': 'secret123'
        })

        # Check auth status
        status_res = self.client.get('/api/auth/status')
        self.assertTrue(status_res.get_json()['logged_in'])

        # Logout
        logout_res = self.client.post('/api/logout')
        self.assertEqual(logout_res.status_code, 200)
        self.assertTrue(logout_res.get_json()['success'])

        # Check auth status after logout
        status_res2 = self.client.get('/api/auth/status')
        self.assertFalse(status_res2.get_json()['logged_in'])

if __name__ == '__main__':
    unittest.main()
