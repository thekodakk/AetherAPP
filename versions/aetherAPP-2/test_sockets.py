import unittest
import json
from app import app, db, User, socketio, Message

class SocketIOTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app = app
        
        with app.app_context():
            db.drop_all()
            db.create_all()
            from flask_bcrypt import generate_password_hash
            u1 = User(
                username='alice',
                email='alice@example.com',
                password_hash=generate_password_hash('password123').decode('utf-8'),
                color='#8b5cf6',
                is_verified=True,
                status_mode='online',
                badges='👑 Owner,⚡ Pro'
            )
            u2 = User(
                username='bob',
                email='bob@example.com',
                password_hash=generate_password_hash('password123').decode('utf-8'),
                color='#ec4899',
                is_verified=True,
                status_mode='online'
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

    def test_socket_messaging_and_ai(self):
        # Authenticate client 1
        flask_client1 = self.app.test_client()
        flask_client1.post('/api/login', json={'username': 'alice', 'password': 'password123'})
        s_client1 = socketio.test_client(self.app, flask_test_client=flask_client1)
        self.assertTrue(s_client1.is_connected())

        # Send normal message
        s_client1.emit('send_message', {
            'text': 'Hello world from Neon Ultra!',
            'target_id': self.u2_id
        })
        received = s_client1.get_received()
        self.assertGreaterEqual(len(received), 1)
        msg_event = [r for r in received if r['name'] == 'receive_message'][0]
        msg_data = msg_event['args'][0]
        self.assertEqual(msg_data['text'], 'Hello world from Neon Ultra!')
        msg_id = msg_data['id']

        # Send @ai message
        s_client1.emit('send_message', {
            'text': '@ai bana python kodu yaz',
            'target_id': self.u2_id
        })
        received_ai = s_client1.get_received()
        ai_events = [r for r in received_ai if r['name'] == 'receive_message']
        self.assertGreaterEqual(len(ai_events), 1)
        ai_msg = [e['args'][0] for e in ai_events if e['args'][0]['username'] == 'Neon AI'][0]
        self.assertIn('python', ai_msg['text'].lower())

        # Test reaction
        s_client1.emit('message_reaction', {
            'message_id': msg_id,
            'emoji': '🚀'
        })
        rx_received = s_client1.get_received()
        rx_events = [r for r in rx_received if r['name'] == 'reaction_updated']
        self.assertEqual(len(rx_events), 1)
        self.assertIn('🚀', rx_events[0]['args'][0]['reactions'])

        # Test edit message
        s_client1.emit('edit_message', {
            'message_id': msg_id,
            'text': 'Edited text!'
        })
        edit_events = [r for r in s_client1.get_received() if r['name'] == 'message_edited']
        self.assertEqual(len(edit_events), 1)
        self.assertEqual(edit_events[0]['args'][0]['text'], 'Edited text!')

        # Test soundboard
        s_client1.emit('soundboard_play', {
            'sound_key': 'airhorn',
            'target_id': self.u2_id
        })
        sb_events = [r for r in s_client1.get_received() if r['name'] == 'soundboard_triggered']
        self.assertEqual(len(sb_events), 1)
        self.assertEqual(sb_events[0]['args'][0]['sound_key'], 'airhorn')

        # Test delete message
        s_client1.emit('delete_message', {
            'message_id': msg_id
        })
        del_events = [r for r in s_client1.get_received() if r['name'] == 'message_deleted']
        self.assertEqual(len(del_events), 1)
        self.assertEqual(del_events[0]['args'][0]['message_id'], msg_id)

        s_client1.disconnect()

    def test_direct_voice_calling_socket_events(self):
        # Client 1 (Alice)
        fc1 = self.app.test_client()
        fc1.post('/api/login', json={'username': 'alice', 'password': 'password123'})
        sc1 = socketio.test_client(self.app, flask_test_client=fc1)
        self.assertTrue(sc1.is_connected())

        # Client 2 (Bob)
        fc2 = self.app.test_client()
        fc2.post('/api/login', json={'username': 'bob', 'password': 'password123'})
        sc2 = socketio.test_client(self.app, flask_test_client=fc2)
        self.assertTrue(sc2.is_connected())

        # Alice calls Bob
        sc1.emit('call_user', {
            'target_id': self.u2_id,
            'call_type': 'audio'
        })
        received_bob = sc2.get_received()
        call_in_events = [r for r in received_bob if r['name'] == 'call_incoming']
        self.assertEqual(len(call_in_events), 1)
        self.assertEqual(call_in_events[0]['args'][0]['caller_name'], 'alice')

        # Bob accepts call
        sc2.emit('call_response', {
            'caller_id': self.u1_id,
            'accepted': True
        })
        received_alice = sc1.get_received()
        call_resp_events = [r for r in received_alice if r['name'] == 'call_response']
        self.assertEqual(len(call_resp_events), 1)
        self.assertTrue(call_resp_events[0]['args'][0]['accepted'])

        # Alice sends WebRTC signal offer
        sc1.emit('call_signal', {
            'target_id': self.u2_id,
            'signal': {'type': 'offer', 'sdp': 'mock_offer_sdp'}
        })
        received_bob_sig = sc2.get_received()
        sig_events = [r for r in received_bob_sig if r['name'] == 'call_signal']
        self.assertEqual(len(sig_events), 1)
        self.assertEqual(sig_events[0]['args'][0]['signal']['sdp'], 'mock_offer_sdp')

        # Bob ends call
        sc2.emit('call_end', {
            'target_id': self.u1_id
        })
        received_alice_end = sc1.get_received()
        end_events = [r for r in received_alice_end if r['name'] == 'call_ended']
        self.assertEqual(len(end_events), 1)
        self.assertEqual(end_events[0]['args'][0]['by_username'], 'bob')

        sc1.disconnect()
        sc2.disconnect()

if __name__ == '__main__':
    unittest.main()

