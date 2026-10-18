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
from datetime import datetime, timezone
from html.parser import HTMLParser

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from models import (
    db, User, Conversation, ConversationMember, Message,
    MessageAttachment, HiddenMessage, CustomEmoji, BlockedUser,
    Friendship
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

    if before_id and before_id.isdigit():
        query = query.filter(Message.id < int(before_id))

    msgs = query.order_by(Message.timestamp.asc()).limit(limit).all()

    # Update reader timestamp
    mem = conv.get_member_record(current_user.id)
    if mem:
        mem.last_read_at = datetime.now(timezone.utc)
        db.session.commit()

    return jsonify({
        'success': True,
        'messages': [m.to_dict(viewer_id=current_user.id) for m in msgs]
    })


@messaging_bp.route('/api/conversations/<int:conv_id>/messages', methods=['POST'])
@login_required
def send_conversation_message(conv_id: int):
    """Sends a message to a conversation (REST fallback)."""
    conv = db.session.get(Conversation, conv_id)
    if not conv:
        return jsonify({'success': False, 'message': 'Sohbet bulunamadı.'}), 404

    if not conv.is_member(current_user.id):
        return jsonify({'success': False, 'message': 'Bu sohbete mesaj gönderemezsiniz.'}), 403

    data = request.get_json(silent=True) or {}
    text = sanitize_text(data.get('text', ''), max_len=4000)
    message_type = data.get('message_type', 'text')
    reply_to_id = data.get('reply_to_id')
    forwarded_from_id = data.get('forwarded_from_id')
    attachments_data = data.get('attachments', [])

    if not text and not attachments_data:
        return jsonify({'success': False, 'message': 'Mesaj içeriği veya dosya gereklidir.'}), 400

    msg = Message(
        conversation_id=conv.id,
        sender_id=current_user.id,
        text=text or 'Dosya Eki',
        message_type=message_type,
        reply_to_id=reply_to_id,
        forwarded_from_id=forwarded_from_id
    )
    db.session.add(msg)
    db.session.flush()

    for att in attachments_data:
        if att.get('file_url'):
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
    db.session.commit()

    msg_dict = msg.to_dict()
    broadcast_socket_event('receive_message', msg_dict, conv_id=conv.id)
    broadcast_socket_event('conversation_updated', {
        'conversation_id': conv.id,
        'last_message': msg_dict
    }, conv_id=conv.id)

    return jsonify({
        'success': True,
        'message': msg.to_dict(viewer_id=current_user.id)
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
    """Returns custom emojis available on the platform."""
    emojis = CustomEmoji.query.order_by(CustomEmoji.name.asc()).all()
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
    Offers curated Astral GIF collections and is structured to connect to Tenor / Giphy.
    """
    q = (request.args.get('q') or '').strip().lower()

    # Curated high-performance curated GIFs catalogue
    catalog = [
        {'id': 'g1', 'title': 'Happy Dance', 'url': 'https://media.giphy.com/media/3o7abKhOpu0NwenH3O/giphy.gif', 'tags': ['happy', 'dance', 'excited', 'astral']},
        {'id': 'g2', 'title': 'Astral Cat Typing', 'url': 'https://media.giphy.com/media/JIX9t2j0ZTN9S/giphy.gif', 'tags': ['cat', 'typing', 'code', 'astro', 'astral']},
        {'id': 'g3', 'title': 'Mind Blown Galaxy', 'url': 'https://media.giphy.com/media/26ufdipQqU2lhNA4g/giphy.gif', 'tags': ['mind blown', 'wow', 'galaxy', 'astro', 'space']},
        {'id': 'g4', 'title': 'High Five', 'url': 'https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif', 'tags': ['high five', 'friend', 'yes']},
        {'id': 'g5', 'title': 'Applause', 'url': 'https://media.giphy.com/media/3o72FcJmLzIdYJdmDe/giphy.gif', 'tags': ['clap', 'bravo', 'applause']},
        {'id': 'g6', 'title': 'Cosmic Space', 'url': 'https://media.giphy.com/media/26AHONQ79FdWZhAI0/giphy.gif', 'tags': ['space', 'cosmic', 'stars', 'astro', 'astral']},
        {'id': 'g7', 'title': 'Gaming Win', 'url': 'https://media.giphy.com/media/3o7TKTDnUxE0g2fSE8/giphy.gif', 'tags': ['gg', 'win', 'gamer']},
        {'id': 'g8', 'title': 'Popcorn', 'url': 'https://media.giphy.com/media/t3cL1iXeEHwx2/giphy.gif', 'tags': ['popcorn', 'watching', 'lol']}
    ]

    if q:
        filtered = [g for g in catalog if q in g['title'].lower() or any(q in t for t in g['tags'])]
    else:
        filtered = catalog

    return jsonify({
        'success': True,
        'gifs': filtered,
        'provider': 'Astral Curated GIF Engine (Extensible for Tenor/Giphy)'
    })
