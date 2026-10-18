import re
import urllib.parse
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models import (
    db, User, Friendship, BlockedUser, Server, ServerMember,
    ProfileLink, ProfileProject, Badge, UserBadge, Achievement, UserAchievement
)
from security_utils import sanitize_text

profile_bp = Blueprint('profile', __name__)

# --- URL Validator Helper ---
URL_PATTERN = re.compile(
    r'^(https?:\/\/)?'  # http:// or https://
    r'(([a-zA-Z0-9\-_]+\.)+[a-zA-Z]{2,})'  # domain name
    r'(:\d+)?(\/.*)?$',  # optional port and path
    re.IGNORECASE
)

def validate_and_normalize_url(url_str: str) -> tuple[bool, str]:
    """Validates URL format and normalizes to https:// if scheme is missing."""
    if not url_str or not url_str.strip():
        return False, 'URL boş olamaz.'
    
    url = url_str.strip()
    if url.startswith(('javascript:', 'data:', 'vbscript:')):
        return False, 'Güvenlik nedeniyle bu URL protokolü kabul edilmez.'
        
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    if not URL_PATTERN.match(url):
        return False, 'Geçersiz bağlantı formatı.'
        
    return True, url

# --- Default Badges & Achievements Seeder ---
def ensure_default_badges_and_achievements():
    """Seeds starter badges and achievements into the database if not present."""
    default_badges = [
        {
            'code': 'beta_tester',
            'name': 'Beta Tester',
            'description': 'AstralPaws erken aşama test katılımcısı ve öncüsü.',
            'icon': 'flask-conical',
            'category': 'special'
        },
        {
            'code': 'developer',
            'name': 'Developer',
            'description': 'AstralPaws platform mimarı ve geliştiricisi.',
            'icon': 'code-2',
            'category': 'staff'
        },
        {
            'code': 'moderator_admin',
            'name': 'Moderatör / Admin',
            'description': 'Topluluk rehberi ve sistem yöneticisi.',
            'icon': 'shield-check',
            'category': 'staff'
        },
        {
            'code': 'premium',
            'name': 'Premium',
            'description': 'AstralPaws Ultra ayrıcalıklı destekçi üye.',
            'icon': 'crown',
            'category': 'premium'
        }
    ]

    for b in default_badges:
        existing = Badge.query.filter_by(code=b['code']).first()
        if not existing:
            db.session.add(Badge(
                code=b['code'],
                name=b['name'],
                description=b['description'],
                icon=b['icon'],
                category=b['category']
            ))

    default_achievements = [
        {
            'code': 'first_message',
            'name': 'İlk Mesaj',
            'description': 'AstralPaws sohbetinde ilk mesajını gönderdin.',
            'icon': 'message-square'
        },
        {
            'code': 'profile_architect',
            'name': 'Profil Mimarı',
            'description': 'Profilini, biyografini ve görsel temalarını kişiselleştirdin.',
            'icon': 'user-pen'
        },
        {
            'code': 'security_champion',
            'name': 'Güvenlik Şampiyonu',
            'description': 'İki Aşamalı Doğrulamayı (2FA) başarıyla aktifleştirdin.',
            'icon': 'shield-check'
        },
        {
            'code': 'community_founder',
            'name': 'Topluluk Kurucusu',
            'description': 'Kendi özel AstralPaws sunucunu kurdun.',
            'icon': 'crown'
        },
        {
            'code': 'voice_explorer',
            'name': 'Sesli Sohbet Kaşifi',
            'description': 'Bir sesli görüşme odasına katıldın.',
            'icon': 'headphones'
        }
    ]

    for a in default_achievements:
        existing = Achievement.query.filter_by(code=a['code']).first()
        if not existing:
            db.session.add(Achievement(
                code=a['code'],
                name=a['name'],
                description=a['description'],
                icon=a['icon']
            ))

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

def award_achievement(user_or_id, achievement_code: str) -> bool:
    """Helper to grant an achievement to a user if not already earned."""
    user_id = user_or_id.id if hasattr(user_or_id, 'id') else int(user_or_id)
    ach = Achievement.query.filter_by(code=achievement_code).first()
    if not ach:
        return False
    existing = UserAchievement.query.filter_by(user_id=user_id, achievement_id=ach.id).first()
    if not existing:
        db.session.add(UserAchievement(user_id=user_id, achievement_id=ach.id))
        try:
            db.session.commit()
            return True
        except Exception:
            db.session.rollback()
            return False
    return False

def assign_badge(user_or_id, badge_code: str) -> bool:
    """Helper to assign a badge to a user."""
    user_id = user_or_id.id if hasattr(user_or_id, 'id') else int(user_or_id)
    badge = Badge.query.filter_by(code=badge_code).first()
    if not badge:
        return False
    existing = UserBadge.query.filter_by(user_id=user_id, badge_id=badge.id).first()
    if not existing:
        db.session.add(UserBadge(user_id=user_id, badge_id=badge.id))
        try:
            db.session.commit()
            return True
        except Exception:
            db.session.rollback()
            return False
    return False

award_badge = assign_badge


# ===================================================================
# 1. PROFILE DETAILS & MUTUAL INFO ENDPOINT
# ===================================================================

@profile_bp.route('/api/profile/<identifier>', methods=['GET'])
@login_required
def get_detailed_profile(identifier):
    """
    Returns complete user profile with mutual friends, mutual communities,
    created servers, badges, achievements, portfolio, and social links.
    Strictly applies privacy policies without any placeholder or fake data.
    """
    user = None
    if identifier.isdigit():
        user = db.session.get(User, int(identifier))
    if not user:
        user = User.query.filter_by(public_id=identifier).first()
    if not user:
        user = User.query.filter(db.func.lower(User.username) == identifier.lower()).first()

    if not user:
        return jsonify({'success': False, 'message': 'Kullanıcı bulunamadı.'}), 404

    is_self = (current_user.id == user.id)

    # 1. Relationship status with viewer
    friendship_status = 'none'
    is_close_friend = False
    is_favorite = False
    notify_on_online = False
    friend_note = ''
    friendship_id = None

    if not is_self:
        # Check blocked
        b_me = BlockedUser.query.filter_by(blocker_id=current_user.id, blocked_id=user.id).first()
        b_other = BlockedUser.query.filter_by(blocker_id=user.id, blocked_id=current_user.id).first()
        if b_me:
            friendship_status = 'blocked_by_me'
        elif b_other:
            friendship_status = 'blocked_me'
        else:
            f = Friendship.query.filter(
                ((Friendship.user_id == current_user.id) & (Friendship.friend_id == user.id)) |
                ((Friendship.user_id == user.id) & (Friendship.friend_id == current_user.id))
            ).first()
            if f:
                friendship_id = f.id
                if f.status == 'accepted':
                    friendship_status = 'friends'
                    is_close_friend = f.get_is_close_friend(current_user.id)
                    is_favorite = f.get_is_favorite(current_user.id)
                    notify_on_online = f.get_notify_on_online(current_user.id)
                    friend_note = f.get_note(current_user.id)
                elif f.status == 'pending':
                    if f.user_id == current_user.id:
                        friendship_status = 'pending_sent'
                    else:
                        friendship_status = 'pending_received'

    # 2. Mutual Friends calculation
    mutual_friends = []
    if not is_self:
        # Get viewer's accepted friends
        viewer_f_rows = Friendship.query.filter(
            ((Friendship.user_id == current_user.id) | (Friendship.friend_id == current_user.id)) &
            (Friendship.status == 'accepted')
        ).all()
        viewer_friend_ids = set()
        for vf in viewer_f_rows:
            viewer_friend_ids.add(vf.friend_id if vf.user_id == current_user.id else vf.user_id)

        # Get target user's accepted friends
        target_f_rows = Friendship.query.filter(
            ((Friendship.user_id == user.id) | (Friendship.friend_id == user.id)) &
            (Friendship.status == 'accepted')
        ).all()
        target_friend_ids = set()
        for tf in target_f_rows:
            target_friend_ids.add(tf.friend_id if tf.user_id == user.id else tf.user_id)

        # Intersection
        mutual_ids = viewer_friend_ids.intersection(target_friend_ids)
        if mutual_ids:
            mutual_users = User.query.filter(User.id.in_(mutual_ids)).all()
            for mu in mutual_users:
                mutual_friends.append({
                    'id': mu.id,
                    'public_id': mu.public_id,
                    'username': mu.username,
                    'display_name': mu.get_effective_display_name(),
                    'avatar': f"/static/uploads/{mu.avatar}" if mu.avatar else None,
                    'color': mu.color or '#8b5cf6',
                    'presence_status': mu.presence_status or 'offline'
                })

    # 3. Mutual Communities (Servers) calculation
    mutual_servers = []
    if not is_self:
        # Check if target user hides communities
        if not user.hide_communities:
            viewer_memberships = ServerMember.query.filter_by(user_id=current_user.id).all()
            viewer_server_ids = {m.server_id for m in viewer_memberships}

            target_memberships = ServerMember.query.filter_by(user_id=user.id).all()
            target_server_ids = {m.server_id for m in target_memberships}

            common_server_ids = viewer_server_ids.intersection(target_server_ids)
            if common_server_ids:
                servers = Server.query.filter(Server.id.in_(common_server_ids)).all()
                for s in servers:
                    mutual_servers.append(s.to_dict())

    # 4. Created Communities (Owned Servers)
    created_servers = []
    if is_self or not user.hide_communities:
        owned = Server.query.filter_by(owner_id=user.id).all()
        for s in owned:
            created_servers.append(s.to_dict())

    # 5. Social Links
    links = [l.to_dict() for l in user.profile_links]

    # 6. Projects & Portfolio
    projects = [p.to_dict() for p in user.profile_projects]

    # 7. Badges & Achievements
    badges = user.get_all_badges()
    achievements = user.get_all_achievements()

    # Base serialized user
    user_dict = user.to_dict(full=is_self, viewer=current_user)

    return jsonify({
        'success': True,
        'user': user_dict,
        'is_self': is_self,
        'friendship_status': friendship_status,
        'friendship_id': friendship_id,
        'is_close_friend': is_close_friend,
        'is_favorite': is_favorite,
        'notify_on_online': notify_on_online,
        'friend_note': friend_note,
        'mutual_friends_count': len(mutual_friends),
        'mutual_friends': mutual_friends,
        'mutual_servers_count': len(mutual_servers),
        'mutual_servers': mutual_servers,
        'created_servers_count': len(created_servers),
        'created_servers': created_servers,
        'links': links,
        'projects': projects,
        'portfolio': {
            'enabled': bool(user.portfolio_enabled),
            'title': user.portfolio_title or 'Portföyüm & Çalışmalarım',
            'description': user.portfolio_description or ''
        },
        'badges': badges,
        'achievements': achievements
    })


# ===================================================================
# 2. CUSTOM THEME & ACCENT COLOR
# ===================================================================

@profile_bp.route('/api/profile/theme', methods=['POST'])
@login_required
def update_profile_theme():
    """Updates user profile accent color and card theme."""
    data = request.json or {}
    accent_color = (data.get('accent_color') or data.get('profile_accent_color') or '').strip()
    card_theme = (data.get('card_theme') or data.get('profile_card_theme') or 'cyber-glass').strip().lower()

    valid_themes = ['cyber-glass', 'neon-glow', 'minimal-dark', 'cosmic-aurora', 'retro-synth']
    if card_theme not in valid_themes:
        card_theme = 'cyber-glass'

    if accent_color:
        if not re.match(r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$', accent_color):
            return jsonify({'success': False, 'message': 'Geçersiz renk kodu (Örn: #8b5cf6)'}), 400
        current_user.profile_accent_color = accent_color

    current_user.profile_card_theme = card_theme
    db.session.commit()

    # Award "Profil Mimarı" achievement if customized
    award_achievement(current_user.id, 'profile_architect')

    return jsonify({
        'success': True,
        'message': 'Profil teması ve vurgu rengi güncellendi.',
        'profile_accent_color': current_user.profile_accent_color,
        'profile_card_theme': current_user.profile_card_theme
    })


# ===================================================================
# 3. PRIVACY SETTINGS (COMMUNITY VISIBILITY)
# ===================================================================

@profile_bp.route('/api/profile/privacy-settings', methods=['POST'])
@login_required
def update_profile_privacy_settings():
    """Updates profile privacy settings including community visibility."""
    data = request.json or {}
    
    if 'hide_communities' in data:
        current_user.hide_communities = bool(data.get('hide_communities'))
        
    last_seen = data.get('last_seen_privacy')
    if last_seen in ['everyone', 'friends_only', 'nobody']:
        current_user.last_seen_privacy = last_seen

    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Gizlilik ayarları başarıyla kaydedildi.',
        'hide_communities': bool(current_user.hide_communities),
        'last_seen_privacy': current_user.last_seen_privacy
    })


# ===================================================================
# 4. PORTFOLIO CONFIGURATION
# ===================================================================

@profile_bp.route('/api/profile/portfolio', methods=['POST'])
@login_required
def update_portfolio_settings():
    """Updates user portfolio status, title, and description."""
    data = request.json or {}
    
    if 'enabled' in data:
        current_user.portfolio_enabled = bool(data.get('enabled'))
        
    title = data.get('title')
    if title is not None:
        current_user.portfolio_title = sanitize_text(title, max_len=100) or 'Portföyüm & Çalışmalarım'

    desc = data.get('description')
    if desc is not None:
        current_user.portfolio_description = sanitize_text(desc, max_len=2000)

    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Portföy ayarları güncellendi.',
        'portfolio': {
            'enabled': bool(current_user.portfolio_enabled),
            'title': current_user.portfolio_title,
            'description': current_user.portfolio_description
        }
    })


# ===================================================================
# 5. PROFILE SOCIAL & WEB LINKS CRUD
# ===================================================================

PLATFORM_ICONS = {
    'website': 'globe',
    'github': 'github',
    'youtube': 'youtube',
    'twitch': 'twitch',
    'instagram': 'instagram',
    'x': 'twitter',
    'twitter': 'twitter',
    'linkedin': 'linkedin',
    'discord': 'message-circle',
    'other': 'link'
}

@profile_bp.route('/api/profile/links', methods=['GET'])
@login_required
def get_user_links():
    """Returns list of social/web links of current user."""
    links = ProfileLink.query.filter_by(user_id=current_user.id).order_by(ProfileLink.id.asc()).all()
    return jsonify({
        'success': True,
        'links': [l.to_dict() for l in links]
    })

@profile_bp.route('/api/profile/links', methods=['POST'])
@login_required
def add_profile_link():
    """Adds a new social or personal website link to current user profile."""
    data = request.json or {}
    title = sanitize_text(data.get('title', ''), max_len=50)
    raw_url = (data.get('url') or '').strip()
    platform = (data.get('platform') or 'website').strip().lower()

    if not title:
        return jsonify({'success': False, 'message': 'Bağlantı başlığı gereklidir.'}), 400

    valid, valid_url = validate_and_normalize_url(raw_url)
    if not valid:
        return jsonify({'success': False, 'message': valid_url}), 400

    if platform not in PLATFORM_ICONS:
        platform = 'other'

    icon = PLATFORM_ICONS.get(platform, 'link')

    link = ProfileLink(
        user_id=current_user.id,
        platform=platform,
        title=title,
        url=valid_url,
        icon=icon
    )
    db.session.add(link)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Bağlantı başarıyla eklendi.',
        'link': link.to_dict()
    })

@profile_bp.route('/api/profile/links', methods=['PUT'])
@profile_bp.route('/api/profile/links/<int:link_id>', methods=['PUT'])
@login_required
def edit_profile_link(link_id=None):
    """Edits an existing profile link."""
    data = request.json or {}
    target_id = link_id or data.get('id')
    if not target_id:
        return jsonify({'success': False, 'message': 'Bağlantı ID gereklidir.'}), 400

    link = ProfileLink.query.filter_by(id=target_id, user_id=current_user.id).first()
    if not link:
        return jsonify({'success': False, 'message': 'Bağlantı bulunamadı.'}), 404

    title = data.get('title')
    if title:
        link.title = sanitize_text(title, max_len=50)

    raw_url = data.get('url')
    if raw_url:
        valid, valid_url = validate_and_normalize_url(raw_url)
        if not valid:
            return jsonify({'success': False, 'message': valid_url}), 400
        link.url = valid_url

    platform = data.get('platform')
    if platform:
        p_clean = platform.strip().lower()
        if p_clean in PLATFORM_ICONS:
            link.platform = p_clean
            link.icon = PLATFORM_ICONS[p_clean]

    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Bağlantı güncellendi.',
        'link': link.to_dict()
    })

@profile_bp.route('/api/profile/links', methods=['DELETE'])
@profile_bp.route('/api/profile/links/<int:link_id>', methods=['DELETE'])
@login_required
def delete_profile_link(link_id=None):
    """Deletes a profile link."""
    data = request.json or {}
    target_id = link_id or data.get('id')
    if not target_id:
        return jsonify({'success': False, 'message': 'Bağlantı ID gereklidir.'}), 400

    link = ProfileLink.query.filter_by(id=target_id, user_id=current_user.id).first()
    if not link:
        return jsonify({'success': False, 'message': 'Bağlantı bulunamadı.'}), 404

    db.session.delete(link)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Bağlantı silindi.'})


# ===================================================================
# 6. FAVORITE PROJECTS & WORKS CRUD
# ===================================================================

@profile_bp.route('/api/profile/projects', methods=['GET'])
@login_required
def get_user_projects():
    """Returns list of projects of current user."""
    projects = ProfileProject.query.filter_by(user_id=current_user.id).order_by(ProfileProject.created_at.desc()).all()
    return jsonify({
        'success': True,
        'projects': [p.to_dict() for p in projects]
    })

@profile_bp.route('/api/profile/projects', methods=['POST'])
@login_required
def add_profile_project():
    """Adds a new favorite project / work."""
    data = request.json or {}
    title = sanitize_text(data.get('title', ''), max_len=100)
    description = sanitize_text(data.get('description', ''), max_len=1000)
    raw_url = (data.get('url') or '').strip()
    image_url = (data.get('image_url') or '').strip()
    is_favorite = bool(data.get('is_favorite', True))

    if not title:
        return jsonify({'success': False, 'message': 'Proje başlığı gereklidir.'}), 400

    valid_url = None
    if raw_url:
        valid, normalized = validate_and_normalize_url(raw_url)
        if not valid:
            return jsonify({'success': False, 'message': f'Geçersiz proje URL: {normalized}'}), 400
        valid_url = normalized

    proj = ProfileProject(
        user_id=current_user.id,
        title=title,
        description=description,
        url=valid_url,
        image_url=image_url if image_url else None,
        is_favorite=is_favorite
    )
    db.session.add(proj)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Proje başarıyla eklendi.',
        'project': proj.to_dict()
    })

@profile_bp.route('/api/profile/projects', methods=['PUT'])
@profile_bp.route('/api/profile/projects/<int:project_id>', methods=['PUT'])
@login_required
def edit_profile_project(project_id=None):
    """Edits an existing project."""
    data = request.json or {}
    target_id = project_id or data.get('id')
    if not target_id:
        return jsonify({'success': False, 'message': 'Proje ID gereklidir.'}), 400

    proj = ProfileProject.query.filter_by(id=target_id, user_id=current_user.id).first()
    if not proj:
        return jsonify({'success': False, 'message': 'Proje bulunamadı.'}), 404

    if 'title' in data:
        t = sanitize_text(data['title'], max_len=100)
        if t:
            proj.title = t

    if 'description' in data:
        proj.description = sanitize_text(data['description'], max_len=1000)

    if 'url' in data:
        raw = (data['url'] or '').strip()
        if raw:
            valid, norm = validate_and_normalize_url(raw)
            if not valid:
                return jsonify({'success': False, 'message': norm}), 400
            proj.url = norm
        else:
            proj.url = None

    if 'image_url' in data:
        proj.image_url = data['image_url'] if data['image_url'] else None

    if 'is_favorite' in data:
        proj.is_favorite = bool(data['is_favorite'])

    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Proje güncellendi.',
        'project': proj.to_dict()
    })

@profile_bp.route('/api/profile/projects', methods=['DELETE'])
@profile_bp.route('/api/profile/projects/<int:project_id>', methods=['DELETE'])
@login_required
def delete_profile_project(project_id=None):
    """Deletes a project."""
    data = request.json or {}
    target_id = project_id or data.get('id')
    if not target_id:
        return jsonify({'success': False, 'message': 'Proje ID gereklidir.'}), 400

    proj = ProfileProject.query.filter_by(id=target_id, user_id=current_user.id).first()
    if not proj:
        return jsonify({'success': False, 'message': 'Proje bulunamadı.'}), 404

    db.session.delete(proj)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Proje silindi.'})


# ===================================================================
# 7. BADGES & ACHIEVEMENTS CATALOG
# ===================================================================

@profile_bp.route('/api/profile/catalog/badges', methods=['GET'])
def get_badges_catalog():
    """Returns available badges in the platform."""
    badges = Badge.query.all()
    return jsonify({
        'success': True,
        'badges': [b.to_dict() for b in badges]
    })

@profile_bp.route('/api/profile/catalog/achievements', methods=['GET'])
def get_achievements_catalog():
    """Returns available achievements in the platform."""
    achievements = Achievement.query.all()
    return jsonify({
        'success': True,
        'achievements': [a.to_dict() for a in achievements]
    })
