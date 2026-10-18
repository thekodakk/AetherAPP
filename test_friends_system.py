import unittest
import json
from app import app, db, bcrypt
from models import *

class FriendsSystemTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()

        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.create_all()

            # Create test users
            from flask_bcrypt import generate_password_hash
            pw_hash = generate_password_hash('Password123!').decode('utf-8')
            
            self.user1 = User(username='alice', email='alice@astral.test', password_hash=pw_hash, is_verified=True, display_name='Alice Wonderland')
            self.user2 = User(username='bob', email='bob@astral.test', password_hash=pw_hash, is_verified=True, display_name='Bob Builder')
            self.user3 = User(username='charlie', email='charlie@astral.test', password_hash=pw_hash, is_verified=True, display_name='Charlie Chaplin')
            self.user4 = User(username='diana', email='diana@astral.test', password_hash=pw_hash, is_verified=True, display_name='Diana Prince')

            db.session.add_all([self.user1, self.user2, self.user3, self.user4])
            db.session.commit()

            self.u1_id = self.user1.id
            self.u2_id = self.user2.id
            self.u3_id = self.user3.id
            self.u4_id = self.user4.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def login(self, username, password='Password123!'):
        return self.client.post('/api/login', json={'username': username, 'password': password})

    # =========================================================================
    # 1. FRIEND REQUEST TESTS (SEND, PENDING, DUPLICATE, SELF)
    # =========================================================================
    def test_friend_request_creation_and_self_check(self):
        """Test sending a friend request and prevention of self-requests."""
        self.login('alice')

        # 1. Send request to oneself -> should fail (400)
        res_self = self.client.post('/api/friends/request', json={'user_id': self.u1_id})
        self.assertEqual(res_self.status_code, 400)
        self.assertFalse(res_self.get_json()['success'])

        # 2. Send valid request to Bob
        res_bob = self.client.post('/api/friends/request', json={'username': 'bob'})
        self.assertEqual(res_bob.status_code, 200)
        self.assertTrue(res_bob.get_json()['success'])
        friendship_id = res_bob.get_json()['friendship_id']

        # 3. Duplicate request should fail (400)
        res_dup = self.client.post('/api/friends/request', json={'username': 'bob'})
        self.assertEqual(res_dup.status_code, 400)
        self.assertIn('zaten', res_dup.get_json()['message'].lower())

        # 4. Check status in DB
        with self.app.app_context():
            f = db.session.get(Friendship, friendship_id)
            self.assertIsNotNone(f)
            self.assertEqual(f.status, 'pending')
            self.assertEqual(f.user_id, self.u1_id)
            self.assertEqual(f.friend_id, self.u2_id)

    def test_cancel_friend_request(self):
        """Test sender cancelling a pending friend request."""
        self.login('alice')
        res_req = self.client.post('/api/friends/request', json={'user_id': self.u2_id})
        f_id = res_req.get_json()['friendship_id']

        # Alice cancels her own request
        res_cancel = self.client.post(f'/api/friends/requests/{f_id}/cancel')
        self.assertEqual(res_cancel.status_code, 200)
        self.assertTrue(res_cancel.get_json()['success'])

        with self.app.app_context():
            f = db.session.get(Friendship, f_id)
            self.assertEqual(f.status, 'cancelled')

        # After cancellation, Alice can send a new request again
        res_retry = self.client.post('/api/friends/request', json={'user_id': self.u2_id})
        self.assertEqual(res_retry.status_code, 200)
        self.assertTrue(res_retry.get_json()['success'])

    def test_accept_friend_request(self):
        """Test receiver accepting a pending friend request."""
        self.login('alice')
        res_req = self.client.post('/api/friends/request', json={'user_id': self.u2_id})
        f_id = res_req.get_json()['friendship_id']

        # Alice cannot accept her own outgoing request -> 404 not found as pending receiver
        res_fail = self.client.post(f'/api/friends/requests/{f_id}/accept')
        self.assertEqual(res_fail.status_code, 404)

        # Bob logs in and accepts
        self.login('bob')
        res_accept = self.client.post(f'/api/friends/requests/{f_id}/accept')
        self.assertEqual(res_accept.status_code, 200)
        self.assertTrue(res_accept.get_json()['success'])

        # Verify accepted status in DB
        with self.app.app_context():
            f = db.session.get(Friendship, f_id)
            self.assertEqual(f.status, 'accepted')

        # Verify friends list for both users
        res_bob_friends = self.client.get('/api/friends')
        self.assertEqual(res_bob_friends.get_json()['counts']['all'], 1)
        self.assertEqual(res_bob_friends.get_json()['friends'][0]['user_id'], self.u1_id)

        self.login('alice')
        res_alice_friends = self.client.get('/api/friends')
        self.assertEqual(res_alice_friends.get_json()['counts']['all'], 1)
        self.assertEqual(res_alice_friends.get_json()['friends'][0]['user_id'], self.u2_id)

    def test_reject_friend_request(self):
        """Test receiver rejecting a pending friend request."""
        self.login('alice')
        res_req = self.client.post('/api/friends/request', json={'user_id': self.u2_id})
        f_id = res_req.get_json()['friendship_id']

        self.login('bob')
        res_rej = self.client.post(f'/api/friends/requests/{f_id}/reject')
        self.assertEqual(res_rej.status_code, 200)
        self.assertTrue(res_rej.get_json()['success'])

        with self.app.app_context():
            f = db.session.get(Friendship, f_id)
            self.assertEqual(f.status, 'rejected')

    # =========================================================================
    # 2. FRIEND REMOVAL TESTS
    # =========================================================================
    def test_remove_friend(self):
        """Test mutual friendship removal."""
        # Establish friendship
        with self.app.app_context():
            f = Friendship(user_id=self.u1_id, friend_id=self.u2_id, status='accepted')
            db.session.add(f)
            db.session.commit()

        self.login('alice')
        res_del = self.client.delete(f'/api/friends/{self.u2_id}')
        self.assertEqual(res_del.status_code, 200)
        self.assertTrue(res_del.get_json()['success'])

        # Check DB
        with self.app.app_context():
            f = Friendship.query.filter(
                ((Friendship.user_id == self.u1_id) & (Friendship.friend_id == self.u2_id)) |
                ((Friendship.user_id == self.u2_id) & (Friendship.friend_id == self.u1_id))
            ).first()
            self.assertIsNone(f)

    # =========================================================================
    # 3. BLOCKING SYSTEM TESTS
    # =========================================================================
    def test_blocking_and_unblocking(self):
        """Test blocking user, terminating existing friendship, and preventing interactions."""
        # Establish friendship first
        with self.app.app_context():
            f = Friendship(user_id=self.u1_id, friend_id=self.u2_id, status='accepted')
            db.session.add(f)
            db.session.commit()

        self.login('alice')

        # 1. Cannot block oneself
        res_self_block = self.client.post(f'/api/friends/{self.u1_id}/block')
        self.assertEqual(res_self_block.status_code, 400)

        # 2. Block Bob with reason
        res_block = self.client.post(f'/api/friends/{self.u2_id}/block', json={'reason': 'Spam'})
        self.assertEqual(res_block.status_code, 200)
        self.assertTrue(res_block.get_json()['success'])

        # 3. Existing friendship must be terminated
        with self.app.app_context():
            f = Friendship.query.filter_by(user_id=self.u1_id, friend_id=self.u2_id).first()
            self.assertIsNone(f)
            b = BlockedUser.query.filter_by(blocker_id=self.u1_id, blocked_id=self.u2_id).first()
            self.assertIsNotNone(b)
            self.assertEqual(b.reason, 'Spam')

        # 4. Bob tries to send friend request to Alice -> blocked (403)
        self.login('bob')
        res_blocked_req = self.client.post('/api/friends/request', json={'user_id': self.u1_id})
        self.assertEqual(res_blocked_req.status_code, 403)
        self.assertIn('engellendi', res_blocked_req.get_json()['message'].lower())

        # 5. Alice unblocks Bob
        self.login('alice')
        res_unblock = self.client.post(f'/api/friends/{self.u2_id}/unblock')
        self.assertEqual(res_unblock.status_code, 200)
        self.assertTrue(res_unblock.get_json()['success'])

        with self.app.app_context():
            b = BlockedUser.query.filter_by(blocker_id=self.u1_id, blocked_id=self.u2_id).first()
            self.assertIsNone(b)

    # =========================================================================
    # 4. PRIVATE FRIEND NOTES TESTS (ISOLATION & PRIVACY)
    # =========================================================================
    def test_private_friend_notes(self):
        """Test private note creation, updating, deletion, and viewer privacy isolation."""
        with self.app.app_context():
            f = Friendship(user_id=self.u1_id, friend_id=self.u2_id, status='accepted')
            db.session.add(f)
            db.session.commit()

        # Alice sets a private note for Bob
        self.login('alice')
        res_note = self.client.post(f'/api/friends/{self.u2_id}/note', json={'note': 'Tasarımcı dostum, Cumartesi buluşulacak'})
        self.assertEqual(res_note.status_code, 200)
        self.assertTrue(res_note.get_json()['success'])

        # Verify note is visible in Alice's GET /api/friends
        res_alice_friends = self.client.get('/api/friends')
        alice_data = res_alice_friends.get_json()
        self.assertEqual(alice_data['friends'][0]['note'], 'Tasarımcı dostum, Cumartesi buluşulacak')

        # Verify note is NOT visible to Bob (Bob's note field should be empty)
        self.login('bob')
        res_bob_friends = self.client.get('/api/friends')
        bob_data = res_bob_friends.get_json()
        self.assertEqual(bob_data['friends'][0]['note'], '')

        # Bob sets his own note for Alice
        res_bob_note = self.client.post(f'/api/friends/{self.u1_id}/note', json={'note': 'Backend geliştiricisi'})
        self.assertEqual(res_bob_note.status_code, 200)

        # Re-check Bob's view
        res_bob_friends2 = self.client.get('/api/friends')
        self.assertEqual(res_bob_friends2.get_json()['friends'][0]['note'], 'Backend geliştiricisi')

        # Re-check Alice's view (Alice still sees her own note, never Bob's note)
        self.login('alice')
        res_alice_friends2 = self.client.get('/api/friends')
        self.assertEqual(res_alice_friends2.get_json()['friends'][0]['note'], 'Tasarımcı dostum, Cumartesi buluşulacak')

    # =========================================================================
    # 5. CLOSE FRIENDS, FAVORITES & ONLINE NOTIFICATIONS
    # =========================================================================
    def test_close_friends_favorites_and_notifications(self):
        """Test toggling close friends, favorites, and online notifications."""
        with self.app.app_context():
            f = Friendship(user_id=self.u1_id, friend_id=self.u2_id, status='accepted')
            db.session.add(f)
            db.session.commit()

        self.login('alice')

        # 1. Toggle Close Friend
        res_close = self.client.post(f'/api/friends/{self.u2_id}/toggle-close')
        self.assertEqual(res_close.status_code, 200)
        self.assertTrue(res_close.get_json()['is_close_friend'])

        # 2. Toggle Favorite
        res_fav = self.client.post(f'/api/friends/{self.u2_id}/toggle-favorite')
        self.assertEqual(res_fav.status_code, 200)
        self.assertTrue(res_fav.get_json()['is_favorite'])

        # 3. Toggle Online Notification
        res_notif = self.client.post(f'/api/friends/{self.u2_id}/toggle-online-notify')
        self.assertEqual(res_notif.status_code, 200)
        self.assertTrue(res_notif.get_json()['notify_on_online'])

        # 4. Verify counts and lists in GET /api/friends
        res_friends = self.client.get('/api/friends')
        data = res_friends.get_json()
        self.assertEqual(data['counts']['close'], 1)
        self.assertEqual(data['counts']['favorites'], 1)
        self.assertEqual(len(data['close_friends']), 1)
        self.assertEqual(len(data['favorites']), 1)
        self.assertTrue(data['friends'][0]['is_close_friend'])
        self.assertTrue(data['friends'][0]['is_favorite'])
        self.assertTrue(data['friends'][0]['notify_on_online'])

        # 5. Verify Bob's viewer isolation (Bob's flags should remain False)
        self.login('bob')
        res_bob_friends = self.client.get('/api/friends')
        b_data = res_bob_friends.get_json()
        self.assertEqual(b_data['counts']['close'], 0)
        self.assertEqual(b_data['counts']['favorites'], 0)
        self.assertFalse(b_data['friends'][0]['is_close_friend'])
        self.assertFalse(b_data['friends'][0]['is_favorite'])
        self.assertFalse(b_data['friends'][0]['notify_on_online'])

    # =========================================================================
    # 6. FRIEND SUGGESTIONS TESTS (MUTUAL FRIENDS & COMMUNITIES)
    # =========================================================================
    def test_friend_suggestions(self):
        """Test friend suggestion algorithm based on mutual friends and servers."""
        with self.app.app_context():
            # Alice and Bob are friends
            # Charlie and Bob are friends
            # Alice and Charlie are NOT friends
            f1 = Friendship(user_id=self.u1_id, friend_id=self.u2_id, status='accepted')
            f2 = Friendship(user_id=self.u3_id, friend_id=self.u2_id, status='accepted')
            db.session.add_all([f1, f2])

            # Alice and Diana share a Server
            srv = Server(name="Gaming Zone", owner_id=self.u1_id, invite_code="gaming_zone_inv", icon_color="#6366f1")
            db.session.add(srv)
            db.session.commit()

            sm1 = ServerMember(server_id=srv.id, user_id=self.u1_id)
            sm2 = ServerMember(server_id=srv.id, user_id=self.u4_id)
            db.session.add_all([sm1, sm2])
            db.session.commit()

        # Alice checks suggestions
        self.login('alice')
        res_sugg = self.client.get('/api/friends/suggestions')
        self.assertEqual(res_sugg.status_code, 200)
        suggs = res_sugg.get_json()['suggestions']
        
        # Charlie should be suggested due to mutual friend Bob
        charlie_sugg = next((s for s in suggs if s['user_id'] == self.u3_id), None)
        self.assertIsNotNone(charlie_sugg)
        self.assertEqual(charlie_sugg['mutual_friends_count'], 1)
        self.assertIn('Bob Builder', charlie_sugg['mutual_friends_sample'])

        # Diana should be suggested due to mutual server
        diana_sugg = next((s for s in suggs if s['user_id'] == self.u4_id), None)
        self.assertIsNotNone(diana_sugg)
        self.assertEqual(diana_sugg['mutual_servers_count'], 1)

    # =========================================================================
    # 7. PROFILE INTEGRATION & BLOCK DETECTION
    # =========================================================================
    def test_profile_api_friend_integration(self):
        """Test GET /api/profile with friend notes and relationship status."""
        with self.app.app_context():
            f = Friendship(user_id=self.u1_id, friend_id=self.u2_id, status='accepted')
            f.set_note(self.u1_id, 'Özel not: Harika takım arkadaşı')
            f.is_favorite_user = True
            db.session.add(f)
            db.session.commit()

        self.login('alice')
        res_prof = self.client.get(f'/api/profile/bob')
        self.assertEqual(res_prof.status_code, 200)
        p_data = res_prof.get_json()
        self.assertEqual(p_data['friendship_status'], 'friends')
        self.assertEqual(p_data['friend_note'], 'Özel not: Harika takım arkadaşı')
        self.assertTrue(p_data['is_favorite'])

    # =========================================================================
    # 8. FRIEND CONTEXT MENU OPTIONS (PIN, NICKNAME, CLOSE DM, IGNORE)
    # =========================================================================
    def test_friend_context_menu_options(self):
        """Test friend 3-dots actions: pin, dm pin, nickname, close dm, ignore."""
        with self.app.app_context():
            f = Friendship(user_id=self.u1_id, friend_id=self.u2_id, status='accepted')
            db.session.add(f)
            db.session.commit()

        self.login('alice')

        # 1. Toggle Pin Friend
        res_pin = self.client.post(f'/api/friends/{self.u2_id}/toggle-pin')
        self.assertEqual(res_pin.status_code, 200)
        self.assertTrue(res_pin.get_json()['is_pinned'])

        # 2. Toggle Pin DM
        res_pdm = self.client.post(f'/api/friends/{self.u2_id}/toggle-pin-dm')
        self.assertEqual(res_pdm.status_code, 200)
        self.assertTrue(res_pdm.get_json()['is_dm_pinned'])

        # 3. Set Nickname
        res_nick = self.client.post(f'/api/friends/{self.u2_id}/nickname', json={'nickname': 'Kanka Bob'})
        self.assertEqual(res_nick.status_code, 200)
        self.assertEqual(res_nick.get_json()['nickname'], 'Kanka Bob')

        # 4. Toggle Ignore
        res_ign = self.client.post(f'/api/friends/{self.u2_id}/toggle-ignore')
        self.assertEqual(res_ign.status_code, 200)
        self.assertTrue(res_ign.get_json()['is_ignored'])

        # 5. Close DM
        res_close = self.client.post(f'/api/friends/{self.u2_id}/close-dm')
        self.assertEqual(res_close.status_code, 200)
        self.assertTrue(res_close.get_json()['is_dm_closed'])

        # 6. Verify in GET /api/friends
        res_f = self.client.get('/api/friends')
        f_data = res_f.get_json()['friends'][0]
        self.assertEqual(f_data['display_name'], 'Kanka Bob')
        self.assertEqual(f_data['nickname'], 'Kanka Bob')
        self.assertTrue(f_data['is_pinned'])
        self.assertTrue(f_data['is_dm_pinned'])
        self.assertTrue(f_data['is_ignored'])
        self.assertTrue(f_data['is_dm_closed'])

        # 7. Reopen DM
        res_open = self.client.post(f'/api/friends/{self.u2_id}/open-dm')
        self.assertEqual(res_open.status_code, 200)
        self.assertFalse(res_open.get_json()['is_dm_closed'])

        # 8. Check Bob's viewer isolation
        self.login('bob')
        res_bob_f = self.client.get('/api/friends')
        bob_f_data = res_bob_f.get_json()['friends'][0]
        self.assertFalse(bob_f_data['is_pinned'])
        self.assertFalse(bob_f_data['is_dm_pinned'])
        self.assertFalse(bob_f_data['is_ignored'])
        self.assertFalse(bob_f_data['is_dm_closed'])
        self.assertEqual(bob_f_data['nickname'], '')

if __name__ == '__main__':
    unittest.main()
