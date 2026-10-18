"""
AstralPaws - Messaging System Blueprint (routes_messaging.py)
Handles Direct Messages, Group Chats, Member Management, Message CRUD (edit, delete for everyone, delete for me),
Replies, Quotes, Forwards, Reactions, SSRF-safe Link Preview, Custom Emojis, Stickers, and GIFs.
"""

import os
import re
import json
import time
import socket
import ipaddress
import secrets
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from models import (
    db, User, Conversation, ConversationMember, Message,
    MessageAttachment, HiddenMessage, SavedMessage, ScheduledMessage,
    CustomEmoji, BlockedUser, Friendship, Channel, ServerMember
)

messaging_bp = Blueprint('messaging_bp', __name__)


# ===================================================================
# Helper Functions & SSRF-Safe Link Scraper
# ===================================================================

def sanitize_text(text: str, max_len: int = 4000) -> str:
    if not text:
        return ''
    return text.strip()[:max_len]


def is_user_blocked_between(user_a_id: int, user_b_id: int) -> bool:
    """Checks if either user has blocked the other."""
    return BlockedUser.is_blocked_between(user_a_id, user_b_id)


def broadcast_socket_event(event: str, data: dict, conv_id: int = None, user_id: int = None):
    """Safely broadcasts real-time socket events across conversation and user rooms."""
    try:
        from app import socketio
        if conv_id:
            socketio.emit(event, data, room=f"conv_{conv_id}")
            conv = db.session.get(Conversation, conv_id)
            if conv:
                for m in conv.members:
                    socketio.emit(event, data, room=f"user_{m.user_id}")
        elif user_id:
            socketio.emit(event, data, room=f"user_{user_id}")
        else:
            socketio.emit(event, data)
    except Exception:
        pass


def is_ip_private_or_restricted(ip_str: str) -> bool:
    """Checks if an IP address is private, loopback, link-local, or reserved."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_private or
            ip.is_loopback or
            ip.is_link_local or
            ip.is_multicast or
            ip.is_reserved or
            ip.is_unspecified or
            ip_str in ['0.0.0.0', '255.255.255.255']
        )
    except ValueError:
        return True


def is_safe_target_url(url: str) -> tuple[bool, str]:
    """
    Validates URL and checks DNS resolution to ensure no SSRF attacks
    to localhost / private networks.
    """
    if not url or not isinstance(url, str):
        return False, "Geçersiz URL."

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return False, "Sadece HTTP ve HTTPS protokolleri desteklenir."

    hostname = parsed.hostname
    if not hostname:
        return False, "Host adı bulunamadı."

    # Prevent obvious loopbacks/local domains
    if hostname.lower() in ('localhost', '127.0.0.1', '0.0.0.0') or hostname.endswith(('.local', '.internal', '.lan')):
        return False, "Yerel ağ adreslerine erişim engellendi."

    try:
        addr_info = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == 'https' else 80))
        for item in addr_info:
            ip_str = item[4][0]
            if is_ip_private_or_restricted(ip_str):
                return False, "Özel ağ adreslerine erişim engellendi."
    except Exception:
        return False, "Alan adı çözümlenemedi."

    return True, ""


class SimpleMetaHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.in_title = False
        self.og_title = ""
        self.og_desc = ""
        self.og_image = ""
        self.meta_desc = ""

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        tag_lower = tag.lower()
        if tag_lower == 'title':
            self.in_title = True
        elif tag_lower == 'meta':
            prop = attrs_dict.get('property', '').lower()
            name = attrs_dict.get('name', '').lower()
            content = attrs_dict.get('content', '')

            if prop == 'og:title' and not self.og_title:
                self.og_title = content
            elif prop == 'og:description' and not self.og_desc:
                self.og_desc = content
            elif prop == 'og:image' and not self.og_image:
                self.og_image = content
            elif name == 'description' and not self.meta_desc:
                self.meta_desc = content

    def handle_endtag(self, tag):
        if tag.lower() == 'title':
            self.in_title = False

    def handle_data(self, data):
        if self.in_title and not self.title:
            self.title = data.strip()


def get_or_create_direct_conv(user_a_id: int, user_b_id: int) -> Conversation:
    """Finds or creates a direct conversation between user_a and user_b."""
    # Look for existing direct conversation where both are members
    cm_a = ConversationMember.query.filter_by(user_id=user_a_id).all()
    conv_ids_a = [m.conversation_id for m in cm_a]

    if conv_ids_a:
        conv = Conversation.query.filter(
            Conversation.id.in_(conv_ids_a),
            Conversation.type == 'direct'
        ).join(ConversationMember).filter(ConversationMember.user_id == user_b_id).first()

        if conv:
            return conv

    # Create new direct conversation
    conv = Conversation(type='direct', created_by_id=user_a_id)
    db.session.add(conv)
    db.session.flush()

    m1 = ConversationMember(conversation_id=conv.id, user_id=user_a_id, role='owner')
    m2 = ConversationMember(conversation_id=conv.id, user_id=user_b_id, role='member')
    db.session.add_all([m1, m2])
    db.session.commit()
    return conv


# ===================================================================
# Conversation Endpoints (DMs & Groups)
# ===================================================================

@messaging_bp.route('/api/conversations', methods=['GET'])
@login_required
def get_conversations():
    """Lists all active direct messages and group conversations for current user."""
    memberships = ConversationMember.query.filter_by(user_id=current_user.id).all()
    conv_ids = [m.conversation_id for m in memberships]

    if not conv_ids:
        return jsonify({'success': True, 'conversations': []})

    convs = Conversation.query.filter(Conversation.id.in_(conv_ids)).order_by(Conversation.updated_at.desc()).all()
    return jsonify({
        'success': True,
        'conversations': [c.to_dict(viewer_id=current_user.id) for c in convs]
    })


@messaging_bp.route('/api/conversations/direct', methods=['POST'])
@login_required
def open_direct_conversation():
    """Opens or starts a 1-on-1 direct conversation with a target user."""
    data = request.get_json(silent=True) or {}
    target_id = data.get('target_id') or data.get('user_id')
    username = data.get('username')

    target_user = None
    if target_id:
        target_user = db.session.get(User, target_id)
    elif username:
        clean_uname = username.lstrip('@').strip()
        target_user = User.query.filter(db.func.lower(User.username) == clean_uname.lower()).first()

    if not target_user:
        return jsonify({'success': False, 'message': 'Kullanıcı bulunamadı.'}), 404

    if target_user.id == current_user.id:
        return jsonify({'success': False, 'message': 'Kendinizle direkt sohbet başlatamazsınız.'}), 400

    if is_user_blocked_between(current_user.id, target_user.id):
        return jsonify({'success': False, 'message': 'Engelleme nedeniyle bu kullanıcıyla sohbet başlatılamaz.'}), 403

    conv = get_or_create_direct_conv(current_user.id, target_user.id)
    return jsonify({
        'success': True,
        'conversation': conv.to_dict(viewer_id=current_user.id)
    })


@messaging_bp.route('/api/conversations/group', methods=['POST'])
@login_required
def create_group_conversation():
    """Creates a new group conversation with name, optional icon, and initial members."""
    data = request.get_json(silent=True) or {}
    name = sanitize_text(data.get('name', ''), max_len=100)
    icon_url = sanitize_text(data.get('icon_url', ''), max_len=255)
    member_ids = data.get('member_ids', [])

    if not name:
        name = "Yeni Grup Sohbeti"

    # Validate member_ids
    valid_user_ids = []
    for uid in member_ids:
        try:
            uid_int = int(uid)
            if uid_int != current_user.id and db.session.get(User, uid_int):
                if not is_user_blocked_between(current_user.id, uid_int):
                    valid_user_ids.append(uid_int)
        except (ValueError, TypeError):
            continue

    conv = Conversation(
        type='group',
        name=name,
        icon_url=icon_url if icon_url else None,
        created_by_id=current_user.id
    )
    db.session.add(conv)
    db.session.flush()

    # Add owner
    owner_member = ConversationMember(
        conversation_id=conv.id,
        user_id=current_user.id,
        role='owner'
    )
    db.session.add(owner_member)

    # Add other members
    for uid in set(valid_user_ids):
        db.session.add(ConversationMember(
            conversation_id=conv.id,
            user_id=uid,
            role='member'
        ))

    # Add initial system message
    sys_msg = Message(
        conversation_id=conv.id,
        sender_id=current_user.id,
        text=f"✨ **{current_user.get_effective_display_name()}** grubu oluşturdu: **{name}**",
        message_type='system'
    )
    db.session.add(sys_msg)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Grup sohbeti oluşturuldu.',
        'conversation': conv.to_dict(viewer_id=current_user.id)
    }), 201


@messaging_bp.route('/api/conversations/<int:conv_id>', methods=['GET'])
@login_required
def get_conversation_details(conv_id: int):
    """Retrieves conversation details, members, and roles."""
    conv = db.session.get(Conversation, conv_id)
    if not conv:
        return jsonify({'success': False, 'message': 'Sohbet bulunamadı.'}), 404

    if not conv.is_member(current_user.id):
        return jsonify({'success': False, 'message': 'Bu sohbete erişim yetkiniz yok.'}), 403

    # Update last read timestamp
    member_rec = conv.get_member_record(current_user.id)
    if member_rec:
        member_rec.last_read_at = datetime.now(timezone.utc)
        db.session.commit()

    return jsonify({
        'success': True,
        'conversation': conv.to_dict(viewer_id=current_user.id)
    })


@messaging_bp.route('/api/conversations/<int:conv_id>', methods=['PUT'])
@login_required
def update_group_conversation(conv_id: int):
    """Updates group conversation name or icon (owner/admin only)."""
    conv = db.session.get(Conversation, conv_id)
    if not conv or conv.type != 'group':
        return jsonify({'success': False, 'message': 'Grup sohbeti bulunamadı.'}), 404

    member_rec = conv.get_member_record(current_user.id)
    if not member_rec or member_rec.role not in ('owner', 'admin'):
        return jsonify({'success': False, 'message': 'Grup ayarlarını düzenleme yetkiniz yok.'}), 403

    data = request.get_json(silent=True) or {}
    if 'name' in data:
        conv.name = sanitize_text(data['name'], max_len=100) or conv.name
    if 'icon_url' in data:
        conv.icon_url = sanitize_text(data['icon_url'], max_len=255)

    conv.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Grup bilgileri güncellendi.',
        'conversation': conv.to_dict(viewer_id=current_user.id)
    })


@messaging_bp.route('/api/conversations/<int:conv_id>/members', methods=['POST'])
@login_required
def add_group_members(conv_id: int):
    """Adds new members to a group conversation."""
    conv = db.session.get(Conversation, conv_id)
    if not conv or conv.type != 'group':
        return jsonify({'success': False, 'message': 'Grup sohbeti bulunamadı.'}), 404

    if not conv.is_member(current_user.id):
        return jsonify({'success': False, 'message': 'Bu gruba üye ekleme yetkiniz yok.'}), 403

    data = request.get_json(silent=True) or {}
    user_ids = data.get('user_ids', [])
    if not isinstance(user_ids, list):
        user_ids = [user_ids]

    existing_uids = set(conv.get_member_user_ids())
    added_names = []

    for uid in user_ids:
        try:
            uid_int = int(uid)
            if uid_int not in existing_uids:
                u = db.session.get(User, uid_int)
                if u and not is_user_blocked_between(current_user.id, uid_int):
                    new_mem = ConversationMember(
                        conversation_id=conv.id,
                        user_id=uid_int,
                        role='member'
                    )
                    db.session.add(new_mem)
                    existing_uids.add(uid_int)
                    added_names.append(u.get_effective_display_name())
        except (ValueError, TypeError):
            continue

    if added_names:
        sys_msg = Message(
            conversation_id=conv.id,
            sender_id=current_user.id,
            text=f"➕ **{current_user.get_effective_display_name()}**, gruba yeni üye(ler) ekledi: {', '.join(added_names)}",
            message_type='system'
        )
        db.session.add(sys_msg)
        conv.updated_at = datetime.now(timezone.utc)
        db.session.commit()

    return jsonify({
        'success': True,
        'message': f"{len(added_names)} üye eklendi.",
        'conversation': conv.to_dict(viewer_id=current_user.id)
    })


@messaging_bp.route('/api/conversations/<int:conv_id>/members/<int:user_id>', methods=['DELETE'])
@login_required
def remove_group_member(conv_id: int, user_id: int):
    """Removes a member from a group (or leaves the group)."""
    conv = db.session.get(Conversation, conv_id)
    if not conv or conv.type != 'group':
        return jsonify({'success': False, 'message': 'Grup sohbeti bulunamadı.'}), 404

    viewer_member = conv.get_member_record(current_user.id)
    if not viewer_member:
        return jsonify({'success': False, 'message': 'Bu grupta değilsiniz.'}), 403

    target_member = conv.get_member_record(user_id)
    if not target_member:
        return jsonify({'success': False, 'message': 'Üye bulunamadı.'}), 404

    # Permission check: Self-leaving is allowed for anyone. Removing others requires owner/admin.
    is_leaving = (user_id == current_user.id)
    if not is_leaving:
        if viewer_member.role not in ('owner', 'admin'):
            return jsonify({'success': False, 'message': 'Üye çıkarma yetkiniz yok.'}), 403
        if target_member.role == 'owner':
            return jsonify({'success': False, 'message': 'Grup kurucusu gruptan çıkarılamaz.'}), 403

    target_user = target_member.user
    target_name = target_user.get_effective_display_name() if target_user else 'Kullanıcı'

    db.session.delete(target_member)

    sys_text = f"🚪 **{target_name}** gruptan ayrıldı." if is_leaving else f"🚫 **{target_name}**, **{current_user.get_effective_display_name()}** tarafından gruptan çıkarıldı."
    sys_msg = Message(
        conversation_id=conv.id,
        sender_id=current_user.id,
        text=sys_text,
        message_type='system'
    )
    db.session.add(sys_msg)
    conv.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'İşlem başarılı.',
        'is_left': is_leaving
    })


# ===================================================================
# Message Listing & CRUD Operations
# ===================================================================

@messaging_bp.route('/api/conversations/<int:conv_id>/messages', methods=['GET'])
@login_required
def get_conversation_messages(conv_id: int):
    """
    Fetches message history for a conversation.
    Filters out any messages hidden by the current user ('Delete for me').
    """
    conv = db.session.get(Conversation, conv_id)
    if not conv:
        return jsonify({'success': False, 'message': 'Sohbet bulunamadı.'}), 404

    if not conv.is_member(current_user.id):
        return jsonify({'success': False, 'message': 'Bu sohbete erişim yetkiniz yok.'}), 403

    limit = min(int(request.args.get('limit', 60)), 100)
    before_id = request.args.get('before_id')

    # Get list of hidden message IDs for this user
    hidden_ids = [h.message_id for h in HiddenMessage.query.filter_by(user_id=current_user.id).all()]

    query = Message.query.filter_by(conversation_id=conv_id)
    if hidden_ids:
        query = query.filter(~Message.id.in_(hidden_ids))

    # Exclude expired disappearing messages
    now = datetime.now(timezone.utc)
    query = query.filter(db.or_(Message.expires_at == None, Message.expires_at > now))

    if before_id and before_id.isdigit():
        query = query.filter(Message.id < int(before_id))

    msgs = query.order_by(Message.timestamp.asc()).limit(limit).all()

    # Update reader timestamp and last read message
    mem = conv.get_member_record(current_user.id)
    if mem:
        mem.last_read_at = now
        if msgs:
            mem.last_read_message_id = msgs[-1].id
        db.session.commit()

    return jsonify({
        'success': True,
        'messages': [m.to_dict(viewer_id=current_user.id) for m in msgs]
    })


@messaging_bp.route('/api/conversations/<int:conv_id>/messages', methods=['POST'])
@login_required
def send_conversation_message(conv_id: int):
    """Sends a message to a conversation (Guaranteed Database-First flow with real-time socket delivery)."""
    conv = db.session.get(Conversation, conv_id)
    if not conv:
        return jsonify({'success': False, 'message': 'Sohbet bulunamadı.'}), 404

    if not conv.is_member(current_user.id):
        return jsonify({'success': False, 'message': 'Bu sohbete mesaj gönderemezsiniz.'}), 403

    data = request.get_json(silent=True) or {}
    text = sanitize_text(data.get('text', ''), max_len=4000)
    message_type = data.get('message_type', 'text')
    raw_reply_to = data.get('reply_to_id')
    raw_forwarded_from = data.get('forwarded_from_id')
    attachments_data = data.get('attachments', [])
    attachment_url = data.get('attachment_url')
    attachment_type = data.get('attachment_type')
    attachment_name = data.get('attachment_name')
    expires_in_seconds = data.get('expires_in_seconds')
    poll_data_raw = data.get('poll_data')
    embed_data_raw = data.get('embed_data')

    if not text and not attachments_data and not attachment_url and not poll_data_raw and not embed_data_raw:
        return jsonify({'success': False, 'message': 'Mesaj içeriği, dosya, anket veya embed gereklidir.'}), 400

    reply_to_id = int(raw_reply_to) if raw_reply_to and str(raw_reply_to).isdigit() else None
    forwarded_from_id = int(raw_forwarded_from) if raw_forwarded_from and str(raw_forwarded_from).isdigit() else None

    expires_at = None
    if expires_in_seconds and int(expires_in_seconds) > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in_seconds))

    poll_data_str = None
    if poll_data_raw:
        message_type = 'poll'
        poll_data_str = json.dumps(poll_data_raw) if isinstance(poll_data_raw, dict) else str(poll_data_raw)

    embed_data_str = None
    if embed_data_raw:
        embed_data_str = json.dumps(embed_data_raw) if isinstance(embed_data_raw, dict) else str(embed_data_raw)

    # 1. Persist message to database
    msg = Message(
        conversation_id=conv.id,
        sender_id=current_user.id,
        text=text or ('📊 Anket' if poll_data_raw else ('Dosya Eki' if (attachments_data or attachment_url) else ('Kart' if embed_data_raw else 'Mesaj'))),
        message_type=message_type,
        attachment_url=attachment_url,
        attachment_type=attachment_type,
        attachment_name=attachment_name,
        reply_to_id=reply_to_id,
        forwarded_from_id=forwarded_from_id,
        expires_at=expires_at,
        poll_data=poll_data_str,
        embed_data=embed_data_str
    )
    db.session.add(msg)
    db.session.flush()

    if attachments_data:
        for att in attachments_data:
            if isinstance(att, dict) and att.get('file_url'):
                attachment = MessageAttachment(
                    message_id=msg.id,
                    file_url=att['file_url'],
                    file_name=att.get('file_name', 'file'),
                    file_size=att.get('file_size', 0),
                    file_type=att.get('file_type', 'file'),
                    mime_type=att.get('mime_type'),
                    is_spoiler=bool(att.get('is_spoiler', False))
                )
                db.session.add(attachment)

    conv.updated_at = datetime.now(timezone.utc)

    # Update sender's last read position to own sent message
    mem = conv.get_member_record(current_user.id)
    if mem:
        mem.last_read_at = datetime.now(timezone.utc)
        mem.last_read_message_id = msg.id

    db.session.commit()

    try:
        from routes_profile import award_achievement
        award_achievement(current_user.id, 'first_message')
    except Exception:
        pass

    msg_dict = msg.to_dict(viewer_id=current_user.id)

    # 2. Real-time socket broadcast to other conversation members
    try:
        broadcast_socket_event('receive_message', msg_dict, conv_id=conv.id)
        broadcast_socket_event('conversation_updated', {
            'conversation_id': conv.id,
            'last_message': msg_dict,
            'conversation': conv.to_dict()
        }, conv_id=conv.id)
    except Exception as sock_err:
        current_app.logger.warning(f"Socket broadcast warning: {sock_err}")

    # 3. Check for @ai / @astral ai auto-reply
    if text and ('@ai' in text.lower() or '@astral ai' in text.lower()):
        try:
            from app import process_ai_response
            cleaned = re.sub(r'@(ai|astral ai)\b', '', text, flags=re.IGNORECASE).strip()
            if not cleaned:
                cleaned = "Merhaba Astral AI!"
            reply_text = process_ai_response(cleaned)
            ai_msg_data = {
                'id': f"ai_{int(time.time() * 1000)}",
                'sender_id': 0,
                'conversation_id': conv.id,
                'username': 'Neon AI',
                'display_name': 'Astral AI',
                'color': '#8b5cf6',
                'badges': ['🤖 Astral AI', '⚡ Ollama Llama 3'],
                'text': reply_text,
                'timestamp': datetime.now().strftime('%H:%M'),
                'created_at': datetime.now(timezone.utc).isoformat(),
                'reply_to_id': msg.id,
                'reactions': {}
            }
            broadcast_socket_event('receive_message', ai_msg_data, conv_id=conv.id)
        except Exception as ai_err:
            current_app.logger.warning(f"AI response error: {ai_err}")

    # 4. Return successful response with serialized message to frontend
    return jsonify({
        'success': True,
        'message': msg_dict
    }), 201


@messaging_bp.route('/api/messages/channel/<int:channel_id>', methods=['POST'])
@login_required
def send_channel_message(channel_id: int):
    """Sends a message to a server channel (Guaranteed Database-First flow)."""
    channel = db.session.get(Channel, channel_id)
    if not channel:
        return jsonify({'success': False, 'message': 'Kanal bulunamadı.'}), 404

    if channel.server_id:
        member = ServerMember.query.filter_by(server_id=channel.server_id, user_id=current_user.id).first()
        if not member:
            return jsonify({'success': False, 'message': 'Bu sunucunun üyesi değilsiniz.'}), 403

    data = request.get_json(silent=True) or {}
    text = sanitize_text(data.get('text', ''), max_len=4000)
    message_type = data.get('message_type', 'text')
    raw_reply_to = data.get('reply_to_id')
    raw_forwarded_from = data.get('forwarded_from_id')
    attachments_data = data.get('attachments', [])
    attachment_url = data.get('attachment_url')
    attachment_type = data.get('attachment_type')
    attachment_name = data.get('attachment_name')
    expires_in_seconds = data.get('expires_in_seconds')
    poll_data_raw = data.get('poll_data')
    embed_data_raw = data.get('embed_data')

    if not text and not attachments_data and not attachment_url and not poll_data_raw and not embed_data_raw:
        return jsonify({'success': False, 'message': 'Mesaj içeriği veya dosya gereklidir.'}), 400

    reply_to_id = int(raw_reply_to) if raw_reply_to and str(raw_reply_to).isdigit() else None
    forwarded_from_id = int(raw_forwarded_from) if raw_forwarded_from and str(raw_forwarded_from).isdigit() else None

    expires_at = None
    if expires_in_seconds and int(expires_in_seconds) > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in_seconds))

    poll_data_str = None
    if poll_data_raw:
        message_type = 'poll'
        poll_data_str = json.dumps(poll_data_raw) if isinstance(poll_data_raw, dict) else str(poll_data_raw)

    embed_data_str = None
    if embed_data_raw:
        embed_data_str = json.dumps(embed_data_raw) if isinstance(embed_data_raw, dict) else str(embed_data_raw)

    msg = Message(
        channel_id=channel.id,
        sender_id=current_user.id,
        text=text or ('📊 Anket' if poll_data_raw else ('Dosya Eki' if (attachments_data or attachment_url) else ('Kart' if embed_data_raw else 'Mesaj'))),
        message_type=message_type,
        attachment_url=attachment_url,
        attachment_type=attachment_type,
        attachment_name=attachment_name,
        reply_to_id=reply_to_id,
        forwarded_from_id=forwarded_from_id,
        expires_at=expires_at,
        poll_data=poll_data_str,
        embed_data=embed_data_str
    )
    db.session.add(msg)
    db.session.flush()

    if attachments_data:
        for att in attachments_data:
            if isinstance(att, dict) and att.get('file_url'):
                attachment = MessageAttachment(
                    message_id=msg.id,
                    file_url=att['file_url'],
                    file_name=att.get('file_name', 'file'),
                    file_size=att.get('file_size', 0),
                    file_type=att.get('file_type', 'file'),
                    mime_type=att.get('mime_type'),
                    is_spoiler=bool(att.get('is_spoiler', False))
                )
                db.session.add(attachment)

    db.session.commit()

    try:
        from routes_profile import award_achievement
        award_achievement(current_user.id, 'first_message')
    except Exception:
        pass

    msg_dict = msg.to_dict(viewer_id=current_user.id)

    try:
        from app import socketio
        socketio.emit('receive_message', msg_dict, room=f"channel_{channel.id}")
    except Exception as sock_err:
        current_app.logger.warning(f"Channel socket broadcast warning: {sock_err}")

    # Check for @ai channel assistant
    if text and ('@ai' in text.lower() or '@astral ai' in text.lower()):
        try:
            from app import process_ai_response, socketio
            cleaned = re.sub(r'@(ai|astral ai)\b', '', text, flags=re.IGNORECASE).strip()
            if not cleaned:
                cleaned = "Merhaba Astral AI!"
            reply_text = process_ai_response(cleaned)
            ai_msg_data = {
                'id': f"ai_{int(time.time() * 1000)}",
                'sender_id': 0,
                'channel_id': channel.id,
                'username': 'Neon AI',
                'display_name': 'Astral AI',
                'color': '#8b5cf6',
                'badges': ['🤖 Astral AI', '⚡ Ollama Llama 3'],
                'text': reply_text,
                'timestamp': datetime.now().strftime('%H:%M'),
                'created_at': datetime.now(timezone.utc).isoformat(),
                'reply_to_id': msg.id,
                'reactions': {}
            }
            socketio.emit('receive_message', ai_msg_data, room=f"channel_{channel.id}")
        except Exception as ai_err:
            current_app.logger.warning(f"Channel AI response error: {ai_err}")

    return jsonify({
        'success': True,
        'message': msg_dict
    }), 201


@messaging_bp.route('/api/messages/<int:msg_id>', methods=['PUT'])
@login_required
def edit_message(msg_id: int):
    """Edits a message (author only)."""
    msg = db.session.get(Message, msg_id)
    if not msg:
        return jsonify({'success': False, 'message': 'Mesaj bulunamadı.'}), 404

    if msg.sender_id != current_user.id:
        return jsonify({'success': False, 'message': 'Yalnızca kendi mesajınızı düzenleyebilirsiniz.'}), 403

    if msg.is_deleted_everyone:
        return jsonify({'success': False, 'message': 'Silinmiş mesaj düzenlenemez.'}), 400
    data = request.get_json(silent=True) or {}
    new_text = sanitize_text(data.get('text', ''), max_len=4000)

    if not new_text:
        return jsonify({'success': False, 'message': 'Mesaj metni boş olamaz.'}), 400

    msg.text = new_text
    msg.is_edited = True
    msg.edited_at = datetime.now(timezone.utc)
    db.session.commit()

    msg_dict = msg.to_dict(viewer_id=current_user.id)
    if msg.conversation_id:
        broadcast_socket_event('message_edited', {
            'message_id': msg.id,
            'text': msg.text,
            'is_edited': True
        }, conv_id=msg.conversation_id)

    return jsonify({
        'success': True,
        'message': 'Mesaj güncellendi.',
        'updated_message': msg_dict
    })


@messaging_bp.route('/api/messages/<int:msg_id>', methods=['DELETE'])
@login_required
def delete_message(msg_id: int):
    """
    Deletes a message.
    Supports:
    - 'delete_for_everyone': Erases content/marks deleted for all (Author or Group Admin/Owner).
    - 'delete_for_me': Hides message only for current user via HiddenMessage.
    """
    msg = db.session.get(Message, msg_id)
    if not msg:
        return jsonify({'success': False, 'message': 'Mesaj bulunamadı.'}), 404

    data = request.get_json(silent=True) or {}
    delete_for_everyone = bool(data.get('delete_for_everyone', False))

    if delete_for_everyone:
        # Check permissions
        can_delete = (msg.sender_id == current_user.id)
        if not can_delete and msg.conversation_id:
            conv = db.session.get(Conversation, msg.conversation_id)
            if conv and conv.type == 'group':
                mem = conv.get_member_record(current_user.id)
                if mem and mem.role in ('owner', 'admin'):
                    can_delete = True

        if not can_delete:
            return jsonify({'success': False, 'message': 'Mesajı herkesten silme yetkiniz yok.'}), 403

        msg.is_deleted_everyone = True
        msg.text = '🚫 Bu mesaj silindi.'
        msg.attachment_url = None
        msg.reactions = '{}'
        db.session.commit()

        if msg.conversation_id:
            broadcast_socket_event('message_deleted', {
                'message_id': msg.id,
                'is_deleted_everyone': True,
                'text': '🚫 Bu mesaj silindi.'
            }, conv_id=msg.conversation_id)

        return jsonify({
            'success': True,
            'message': 'Mesaj herkesten silindi.',
            'mode': 'everyone',
            'message_id': msg_id
        })
    else:
        # Delete for me (hide for caller)
        hidden = HiddenMessage.query.filter_by(user_id=current_user.id, message_id=msg_id).first()
        if not hidden:
            hidden = HiddenMessage(user_id=current_user.id, message_id=msg_id)
            db.session.add(hidden)
            db.session.commit()

        broadcast_socket_event('message_hidden_for_me', {
            'message_id': msg_id
        }, user_id=current_user.id)

        return jsonify({
            'success': True,
            'message': 'Mesaj sadece sizin ekranınızdan kaldırıldı.',
            'mode': 'me',
            'message_id': msg_id
        })


@messaging_bp.route('/api/messages/<int:msg_id>/reaction', methods=['POST'])
@login_required
def toggle_message_reaction(msg_id: int):
    """Toggles an emoji reaction on a message."""
    msg = db.session.get(Message, msg_id)
    if not msg:
        return jsonify({'success': False, 'message': 'Mesaj bulunamadı.'}), 404

    data = request.get_json(silent=True) or {}
    emoji = sanitize_text(data.get('emoji', ''), max_len=60)

    if not emoji:
        return jsonify({'success': False, 'message': 'Emoji gereklidir.'}), 400

    try:
        rx = json.loads(msg.reactions) if msg.reactions else {}
    except Exception:
        rx = {}

    user_ids = rx.get(emoji, [])
    if current_user.id in user_ids:
        user_ids.remove(current_user.id)
        if not user_ids:
            rx.pop(emoji, None)
        else:
            rx[emoji] = user_ids
        added = False
    else:
        user_ids.append(current_user.id)
        rx[emoji] = user_ids
        added = True

    msg.reactions = json.dumps(rx)
    db.session.commit()

    if msg.conversation_id:
        broadcast_socket_event('reaction_updated', {
            'message_id': msg.id,
            'reactions': rx
        }, conv_id=msg.conversation_id)

    return jsonify({
        'success': True,
        'message_id': msg_id,
        'emoji': emoji,
        'added': added,
        'action': 'added' if added else 'removed',
        'reactions': rx
    })


@messaging_bp.route('/api/messages/<int:msg_id>/forward', methods=['POST'])
@login_required
def forward_message(msg_id: int):
    """Forwards a message to another conversation."""
    source_msg = db.session.get(Message, msg_id)
    if not source_msg or source_msg.is_deleted_everyone:
        return jsonify({'success': False, 'message': 'İletilecek mesaj bulunamadı.'}), 404

    data = request.get_json(silent=True) or {}
    target_conv_id = data.get('target_conversation_id')

    if not target_conv_id:
        return jsonify({'success': False, 'message': 'Hedef sohbet seçilmelidir.'}), 400

    target_conv = db.session.get(Conversation, target_conv_id)
    if not target_conv or not target_conv.is_member(current_user.id):
        return jsonify({'success': False, 'message': 'Hedef sohbete erişim yetkiniz yok.'}), 403

    forwarded_msg = Message(
        conversation_id=target_conv.id,
        sender_id=current_user.id,
        text=source_msg.text,
        message_type=source_msg.message_type,
        attachment_url=source_msg.attachment_url,
        attachment_type=source_msg.attachment_type,
        attachment_name=source_msg.attachment_name,
        forwarded_from_id=source_msg.id
    )
    db.session.add(forwarded_msg)
    db.session.flush()

    # Clone attachments if any
    for att in source_msg.attachments:
        db.session.add(MessageAttachment(
            message_id=forwarded_msg.id,
            file_url=att.file_url,
            file_name=att.file_name,
            file_size=att.file_size,
            file_type=att.file_type,
            mime_type=att.mime_type,
            is_spoiler=att.is_spoiler
        ))

    target_conv.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    forwarded_dict = forwarded_msg.to_dict(viewer_id=current_user.id)
    broadcast_socket_event('receive_message', forwarded_dict, conv_id=target_conv.id)
    broadcast_socket_event('conversation_updated', {
        'conversation_id': target_conv.id,
        'last_message': forwarded_dict
    }, conv_id=target_conv.id)

    return jsonify({
        'success': True,
        'message': forwarded_dict,
        'new_message': forwarded_dict
    }), 201


# ===================================================================
# SSRF-Protected Link Preview Service
# ===================================================================

@messaging_bp.route('/api/messages/link-preview', methods=['POST'])
@login_required
def get_link_preview():
    """
    Safely scrapes OpenGraph / HTML metadata for link previews.
    Guards strictly against SSRF and private IP queries.
    """
    data = request.get_json(silent=True) or {}
    url = (data.get('url') or '').strip()

    is_safe, error_msg = is_safe_target_url(url)
    if not is_safe:
        return jsonify({'success': False, 'message': error_msg}), 400

    try:
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'AstralPawsBot/1.0 (+https://astralpaws.com)',
                'Accept': 'text/html,application/xhtml+xml'
            }
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            content_type = resp.headers.get('Content-Type', '')
            if 'text/html' not in content_type and 'application/xhtml+xml' not in content_type:
                return jsonify({'success': False, 'message': 'HTML içeriği değil.'}), 400

            # Read max 100KB to prevent memory exhaustion
            raw_html = resp.read(102400).decode('utf-8', errors='ignore')

        parser = SimpleMetaHTMLParser()
        parser.feed(raw_html)

        title = parser.og_title or parser.title or ""
        description = parser.og_desc or parser.meta_desc or ""
        image = parser.og_image or ""

        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc

        if image and not image.startswith(('http://', 'https://')):
            image = urllib.parse.urljoin(url, image)

        return jsonify({
            'success': True,
            'preview': {
                'url': url,
                'domain': domain,
                'title': title[:200],
                'description': description[:350],
                'image': image if image.startswith(('http://', 'https://')) else ''
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': 'Link önizlemesi alınamadı.'}), 400


# ===================================================================
# Custom Emojis, Stickers, & GIFs Engine
# ===================================================================

@messaging_bp.route('/api/emojis/custom', methods=['GET'])
@login_required
def list_custom_emojis():
    """
    Returns custom emojis available on the platform.
    Supports global platform emojis and community/server scoped custom emojis.
    """
    server_id = request.args.get('server_id')
    query = CustomEmoji.query
    if server_id and server_id.isdigit():
        query = query.filter((CustomEmoji.server_id.is_(None)) | (CustomEmoji.server_id == int(server_id)))
    else:
        query = query.filter(CustomEmoji.server_id.is_(None))

    emojis = query.order_by(CustomEmoji.name.asc()).all()
    return jsonify({
        'success': True,
        'emojis': [e.to_dict() for e in emojis]
    })


@messaging_bp.route('/api/emojis/custom', methods=['POST'])
@login_required
def create_custom_emoji():
    """Creates a new custom emoji."""
    data = request.get_json(silent=True) or {}
    name = sanitize_text(data.get('name', ''), max_len=32).strip(': ')
    image_url = sanitize_text(data.get('image_url', ''), max_len=255)
    server_id = data.get('server_id')

    if not name or not image_url:
        return jsonify({'success': False, 'message': 'Emoji adı ve görsel bağlantısı gereklidir.'}), 400

    code = f":{name}:"
    existing = CustomEmoji.query.filter((CustomEmoji.name == name) | (CustomEmoji.code == code)).first()
    if existing:
        return jsonify({'success': False, 'message': 'Bu isimde bir özel emoji zaten var.'}), 400

    emoji = CustomEmoji(
        name=name,
        code=code,
        image_url=image_url,
        server_id=int(server_id) if server_id and str(server_id).isdigit() else None,
        created_by_id=current_user.id
    )
    db.session.add(emoji)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Özel emoji oluşturuldu.',
        'emoji': emoji.to_dict()
    }), 201


@messaging_bp.route('/api/stickers', methods=['GET'])
@login_required
def get_stickers_catalog():
    """Returns the built-in Astral sticker packs."""
    packs = [
        {
            'id': 'astral_paws_pack',
            'name': '🐾 Astral Paws Klasik',
            'stickers': [
                {'id': 'paws_wave', 'name': 'Astral Wave', 'url': 'https://api.iconify.design/twemoji:waving-hand.svg', 'image_url': 'https://api.iconify.design/twemoji:waving-hand.svg', 'emoji': '👋'},
                {'id': 'paws_sparkle', 'name': 'Star Cat', 'url': 'https://api.iconify.design/twemoji:cat-face.svg', 'image_url': 'https://api.iconify.design/twemoji:cat-face.svg', 'emoji': '🐱'},
                {'id': 'paws_rocket', 'name': 'Cosmic Rocket', 'url': 'https://api.iconify.design/twemoji:rocket.svg', 'image_url': 'https://api.iconify.design/twemoji:rocket.svg', 'emoji': '🚀'},
                {'id': 'paws_heart', 'name': 'Neon Heart', 'url': 'https://api.iconify.design/twemoji:sparkling-heart.svg', 'image_url': 'https://api.iconify.design/twemoji:sparkling-heart.svg', 'emoji': '💖'},
                {'id': 'paws_fire', 'name': 'Aura Fire', 'url': 'https://api.iconify.design/twemoji:fire.svg', 'image_url': 'https://api.iconify.design/twemoji:fire.svg', 'emoji': '🔥'},
                {'id': 'paws_party', 'name': 'Celebration', 'url': 'https://api.iconify.design/twemoji:party-popper.svg', 'image_url': 'https://api.iconify.design/twemoji:party-popper.svg', 'emoji': '🎉'}
            ]
        },
        {
            'id': 'cyber_vibes_pack',
            'name': '⚡ Cyber & Gaming',
            'stickers': [
                {'id': 'cyber_controller', 'name': 'Game On', 'url': 'https://api.iconify.design/twemoji:video-game.svg', 'image_url': 'https://api.iconify.design/twemoji:video-game.svg', 'emoji': '🎮'},
                {'id': 'cyber_laptop', 'name': 'Dev Mode', 'url': 'https://api.iconify.design/twemoji:laptop.svg', 'image_url': 'https://api.iconify.design/twemoji:laptop.svg', 'emoji': '💻'},
                {'id': 'cyber_headphone', 'name': 'Vibe Time', 'url': 'https://api.iconify.design/twemoji:headphone.svg', 'image_url': 'https://api.iconify.design/twemoji:headphone.svg', 'emoji': '🎧'},
                {'id': 'cyber_bot', 'name': 'Bot Friend', 'url': 'https://api.iconify.design/twemoji:robot.svg', 'image_url': 'https://api.iconify.design/twemoji:robot.svg', 'emoji': '🤖'}
            ]
        }
    ]
    all_stickers = [s for p in packs for s in p['stickers']]
    return jsonify({'success': True, 'packs': packs, 'stickers': all_stickers})


@messaging_bp.route('/api/gifs/search', methods=['GET'])
@login_required
def search_gifs():
    """
    Modular GIF provider endpoint.
    Offers curated high-quality GIFs catalogue and is designed to proxy Tenor / Giphy APIs.
    """
    q = (request.args.get('q') or '').strip().lower()

    # Curated high-performance GIFs catalogue with diverse themes
    catalog = [
        {'id': 'g1', 'title': 'Happy Dance', 'url': 'https://media.giphy.com/media/3o7abKhOpu0NwenH3O/giphy.gif', 'tags': ['happy', 'dance', 'excited', 'astral', 'party']},
        {'id': 'g2', 'title': 'Astral Cat Typing', 'url': 'https://media.giphy.com/media/JIX9t2j0ZTN9S/giphy.gif', 'tags': ['cat', 'typing', 'code', 'astro', 'astral', 'work']},
        {'id': 'g3', 'title': 'Mind Blown Galaxy', 'url': 'https://media.giphy.com/media/26ufdipQqU2lhNA4g/giphy.gif', 'tags': ['mind blown', 'wow', 'galaxy', 'astro', 'space', 'omg']},
        {'id': 'g4', 'title': 'High Five', 'url': 'https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif', 'tags': ['high five', 'friend', 'yes', 'team', 'agree']},
        {'id': 'g5', 'title': 'Applause', 'url': 'https://media.giphy.com/media/3o72FcJmLzIdYJdmDe/giphy.gif', 'tags': ['clap', 'bravo', 'applause', 'great', 'tebrik']},
        {'id': 'g6', 'title': 'Cosmic Space', 'url': 'https://media.giphy.com/media/26AHONQ79FdWZhAI0/giphy.gif', 'tags': ['space', 'cosmic', 'stars', 'astro', 'astral', 'future']},
        {'id': 'g7', 'title': 'Gaming Win', 'url': 'https://media.giphy.com/media/3o7TKTDnUxE0g2fSE8/giphy.gif', 'tags': ['gg', 'win', 'gamer', 'play', 'victory']},
        {'id': 'g8', 'title': 'Popcorn Time', 'url': 'https://media.giphy.com/media/t3cL1iXeEHwx2/giphy.gif', 'tags': ['popcorn', 'watching', 'lol', 'fun', 'film']},
        {'id': 'g9', 'title': 'Cute Wave Hello', 'url': 'https://media.giphy.com/media/dzaUX7CAG0Ihi/giphy.gif', 'tags': ['hello', 'hi', 'wave', 'selam', 'merhaba']},
        {'id': 'g10', 'title': 'Thumbs Up Hacker', 'url': 'https://media.giphy.com/media/13HgwGsXF0aiGY/giphy.gif', 'tags': ['ok', 'yes', 'thumbs up', 'dev', 'code', 'matrix']},
        {'id': 'g11', 'title': 'Shocked Pikachu', 'url': 'https://media.giphy.com/media/6nWhy3ulBL7GSCvKw6/giphy.gif', 'tags': ['shock', 'surprised', 'pikachu', 'meme', 'nani']},
        {'id': 'g12', 'title': 'Coffee Energy', 'url': 'https://media.giphy.com/media/3oriO04qxVReM5rJEA/giphy.gif', 'tags': ['coffee', 'morning', 'energy', 'work', 'kahve']}
    ]

    if q:
        filtered = [g for g in catalog if q in g['title'].lower() or any(q in t.lower() for t in g['tags'])]
    else:
        filtered = catalog

    return jsonify({
        'success': True,
        'gifs': filtered,
        'provider': 'Astral Curated GIF Engine (Modular & Extensible for Tenor/Giphy)'
    })


# ===================================================================
# 1. Mesaj Sabitleme (Pinned Messages) Endpoints
# ===================================================================

@messaging_bp.route('/api/messages/<int:msg_id>/pin', methods=['POST'])
@login_required
def toggle_pin_message(msg_id: int):
    """Pins or unpins a message in a conversation or channel."""
    msg = db.session.get(Message, msg_id)
    if not msg:
        return jsonify({'success': False, 'message': 'Mesaj bulunamadı.'}), 404

    # Permission check
    if msg.conversation_id:
        conv = db.session.get(Conversation, msg.conversation_id)
        if not conv or not conv.is_member(current_user.id):
            return jsonify({'success': False, 'message': 'Bu sohbette mesaj sabitleme yetkiniz yok.'}), 403
    elif msg.channel_id:
        # Channel permission (server member check)
        from models import Channel, ServerMember
        ch = db.session.get(Channel, msg.channel_id)
        if not ch or not ServerMember.query.filter_by(server_id=ch.server_id, user_id=current_user.id).first():
            return jsonify({'success': False, 'message': 'Bu kanalda mesaj sabitleme yetkiniz yok.'}), 403

    now = datetime.now(timezone.utc)
    msg.is_pinned = not msg.is_pinned
    msg.pinned_at = now if msg.is_pinned else None
    msg.pinned_by_id = current_user.id if msg.is_pinned else None
    db.session.commit()

    broadcast_socket_event('message_pinned_updated', {
        'message_id': msg.id,
        'conversation_id': msg.conversation_id,
        'channel_id': msg.channel_id,
        'is_pinned': msg.is_pinned,
        'pinned_by': current_user.username if msg.is_pinned else None,
        'pinned_at': msg.pinned_at.isoformat() if msg.pinned_at else None
    }, conv_id=msg.conversation_id)

    return jsonify({
        'success': True,
        'message': 'Mesaj sabitlendi.' if msg.is_pinned else 'Mesaj sabitlemesi kaldırıldı.',
        'is_pinned': msg.is_pinned,
        'message_data': msg.to_dict(viewer_id=current_user.id)
    })


@messaging_bp.route('/api/conversations/<int:conv_id>/pinned-messages', methods=['GET'])
@login_required
def get_conversation_pinned_messages(conv_id: int):
    """Retrieves all pinned messages in a conversation."""
    conv = db.session.get(Conversation, conv_id)
    if not conv or not conv.is_member(current_user.id):
        return jsonify({'success': False, 'message': 'Erişim yetkiniz yok.'}), 403

    now = datetime.now(timezone.utc)
    hidden_ids = [h.message_id for h in HiddenMessage.query.filter_by(user_id=current_user.id).all()]
    
    query = Message.query.filter(
        Message.conversation_id == conv_id,
        Message.is_pinned == True,
        Message.is_deleted_everyone == False,
        db.or_(Message.expires_at == None, Message.expires_at > now)
    )
    if hidden_ids:
        query = query.filter(~Message.id.in_(hidden_ids))

    pinned_msgs = query.order_by(Message.pinned_at.desc()).all()
    return jsonify({
        'success': True,
        'pinned_messages': [m.to_dict(viewer_id=current_user.id) for m in pinned_msgs]
    })


@messaging_bp.route('/api/channels/<int:channel_id>/pinned-messages', methods=['GET'])
@login_required
def get_channel_pinned_messages(channel_id: int):
    """Retrieves all pinned messages in a server channel."""
    from models import Channel, ServerMember
    ch = db.session.get(Channel, channel_id)
    if not ch:
        return jsonify({'success': False, 'message': 'Kanal bulunamadı.'}), 404

    now = datetime.now(timezone.utc)
    pinned_msgs = Message.query.filter(
        Message.channel_id == channel_id,
        Message.is_pinned == True,
        Message.is_deleted_everyone == False,
        db.or_(Message.expires_at == None, Message.expires_at > now)
    ).order_by(Message.pinned_at.desc()).all()

    return jsonify({
        'success': True,
        'pinned_messages': [m.to_dict(viewer_id=current_user.id) for m in pinned_msgs]
    })


@messaging_bp.route('/api/messages/pins', methods=['GET'])
@login_required
def get_legacy_pinned_messages():
    """Legacy endpoint for pinned messages querying by target_id or channel_id."""
    target_id = request.args.get('target_id', type=int)
    channel_id = request.args.get('channel_id', type=int)
    now = datetime.now(timezone.utc)

    query = Message.query.filter(
        Message.is_pinned == True,
        Message.is_deleted_everyone == False,
        db.or_(Message.expires_at == None, Message.expires_at > now)
    )

    if channel_id:
        query = query.filter(Message.channel_id == channel_id)
    elif target_id:
        query = query.filter(
            db.or_(
                db.and_(Message.sender_id == current_user.id, Message.receiver_id == target_id),
                db.and_(Message.sender_id == target_id, Message.receiver_id == current_user.id)
            )
        )

    pinned_msgs = query.order_by(Message.pinned_at.desc()).all()
    pins_list = [m.to_dict(viewer_id=current_user.id) for m in pinned_msgs]
    return jsonify({
        'success': True,
        'pins': pins_list,
        'pinned_messages': pins_list
    })


# ===================================================================
# 2. Mesaj Kaydetme & Yer İmleri (Saved Messages / Bookmarks)
# ===================================================================

@messaging_bp.route('/api/messages/<int:msg_id>/save', methods=['POST'])
@login_required
def save_message(msg_id: int):
    """Saves/bookmarks a message privately for current user."""
    msg = db.session.get(Message, msg_id)
    if not msg or msg.is_deleted_everyone:
        return jsonify({'success': False, 'message': 'Mesaj bulunamadı veya silinmiş.'}), 404

    # Permission check: must be a member of the conversation or channel
    if msg.conversation_id:
        conv = db.session.get(Conversation, msg.conversation_id)
        if not conv or not conv.is_member(current_user.id):
            return jsonify({'success': False, 'message': 'Erişim yetkiniz yok.'}), 403

    existing = SavedMessage.query.filter_by(user_id=current_user.id, message_id=msg_id).first()
    if existing:
        return jsonify({'success': True, 'message': 'Mesaj zaten kaydedilmiş.', 'is_saved': True})

    data = request.get_json(silent=True) or {}
    note = sanitize_text(data.get('note', ''), max_len=255)

    saved = SavedMessage(
        user_id=current_user.id,
        message_id=msg_id,
        note=note or None
    )
    db.session.add(saved)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '🔖 Mesaj yer imlerine kaydedildi!',
        'is_saved': True,
        'saved': saved.to_dict()
    }), 201


@messaging_bp.route('/api/messages/<int:msg_id>/save', methods=['DELETE'])
@login_required
def unsave_message(msg_id: int):
    """Removes a saved/bookmarked message for current user."""
    saved = SavedMessage.query.filter_by(user_id=current_user.id, message_id=msg_id).first()
    if not saved:
        return jsonify({'success': True, 'message': 'Mesaj zaten kayıtlı değil.', 'is_saved': False})

    db.session.delete(saved)
    db.session.commit()
    return jsonify({
        'success': True,
        'message': 'Mesaj yer imlerinden kaldırıldı.',
        'is_saved': False
    })


@messaging_bp.route('/api/saved-messages', methods=['GET'])
@login_required
def get_saved_messages():
    """Returns all messages bookmarked by the current user."""
    saved_items = SavedMessage.query.filter_by(user_id=current_user.id).order_by(SavedMessage.created_at.desc()).all()
    results = []
    for item in saved_items:
        msg = item.message
        if msg and not msg.is_deleted_everyone:
            conv_name = 'Sohbet'
            if msg.conversation:
                conv_name = msg.conversation.get_display_name(current_user.id)
            elif msg.channel_id:
                from models import Channel
                ch = db.session.get(Channel, msg.channel_id)
                if ch:
                    conv_name = f"#{ch.name}"

            results.append({
                'id': item.id,
                'message_id': item.message_id,
                'note': item.note,
                'saved_at': item.created_at.isoformat() if item.created_at else '',
                'conversation_name': conv_name,
                'conversation_id': msg.conversation_id,
                'channel_id': msg.channel_id,
                'message': msg.to_dict(viewer_id=current_user.id)
            })

    return jsonify({
        'success': True,
        'saved_messages': results,
        'total': len(results)
    })


# ===================================================================
# 3. Gelişmiş Mesaj Arama (Advanced Multi-Filter Search)
# ===================================================================

@messaging_bp.route('/api/messages/search', methods=['GET'])
@login_required
def search_messages():
    """
    Searches messages across accessible conversations and channels with multi-criteria filtering:
    - q: Text search substring
    - conversation_id: Specific conversation ID
    - channel_id: Specific channel ID
    - user_id / username: Author filter
    - file_type: Filter by media type ('image', 'video', 'audio', 'file', 'poll', 'link')
    - date_from, date_to: Date range
    """
    q_str = (request.args.get('q') or '').strip()
    conv_id = request.args.get('conversation_id')
    channel_id = request.args.get('channel_id')
    target_id = request.args.get('target_id')
    author_username = (request.args.get('username') or '').strip()
    author_id = request.args.get('user_id')
    file_type = (request.args.get('file_type') or '').strip().lower()
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    limit = min(int(request.args.get('limit', 50)), 100)

    # 1. Collect accessible conversation IDs for current user
    user_conv_ids = [cm.conversation_id for cm in ConversationMember.query.filter_by(user_id=current_user.id).all()]
    hidden_ids = [h.message_id for h in HiddenMessage.query.filter_by(user_id=current_user.id).all()]

    now = datetime.now(timezone.utc)
    query = Message.query.filter(
        Message.is_deleted_everyone == False,
        db.or_(Message.expires_at == None, Message.expires_at > now)
    )

    if target_id and target_id.isdigit():
        t_id = int(target_id)
        query = query.filter(
            db.or_(
                Message.conversation_id.in_(user_conv_ids),
                db.and_(Message.sender_id == current_user.id, Message.receiver_id == t_id),
                db.and_(Message.sender_id == t_id, Message.receiver_id == current_user.id)
            )
        )
    elif conv_id and conv_id.isdigit():
        target_conv_id = int(conv_id)
        if target_conv_id not in user_conv_ids:
            return jsonify({'success': False, 'message': 'Bu sohbette arama yetkiniz yok.'}), 403
        query = query.filter(Message.conversation_id == target_conv_id)
    else:
        # Search all accessible conversations and direct messages
        query = query.filter(
            db.or_(
                Message.conversation_id.in_(user_conv_ids),
                Message.sender_id == current_user.id,
                Message.receiver_id == current_user.id
            )
        )

    if hidden_ids:
        query = query.filter(~Message.id.in_(hidden_ids))

    # Text filter
    if q_str:
        query = query.filter(Message.text.ilike(f"%{q_str}%"))

    # Author filter
    if author_id and author_id.isdigit():
        query = query.filter(Message.sender_id == int(author_id))
    elif author_username:
        u = User.query.filter(User.username.ilike(author_username)).first()
        if u:
            query = query.filter(Message.sender_id == u.id)
        else:
            return jsonify({'success': True, 'results': [], 'total': 0})

    # File / Media Type filter
    if file_type:
        if file_type == 'poll':
            query = query.filter(Message.message_type == 'poll')
        elif file_type == 'link':
            query = query.filter(Message.text.ilike('%http%'))
        else:
            query = query.filter(
                db.or_(
                    Message.attachment_type == file_type,
                    Message.attachments.any(MessageAttachment.file_type == file_type)
                )
            )

    # Date Range filter
    if date_from:
        try:
            d_from = datetime.fromisoformat(date_from)
            query = query.filter(Message.timestamp >= d_from)
        except Exception:
            pass

    if date_to:
        try:
            d_to = datetime.fromisoformat(date_to) + timedelta(days=1)
            query = query.filter(Message.timestamp <= d_to)
        except Exception:
            pass

    messages = query.order_by(Message.timestamp.desc()).limit(limit).all()

    results = []
    for m in messages:
        conv_name = 'Sohbet'
        if m.conversation:
            conv_name = m.conversation.get_display_name(current_user.id)
        results.append({
            'message': m.to_dict(viewer_id=current_user.id),
            'conversation_id': m.conversation_id,
            'conversation_name': conv_name,
            'channel_id': m.channel_id
        })

    return jsonify({
        'success': True,
        'results': results,
        'messages': [r['message'] for r in results],
        'total': len(results)
    })


# ===================================================================
# 4. Mesaj Görüldü & Okunmamış Sayısı (Read Receipts & Sync)
# ===================================================================

@messaging_bp.route('/api/conversations/<int:conv_id>/read', methods=['POST'])
@login_required
def mark_conversation_as_read(conv_id: int):
    """Marks conversation as read up to the latest message."""
    conv = db.session.get(Conversation, conv_id)
    if not conv or not conv.is_member(current_user.id):
        return jsonify({'success': False, 'message': 'Erişim yetkiniz yok.'}), 403

    now = datetime.now(timezone.utc)
    mem = conv.get_member_record(current_user.id)
    if not mem:
        return jsonify({'success': False, 'message': 'Üyelik bulunamadı.'}), 404

    last_msg = Message.query.filter_by(conversation_id=conv_id).order_by(Message.id.desc()).first()
    mem.last_read_at = now
    if last_msg:
        mem.last_read_message_id = last_msg.id

    db.session.commit()

    broadcast_socket_event('conversation_read', {
        'conversation_id': conv_id,
        'user_id': current_user.id,
        'username': current_user.username,
        'last_read_at': now.isoformat(),
        'last_read_message_id': last_msg.id if last_msg else None
    }, conv_id=conv_id)

    return jsonify({
        'success': True,
        'conversation_id': conv_id,
        'last_read_at': now.isoformat(),
        'last_read_message_id': last_msg.id if last_msg else None
    })


# ===================================================================
# 5. Zamanlanmış Mesajlar (Scheduled Messages)
# ===================================================================

@messaging_bp.route('/api/messages/scheduled', methods=['POST'])
@login_required
def schedule_message():
    """Schedules a message to be sent at a future date and time."""
    data = request.get_json(silent=True) or {}
    conv_id = data.get('conversation_id')
    channel_id = data.get('channel_id')
    receiver_id = data.get('receiver_id')
    text = sanitize_text(data.get('text', ''), max_len=4000)
    scheduled_for_str = data.get('scheduled_for')
    expires_in_seconds = data.get('expires_in_seconds')
    poll_data_raw = data.get('poll_data')
    embed_data_raw = data.get('embed_data')

    if not scheduled_for_str:
        return jsonify({'success': False, 'message': 'Zamanlama tarihi gereklidir.'}), 400

    try:
        scheduled_for = datetime.fromisoformat(scheduled_for_str)
    except Exception:
        return jsonify({'success': False, 'message': 'Geçersiz tarih formatı.'}), 400

    now = datetime.now(timezone.utc)
    if scheduled_for.tzinfo is None:
        scheduled_for = scheduled_for.replace(tzinfo=timezone.utc)

    if scheduled_for <= now:
        return jsonify({'success': False, 'message': 'Zamanlama tarihi gelecekte bir an olmalıdır.'}), 400

    if not text and not poll_data_raw and not embed_data_raw:
        return jsonify({'success': False, 'message': 'Mesaj metni veya içeriği gereklidir.'}), 400

    # Permission check
    if conv_id:
        conv = db.session.get(Conversation, conv_id)
        if not conv or not conv.is_member(current_user.id):
            return jsonify({'success': False, 'message': 'Bu sohbete zamanlanmış mesaj gönderemezsiniz.'}), 403

    sched_msg = ScheduledMessage(
        user_id=current_user.id,
        conversation_id=conv_id,
        channel_id=channel_id,
        receiver_id=receiver_id,
        text=text,
        scheduled_for=scheduled_for,
        expires_in_seconds=int(expires_in_seconds) if expires_in_seconds else None,
        poll_data=json.dumps(poll_data_raw) if poll_data_raw else None,
        embed_data=json.dumps(embed_data_raw) if embed_data_raw else None,
        status='pending'
    )
    db.session.add(sched_msg)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f"Mesaj {scheduled_for.strftime('%d.%m.%Y %H:%M')} zamanına planlandı.",
        'scheduled_message': sched_msg.to_dict()
    }), 201


@messaging_bp.route('/api/messages/scheduled', methods=['GET'])
@login_required
def get_scheduled_messages():
    """Lists all pending scheduled messages for current user."""
    process_due_scheduled_and_expired_messages()
    items = ScheduledMessage.query.filter_by(user_id=current_user.id, status='pending').order_by(ScheduledMessage.scheduled_for.asc()).all()
    return jsonify({
        'success': True,
        'scheduled_messages': [it.to_dict() for it in items]
    })


@messaging_bp.route('/api/messages/scheduled/<int:sched_id>', methods=['PUT'])
@login_required
def update_scheduled_message(sched_id: int):
    """Edits a pending scheduled message."""
    item = db.session.get(ScheduledMessage, sched_id)
    if not item or item.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Zamanlanmış mesaj bulunamadı.'}), 404

    if item.status != 'pending':
        return jsonify({'success': False, 'message': 'Yalnızca bekleyen zamanlanmış mesajlar düzenlenebilir.'}), 400

    data = request.get_json(silent=True) or {}
    if 'text' in data:
        item.text = sanitize_text(data['text'], max_len=4000)
    if 'scheduled_for' in data:
        try:
            dt = datetime.fromisoformat(data['scheduled_for'])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt > datetime.now(timezone.utc):
                item.scheduled_for = dt
        except Exception:
            pass

    db.session.commit()
    return jsonify({'success': True, 'message': 'Zamanlanmış mesaj güncellendi.', 'scheduled_message': item.to_dict()})


@messaging_bp.route('/api/messages/scheduled/<int:sched_id>', methods=['DELETE'])
@login_required
def cancel_scheduled_message(sched_id: int):
    """Cancels/deletes a scheduled message."""
    item = db.session.get(ScheduledMessage, sched_id)
    if not item or item.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Zamanlanmış mesaj bulunamadı.'}), 404

    item.status = 'cancelled'
    db.session.delete(item)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Zamanlanmış mesaj iptal edildi.'})


# ===================================================================
# 6. Anketler (Polls System)
# ===================================================================

@messaging_bp.route('/api/conversations/<int:conv_id>/polls', methods=['POST'])
@login_required
def create_conversation_poll(conv_id: int):
    """Creates an interactive poll message."""
    conv = db.session.get(Conversation, conv_id)
    if not conv or not conv.is_member(current_user.id):
        return jsonify({'success': False, 'message': 'Bu sohbette anket oluşturamazsınız.'}), 403

    data = request.get_json(silent=True) or {}
    question = sanitize_text(data.get('question', ''), max_len=255)
    options_raw = data.get('options', [])

    if not question:
        return jsonify({'success': False, 'message': 'Anket sorusu gereklidir.'}), 400

    clean_options = []
    for idx, opt in enumerate(options_raw):
        opt_text = sanitize_text(opt if isinstance(opt, str) else opt.get('text', ''), max_len=100)
        if opt_text:
            clean_options.append({
                'id': idx + 1,
                'text': opt_text,
                'votes': []
            })

    if len(clean_options) < 2:
        return jsonify({'success': False, 'message': 'En az 2 seçenek gereklidir.'}), 400

    poll_dict = {
        'question': question,
        'options': clean_options,
        'total_votes': 0,
        'closed': False,
        'created_by': current_user.username
    }

    msg = Message(
        conversation_id=conv.id,
        sender_id=current_user.id,
        text=f"📊 Anket: {question}",
        message_type='poll',
        poll_data=json.dumps(poll_dict)
    )
    db.session.add(msg)
    conv.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    msg_dict = msg.to_dict(viewer_id=current_user.id)
    broadcast_socket_event('receive_message', msg_dict, conv_id=conv.id)
    return jsonify({'success': True, 'message': msg_dict}), 201


@messaging_bp.route('/api/messages/<int:msg_id>/poll/vote', methods=['POST'])
@login_required
def vote_on_poll(msg_id: int):
    """Casts or toggles a vote on a poll message."""
    msg = db.session.get(Message, msg_id)
    if not msg or not msg.poll_data or msg.is_deleted_everyone:
        return jsonify({'success': False, 'message': 'Anket bulunamadı.'}), 404

    # Permission check
    if msg.conversation_id:
        conv = db.session.get(Conversation, msg.conversation_id)
        if not conv or not conv.is_member(current_user.id):
            return jsonify({'success': False, 'message': 'Bu ankete oy verme yetkiniz yok.'}), 403

    try:
        poll_dict = json.loads(msg.poll_data)
    except Exception:
        return jsonify({'success': False, 'message': 'Geçersiz anket verisi.'}), 500

    if poll_dict.get('closed'):
        return jsonify({'success': False, 'message': 'Bu anket oylamaya kapatılmıştır.'}), 400

    data = request.get_json(silent=True) or {}
    option_id = int(data.get('option_id', 0))

    user_id = current_user.id
    target_opt = None
    
    # Remove user's previous votes from all options (single choice enforcement)
    for opt in poll_dict.get('options', []):
        if user_id in opt.get('votes', []):
            opt['votes'].remove(user_id)
        if opt.get('id') == option_id:
            target_opt = opt

    # Toggle vote on target option
    if target_opt:
        target_opt.setdefault('votes', []).append(user_id)

    # Recalculate total votes
    total = sum(len(opt.get('votes', [])) for opt in poll_dict.get('options', []))
    poll_dict['total_votes'] = total

    msg.poll_data = json.dumps(poll_dict)
    db.session.commit()

    broadcast_socket_event('poll_updated', {
        'message_id': msg.id,
        'conversation_id': msg.conversation_id,
        'channel_id': msg.channel_id,
        'poll_data': poll_dict
    }, conv_id=msg.conversation_id)

    return jsonify({
        'success': True,
        'poll_data': poll_dict,
        'message_id': msg.id
    })


# ===================================================================
# Helper: Scheduled & Expired Messages Processing
# ===================================================================

def process_due_scheduled_and_expired_messages():
    """Processes due scheduled messages and expires ephemeral messages."""
    from flask import current_app, has_app_context
    if not has_app_context():
        from app import app
        with app.app_context():
            _run_scheduled_and_expired_processing()
    else:
        _run_scheduled_and_expired_processing()

def _run_scheduled_and_expired_processing():
    try:
        now_utc = datetime.now(timezone.utc)
        now_naive = datetime.utcnow()
        # 1. Process Due Scheduled Messages
        due_items = ScheduledMessage.query.filter(
            ScheduledMessage.status == 'pending',
            db.or_(ScheduledMessage.scheduled_for <= now_utc, ScheduledMessage.scheduled_for <= now_naive)
        ).all()

        for item in due_items:
            expires_at = None
            if item.expires_in_seconds:
                expires_at = now_utc + timedelta(seconds=item.expires_in_seconds)

            msg = Message(
                conversation_id=item.conversation_id,
                channel_id=item.channel_id,
                receiver_id=item.receiver_id,
                sender_id=item.user_id,
                text=item.text,
                message_type=item.message_type or 'text',
                attachment_url=item.attachment_url,
                attachment_type=item.attachment_type,
                attachment_name=item.attachment_name,
                expires_at=expires_at,
                poll_data=item.poll_data,
                embed_data=item.embed_data
            )
            db.session.add(msg)
            item.status = 'sent'
            db.session.flush()

            msg_dict = msg.to_dict()
            broadcast_socket_event('receive_message', msg_dict, conv_id=item.conversation_id)

        # 2. Expire ephemeral messages
        expired_msgs = Message.query.filter(
            Message.expires_at != None,
            db.or_(Message.expires_at <= now_utc, Message.expires_at <= now_naive),
            Message.is_deleted_everyone == False
        ).all()

        for exp in expired_msgs:
            exp.is_deleted_everyone = True
            exp.text = '🚫 Bu süreli mesajın süresi doldu.'
            broadcast_socket_event('message_deleted', {
                'message_id': exp.id,
                'conversation_id': exp.conversation_id,
                'channel_id': exp.channel_id,
                'is_deleted_everyone': True
            }, conv_id=exp.conversation_id)

        if due_items or expired_msgs:
            db.session.commit()
    except Exception as e:
        print(f"[Scheduler/Ephemeral Notice]: {e}")

