import unittest
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from app import app, db, seed_defaults
from models import (
    User, Server, ServerMember, Friendship, ProfileLink, ProfileProject,
    Badge, UserBadge, Achievement, UserAchievement
)
from routes_profile import ensure_default_badges_and_achievements, award_badge, award_achievement

class ProfileSystemTestCase(unittest.TestCase):
    def setUp(self):
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SECRET_KEY'] = 'test_secret_key_profile'
        
        self.client = app.test_client()
        
        with app.app_context():
            db.session.remove()
            db.drop_all()
            db.create_all()
            ensure_default_badges_and_achievements()
            from flask_bcrypt import generate_password_hash
            pwd_hash = generate_password_hash('Password123!').decode('utf-8')

            # Create User 1 (Alice)
            u1 = User(
                username='alice_profile',
                email='alice@example.com',
                password_hash=pwd_hash,
                is_verified=True,
                display_name='Alice Wonderland',
                bio='Adventurer in wonderland',
                created_at=datetime.now(timezone.utc) - timedelta(days=400) # > 1 year for badge test
            )
            db.session.add(u1)

            # Create User 2 (Bob)
            u2 = User(
                username='bob_builder',
                email='bob@example.com',
                password_hash=pwd_hash,
                is_verified=True,
                display_name='Bob The Builder',
                bio='Can we fix it? Yes we can!',
                created_at=datetime.now(timezone.utc) - timedelta(days=60) # > 1 month for badge test
            )
            db.session.add(u2)

            # Create User 3 (Charlie)
            u3 = User(
                username='charlie_chaplin',
                email='charlie@example.com',
                password_hash=pwd_hash,
                is_verified=True,
                display_name='Charlie',
                created_at=datetime.now(timezone.utc) - timedelta(days=2) # < 1 month
            )
            db.session.add(u3)

            db.session.commit()

            # Create mutual friendship between Alice and Charlie, and Bob and Charlie
            f1 = Friendship(user_id=u1.id, friend_id=u3.id, status='accepted')
            f2 = Friendship(user_id=u2.id, friend_id=u3.id, status='accepted')
            db.session.add_all([f1, f2])

            # Create Server owned by Alice where Bob is also a member
            srv = Server(name='Alice & Bob Community', owner_id=u1.id, invite_code='alice_srv_inv', icon_color='#8b5cf6')
            db.session.add(srv)
            db.session.commit()

            mem1 = ServerMember(server_id=srv.id, user_id=u1.id, role='owner')
            mem2 = ServerMember(server_id=srv.id, user_id=u2.id, role='member')
            db.session.add_all([mem1, mem2])
            db.session.commit()

            self.u1_id = u1.id
            self.u1_public_id = u1.public_id
            self.u2_id = u2.id
            self.u2_public_id = u2.public_id
            self.u3_id = u3.id

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def login(self, username='alice_profile', password='Password123!'):
        return self.client.post('/api/login', json={
            'username': username,
            'password': password
        })

    def test_default_badges_and_achievements_seeded(self):
        with app.app_context():
            badges = Badge.query.all()
            self.assertGreaterEqual(len(badges), 4)
            badge_codes = [b.code for b in badges]
            self.assertIn('beta_tester', badge_codes)
            self.assertIn('developer', badge_codes)
            self.assertIn('moderator_admin', badge_codes)
            self.assertIn('premium', badge_codes)

            achievements = Achievement.query.all()
            self.assertGreaterEqual(len(achievements), 5)
            ach_codes = [a.code for a in achievements]
            self.assertIn('first_message', ach_codes)
            self.assertIn('profile_architect', ach_codes)

    def test_account_age_badges(self):
        with app.app_context():
            alice = db.session.get(User, self.u1_id)
            bob = db.session.get(User, self.u2_id)
            charlie = db.session.get(User, self.u3_id)

            alice_badge = alice.get_account_age_badge()
            self.assertIsNotNone(alice_badge)
            self.assertEqual(alice_badge['code'], 'account_age_veteran')

            bob_badge = bob.get_account_age_badge()
            self.assertIsNotNone(bob_badge)
            self.assertEqual(bob_badge['code'], 'account_age_explorer')

            charlie_badge = charlie.get_account_age_badge()
            self.assertIsNotNone(charlie_badge)
            self.assertEqual(charlie_badge['code'], 'account_age_newbie')

    def test_get_profile_and_mutual_information(self):
        self.login('alice_profile', 'Password123!')

        # 1. Fetch own profile via public_id
        res = self.client.get(f'/api/profile/{self.u1_public_id}')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertTrue(data['is_self'])
        self.assertEqual(data['user']['username'], 'alice_profile')
        self.assertGreaterEqual(len(data['created_servers']), 1)

        # 2. Fetch Bob's profile as Alice (mutual friend Charlie, mutual server 'Alice & Bob Community')
        res = self.client.get(f'/api/profile/{self.u2_public_id}')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertFalse(data['is_self'])
        self.assertEqual(data['user']['username'], 'bob_builder')
        self.assertEqual(data['mutual_friends_count'], 1)
        self.assertEqual(data['mutual_friends'][0]['username'], 'charlie_chaplin')
        self.assertEqual(data['mutual_servers_count'], 1)
        self.assertEqual(data['mutual_servers'][0]['name'], 'Alice & Bob Community')

    def test_profile_theme_customization(self):
        self.login('alice_profile', 'Password123!')

        # Set custom theme
        res = self.client.post('/api/profile/theme', json={
            'accent_color': '#ec4899',
            'card_theme': 'neon-glow'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['profile_accent_color'], '#ec4899')
        self.assertEqual(data['profile_card_theme'], 'neon-glow')

        # Verify profile reflects theme
        res = self.client.get(f'/api/profile/{self.u1_public_id}')
        data = res.get_json()
        self.assertEqual(data['user']['profile_accent_color'], '#ec4899')
        self.assertEqual(data['user']['profile_card_theme'], 'neon-glow')

    def test_profile_privacy_and_hidden_communities(self):
        self.login('bob_builder', 'Password123!')

        # Hide communities on Bob's profile
        res = self.client.post('/api/profile/privacy-settings', json={
            'hide_communities': True,
            'last_seen_privacy': 'friends_only'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertTrue(data['hide_communities'])

        # Now login as Alice and view Bob's profile -> mutual and created servers should be hidden
        self.login('alice_profile', 'Password123!')
        res = self.client.get(f'/api/profile/{self.u2_public_id}')
        data = res.get_json()
        self.assertEqual(data['mutual_servers_count'], 0)
        self.assertEqual(len(data['created_servers']), 0)

    def test_social_links_crud(self):
        self.login('alice_profile', 'Password123!')

        # 1. Add link
        res = self.client.post('/api/profile/links', json={
            'platform': 'github',
            'title': 'My GitHub Profile',
            'url': 'https://github.com/alice'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        link_id = data['link']['id']
        self.assertEqual(data['link']['icon'], 'github')

        # 2. Get links
        res = self.client.get('/api/profile/links')
        data = res.get_json()
        self.assertEqual(len(data['links']), 1)
        self.assertEqual(data['links'][0]['title'], 'My GitHub Profile')

        # 3. Update link
        res = self.client.put('/api/profile/links', json={
            'id': link_id,
            'title': 'Alice Coding Hub',
            'url': 'https://github.com/alice-hub'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['link']['title'], 'Alice Coding Hub')

        # 4. Delete link
        res = self.client.delete('/api/profile/links', json={'id': link_id})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])

        res = self.client.get('/api/profile/links')
        self.assertEqual(len(res.get_json()['links']), 0)

    def test_projects_and_portfolio_crud(self):
        self.login('alice_profile', 'Password123!')

        # 1. Configure portfolio settings
        res = self.client.post('/api/profile/portfolio', json={
            'enabled': True,
            'title': 'Alice Creative Works',
            'description': 'Showcase of my open-source projects'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['portfolio']['enabled'])
        self.assertEqual(data['portfolio']['title'], 'Alice Creative Works')

        # 2. Add Project
        res = self.client.post('/api/profile/projects', json={
            'title': 'Astral Engine',
            'description': 'Next-gen realtime chat engine',
            'url': 'https://github.com/astral/engine',
            'image_url': 'https://images.unsplash.com/photo-1550745165-9bc0b252726f',
            'is_favorite': True
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        proj_id = data['project']['id']

        # 3. View profile with portfolio & projects
        res = self.client.get(f'/api/profile/{self.u1_public_id}')
        data = res.get_json()
        self.assertTrue(data['portfolio']['enabled'])
        self.assertEqual(len(data['projects']), 1)
        self.assertEqual(data['projects'][0]['title'], 'Astral Engine')

        # 4. Delete project
        res = self.client.delete('/api/profile/projects', json={'id': proj_id})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])

    def test_award_badge_and_achievement(self):
        with app.app_context():
            alice = db.session.get(User, self.u1_id)
            award_badge(alice, 'developer')
            award_achievement(alice, 'first_message')

            badges = alice.get_all_badges()
            achievements = alice.get_all_achievements()

            badge_names = [b['code'] for b in badges]
            ach_names = [a['code'] for a in achievements]

            self.assertIn('developer', badge_names)
            self.assertIn('first_message', ach_names)

if __name__ == '__main__':
    unittest.main()
