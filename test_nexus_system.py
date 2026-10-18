import unittest
import json
from app import app, db
from models import User, Nexus, NexusMember, NexusInvite, NexusApplication, Channel

class NexusSystemTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        self.app = app
        self.client = app.test_client()

        with app.app_context():
            db.session.remove()
            db.drop_all()
            db.create_all()

            from flask_bcrypt import generate_password_hash
            pw_hash = generate_password_hash('Password123!').decode('utf-8')

            self.u1 = User(username='alice', email='alice@astral.test', password_hash=pw_hash, is_verified=True, display_name='Alice')
            self.u2 = User(username='bob', email='bob@astral.test', password_hash=pw_hash, is_verified=True, display_name='Bob')
            self.u3 = User(username='charlie', email='charlie@astral.test', password_hash=pw_hash, is_verified=True, display_name='Charlie')

            db.session.add_all([self.u1, self.u2, self.u3])
            db.session.commit()

            self.u1_id = self.u1.id
            self.u2_id = self.u2.id
            self.u3_id = self.u3.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def login(self, username='alice', password='Password123!'):
        return self.client.post('/api/login', json={'username': username, 'password': password})

    def test_nexus_creation_and_details(self):
        self.login('alice')
        res = self.client.post('/api/nexus', json={
            'name': 'Astral Developers',
            'description': 'Hub for coders and creators',
            'category': 'Yazılım',
            'tags': ['python', 'flask', 'ai']
        })
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data['success'])
        nexus_id = data['nexus']['id']
        self.assertEqual(data['nexus']['name'], 'Astral Developers')
        self.assertEqual(len(data['nexus']['channels']), 2)

        # Get details
        res_det = self.client.get(f'/api/nexus/{nexus_id}')
        self.assertEqual(res_det.status_code, 200)
        det_data = res_det.get_json()
        self.assertTrue(det_data['success'])
        self.assertEqual(det_data['nexus']['name'], 'Astral Developers')
        self.assertTrue(det_data['nexus']['is_member'])

    def test_nexus_explore_and_my_nexuses(self):
        self.login('alice')
        self.client.post('/api/nexus', json={
            'name': 'Gaming Realm',
            'category': 'Oyun',
            'tags': ['rpg', 'mmo']
        })

        # Explore
        res_exp = self.client.get('/api/nexus/explore?category=Oyun')
        self.assertEqual(res_exp.status_code, 200)
        exp_data = res_exp.get_json()
        self.assertTrue(exp_data['success'])
        self.assertEqual(len(exp_data['nexuses']), 1)

        # My Nexuses
        res_my = self.client.get('/api/nexus/my')
        self.assertEqual(res_my.status_code, 200)
        my_data = res_my.get_json()
        self.assertTrue(my_data['success'])
        self.assertEqual(len(my_data['nexuses']), 1)

    def test_nexus_join_leave_and_invites(self):
        self.login('alice')
        res_create = self.client.post('/api/nexus', json={'name': 'Astral Music', 'category': 'Müzik'})
        nexus_id = res_create.get_json()['nexus']['id']

        # Bob joins
        self.login('bob')
        res_join = self.client.post(f'/api/nexus/{nexus_id}/join')
        self.assertEqual(res_join.status_code, 200)
        self.assertTrue(res_join.get_json()['success'])

        # Bob leaves
        res_leave = self.client.post(f'/api/nexus/{nexus_id}/leave')
        self.assertEqual(res_leave.status_code, 200)
        self.assertTrue(res_leave.get_json()['success'])

        # Alice creates invite code
        self.login('alice')
        res_inv = self.client.post(f'/api/nexus/{nexus_id}/invites', json={'max_uses': 5})
        self.assertEqual(res_inv.status_code, 201)
        code = res_inv.get_json()['invite']['code']

        # Bob joins via invite code
        self.login('bob')
        res_join_code = self.client.post('/api/nexus/join-by-code', json={'code': code})
        self.assertEqual(res_join_code.status_code, 200)
        self.assertTrue(res_join_code.get_json()['success'])

    def test_nexus_applications_and_review(self):
        self.login('alice')
        res_create = self.client.post('/api/nexus', json={
            'name': 'Elite Gamers',
            'category': 'Oyun',
            'requires_application': True
        })
        nexus_id = res_create.get_json()['nexus']['id']

        # Charlie applies
        self.login('charlie')
        res_app = self.client.post(f'/api/nexus/{nexus_id}/apply', json={
            'application_text': 'I have 10 years of esports experience.'
        })
        self.assertEqual(res_app.status_code, 201)
        app_id = res_app.get_json()['application']['id']

        # Alice reviews and accepts
        self.login('alice')
        res_review = self.client.post(f'/api/nexus/{nexus_id}/applications/{app_id}/review', json={
            'action': 'approve',
            'review_notes': 'Welcome to the team!'
        })
        self.assertEqual(res_review.status_code, 200)
        self.assertEqual(res_review.get_json()['application']['status'], 'approved')

        # Charlie is now a member
        self.login('charlie')
        res_my = self.client.get('/api/nexus/my')
        self.assertEqual(len(res_my.get_json()['nexuses']), 1)

if __name__ == '__main__':
    unittest.main()
