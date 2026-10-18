import unittest
import json
from app import app, db
from models import User, Conversation, ConversationMember, Message, MessageAttachment, HiddenMessage, CustomEmoji

class MessagingSystemTestCase(unittest.TestCase):
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

            from flask_bcrypt import generate_password_hash
            pw_hash = generate_password_hash('Password123!').decode('utf-8')

            # Create test users
            self.u1 = User(username="alice", public_id="astral_alice", email="alice@astral.test", password_hash=pw_hash, is_verified=True, display_name="Alice")
            self.u2 = User(username="bob", public_id="astral_bob", email="bob@astral.test", password_hash=pw_hash, is_verified=True, display_name="Bob")
            self.u3 = User(username="charlie", public_id="astral_charlie", email="charlie@astral.test", password_hash=pw_hash, is_verified=True, display_name="Charlie")

            db.session.add_all([self.u1, self.u2, self.u3])
            db.session.commit()

            self.u1_id = self.u1.id
            self.u2_id = self.u2.id
            self.u3_id = self.u3.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def login(self, username="alice", password="Password123!"):
        return self.client.post('/api/login', json={"username": username, "password": password})

    def test_direct_conversation_creation_and_listing(self):
        """Test creating and retrieving direct (1:1) conversations."""
        self.login("alice")
        res = self.client.post('/api/conversations/direct', json={"target_id": self.u2_id})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        conv_id = data['conversation']['id']
        self.assertEqual(data['conversation']['type'], 'direct')

        # Requesting direct conversation again should return the existing one
        res2 = self.client.post('/api/conversations/direct', json={"target_id": self.u2_id})
        data2 = res2.get_json()
        self.assertEqual(data2['conversation']['id'], conv_id)

        # Listing conversations
        list_res = self.client.get('/api/conversations')
        list_data = list_res.get_json()
        self.assertTrue(list_data['success'])
        self.assertEqual(len(list_data['conversations']), 1)
        self.assertEqual(list_data['conversations'][0]['id'], conv_id)

    def test_group_conversation_lifecycle(self):
        """Test group creation, renaming, adding members, and removing members."""
        self.login("alice")
        
        # 1. Create group with Bob and Charlie
        res = self.client.post('/api/conversations/group', json={
            "name": "Astral Explorers",
            "member_ids": [self.u2_id, self.u3_id]
        })
        self.assertIn(res.status_code, (200, 201))
        data = res.get_json()
        self.assertTrue(data['success'])
        group_id = data['conversation']['id']
        self.assertEqual(data['conversation']['name'], "Astral Explorers")
        self.assertEqual(data['conversation']['member_count'], 3)

        # 2. Get group details
        detail_res = self.client.get(f'/api/conversations/{group_id}')
        detail_data = detail_res.get_json()
        self.assertTrue(detail_data['success'])
        self.assertEqual(len(detail_data['conversation']['members']), 3)

        # 3. Rename group
        rename_res = self.client.put(f'/api/conversations/{group_id}', json={"name": "Cosmic Explorers"})
        self.assertEqual(rename_res.status_code, 200)
        self.assertEqual(rename_res.get_json()['conversation']['name'], "Cosmic Explorers")

        # 4. Remove a member (Alice removes Charlie)
        remove_res = self.client.delete(f'/api/conversations/{group_id}/members/{self.u3_id}')
        self.assertEqual(remove_res.status_code, 200)
        self.assertTrue(remove_res.get_json()['success'])

        # Check member count after removal
        detail_res2 = self.client.get(f'/api/conversations/{group_id}')
        self.assertEqual(len(detail_res2.get_json()['conversation']['members']), 2)

    def test_message_send_and_listing(self):
        """Test sending a message and fetching conversation history."""
        self.login("alice")
        res = self.client.post('/api/conversations/direct', json={"target_id": self.u2_id})
        conv_id = res.get_json()['conversation']['id']

        # Send text message
        msg_res = self.client.post(f'/api/conversations/{conv_id}/messages', json={
            "text": "Hello Bob! ||secret message|| ```js\nconsole.log(42);\n```",
            "attachments": [
                {
                    "file_url": "/uploads/test.png",
                    "file_name": "test.png",
                    "file_size": 1024,
                    "file_type": "image",
                    "is_spoiler": True
                }
            ]
        })
        self.assertIn(msg_res.status_code, (200, 201))
        msg_data = msg_res.get_json()
        self.assertTrue(msg_data['success'])
        self.assertIn("Hello Bob!", msg_data['message']['text'])
        self.assertEqual(len(msg_data['message']['attachments']), 1)
        self.assertTrue(msg_data['message']['attachments'][0]['is_spoiler'])

        # Fetch messages
        list_res = self.client.get(f'/api/conversations/{conv_id}/messages')
        list_data = list_res.get_json()
        self.assertEqual(len(list_data['messages']), 1)
        self.assertEqual(list_data['messages'][0]['text'], "Hello Bob! ||secret message|| ```js\nconsole.log(42);\n```")

    def test_message_editing_authorization(self):
        """Test that only message author can edit their message."""
        self.login("alice")
        conv = self.client.post('/api/conversations/direct', json={"target_id": self.u2_id}).get_json()['conversation']
        msg = self.client.post(f'/api/conversations/{conv["id"]}/messages', json={"text": "Original text"}).get_json()['message']
        msg_id = msg['id']

        # Alice edits her own message -> Success
        edit_res = self.client.put(f'/api/messages/{msg_id}', json={"text": "Edited text"})
        self.assertEqual(edit_res.status_code, 200)
        edit_json = edit_res.get_json()
        edited_msg = edit_json.get('updated_message') or edit_json.get('message')
        self.assertEqual(edited_msg['text'], "Edited text")
        self.assertTrue(edited_msg['is_edited'])

        # Bob logs in and tries to edit Alice's message -> 403 Forbidden
        self.login("bob")
        bad_edit = self.client.put(f'/api/messages/{msg_id}', json={"text": "Hacked text"})
        self.assertEqual(bad_edit.status_code, 403)

    def test_message_deletion_for_everyone_vs_for_me(self):
        """Test difference between Delete for Everyone vs Delete for Me."""
        self.login("alice")
        conv = self.client.post('/api/conversations/direct', json={"target_id": self.u2_id}).get_json()['conversation']
        conv_id = conv['id']
        msg1 = self.client.post(f'/api/conversations/{conv_id}/messages', json={"text": "Message 1 for me"}).get_json()['message']
        msg2 = self.client.post(f'/api/conversations/{conv_id}/messages', json={"text": "Message 2 for everyone"}).get_json()['message']

        # 1. Alice deletes msg1 "for me"
        del_me_res = self.client.delete(f'/api/messages/{msg1["id"]}', json={"delete_for_me": True})
        self.assertEqual(del_me_res.status_code, 200)
        self.assertTrue(del_me_res.get_json()['success'])

        # Alice listing: msg1 should NOT appear in Alice's messages
        alice_msgs = self.client.get(f'/api/conversations/{conv_id}/messages').get_json()['messages']
        alice_ids = [m['id'] for m in alice_msgs]
        self.assertNotIn(msg1['id'], alice_ids)
        self.assertIn(msg2['id'], alice_ids)

        # Bob listing: msg1 SHOULD still appear for Bob!
        self.login("bob")
        bob_msgs = self.client.get(f'/api/conversations/{conv_id}/messages').get_json()['messages']
        bob_ids = [m['id'] for m in bob_msgs]
        self.assertIn(msg1['id'], bob_ids)

        # 2. Alice deletes msg2 "for everyone"
        self.login("alice")
        del_everyone_res = self.client.delete(f'/api/messages/{msg2["id"]}', json={"delete_for_everyone": True})
        self.assertEqual(del_everyone_res.status_code, 200)

        # Both Alice and Bob should see the deleted tombstone
        alice_msgs2 = self.client.get(f'/api/conversations/{conv_id}/messages').get_json()['messages']
        msg2_alice = next(m for m in alice_msgs2 if m['id'] == msg2['id'])
        self.assertTrue(msg2_alice['is_deleted_everyone'])
        self.assertEqual(msg2_alice['text'], "🚫 Bu mesaj silindi.")

        self.login("bob")
        bob_msgs2 = self.client.get(f'/api/conversations/{conv_id}/messages').get_json()['messages']
        msg2_bob = next(m for m in bob_msgs2 if m['id'] == msg2['id'])
        self.assertTrue(msg2_bob['is_deleted_everyone'])

    def test_message_reply_and_forward(self):
        """Test replying to a message and forwarding to another conversation."""
        self.login("alice")
        conv1 = self.client.post('/api/conversations/direct', json={"target_id": self.u2_id}).get_json()['conversation']
        conv2 = self.client.post('/api/conversations/direct', json={"target_id": self.u3_id}).get_json()['conversation']

        # Original message
        orig_msg = self.client.post(f'/api/conversations/{conv1["id"]}/messages', json={"text": "Original announcement"}).get_json()['message']

        # Reply
        reply_res = self.client.post(f'/api/conversations/{conv1["id"]}/messages', json={
            "text": "I agree with this!",
            "reply_to_id": orig_msg['id']
        })
        self.assertIn(reply_res.status_code, (200, 201))
        reply_data = reply_res.get_json()['message']
        self.assertIsNotNone(reply_data['reply_to'])
        self.assertEqual(reply_data['reply_to']['id'], orig_msg['id'])
        self.assertEqual(reply_data['reply_to']['username'], "alice")

        # Forward to conv2
        forward_res = self.client.post(f'/api/messages/{orig_msg["id"]}/forward', json={
            "target_conversation_id": conv2['id']
        })
        self.assertIn(forward_res.status_code, (200, 201))
        forward_data = forward_res.get_json()['message']
        self.assertEqual(forward_data['conversation_id'], conv2['id'])
        self.assertIsNotNone(forward_data['forwarded_from'])
        self.assertEqual(forward_data['forwarded_from']['username'], "alice")

    def test_emoji_reaction_toggle(self):
        """Test adding and removing emoji reactions on messages."""
        self.login("alice")
        conv = self.client.post('/api/conversations/direct', json={"target_id": self.u2_id}).get_json()['conversation']
        msg = self.client.post(f'/api/conversations/{conv["id"]}/messages', json={"text": "React to me!"}).get_json()['message']
        msg_id = msg['id']

        # 1. Add reaction '❤️'
        react1 = self.client.post(f'/api/messages/{msg_id}/reaction', json={"emoji": "❤️"}).get_json()
        self.assertTrue(react1['success'])
        self.assertEqual(react1['action'], 'added')
        self.assertIn(self.u1_id, react1['reactions']['❤️'])

        # 2. Toggle same reaction '❤️' -> removed
        react2 = self.client.post(f'/api/messages/{msg_id}/reaction', json={"emoji": "❤️"}).get_json()
        self.assertEqual(react2['action'], 'removed')
        self.assertNotIn('❤️', react2['reactions'])

    def test_ssrf_protected_link_preview_scraper(self):
        """Test SSRF protection: reject localhost, loopback, private networks and invalid schemes."""
        self.login("alice")

        # Loopback IPv4
        res1 = self.client.post('/api/messages/link-preview', json={"url": "http://127.0.0.1:5000/api/conversations"})
        self.assertEqual(res1.status_code, 400)
        self.assertFalse(res1.get_json()['success'])

        # Localhost domain
        res2 = self.client.post('/api/messages/link-preview', json={"url": "http://localhost:8080/admin"})
        self.assertEqual(res2.status_code, 400)

        # Private Class C network
        res3 = self.client.post('/api/messages/link-preview', json={"url": "http://192.168.1.1/"})
        self.assertEqual(res3.status_code, 400)

        # Invalid scheme
        res4 = self.client.post('/api/messages/link-preview', json={"url": "file:///etc/passwd"})
        self.assertEqual(res4.status_code, 400)

    def test_custom_emojis_stickers_gifs_endpoints(self):
        """Test custom emojis, stickers catalog, and GIF search endpoint."""
        self.login("alice")

        # Custom emoji creation
        em_res = self.client.post('/api/emojis/custom', json={
            "name": "astral_paws",
            "image_url": "/static/stickers/astral_paw.png"
        })
        self.assertIn(em_res.status_code, (200, 201))
        self.assertTrue(em_res.get_json()['success'])

        # Custom emoji listing
        em_list = self.client.get('/api/emojis/custom').get_json()
        self.assertEqual(len(em_list['emojis']), 1)
        self.assertEqual(em_list['emojis'][0]['name'], "astral_paws")

        # Stickers listing
        stickers_res = self.client.get('/api/stickers')
        self.assertEqual(stickers_res.status_code, 200)
        self.assertGreater(len(stickers_res.get_json()['stickers']), 0)

        # GIF search
        gifs_res = self.client.get('/api/gifs/search?q=astro')
        self.assertEqual(gifs_res.status_code, 200)
        self.assertGreater(len(gifs_res.get_json()['gifs']), 0)

if __name__ == '__main__':
    unittest.main()
