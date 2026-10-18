import unittest
import json
import os
import tempfile
import io
from app import app, db, User, Server, Channel, Message, ServerMember, Friendship, process_ai_response

class NeonChatUltraTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        self.app = app
        self.client = app.test_client()

        with app.app_context():
            db.create_all()
            
            # Create Test User 1
            from flask_bcrypt import generate_password_hash
            u1 = User(
                username='alice',
                email='alice@example.com',
                password_hash=generate_password_hash('password123').decode('utf-8'),
                color='#8b5cf6',
                is_verified=True,
                status_mode='online',
                custom_status='Coding Neon Chat',
                bio='Alice in Cyberland',
                banner_color='#8b5cf6',
                badges='👑 Owner,⚡ Pro'
            )
            # Create Test User 2
            u2 = User(
                username='bob',
                email='bob@example.com',
                password_hash=generate_password_hash('password123').decode('utf-8'),
                color='#ec4899',
                is_verified=True,
                status_mode='idle',
                custom_status='Vibing',
                bio='Bob the Builder',
                banner_color='#ec4899',
                badges='🌟 Supporter'
            )
            db.session.add(u1)
            db.session.add(u2)
            db.session.commit()

            self.u1_id = u1.id
            self.u2_id = u2.id

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def login(self, username='alice', password='password123'):
        return self.client.post('/api/login', json={
            'username': username,
            'password': password
        })

    def test_auth_status(self):
        # Not logged in
        res = self.client.get('/api/auth/status')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertFalse(data['logged_in'])

        # Login
        log_res = self.login()
        self.assertEqual(log_res.status_code, 200)
        
        # Logged in
        res = self.client.get('/api/auth/status')
        data = res.get_json()
        self.assertTrue(data['logged_in'])
        self.assertEqual(data['user']['username'], 'alice')

    def test_registration(self):
        res = self.client.post('/api/register', json={
            'username': 'charlie',
            'email': 'charlie@example.com',
            'password': 'password123'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertTrue(data['requires_verification'])
        self.assertEqual(data['username'], 'charlie')

        with app.app_context():
            u = User.query.filter_by(username='charlie').first()
            code = u.verification_code

        v_res = self.client.post('/api/verify-email', json={
            'email': 'charlie@example.com',
            'code': code
        })
        self.assertEqual(v_res.status_code, 200)
        v_data = v_res.get_json()
        self.assertTrue(v_data['success'])
        self.assertEqual(v_data['user']['username'], 'charlie')

    def test_profile_update(self):
        self.login()
        res = self.client.post('/api/profile/update', json={
            'status_mode': 'dnd',
            'custom_status': 'Do Not Disturb - In Match',
            'bio': 'Pro Gamer',
            'banner_color': '#ef4444'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['user']['status_mode'], 'dnd')
        self.assertEqual(data['user']['custom_status'], 'Do Not Disturb - In Match')
        self.assertEqual(data['user']['bio'], 'Pro Gamer')

    def test_user_public_profile(self):
        self.login()
        res = self.client.get(f'/api/users/{self.u2_id}')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['user']['username'], 'bob')

    def test_friend_request_and_accept(self):
        self.login('alice', 'password123')
        
        # Alice sends request to Bob
        add_res = self.client.post('/api/friends/add', json={'username': 'bob'})
        self.assertEqual(add_res.status_code, 200)
        self.assertTrue(add_res.get_json()['success'])

        # Bob logs in and checks friends
        self.client.post('/api/logout')
        self.login('bob', 'password123')
        f_res = self.client.get('/api/friends')
        f_data = f_res.get_json()
        self.assertEqual(len(f_data['friends']), 1)
        self.assertEqual(f_data['friends'][0]['status'], 'pending')
        friendship_id = f_data['friends'][0]['friendship_id']

        # Bob accepts request
        acc_res = self.client.post('/api/friends/accept', json={'friendship_id': friendship_id})
        self.assertEqual(acc_res.status_code, 200)
        self.assertTrue(acc_res.get_json()['success'])

        # Check friends again
        f_res2 = self.client.get('/api/friends')
        f_data2 = f_res2.get_json()
        self.assertEqual(f_data2['friends'][0]['status'], 'accepted')

    def test_server_and_channels(self):
        self.login('alice', 'password123')
        
        # Create server
        create_res = self.client.post('/api/servers', json={'name': 'Cyber Squad'})
        self.assertEqual(create_res.status_code, 200)
        server_data = create_res.get_json()['server']
        server_id = server_data['id']
        invite_code = server_data['invite_code']

        # Get channels
        c_res = self.client.get(f'/api/servers/{server_id}/channels')
        self.assertEqual(c_res.status_code, 200)
        channels = c_res.get_json()['channels']
        self.assertGreaterEqual(len(channels), 3) # text, canvas, voice default channels

        # Create custom canvas channel
        add_c_res = self.client.post(f'/api/servers/{server_id}/channels', json={
            'name': 'artwork-room',
            'type': 'canvas'
        })
        self.assertEqual(add_c_res.status_code, 200)
        self.assertTrue(add_c_res.get_json()['success'])

        # Bob joins server with invite code
        self.client.post('/api/logout')
        self.login('bob', 'password123')
        join_res = self.client.post('/api/servers/join', json={'invite_code': invite_code})
        self.assertEqual(join_res.status_code, 200)
        self.assertTrue(join_res.get_json()['success'])

        # Check server members
        m_res = self.client.get(f'/api/servers/{server_id}/members')
        self.assertEqual(m_res.status_code, 200)
        members = m_res.get_json()['members']
        self.assertEqual(len(members), 2)

    def test_message_pin_and_search(self):
        self.login('alice', 'password123')
        
        with app.app_context():
            msg = Message(
                sender_id=self.u1_id,
                receiver_id=self.u2_id,
                text="Important meeting at 8 PM",
                is_pinned=False
            )
            db.session.add(msg)
            db.session.commit()
            msg_id = msg.id

        # Toggle Pin
        pin_res = self.client.post(f'/api/messages/{msg_id}/pin')
        self.assertEqual(pin_res.status_code, 200)
        self.assertTrue(pin_res.get_json()['is_pinned'])

        # Get Pins
        get_pins_res = self.client.get(f'/api/messages/pins?target_id={self.u2_id}')
        self.assertEqual(get_pins_res.status_code, 200)
        pins = get_pins_res.get_json()['pins']
        self.assertEqual(len(pins), 1)
        self.assertEqual(pins[0]['id'], msg_id)

        # Search messages
        search_res = self.client.get(f'/api/messages/search?q=meeting&target_id={self.u2_id}')
        self.assertEqual(search_res.status_code, 200)
        msgs = search_res.get_json()['messages']
        self.assertEqual(len(msgs), 1)

    def test_ai_engine(self):
        self.login('alice', 'password123')
        
        # Test Python code prompt
        res1 = self.client.post('/api/ai/ask', json={'prompt': 'Bana python örneği verir misin?'})
        self.assertEqual(res1.status_code, 200)
        data1 = res1.get_json()
        self.assertTrue(data1['success'])
        self.assertIn('python', data1['response'].lower())

        # Test Joke prompt
        res2 = self.client.post('/api/ai/ask', json={'prompt': 'Bize komik bir şaka yap'})
        self.assertEqual(res2.status_code, 200)
        data2 = res2.get_json()
        self.assertTrue(data2['success'])
        self.assertIn('şaka', data2['response'].lower())

    def test_file_upload(self):
        self.login('alice', 'password123')
        data = {
            'file': (io.BytesIO(b"fake image data"), 'test_image.png')
        }
        res = self.client.post('/api/upload', data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 200)
        out = res.get_json()
        self.assertTrue(out['success'])
        self.assertEqual(out['type'], 'image')
        self.assertIn('uploads/', out['url'])

if __name__ == '__main__':
    unittest.main()
