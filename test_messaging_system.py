import unittest
import json
from app import app, db
from models import User, Conversation, ConversationMember, Message, MessageAttachment, HiddenMessage, CustomEmoji, Server, Channel, ServerMember

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

    def test_message_pinning_lifecycle(self):
        """Test pinning, listing pinned messages, and unpinning."""
        self.login("alice")
        conv = self.client.post('/api/conversations/direct', json={"target_id": self.u2_id}).get_json()['conversation']
        conv_id = conv['id']

        msg = self.client.post(f'/api/conversations/{conv_id}/messages', json={"text": "Important announcement!"}).get_json()['message']
        msg_id = msg['id']

        # 1. Pin the message
        pin_res = self.client.post(f'/api/messages/{msg_id}/pin')
        self.assertEqual(pin_res.status_code, 200)
        self.assertTrue(pin_res.get_json()['is_pinned'])

        # 2. Get pinned messages in conversation
        pinned_list_res = self.client.get(f'/api/conversations/{conv_id}/pinned-messages')
        self.assertEqual(pinned_list_res.status_code, 200)
        pinned_data = pinned_list_res.get_json()
        self.assertTrue(pinned_data['success'])
        self.assertEqual(len(pinned_data['pinned_messages']), 1)
        self.assertEqual(pinned_data['pinned_messages'][0]['id'], msg_id)

        # 3. Unpin the message
        unpin_res = self.client.post(f'/api/messages/{msg_id}/pin')
        self.assertEqual(unpin_res.status_code, 200)
        self.assertFalse(unpin_res.get_json()['is_pinned'])

        # Check list is empty
        pinned_list_res2 = self.client.get(f'/api/conversations/{conv_id}/pinned-messages')
        self.assertEqual(len(pinned_list_res2.get_json()['pinned_messages']), 0)

    def test_saved_messages_and_bookmarks(self):
        """Test bookmarking/saving messages privately and searching within saved messages."""
        self.login("alice")
        conv = self.client.post('/api/conversations/direct', json={"target_id": self.u2_id}).get_json()['conversation']
        conv_id = conv['id']

        msg = self.client.post(f'/api/conversations/{conv_id}/messages', json={"text": "Save this recipe for later"}).get_json()['message']
        msg_id = msg['id']

        # 1. Save message
        save_res = self.client.post(f'/api/messages/{msg_id}/save', json={"note": "Dinner ideas"})
        self.assertIn(save_res.status_code, (200, 201))
        self.assertTrue(save_res.get_json()['is_saved'])

        # 2. List saved messages for Alice
        saved_list_res = self.client.get('/api/saved-messages')
        self.assertEqual(saved_list_res.status_code, 200)
        saved_items = saved_list_res.get_json()['saved_messages']
        self.assertEqual(len(saved_items), 1)
        self.assertEqual(saved_items[0]['message_id'], msg_id)
        self.assertIn("Save this recipe", saved_items[0]['message']['text'])

        # 3. Bob should NOT see Alice's saved messages
        self.login("bob")
        bob_saved = self.client.get('/api/saved-messages').get_json()
        self.assertEqual(len(bob_saved['saved_messages']), 0)

        # 4. Alice removes from saved
        self.login("alice")
        unsave_res = self.client.delete(f'/api/messages/{msg_id}/save')
        self.assertEqual(unsave_res.status_code, 200)
        self.assertFalse(unsave_res.get_json()['is_saved'])

    def test_advanced_message_search(self):
        """Test multi-parameter search (text query, username, date, file type)."""
        self.login("alice")
        conv = self.client.post('/api/conversations/direct', json={"target_id": self.u2_id}).get_json()['conversation']
        conv_id = conv['id']

        self.client.post(f'/api/conversations/{conv_id}/messages', json={"text": "Quantum computing update 2026"})
        self.client.post(f'/api/conversations/{conv_id}/messages', json={"text": "Regular chat hello"})
        self.client.post(f'/api/conversations/{conv_id}/messages', json={
            "text": "Check image",
            "attachments": [{"file_url": "/img.png", "file_type": "image", "file_name": "img.png"}]
        })

        # Search by text query
        s1 = self.client.get('/api/messages/search?q=Quantum').get_json()
        self.assertTrue(s1['success'])
        self.assertEqual(len(s1['results']), 1)
        self.assertIn("Quantum computing", s1['results'][0]['message']['text'])

        # Search by media type
        s2 = self.client.get('/api/messages/search?file_type=image').get_json()
        self.assertEqual(len(s2['results']), 1)
        self.assertEqual(s2['results'][0]['message']['attachments'][0]['file_type'], 'image')

        # Search by author
        s3 = self.client.get('/api/messages/search?username=alice').get_json()
        self.assertEqual(len(s3['results']), 3)

    def test_poll_creation_and_single_voting(self):
        """Test creating a poll, voting for an option, changing vote, and single-vote constraint."""
        self.login("alice")
        conv = self.client.post('/api/conversations/direct', json={"target_id": self.u2_id}).get_json()['conversation']
        conv_id = conv['id']

        # 1. Create poll
        poll_res = self.client.post(f'/api/conversations/{conv_id}/polls', json={
            "question": "What is the best cosmic beverage?",
            "options": ["Nebula Coffee", "Starlight Tea", "Solar Energy Drink"]
        })
        self.assertIn(poll_res.status_code, (200, 201))
        poll_msg = poll_res.get_json()['message']
        msg_id = poll_msg['id']
        self.assertIsNotNone(poll_msg['poll_data'])
        self.assertEqual(len(poll_msg['poll_data']['options']), 3)

        # 2. Alice votes for option 1 ("Nebula Coffee")
        v1_res = self.client.post(f'/api/messages/{msg_id}/poll/vote', json={"option_id": 1})
        self.assertEqual(v1_res.status_code, 200)
        pdata1 = v1_res.get_json()['poll_data']
        self.assertEqual(pdata1['total_votes'], 1)
        self.assertIn(self.u1_id, pdata1['options'][0]['votes'])

        # 3. Alice toggles to option 2 ("Starlight Tea") -> vote shifts to option 2, total remains 1!
        v2_res = self.client.post(f'/api/messages/{msg_id}/poll/vote', json={"option_id": 2})
        pdata2 = v2_res.get_json()['poll_data']
        self.assertEqual(pdata2['total_votes'], 1)
        self.assertNotIn(self.u1_id, pdata2['options'][0]['votes'])
        self.assertIn(self.u1_id, pdata2['options'][1]['votes'])

        # 4. Bob votes for option 1 -> total becomes 2
        self.login("bob")
        v3_res = self.client.post(f'/api/messages/{msg_id}/poll/vote', json={"option_id": 1})
        pdata3 = v3_res.get_json()['poll_data']
        self.assertEqual(pdata3['total_votes'], 2)

    def test_rich_embed_and_scheduled_messages(self):
        """Test rich embed cards and scheduled messages scheduling & processing."""
        self.login("alice")
        conv = self.client.post('/api/conversations/direct', json={"target_id": self.u2_id}).get_json()['conversation']
        conv_id = conv['id']

        # 1. Send Rich Embed
        embed_res = self.client.post(f'/api/conversations/{conv_id}/messages', json={
            "text": "Check this out",
            "embed_data": {
                "title": "Astral Update v3",
                "description": "Next gen real-time engine",
                "url": "https://astralpaws.test",
                "color": "#8b5cf6"
            }
        })
        self.assertIn(embed_res.status_code, (200, 201))
        embed_msg = embed_res.get_json()['message']
        self.assertEqual(embed_msg['embed_data']['title'], "Astral Update v3")

        # 2. Schedule a message for the future
        from datetime import datetime, timedelta, timezone
        future_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        sched_res = self.client.post('/api/messages/scheduled', json={
            "conversation_id": conv_id,
            "text": "Automated scheduled dispatch",
            "scheduled_for": future_time
        })
        self.assertIn(sched_res.status_code, (200, 201))
        sched_id = sched_res.get_json()['scheduled_message']['id']

        # Check in pending list
        sched_list = self.client.get('/api/messages/scheduled').get_json()
        self.assertEqual(len(sched_list['scheduled_messages']), 1)

        # 3. Backdate scheduled_for in DB to trigger execution
        with self.app.app_context():
            from models import ScheduledMessage
            s_obj = db.session.get(ScheduledMessage, sched_id)
            s_obj.scheduled_for = datetime.now(timezone.utc) - timedelta(minutes=5)
            db.session.commit()

        # Process due messages
        from routes_messaging import process_due_scheduled_and_expired_messages
        process_due_scheduled_and_expired_messages()

        # Check that scheduled message was dispatched
        msgs = self.client.get(f'/api/conversations/{conv_id}/messages').get_json()['messages']
        texts = [m['text'] for m in msgs]
        self.assertIn("Automated scheduled dispatch", texts)

    def test_ephemeral_message_expiration(self):
        """Test that ephemeral (disappearing) messages automatically expire when due."""
        self.login("alice")
        conv = self.client.post('/api/conversations/direct', json={"target_id": self.u2_id}).get_json()['conversation']
        conv_id = conv['id']

        # Send an ephemeral message with 1 second expiry
        msg_res = self.client.post(f'/api/conversations/{conv_id}/messages', json={
            "text": "This secret will self-destruct",
            "expires_in_seconds": 1
        })
        self.assertIn(msg_res.status_code, (200, 201))
        msg_id = msg_res.get_json()['message']['id']

        # Manually backdate expires_at to test expiration cleanup
        with self.app.app_context():
            from datetime import datetime, timedelta, timezone
            msg_obj = db.session.get(Message, msg_id)
            msg_obj.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
            db.session.commit()

        # Run processor
        from routes_messaging import process_due_scheduled_and_expired_messages
        process_due_scheduled_and_expired_messages()

        # Check that expired message is excluded from conversation messages API
        msgs = self.client.get(f'/api/conversations/{conv_id}/messages').get_json()['messages']
        target_msg = next((m for m in msgs if m['id'] == msg_id), None)
        self.assertIsNone(target_msg)

        # Check in DB that message was marked expired/deleted
        with self.app.app_context():
            msg_obj = db.session.get(Message, msg_id)
            self.assertTrue(msg_obj.is_deleted_everyone)
            self.assertIn("süresi doldu", msg_obj.text)

    def test_channel_message_send_and_authorization(self):
        """Test sending messages to a server channel and checking membership authorization."""
        with self.app.app_context():
            srv = Server(name="Astral Hub", owner_id=self.u1_id, invite_code="ASTRALHUB1", icon_color="#8b5cf6")
            db.session.add(srv)
            db.session.flush()
            chan = Channel(server_id=srv.id, name="genel-sohbet", type="text")
            mem = ServerMember(server_id=srv.id, user_id=self.u1_id, role="owner")
            db.session.add_all([chan, mem])
            db.session.commit()
            chan_id = chan.id

        # 1. Alice (server member) sends channel message
        self.login("alice")
        res = self.client.post(f'/api/messages/channel/{chan_id}', json={
            "text": "Hello channel members!"
        })
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['message']['text'], "Hello channel members!")
        self.assertEqual(data['message']['channel_id'], chan_id)

        # 2. Bob (not server member) tries to send channel message -> 403
        self.login("bob")
        bad_res = self.client.post(f'/api/messages/channel/{chan_id}', json={
            "text": "Intruder message"
        })
        self.assertEqual(bad_res.status_code, 403)

    def test_message_send_with_direct_attachment_url(self):
        """Test sending message with single attachment_url and attachment_type."""
        self.login("alice")
        conv = self.client.post('/api/conversations/direct', json={"target_id": self.u2_id}).get_json()['conversation']
        conv_id = conv['id']

        msg_res = self.client.post(f'/api/conversations/{conv_id}/messages', json={
            "text": "Check this picture",
            "attachment_url": "/static/uploads/image.png",
            "attachment_type": "image",
            "attachment_name": "image.png"
        })
        self.assertEqual(msg_res.status_code, 201)
        msg_data = msg_res.get_json()['message']
        self.assertEqual(msg_data['attachment_url'], "/static/uploads/image.png")
        self.assertEqual(msg_data['attachment_type'], "image")

    def test_message_send_unauthorized_and_non_member(self):
        """Test sending message to non-existent conversation or without membership."""
        # Unauthenticated request
        self.client.get('/api/logout')
        res = self.client.post('/api/conversations/999/messages', json={"text": "Anonymous msg"})
        self.assertIn(res.status_code, (302, 401))

        # Alice creates group with Bob only
        self.login("alice")
        grp = self.client.post('/api/conversations/group', json={
            "name": "Alice & Bob Secret",
            "member_ids": [self.u2_id]
        }).get_json()['conversation']
        grp_id = grp['id']

        # Charlie (not member) tries to post message to group -> 403
        self.login("charlie")
        non_mem_res = self.client.post(f'/api/conversations/{grp_id}/messages', json={"text": "I want to join"})
        self.assertEqual(non_mem_res.status_code, 403)

if __name__ == '__main__':
    unittest.main()

