import json
import secrets
import string
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user

from models import (
    db, User, Nexus, NexusMember, NexusInvite, NexusApplication, Channel
)
from security_utils import sanitize_text

nexus_bp = Blueprint('nexus', __name__)

NEXUS_CATEGORIES = (
    'Oyun', 'Teknoloji', 'Sanat', 'Yazılım', 'Eğitim',
    'Müzik', 'Topluluk', 'Tasarım', 'Bilim', 'Diğer'
)

def generate_invite_code(length: int = 8) -> str:
    """Generates a random uppercase alphanumeric invite code."""
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


# ===================================================================
# 1. EXPLORE & DISCOVERY
# ===================================================================

@nexus_bp.route('/api/nexus/explore', methods=['GET'])
def explore_nexuses():
    """Returns a list of public Nexuses matching category, tag or search term."""
    category = request.args.get('category', '').strip()
    tag = request.args.get('tag', '').strip()
    q = request.args.get('q', '').strip().lower()

    base_query = Nexus.query.filter(Nexus.privacy != 'private')

    if category and category in NEXUS_CATEGORIES:
        base_query = base_query.filter(Nexus.category == category)

    nexuses = base_query.order_by(Nexus.created_at.desc()).all()
    results = []
    viewer_id = current_user.id if current_user.is_authenticated else None

    for n in nexuses:
        if tag:
            tags = n.get_tags()
            if not any(tag.lower() == t.lower() for t in tags):
                continue

        if q:
            match_name = q in n.name.lower()
            match_desc = q in (n.description or '').lower()
            match_tags = any(q in t.lower() for t in n.get_tags())
            if not (match_name or match_desc or match_tags):
                continue

        results.append(n.to_dict(viewer_id=viewer_id))

    return jsonify({
        'success': True,
        'nexuses': results,
        'categories': list(NEXUS_CATEGORIES)
    })


@nexus_bp.route('/api/nexus/my', methods=['GET'])
@login_required
def get_my_nexuses():
    """Lists all Nexuses where the current user is a member or owner."""
    memberships = NexusMember.query.filter_by(user_id=current_user.id).all()
    nexus_ids = [m.nexus_id for m in memberships]

    if not nexus_ids:
        return jsonify({'success': True, 'nexuses': []})

    nexuses = Nexus.query.filter(Nexus.id.in_(nexus_ids)).order_by(Nexus.updated_at.desc()).all()
    data = [n.to_dict(viewer_id=current_user.id) for n in nexuses]
    return jsonify({
        'success': True,
        'nexuses': data
    })


# ===================================================================
# 2. NEXUS CRUD & SETTINGS
# ===================================================================

@nexus_bp.route('/api/nexus', methods=['POST'])
@login_required
def create_nexus():
    """Creates a new Nexus community, assigns creator as owner and creates default channels."""
    data = request.get_json(silent=True) or {}
    name = sanitize_text(data.get('name', ''), max_len=100)
    description = sanitize_text(data.get('description', ''), max_len=1000)
    category = data.get('category', 'Topluluk')
    tags = data.get('tags', [])
    rules = sanitize_text(data.get('rules', ''), max_len=2000)
    privacy = data.get('privacy', 'public')
    requires_application = bool(data.get('requires_application', False))
    verification_level = data.get('verification_level', 'none')
    age_restricted = bool(data.get('age_restricted', False))
    min_age = int(data.get('min_age', 13)) if str(data.get('min_age', '')).isdigit() else 13
    icon_color = str(data.get('icon_color', '#8b5cf6'))[:30]
    banner_color = str(data.get('banner_color', '#8b5cf6'))[:30]
    icon_url = sanitize_text(data.get('icon_url', ''), max_len=255)
    banner_url = sanitize_text(data.get('banner_url', ''), max_len=255)

    if not name or len(name) < 2:
        return jsonify({'success': False, 'message': 'Topluluk adı en az 2 karakter olmalıdır.'}), 400

    if category not in NEXUS_CATEGORIES:
        category = 'Topluluk'

    nexus = Nexus(
        name=name,
        description=description,
        owner_id=current_user.id,
        category=category,
        rules=rules,
        privacy=privacy,
        requires_application=requires_application,
        verification_level=verification_level,
        age_restricted=age_restricted,
        min_age=min_age,
        icon_color=icon_color,
        banner_color=banner_color,
        icon_url=icon_url if icon_url else None,
        banner_url=banner_url if banner_url else None
    )
    nexus.set_tags(tags)

    db.session.add(nexus)
    db.session.flush()

    # Add owner member
    owner_member = NexusMember(
        nexus_id=nexus.id,
        user_id=current_user.id,
        role='owner'
    )
    db.session.add(owner_member)

    # Create default text & voice channels
    default_text_chan = Channel(nexus_id=nexus.id, name="genel-sohbet", type="text")
    default_voice_chan = Channel(nexus_id=nexus.id, name="Ses Odası 1", type="voice")
    db.session.add_all([default_text_chan, default_voice_chan])

    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'"{nexus.name}" topluluğu başarıyla oluşturuldu.',
        'nexus': nexus.to_dict(viewer_id=current_user.id)
    }), 201


@nexus_bp.route('/api/nexus/<int:nexus_id>', methods=['GET'])
def get_nexus_details(nexus_id: int):
    """Retrieves full details of a specific Nexus."""
    nexus = db.session.get(Nexus, nexus_id)
    if not nexus:
        return jsonify({'success': False, 'message': 'Nexus bulunamadı.'}), 404

    viewer_id = current_user.id if current_user.is_authenticated else None

    # Privacy check
    if nexus.privacy == 'private' and not nexus.is_member(viewer_id):
        return jsonify({
            'success': True,
            'nexus': {
                'id': nexus.id,
                'name': nexus.name,
                'icon_url': nexus.icon_url,
                'icon_color': nexus.icon_color,
                'banner_color': nexus.banner_color,
                'privacy': 'private',
                'requires_application': bool(nexus.requires_application),
                'member_count': len(nexus.members),
                'is_member': False
            }
        })

    return jsonify({
        'success': True,
        'nexus': nexus.to_dict(viewer_id=viewer_id)
    })


@nexus_bp.route('/api/nexus/<int:nexus_id>', methods=['PUT'])
@login_required
def update_nexus_settings(nexus_id: int):
    """Updates settings for a Nexus. Requires owner or admin role."""
    nexus = db.session.get(Nexus, nexus_id)
    if not nexus:
        return jsonify({'success': False, 'message': 'Nexus bulunamadı.'}), 404

    user_role = nexus.get_user_role(current_user.id)
    if user_role not in ('owner', 'admin'):
        return jsonify({'success': False, 'message': 'Bu işlem için yönetici yetkisi gereklidir.'}), 403

    data = request.get_json(silent=True) or {}

    if 'name' in data:
        name = sanitize_text(data['name'], max_len=100)
        if len(name) >= 2:
            nexus.name = name

    if 'description' in data:
        nexus.description = sanitize_text(data['description'], max_len=1000)

    if 'category' in data and data['category'] in NEXUS_CATEGORIES:
        nexus.category = data['category']

    if 'tags' in data:
        nexus.set_tags(data['tags'])

    if 'rules' in data:
        nexus.rules = sanitize_text(data['rules'], max_len=2000)

    if 'privacy' in data and data['privacy'] in ('public', 'private', 'gated'):
        nexus.privacy = data['privacy']

    if 'requires_application' in data:
        nexus.requires_application = bool(data['requires_application'])

    if 'verification_level' in data:
        nexus.verification_level = str(data['verification_level'])[:30]

    if 'age_restricted' in data:
        nexus.age_restricted = bool(data['age_restricted'])

    if 'min_age' in data and str(data['min_age']).isdigit():
        nexus.min_age = int(data['min_age'])

    if 'icon_color' in data and data['icon_color']:
        nexus.icon_color = str(data['icon_color'])[:30]

    if 'banner_color' in data and data['banner_color']:
        nexus.banner_color = str(data['banner_color'])[:30]

    if 'icon_url' in data:
        nexus.icon_url = sanitize_text(data['icon_url'], max_len=255)

    if 'banner_url' in data:
        nexus.banner_url = sanitize_text(data['banner_url'], max_len=255)

    nexus.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Topluluk ayarları güncellendi.',
        'nexus': nexus.to_dict(viewer_id=current_user.id)
    })


@nexus_bp.route('/api/nexus/<int:nexus_id>', methods=['DELETE'])
@login_required
def delete_nexus(nexus_id: int):
    """Deletes a Nexus. Owner only."""
    nexus = db.session.get(Nexus, nexus_id)
    if not nexus:
        return jsonify({'success': False, 'message': 'Nexus bulunamadı.'}), 404

    if nexus.owner_id != current_user.id:
        return jsonify({'success': False, 'message': 'Topluluğu yalnızca sahibi silebilir.'}), 403

    db.session.delete(nexus)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'"{nexus.name}" topluluğu başarıyla silindi.'
    })


# ===================================================================
# 3. MEMBERSHIP & JOIN / LEAVE
# ===================================================================

@nexus_bp.route('/api/nexus/<int:nexus_id>/join', methods=['POST'])
@login_required
def join_nexus(nexus_id: int):
    """Directly joins a public Nexus that does not require an application."""
    nexus = db.session.get(Nexus, nexus_id)
    if not nexus:
        return jsonify({'success': False, 'message': 'Nexus bulunamadı.'}), 404

    if nexus.is_member(current_user.id):
        return jsonify({'success': False, 'message': 'Zaten bu topluluğun üyesisiniz.'}), 400

    if nexus.privacy == 'private':
        return jsonify({'success': False, 'message': 'Bu özel topluluğa sadece davet bağlantısıyla katılabilirsiniz.'}), 403

    if nexus.requires_application:
        return jsonify({'success': False, 'message': 'Bu topluluğa katılmak için başvuru yapmanız gerekmektedir.'}), 400

    member = NexusMember(
        nexus_id=nexus.id,
        user_id=current_user.id,
        role='member'
    )
    db.session.add(member)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'"{nexus.name}" topluluğuna katıldınız.',
        'nexus': nexus.to_dict(viewer_id=current_user.id)
    })


@nexus_bp.route('/api/nexus/<int:nexus_id>/leave', methods=['POST'])
@login_required
def leave_nexus(nexus_id: int):
    """Leaves a Nexus community."""
    nexus = db.session.get(Nexus, nexus_id)
    if not nexus:
        return jsonify({'success': False, 'message': 'Nexus bulunamadı.'}), 404

    if nexus.owner_id == current_user.id:
        return jsonify({'success': False, 'message': 'Topluluk sahibi ayrılamaz. Önce sahipliği devredin veya topluluğu silin.'}), 400

    member = nexus.get_member(current_user.id)
    if not member:
        return jsonify({'success': False, 'message': 'Bu topluluğun üyesi değilsiniz.'}), 400

    db.session.delete(member)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'"{nexus.name}" topluluğundan ayrıldınız.'
    })


# ===================================================================
# 4. INVITES SYSTEM
# ===================================================================

@nexus_bp.route('/api/nexus/<int:nexus_id>/invites', methods=['GET'])
@login_required
def get_nexus_invites(nexus_id: int):
    """Lists active invites for a Nexus. Admin/Owner only."""
    nexus = db.session.get(Nexus, nexus_id)
    if not nexus:
        return jsonify({'success': False, 'message': 'Nexus bulunamadı.'}), 404

    user_role = nexus.get_user_role(current_user.id)
    if user_role not in ('owner', 'admin'):
        return jsonify({'success': False, 'message': 'Yetkiniz yetersiz.'}), 403

    invites = NexusInvite.query.filter_by(nexus_id=nexus.id).order_by(NexusInvite.created_at.desc()).all()
    return jsonify({
        'success': True,
        'invites': [inv.to_dict() for inv in invites]
    })


@nexus_bp.route('/api/nexus/<int:nexus_id>/invites', methods=['POST'])
@login_required
def create_nexus_invite(nexus_id: int):
    """Creates a new unique invite with expiration and usage limits."""
    nexus = db.session.get(Nexus, nexus_id)
    if not nexus:
        return jsonify({'success': False, 'message': 'Nexus bulunamadı.'}), 404

    user_role = nexus.get_user_role(current_user.id)
    if user_role not in ('owner', 'admin'):
        return jsonify({'success': False, 'message': 'Davet oluşturma yetkiniz yok.'}), 403

    data = request.get_json(silent=True) or {}
    max_uses = int(data.get('max_uses', 0)) if str(data.get('max_uses', '')).isdigit() else 0
    expires_in_hours = int(data.get('expires_in_hours', 0)) if str(data.get('expires_in_hours', '')).isdigit() else 0

    expires_at = None
    if expires_in_hours > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)

    custom_code = sanitize_text(data.get('code', ''), max_len=32).upper()
    if custom_code:
        if NexusInvite.query.filter_by(code=custom_code).first():
            return jsonify({'success': False, 'message': 'Bu davet kodu zaten kullanımda.'}), 400
        code = custom_code
    else:
        code = generate_invite_code(8)
        while NexusInvite.query.filter_by(code=code).first():
            code = generate_invite_code(8)

    invite = NexusInvite(
        nexus_id=nexus.id,
        code=code,
        created_by_id=current_user.id,
        max_uses=max_uses,
        expires_at=expires_at
    )
    db.session.add(invite)
    db.session.commit()

    return jsonify({
        'success': True,
        'invite': invite.to_dict()
    }), 201


@nexus_bp.route('/api/nexus/<int:nexus_id>/invites/<int:invite_id>', methods=['DELETE'])
@login_required
def revoke_nexus_invite(nexus_id: int, invite_id: int):
    """Revokes / cancels an existing invite."""
    nexus = db.session.get(Nexus, nexus_id)
    if not nexus:
        return jsonify({'success': False, 'message': 'Nexus bulunamadı.'}), 404

    user_role = nexus.get_user_role(current_user.id)
    if user_role not in ('owner', 'admin'):
        return jsonify({'success': False, 'message': 'Yetkiniz yetersiz.'}), 403

    invite = db.session.get(NexusInvite, invite_id)
    if not invite or invite.nexus_id != nexus.id:
        return jsonify({'success': False, 'message': 'Davet bulunamadı.'}), 404

    invite.is_revoked = True
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Davet bağlantısı iptal edildi.'
    })


@nexus_bp.route('/api/nexus/join-by-code', methods=['POST'])
@login_required
def join_nexus_by_code():
    """Joins a Nexus using a valid invite code."""
    data = request.get_json(silent=True) or {}
    code = sanitize_text(data.get('code', ''), max_len=32).upper()

    if not code:
        return jsonify({'success': False, 'message': 'Davet kodu girilmelidir.'}), 400

    invite = NexusInvite.query.filter_by(code=code).first()
    if not invite or not invite.is_valid():
        return jsonify({'success': False, 'message': 'Geçersiz veya süresi dolmuş davet kodu.'}), 400

    nexus = db.session.get(Nexus, invite.nexus_id)
    if not nexus:
        return jsonify({'success': False, 'message': 'Topluluk bulunamadı.'}), 404

    if nexus.is_member(current_user.id):
        return jsonify({'success': False, 'message': 'Zaten bu topluluğun üyesisiniz.'}), 400

    member = NexusMember(
        nexus_id=nexus.id,
        user_id=current_user.id,
        role='member'
    )
    invite.uses_count = (invite.uses_count or 0) + 1
    db.session.add(member)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'"{nexus.name}" topluluğuna davetle katıldınız.',
        'nexus': nexus.to_dict(viewer_id=current_user.id)
    })


# ===================================================================
# 5. APPLICATIONS & REVIEWS
# ===================================================================

@nexus_bp.route('/api/nexus/<int:nexus_id>/apply', methods=['POST'])
@login_required
def apply_to_nexus(nexus_id: int):
    """Submits an application to join a gated Nexus."""
    nexus = db.session.get(Nexus, nexus_id)
    if not nexus:
        return jsonify({'success': False, 'message': 'Nexus bulunamadı.'}), 404

    if nexus.is_member(current_user.id):
        return jsonify({'success': False, 'message': 'Zaten üyesiniz.'}), 400

    existing_app = NexusApplication.query.filter_by(nexus_id=nexus.id, user_id=current_user.id, status='pending').first()
    if existing_app:
        return jsonify({'success': False, 'message': 'Zaten bekleyen bir başvurunuz bulunmaktadır.'}), 400

    data = request.get_json(silent=True) or {}
    app_text = sanitize_text(data.get('application_text', ''), max_len=2000)

    if not app_text or len(app_text) < 5:
        return jsonify({'success': False, 'message': 'Başvuru metni en az 5 karakter olmalıdır.'}), 400

    application = NexusApplication(
        nexus_id=nexus.id,
        user_id=current_user.id,
        application_text=app_text,
        status='pending'
    )
    db.session.add(application)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'"{nexus.name}" için başvurunuz iletildi. Yönetici incelemesi bekleniyor.',
        'application': application.to_dict()
    }), 201


@nexus_bp.route('/api/nexus/<int:nexus_id>/applications', methods=['GET'])
@login_required
def get_nexus_applications(nexus_id: int):
    """Lists applications for a Nexus. Admin/Owner only."""
    nexus = db.session.get(Nexus, nexus_id)
    if not nexus:
        return jsonify({'success': False, 'message': 'Nexus bulunamadı.'}), 404

    user_role = nexus.get_user_role(current_user.id)
    if user_role not in ('owner', 'admin'):
        return jsonify({'success': False, 'message': 'Yetkiniz yetersiz.'}), 403

    status_filter = request.args.get('status')
    q = NexusApplication.query.filter_by(nexus_id=nexus.id)
    if status_filter:
        q = q.filter_by(status=status_filter)

    applications = q.order_by(NexusApplication.created_at.desc()).all()
    return jsonify({
        'success': True,
        'applications': [a.to_dict() for a in applications]
    })


@nexus_bp.route('/api/nexus/<int:nexus_id>/applications/<int:app_id>/review', methods=['POST'])
@login_required
def review_nexus_application(nexus_id: int, app_id: int):
    """Reviews (accepts or rejects) an application. Auto-adds user to members if accepted."""
    nexus = db.session.get(Nexus, nexus_id)
    if not nexus:
        return jsonify({'success': False, 'message': 'Nexus bulunamadı.'}), 404

    user_role = nexus.get_user_role(current_user.id)
    if user_role not in ('owner', 'admin'):
        return jsonify({'success': False, 'message': 'Yetkiniz yetersiz.'}), 403

    application = db.session.get(NexusApplication, app_id)
    if not application or application.nexus_id != nexus.id:
        return jsonify({'success': False, 'message': 'Başvuru bulunamadı.'}), 404

    data = request.get_json(silent=True) or {}
    action = data.get('action', '').lower()
    review_notes = sanitize_text(data.get('review_notes', ''), max_len=500)

    if action not in ('approve', 'accept', 'reject'):
        return jsonify({'success': False, 'message': 'Geçersiz inceleme eylemi (approve veya reject olmalıdır).'}), 400

    application.reviewed_by_id = current_user.id
    application.review_notes = review_notes
    application.reviewed_at = datetime.now(timezone.utc)

    if action in ('approve', 'accept'):
        application.status = 'approved'
        if not nexus.is_member(application.user_id):
            member = NexusMember(
                nexus_id=nexus.id,
                user_id=application.user_id,
                role='member'
            )
            db.session.add(member)
        msg = f"{application.applicant.username if application.applicant else 'Kullanıcı'} başvurusu onaylandı ve topluluğa eklendi."
    else:
        application.status = 'rejected'
        msg = "Başvuru reddedildi."

    db.session.commit()

    return jsonify({
        'success': True,
        'message': msg,
        'application': application.to_dict()
    })


# ===================================================================
# 6. MEMBER MANAGEMENT
# ===================================================================

@nexus_bp.route('/api/nexus/<int:nexus_id>/members', methods=['GET'])
@login_required
def get_nexus_members(nexus_id: int):
    """Returns the member list of a Nexus with optional role/query filtering."""
    nexus = db.session.get(Nexus, nexus_id)
    if not nexus:
        return jsonify({'success': False, 'message': 'Nexus bulunamadı.'}), 404

    if not nexus.is_member(current_user.id) and nexus.privacy == 'private':
        return jsonify({'success': False, 'message': 'Yetkiniz yetersiz.'}), 403

    query = request.args.get('q', '').strip().lower()
    role_filter = request.args.get('role', '').strip().lower()

    members = NexusMember.query.filter_by(nexus_id=nexus.id).all()
    results = []

    for m in members:
        if role_filter and m.role.lower() != role_filter:
            continue
        if query and m.user:
            u_name = m.user.username.lower()
            d_name = (m.nickname or m.user.get_effective_display_name()).lower()
            if query not in u_name and query not in d_name:
                continue
        results.append(m.to_dict())

    return jsonify({
        'success': True,
        'members': results,
        'total': len(results)
    })


@nexus_bp.route('/api/nexus/<int:nexus_id>/members/<int:target_user_id>/role', methods=['PUT'])
@login_required
def update_nexus_member_role(nexus_id: int, target_user_id: int):
    """Updates a member's role (admin, moderator, member). Owner or Admin only."""
    nexus = db.session.get(Nexus, nexus_id)
    if not nexus:
        return jsonify({'success': False, 'message': 'Nexus bulunamadı.'}), 404

    caller_role = nexus.get_user_role(current_user.id)
    if caller_role not in ('owner', 'admin'):
        return jsonify({'success': False, 'message': 'Yetkiniz yetersiz.'}), 403

    if target_user_id == nexus.owner_id:
        return jsonify({'success': False, 'message': 'Sahibin rolü değiştirilemez.'}), 400

    target_member = nexus.get_member(target_user_id)
    if not target_member:
        return jsonify({'success': False, 'message': 'Üye bulunamadı.'}), 404

    data = request.get_json(silent=True) or {}
    new_role = data.get('role', '').lower()

    if new_role not in ('admin', 'moderator', 'member'):
        return jsonify({'success': False, 'message': 'Geçersiz rol.'}), 400

    if caller_role != 'owner' and new_role == 'admin':
        return jsonify({'success': False, 'message': 'Yalnızca kurucu yeni admin atayabilir.'}), 403

    target_member.role = new_role
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Üye rolü güncellendi.',
        'member': target_member.to_dict()
    })


@nexus_bp.route('/api/nexus/<int:nexus_id>/members/<int:target_user_id>/kick', methods=['DELETE'])
@login_required
def kick_nexus_member(nexus_id: int, target_user_id: int):
    """Kicks a member from the Nexus."""
    nexus = db.session.get(Nexus, nexus_id)
    if not nexus:
        return jsonify({'success': False, 'message': 'Nexus bulunamadı.'}), 404

    caller_role = nexus.get_user_role(current_user.id)
    if caller_role not in ('owner', 'admin'):
        return jsonify({'success': False, 'message': 'Yetkiniz yetersiz.'}), 403

    if target_user_id == nexus.owner_id:
        return jsonify({'success': False, 'message': 'Topluluk sahibi atılamaz.'}), 400

    target_member = nexus.get_member(target_user_id)
    if not target_member:
        return jsonify({'success': False, 'message': 'Üye bulunamadı.'}), 404

    if caller_role == 'admin' and target_member.role in ('admin', 'owner'):
        return jsonify({'success': False, 'message': 'Adminler diğer adminleri atamaz.'}), 403

    target_name = target_member.user.username if target_member.user else 'Kullanıcı'
    db.session.delete(target_member)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'"{target_name}" topluluktan çıkarıldı.'
    })


# ===================================================================
# 7. CHANNELS MANAGEMENT
# ===================================================================

@nexus_bp.route('/api/nexus/<int:nexus_id>/channels', methods=['POST'])
@login_required
def create_nexus_channel(nexus_id: int):
    """Creates a new text or voice channel in the Nexus."""
    nexus = db.session.get(Nexus, nexus_id)
    if not nexus:
        return jsonify({'success': False, 'message': 'Nexus bulunamadı.'}), 404

    user_role = nexus.get_user_role(current_user.id)
    if user_role not in ('owner', 'admin'):
        return jsonify({'success': False, 'message': 'Kanal oluşturma yetkiniz yok.'}), 403

    data = request.get_json(silent=True) or {}
    name = sanitize_text(data.get('name', ''), max_len=100)
    c_type = data.get('type', 'text').lower()

    if not name or len(name) < 1:
        return jsonify({'success': False, 'message': 'Kanal adı boş olamaz.'}), 400

    if c_type not in ('text', 'voice'):
        c_type = 'text'

    channel = Channel(
        nexus_id=nexus.id,
        name=name,
        type=c_type
    )
    db.session.add(channel)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'"{name}" kanalı oluşturuldu.',
        'channel': channel.to_dict()
    }), 201


@nexus_bp.route('/api/nexus/<int:nexus_id>/channels/<int:channel_id>', methods=['DELETE'])
@login_required
def delete_nexus_channel(nexus_id: int, channel_id: int):
    """Deletes a channel in the Nexus."""
    nexus = db.session.get(Nexus, nexus_id)
    if not nexus:
        return jsonify({'success': False, 'message': 'Nexus bulunamadı.'}), 404

    user_role = nexus.get_user_role(current_user.id)
    if user_role not in ('owner', 'admin'):
        return jsonify({'success': False, 'message': 'Kanal silme yetkiniz yok.'}), 403

    channel = db.session.get(Channel, channel_id)
    if not channel or channel.nexus_id != nexus.id:
        return jsonify({'success': False, 'message': 'Kanal bulunamadı.'}), 404

    db.session.delete(channel)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Kanal başarıyla silindi.'
    })
