"""
AstralPaws - Routes Friends Blueprint
=====================================
Modular endpoints for comprehensive Friend System:
- Friend Requests (Send, Accept, Reject, Cancel)
- Remove Friend
- Block System (Block, Unblock, List Blocked)
- Friend Private Notes
- Close Friends & Favorites Toggles
- Online Notification Preference
- Mutual Friend & Community Suggestions
- Friends Dashboard Listing with Aggregated Counts
"""

from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from models import (
    db, User, Friendship, BlockedUser, Server, ServerMember
)
from security_utils import sanitize_text

friends_bp = Blueprint('friends_bp', __name__)


# -------------------------------------------------------------------
# Helper Utilities
# -------------------------------------------------------------------

def is_blocked_between(user_a_id: int, user_b_id: int) -> bool:
    """Checks if either user_a has blocked user_b, or user_b has blocked user_a."""
    return BlockedUser.query.filter(
        ((BlockedUser.blocker_id == user_a_id) & (BlockedUser.blocked_id == user_b_id)) |
        ((BlockedUser.blocker_id == user_b_id) & (BlockedUser.blocked_id == user_a_id))
    ).first() is not None


def get_friendship_row(user_a_id: int, user_b_id: int):
    """Finds existing friendship row between two users in either direction."""
    return Friendship.query.filter(
        ((Friendship.user_id == user_a_id) & (Friendship.friend_id == user_b_id)) |
        ((Friendship.user_id == user_b_id) & (Friendship.friend_id == user_a_id))
    ).first()


def emit_socket_event(event_name: str, data: dict, room: str = None):
    """Safely emits a Socket.IO event if socketio is present in app."""
    try:
        from app import socketio
        if socketio:
            if room:
                socketio.emit(event_name, data, room=room)
            else:
                socketio.emit(event_name, data)
    except Exception as e:
        # Logging without disrupting request lifecycle
        print(f"[SocketIO Event Notice] {event_name}: {e}")


# ===================================================================
# 1. FRIENDS LISTING & DASHBOARD COUNTS
# ===================================================================

@friends_bp.route('/api/friends', methods=['GET'])
@login_required
def get_friends_dashboard():
    """
    Returns full categorized list of friends, pending requests, blocked users,
    and aggregate counts for the dashboard tabs.
    """
    uid = current_user.id

    # 1. Query all friendships involving current user
    friendships = Friendship.query.filter(
        (Friendship.user_id == uid) | (Friendship.friend_id == uid)
    ).order_by(Friendship.updated_at.desc(), Friendship.created_at.desc()).all()

    all_friends = []
    online_friends = []
    pending_in = []
    pending_out = []
    close_friends = []
    favorites = []

    for f in friendships:
        data = f.to_dict(uid)
        if not data:
            continue

        if f.status == 'accepted':
            all_friends.append(data)
            status_mode = data.get('status_mode') or 'offline'
            if status_mode != 'offline':
                online_friends.append(data)

            if data.get('is_close_friend'):
                close_friends.append(data)

            if data.get('is_favorite'):
                favorites.append(data)

        elif f.status == 'pending':
            if f.friend_id == uid:
                pending_in.append(data)
            else:
                pending_out.append(data)

    # 2. Query blocked users
    blocked_rows = BlockedUser.query.filter_by(blocker_id=uid).order_by(BlockedUser.created_at.desc()).all()
    blocked_list = [b.to_dict() for b in blocked_rows]

    # 3. Aggregate counts for UI Badges
    counts = {
        'all': len(all_friends),
        'online': len(online_friends),
        'pending_in': len(pending_in),
        'pending_out': len(pending_out),
        'pending_total': len(pending_in) + len(pending_out),
        'close': len(close_friends),
        'favorites': len(favorites),
        'blocked': len(blocked_list)
    }

    return jsonify({
        'success': True,
        'friends': all_friends,
        'online': online_friends,
        'pending_incoming': pending_in,
        'pending_outgoing': pending_out,
        'close_friends': close_friends,
        'favorites': favorites,
        'blocked': blocked_list,
        'counts': counts
    })


# ===================================================================
# 2. FRIEND REQUESTS (SEND, ACCEPT, REJECT, CANCEL)
# ===================================================================

@friends_bp.route('/api/friends/request', methods=['POST'])
@friends_bp.route('/api/friends/add', methods=['POST'])
@login_required
def send_friend_request():
    """
    Sends a new friend request using username, public_id, or user_id.
    Prevents duplicates, self-requests, and blocked interactions.
    """
    data = request.get_json(silent=True) or {}
    identifier = (data.get('username') or data.get('identifier') or '').strip()
    target_user_id = data.get('user_id')

    target_user = None
    if target_user_id:
        target_user = db.session.get(User, target_user_id)
    elif identifier:
        clean_id = identifier.lstrip('@')
        target_user = User.query.filter(
            (db.func.lower(User.username) == clean_id.lower()) |
            (User.public_id == clean_id)
        ).first()

    if not target_user:
        return jsonify({'success': False, 'message': 'Kullanıcı bulunamadı. Lütfen geçerli bir kullanıcı adı veya Astral ID girin.'}), 404

    if target_user.id == current_user.id:
        return jsonify({'success': False, 'message': 'Kendinize arkadaşlık isteği gönderemezsiniz.'}), 400

    # Check if either user has blocked the other
    if is_blocked_between(current_user.id, target_user.id):
        return jsonify({'success': False, 'message': 'Bu kullanıcıyla bağlantı kurulamıyor. Engellendi.'}), 403

    existing = get_friendship_row(current_user.id, target_user.id)

    if existing:
        if existing.status == 'accepted':
            return jsonify({'success': False, 'message': 'Bu kullanıcı zaten arkadaş listenizde.'}), 400

        if existing.status == 'pending':
            if existing.user_id == current_user.id:
                return jsonify({'success': False, 'message': 'Arkadaşlık isteği zaten gönderilmiş, karşı tarafın yanıtı bekleniyor.'}), 400
            else:
                # Other user already sent us a request! Auto-accept or notify
                existing.status = 'accepted'
                existing.updated_at = datetime.now(timezone.utc)
                db.session.commit()

                emit_socket_event('friend_request_accepted', {
                    'user_id': current_user.id,
                    'username': current_user.username,
                    'display_name': current_user.get_effective_display_name(),
                    'color': current_user.color
                }, room=f"user_{target_user.id}")

                return jsonify({
                    'success': True,
                    'message': f'{target_user.get_effective_display_name()} zaten size bir istek göndermişti! Arkadaşlık kabul edildi.',
                    'status': 'accepted',
                    'friendship_id': existing.id,
                    'friend': existing.to_dict(current_user.id)
                })

        # If previous was rejected or cancelled, reopen cleanly
        if existing.status in ('rejected', 'cancelled'):
            existing.user_id = current_user.id
            existing.friend_id = target_user.id
            existing.status = 'pending'
            existing.updated_at = datetime.now(timezone.utc)
            db.session.commit()

            emit_socket_event('friend_request_received', {
                'from_id': current_user.id,
                'from_username': current_user.username,
                'from_display_name': current_user.get_effective_display_name(),
                'from_color': current_user.color or '#8b5cf6'
            }, room=f"user_{target_user.id}")

            return jsonify({
                'success': True,
                'message': f'{target_user.get_effective_display_name()} kullanıcısına arkadaşlık isteği gönderildi.',
                'status': 'pending',
                'friendship_id': existing.id,
                'friend': existing.to_dict(current_user.id)
            })

    # Create brand new friendship row
    new_f = Friendship(
        user_id=current_user.id,
        friend_id=target_user.id,
        status='pending',
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db.session.add(new_f)
    db.session.commit()

    emit_socket_event('friend_request_received', {
        'from_id': current_user.id,
        'from_username': current_user.username,
        'from_display_name': current_user.get_effective_display_name(),
        'from_color': current_user.color or '#8b5cf6'
    }, room=f"user_{target_user.id}")

    return jsonify({
        'success': True,
        'message': f'{target_user.get_effective_display_name()} kullanıcısına arkadaşlık isteği gönderildi.',
        'status': 'pending',
        'friendship_id': new_f.id,
        'friend': new_f.to_dict(current_user.id)
    })


@friends_bp.route('/api/friends/requests/<int:request_id>/accept', methods=['POST'])
@friends_bp.route('/api/friends/accept', methods=['POST'])
@login_required
def accept_friend_request(request_id: int = None):
    """Accepts a pending incoming friend request."""
    data = request.get_json(silent=True) or {}
    target_id = request_id or data.get('friendship_id') or data.get('id')
    if not target_id:
        return jsonify({'success': False, 'message': 'İstek ID gereklidir.'}), 400

    f = db.session.get(Friendship, target_id)
    if not f or f.friend_id != current_user.id or f.status != 'pending':
        return jsonify({'success': False, 'message': 'Kabul edilecek bekleyen arkadaşlık isteği bulunamadı.'}), 404

    f.status = 'accepted'
    f.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    emit_socket_event('friend_request_accepted', {
        'user_id': current_user.id,
        'username': current_user.username,
        'display_name': current_user.get_effective_display_name(),
        'color': current_user.color or '#8b5cf6'
    }, room=f"user_{f.user_id}")

    return jsonify({
        'success': True,
        'message': 'Arkadaşlık isteği kabul edildi.',
        'friendship_id': f.id,
        'friend': f.to_dict(current_user.id)
    })


@friends_bp.route('/api/friends/requests/<int:request_id>/reject', methods=['POST'])
@friends_bp.route('/api/friends/reject', methods=['POST'])
@login_required
def reject_friend_request(request_id: int = None):
    """Rejects an incoming friend request."""
    data = request.get_json(silent=True) or {}
    target_id = request_id or data.get('friendship_id') or data.get('id')
    if not target_id:
        return jsonify({'success': False, 'message': 'İstek ID gereklidir.'}), 400

    f = db.session.get(Friendship, target_id)
    if not f or f.friend_id != current_user.id or f.status != 'pending':
        return jsonify({'success': False, 'message': 'Reddedilecek bekleyen arkadaşlık isteği bulunamadı.'}), 404

    f.status = 'rejected'
    f.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Arkadaşlık isteği reddedildi.', 'friendship_id': f.id})


@friends_bp.route('/api/friends/requests/<int:request_id>/cancel', methods=['POST'])
@friends_bp.route('/api/friends/cancel', methods=['POST'])
@login_required
def cancel_friend_request(request_id: int = None):
    """Cancels a pending outgoing friend request sent by current user."""
    data = request.get_json(silent=True) or {}
    target_id = request_id or data.get('friendship_id') or data.get('id')
    if not target_id:
        return jsonify({'success': False, 'message': 'İstek ID gereklidir.'}), 400

    f = db.session.get(Friendship, target_id)
    if not f or f.user_id != current_user.id or f.status != 'pending':
        return jsonify({'success': False, 'message': 'İptal edilecek bekleyen arkadaşlık isteği bulunamadı.'}), 404

    f.status = 'cancelled'
    f.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Arkadaşlık isteği iptal edildi.', 'friendship_id': f.id})


# ===================================================================
# 3. REMOVE FRIEND
# ===================================================================

@friends_bp.route('/api/friends/<int:friend_id>', methods=['DELETE'])
@friends_bp.route('/api/friends/remove', methods=['POST', 'DELETE'])
@login_required
def remove_friend(friend_id: int = None):
    """Removes a friend and cleanly terminates mutual friendship."""
    data = request.get_json(silent=True) or {}
    target_id = friend_id or data.get('user_id') or data.get('friend_id')
    if not target_id:
        return jsonify({'success': False, 'message': 'Arkadaş ID gereklidir.'}), 400

    f = get_friendship_row(current_user.id, target_id)
    if not f:
        # Check if target_id is the friendship.id itself
        f = db.session.get(Friendship, target_id)
        if not f or (f.user_id != current_user.id and f.friend_id != current_user.id):
            return jsonify({'success': False, 'message': 'Arkadaşlık ilişkisi bulunamadı.'}), 404

    other_user_id = f.friend_id if f.user_id == current_user.id else f.user_id

    db.session.delete(f)
    db.session.commit()

    emit_socket_event('friend_removed', {
        'user_id': current_user.id,
        'other_user_id': other_user_id
    }, room=f"user_{other_user_id}")

    return jsonify({'success': True, 'message': 'Arkadaş listenizden kaldırıldı.'})


# ===================================================================
# 4. BLOCK SYSTEM (BLOCK, UNBLOCK, LIST BLOCKED)
# ===================================================================

@friends_bp.route('/api/friends/<int:target_user_id>/block', methods=['POST'])
@friends_bp.route('/api/friends/block', methods=['POST'])
@login_required
def block_user(target_user_id: int = None):
    """
    Blocks a user. Removes existing friendship or pending requests between both users.
    Cannot block self.
    """
    data = request.get_json(silent=True) or {}
    target_id = target_user_id or data.get('user_id') or data.get('target_user_id')
    reason = sanitize_text(data.get('reason', ''), max_len=255)

    if not target_id:
        return jsonify({'success': False, 'message': 'Engellenecek kullanıcı ID gereklidir.'}), 400

    if target_id == current_user.id:
        return jsonify({'success': False, 'message': 'Kendinizi engelleyemezsiniz.'}), 400

    target = db.session.get(User, target_id)
    if not target:
        return jsonify({'success': False, 'message': 'Kullanıcı bulunamadı.'}), 404

    existing_block = BlockedUser.query.filter_by(blocker_id=current_user.id, blocked_id=target_id).first()
    if not existing_block:
        b = BlockedUser(
            blocker_id=current_user.id,
            blocked_id=target_id,
            reason=reason if reason else None,
            created_at=datetime.now(timezone.utc)
        )
        db.session.add(b)

    # Terminate any existing friendship or pending requests
    f = get_friendship_row(current_user.id, target_id)
    if f:
        db.session.delete(f)

    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'{target.get_effective_display_name()} engellendi.'
    })


@friends_bp.route('/api/friends/<int:target_user_id>/unblock', methods=['POST'])
@friends_bp.route('/api/friends/unblock', methods=['POST'])
@login_required
def unblock_user(target_user_id: int = None):
    """Unblocks a previously blocked user."""
    data = request.get_json(silent=True) or {}
    target_id = target_user_id or data.get('user_id') or data.get('target_user_id')
    if not target_id:
        return jsonify({'success': False, 'message': 'Kullanıcı ID gereklidir.'}), 400

    block_record = BlockedUser.query.filter_by(blocker_id=current_user.id, blocked_id=target_id).first()
    if not block_record:
        return jsonify({'success': False, 'message': 'Bu kullanıcı engellenenler listenizde bulunmuyor.'}), 404

    db.session.delete(block_record)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Kullanıcının engeli kaldırıldı.'})


@friends_bp.route('/api/friends/blocked', methods=['GET'])
@login_required
def get_blocked_users():
    """Lists all users blocked by the current user."""
    blocked_rows = BlockedUser.query.filter_by(blocker_id=current_user.id).order_by(BlockedUser.created_at.desc()).all()
    return jsonify({
        'success': True,
        'blocked': [b.to_dict() for b in blocked_rows]
    })


# ===================================================================
# 5. FRIEND PRIVATE NOTES
# ===================================================================

@friends_bp.route('/api/friends/<int:friend_id>/note', methods=['POST'])
@friends_bp.route('/api/friends/note', methods=['POST'])
@login_required
def set_friend_note(friend_id: int = None):
    """
    Saves or removes a private personal note about a friend.
    Notes are strictly private to the creating user.
    """
    data = request.get_json(silent=True) or {}
    target_id = friend_id or data.get('friend_id') or data.get('user_id')
    note_text = sanitize_text(data.get('note', ''), max_len=500)

    if not target_id:
        return jsonify({'success': False, 'message': 'Arkadaş ID gereklidir.'}), 400

    f = get_friendship_row(current_user.id, target_id)
    if not f:
        # Also check if target_id was the friendship row ID
        f = db.session.get(Friendship, target_id)
        if not f or (f.user_id != current_user.id and f.friend_id != current_user.id):
            return jsonify({'success': False, 'message': 'Arkadaşlık ilişkisi bulunamadı.'}), 404

    f.set_note(current_user.id, note_text if note_text else None)
    f.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Arkadaş notu kaydedildi.',
        'note': f.get_note(current_user.id)
    })


# ===================================================================
# 6. CLOSE FRIENDS, FAVORITES & ONLINE NOTIFICATIONS
# ===================================================================

@friends_bp.route('/api/friends/<int:friend_id>/toggle-close', methods=['POST'])
@login_required
def toggle_close_friend(friend_id: int):
    """Toggles close friend flag for current user."""
    f = get_friendship_row(current_user.id, friend_id)
    if not f or f.status != 'accepted':
        return jsonify({'success': False, 'message': 'Kullanıcı arkadaş listenizde bulunmuyor.'}), 404

    current_val = f.get_is_close_friend(current_user.id)
    new_val = not current_val
    f.set_is_close_friend(current_user.id, new_val)
    f.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({
        'success': True,
        'is_close_friend': new_val,
        'message': 'Yakın arkadaşlara eklendi.' if new_val else 'Yakın arkadaşlardan çıkarıldı.'
    })


@friends_bp.route('/api/friends/<int:friend_id>/toggle-favorite', methods=['POST'])
@login_required
def toggle_favorite_friend(friend_id: int):
    """Toggles favorite flag for current user."""
    f = get_friendship_row(current_user.id, friend_id)
    if not f or f.status != 'accepted':
        return jsonify({'success': False, 'message': 'Kullanıcı arkadaş listenizde bulunmuyor.'}), 404

    current_val = f.get_is_favorite(current_user.id)
    new_val = not current_val
    f.set_is_favorite(current_user.id, new_val)
    f.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({
        'success': True,
        'is_favorite': new_val,
        'message': 'Favorilere eklendi.' if new_val else 'Favorilerden çıkarıldı.'
    })


@friends_bp.route('/api/friends/<int:friend_id>/toggle-online-notify', methods=['POST'])
@login_required
def toggle_online_notify(friend_id: int):
    """Toggles online status notification preference for current user."""
    f = get_friendship_row(current_user.id, friend_id)
    if not f or f.status != 'accepted':
        return jsonify({'success': False, 'message': 'Kullanıcı arkadaş listenizde bulunmuyor.'}), 404

    current_val = f.get_notify_on_online(current_user.id)
    new_val = not current_val
    f.set_notify_on_online(current_user.id, new_val)
    f.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({
        'success': True,
        'notify_on_online': new_val,
        'message': 'Çevrimiçi olduğunda bildirim gönderilecek.' if new_val else 'Çevrimiçi bildirimleri kapatıldı.'
    })


# ===================================================================
# 7. FRIEND SUGGESTIONS / RECOMMENDATIONS
# ===================================================================

@friends_bp.route('/api/friends/suggestions', methods=['GET'])
@login_required
def get_friend_suggestions():
    """
    Computes intelligent friend recommendations based on:
    - Number of mutual friends
    - Shared communities/servers
    Excludes: self, current friends, pending request targets, blocked users.
    """
    uid = current_user.id

    # 1. Fetch all existing friendships
    all_f_rows = Friendship.query.filter(
        (Friendship.user_id == uid) | (Friendship.friend_id == uid)
    ).all()

    existing_friend_ids = set()
    pending_ids = set()
    for f in all_f_rows:
        other_id = f.friend_id if f.user_id == uid else f.user_id
        if f.status == 'accepted':
            existing_friend_ids.add(other_id)
        elif f.status == 'pending':
            pending_ids.add(other_id)

    # 2. Fetch all blocked user IDs (both directions)
    blocked_by_me = BlockedUser.query.filter_by(blocker_id=uid).all()
    blocked_me = BlockedUser.query.filter_by(blocked_id=uid).all()
    blocked_ids = set([b.blocked_id for b in blocked_by_me] + [b.blocker_id for b in blocked_me])

    # Combined excluded set
    excluded_ids = existing_friend_ids | pending_ids | blocked_ids | {uid}

    # 3. Find candidates through mutual friends
    candidate_scores = {}  # candidate_id -> { 'mutual_friends': set(), 'mutual_servers': set() }

    if existing_friend_ids:
        friends_of_friends = Friendship.query.filter(
            ((Friendship.user_id.in_(existing_friend_ids)) | (Friendship.friend_id.in_(existing_friend_ids))) &
            (Friendship.status == 'accepted')
        ).all()

        for f in friends_of_friends:
            if f.user_id in existing_friend_ids and f.friend_id not in excluded_ids:
                cand_id = f.friend_id
                conn_id = f.user_id
                if cand_id not in candidate_scores:
                    candidate_scores[cand_id] = {'mutual_friends': set(), 'mutual_servers': set()}
                candidate_scores[cand_id]['mutual_friends'].add(conn_id)

            elif f.friend_id in existing_friend_ids and f.user_id not in excluded_ids:
                cand_id = f.user_id
                conn_id = f.friend_id
                if cand_id not in candidate_scores:
                    candidate_scores[cand_id] = {'mutual_friends': set(), 'mutual_servers': set()}
                candidate_scores[cand_id]['mutual_friends'].add(conn_id)

    # 4. Find candidates through shared servers
    my_memberships = ServerMember.query.filter_by(user_id=uid).all()
    my_server_ids = [m.server_id for m in my_memberships]

    if my_server_ids:
        shared_members = ServerMember.query.filter(
            (ServerMember.server_id.in_(my_server_ids)) &
            (~ServerMember.user_id.in_(excluded_ids))
        ).all()

        for sm in shared_members:
            if sm.user_id not in candidate_scores:
                candidate_scores[sm.user_id] = {'mutual_friends': set(), 'mutual_servers': set()}
            candidate_scores[sm.user_id]['mutual_servers'].add(sm.server_id)

    # 5. Build and rank suggestions list
    suggestions = []
    for cand_id, meta in candidate_scores.items():
        cand_user = db.session.get(User, cand_id)
        if not cand_user or cand_user.account_status == 'pending_deletion':
            continue

        mutual_f_count = len(meta['mutual_friends'])
        mutual_s_count = len(meta['mutual_servers'])
        score = (mutual_f_count * 3) + (mutual_s_count * 1)

        # Get mutual friends sample names
        sample_names = []
        if meta['mutual_friends']:
            sample_users = User.query.filter(User.id.in_(list(meta['mutual_friends'])[:3])).all()
            sample_names = [u.get_effective_display_name() for u in sample_users]

        suggestions.append({
            'user_id': cand_user.id,
            'public_id': cand_user.public_id,
            'username': cand_user.username,
            'display_name': cand_user.get_effective_display_name(),
            'color': cand_user.color or '#8b5cf6',
            'avatar': f"/static/uploads/{cand_user.avatar}" if cand_user.avatar else None,
            'status_mode': cand_user.presence_status or 'offline',
            'custom_status': cand_user.get_active_custom_status(),
            'bio': cand_user.bio or '',
            'badges': [b['name'] for b in cand_user.get_all_badges()],
            'account_age_badge': cand_user.get_account_age_badge(),
            'mutual_friends_count': mutual_f_count,
            'mutual_servers_count': mutual_s_count,
            'mutual_friends_sample': sample_names,
            'score': score
        })

    # Sort suggestions by score descending, then mutual friends count
    suggestions.sort(key=lambda x: (x['score'], x['mutual_friends_count'], x['mutual_servers_count']), reverse=True)

    return jsonify({
        'success': True,
        'suggestions': suggestions[:20]
    })
