import json
import secrets
from datetime import datetime, timezone, timedelta
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

# -------------------------------------------------------------------
# 1. User & Authentication Models
# -------------------------------------------------------------------

class User(UserMixin, db.Model):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, index=True, nullable=False, default=lambda: f"astral_{secrets.token_hex(8)}")
    email = db.Column(db.String(120), unique=True, index=True, nullable=False)
    username = db.Column(db.String(30), unique=True, index=True, nullable=False)
    display_name = db.Column(db.String(50), nullable=True)
    password_hash = db.Column(db.String(128), nullable=False)
    color = db.Column(db.String(30), default='#8b5cf6')
    is_verified = db.Column(db.Boolean, default=False)
    email_verified_at = db.Column(db.DateTime, nullable=True)
    account_status = db.Column(db.String(20), default='active')
    avatar = db.Column(db.String(255), nullable=True)
    banner = db.Column(db.String(255), nullable=True)
    banner_color = db.Column(db.String(30), default='#8b5cf6')
    bio = db.Column(db.Text, nullable=True)
    profile_accent_color = db.Column(db.String(30), default='#8b5cf6')
    profile_card_theme = db.Column(db.String(30), default='default')
    portfolio_enabled = db.Column(db.Boolean, default=False)
    portfolio_title = db.Column(db.String(100), nullable=True)
    portfolio_description = db.Column(db.Text, nullable=True)
    presence_status = db.Column(db.String(20), default='offline')
    custom_status = db.Column(db.String(100), nullable=True)
    custom_status_emoji = db.Column(db.String(10), nullable=True)
    custom_status_expires_at = db.Column(db.DateTime, nullable=True)
    last_seen_at = db.Column(db.DateTime, nullable=True)
    last_seen_privacy = db.Column(db.String(20), default='everyone')
    hide_communities = db.Column(db.Boolean, default=False)
    badges = db.Column(db.String(150), nullable=True)
    deletion_requested_at = db.Column(db.DateTime, nullable=True)
    deletion_scheduled_for = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    sessions = db.relationship('Session', backref='user', lazy=True, cascade='all, delete-orphan')
    email_tokens = db.relationship('EmailVerificationToken', backref='user', lazy=True, cascade='all, delete-orphan')
    password_reset_tokens = db.relationship('PasswordResetToken', backref='user', lazy=True, cascade='all, delete-orphan')
    two_factor = db.relationship('TwoFactorAuthentication', backref='user', uselist=False, lazy=True, cascade='all, delete-orphan')
    recovery_codes = db.relationship('RecoveryCode', backref='user', lazy=True, cascade='all, delete-orphan')
    trusted_devices = db.relationship('TrustedDevice', backref='user', lazy=True, cascade='all, delete-orphan')
    username_history = db.relationship('UsernameHistory', backref='user', lazy=True, cascade='all, delete-orphan')
    profile_links = db.relationship('ProfileLink', backref='user', lazy=True, cascade='all, delete-orphan')
    profile_projects = db.relationship('ProfileProject', backref='user', lazy=True, cascade='all, delete-orphan')
    user_badges = db.relationship('UserBadge', backref='user', lazy=True, cascade='all, delete-orphan')
    user_achievements = db.relationship('UserAchievement', backref='user', lazy=True, cascade='all, delete-orphan')

    def __init__(self, **kwargs):
        if 'status_mode' in kwargs and 'presence_status' not in kwargs:
            kwargs['presence_status'] = kwargs.pop('status_mode')
        v_code = kwargs.pop('verification_code', None)
        v_code_exp = kwargs.pop('verification_code_expires_at', None)
        super().__init__(**kwargs)
        if not self.public_id:
            self.public_id = f"astral_{secrets.token_hex(8)}"
        if v_code:
            tok = EmailVerificationToken(
                user=self,
                token_hash=secrets.token_hex(16),
                otp_code=str(v_code),
                expires_at=v_code_exp or (datetime.now(timezone.utc) + timedelta(minutes=15))
            )
            self.email_tokens.append(tok)

    @property
    def status_mode(self):
        return self.presence_status or 'offline'

    @status_mode.setter
    def status_mode(self, value):
        self.presence_status = value

    @property
    def verification_code(self):
        active_token = next((t for t in reversed(self.email_tokens) if t.used_at is None), None)
        return active_token.otp_code if active_token else None

    @verification_code.setter
    def verification_code(self, val):
        if val is None:
            for t in self.email_tokens:
                if t.used_at is None:
                    t.used_at = datetime.now(timezone.utc)
        else:
            active_token = next((t for t in reversed(self.email_tokens) if t.used_at is None), None)
            if active_token:
                active_token.otp_code = str(val)
            else:
                tok = EmailVerificationToken(
                    user=self,
                    token_hash=secrets.token_hex(16),
                    otp_code=str(val),
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=15)
                )
                self.email_tokens.append(tok)

    @property
    def verification_code_expires_at(self):
        active_token = next((t for t in reversed(self.email_tokens) if t.used_at is None), None)
        return active_token.expires_at if active_token else None

    @verification_code_expires_at.setter
    def verification_code_expires_at(self, val):
        active_token = next((t for t in reversed(self.email_tokens) if t.used_at is None), None)
        if active_token:
            active_token.expires_at = val
        elif val:
            tok = EmailVerificationToken(
                user=self,
                token_hash=secrets.token_hex(16),
                otp_code="123456",
                expires_at=val
            )
            self.email_tokens.append(tok)

    def get_effective_display_name(self) -> str:
        if self.display_name and self.display_name.strip():
            return self.display_name.strip()
        return self.username

    def get_active_custom_status(self):
        if not self.custom_status:
            return None
        if self.custom_status_expires_at:
            now = datetime.now(timezone.utc)
            exp = self.custom_status_expires_at if self.custom_status_expires_at.tzinfo else self.custom_status_expires_at.replace(tzinfo=timezone.utc)
            if exp < now:
                return None
        return self.custom_status

    def get_account_age_badge(self):
        if not self.created_at:
            return {'code': 'account_age_newbie', 'name': 'Yeni Gezgin', 'description': 'Yeni katılan üye.', 'icon': 'sprout', 'category': 'age'}
        
        now = datetime.now(timezone.utc)
        created = self.created_at if self.created_at.tzinfo else self.created_at.replace(tzinfo=timezone.utc)
        days = (now - created).days

        if days >= 365:
            return {
                'code': 'account_age_veteran',
                'name': 'Kıdemli Astral',
                'description': '1 yıldan uzun süredir AstralPaws üyesi.',
                'icon': 'sparkles',
                'category': 'age'
            }
        elif days >= 30:
            return {
                'code': 'account_age_explorer',
                'name': 'Astral Kaşif',
                'description': '1 aydan uzun süredir AstralPaws üyesi.',
                'icon': 'compass',
                'category': 'age'
            }
        else:
            return {
                'code': 'account_age_newbie',
                'name': 'Yeni Gezgin',
                'description': 'Topluluğa yeni katıldı.',
                'icon': 'sprout',
                'category': 'age'
            }

    def get_all_badges(self):
        badge_list = []
        seen_codes = set()
        
        # 1. From UserBadge relationship
        if self.user_badges:
            for ub in self.user_badges:
                if ub.badge and ub.badge.code not in seen_codes:
                    badge_list.append(ub.badge.to_dict())
                    seen_codes.add(ub.badge.code)

        # 2. From legacy comma-separated badges column if any
        if self.badges:
            codes = [c.strip() for c in self.badges.split(',') if c.strip()]
            for code in codes:
                if code not in seen_codes:
                    b_obj = Badge.query.filter_by(code=code).first()
                    if b_obj:
                        badge_list.append(b_obj.to_dict())
                    else:
                        badge_list.append({'code': code, 'name': code.replace('_', ' ').title(), 'icon': 'award', 'category': 'general'})
                    seen_codes.add(code)

        return badge_list

    def get_all_achievements(self):
        ach_list = []
        seen_codes = set()
        if self.user_achievements:
            for ua in self.user_achievements:
                if ua.achievement and ua.achievement.code not in seen_codes:
                    ach_list.append(ua.achievement.to_dict())
                    seen_codes.add(ua.achievement.code)
        return ach_list

    def to_dict(self, full=False, viewer=None):
        base_avatar = f"/static/uploads/{self.avatar}" if self.avatar else None
        base_banner = f"/static/uploads/{self.banner}" if self.banner else None
        active_cs = self.get_active_custom_status()

        data = {
            'id': self.id,
            'public_id': self.public_id,
            'username': self.username,
            'display_name': self.get_effective_display_name(),
            'color': self.color or '#8b5cf6',
            'status_mode': self.presence_status or 'offline',
            'presence_status': self.presence_status or 'offline',
            'avatar': base_avatar,
            'banner': base_banner,
            'banner_color': self.banner_color or '#8b5cf6',
            'bio': self.bio or '',
            'profile_accent_color': self.profile_accent_color or '#8b5cf6',
            'profile_card_theme': self.profile_card_theme or 'default',
            'custom_status': active_cs,
            'custom_status_emoji': self.custom_status_emoji if active_cs else None,
            'badges': [b['name'] for b in self.get_all_badges()],
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

        if full or (viewer and getattr(viewer, 'id', None) == self.id):
            data.update({
                'email': self.email,
                'is_verified': bool(self.is_verified),
                'email_verified_at': self.email_verified_at.isoformat() if self.email_verified_at else None,
                'account_status': self.account_status or 'active',
                'portfolio_enabled': bool(self.portfolio_enabled),
                'portfolio_title': self.portfolio_title or 'Portföyüm & Çalışmalarım',
                'portfolio_description': self.portfolio_description or '',
                'last_seen_at': self.last_seen_at.isoformat() if self.last_seen_at else None,
                'last_seen_privacy': self.last_seen_privacy or 'everyone',
                'hide_communities': bool(self.hide_communities),
                'two_factor_enabled': bool(self.two_factor and self.two_factor.enabled),
                'deletion_requested_at': self.deletion_requested_at.isoformat() if self.deletion_requested_at else None,
                'deletion_scheduled_for': self.deletion_scheduled_for.isoformat() if self.deletion_scheduled_for else None,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None
            })

        return data


class Session(db.Model):
    __tablename__ = 'session'

    id = db.Column(db.Integer, primary_key=True)
    session_token_hash = db.Column(db.String(64), unique=True, index=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True, nullable=False)
    device_name = db.Column(db.String(100), nullable=True)
    browser = db.Column(db.String(50), nullable=True)
    os = db.Column(db.String(50), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    last_active_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime, nullable=False)
    revoked_at = db.Column(db.DateTime, nullable=True)

    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        if self.expires_at:
            now = datetime.now(timezone.utc)
            exp = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=timezone.utc)
            if exp < now:
                return False
        return True

    def is_valid(self) -> bool:
        return self.is_active()

    def to_dict(self, current_token_hash=None):
        return {
            'id': self.id,
            'device_name': self.device_name or 'Bilinmeyen Cihaz',
            'browser': self.browser or 'Bilinmeyen Tarayıcı',
            'os': self.os or 'Bilinmeyen İşletim Sistemi',
            'ip_address': self.ip_address or '',
            'last_active_at': self.last_active_at.isoformat() if self.last_active_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'is_current': bool(current_token_hash and self.session_token_hash == current_token_hash)
        }


class EmailVerificationToken(db.Model):
    __tablename__ = 'email_verification_token'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False)
    otp_code = db.Column(db.String(10), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    resend_count = db.Column(db.Integer, default=0)
    last_sent_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def is_valid(self) -> bool:
        if self.used_at is not None:
            return False
        if self.expires_at:
            now = datetime.now(timezone.utc)
            exp = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=timezone.utc)
            if exp < now:
                return False
        return True


class PasswordResetToken(db.Model):
    __tablename__ = 'password_reset_token'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def is_valid(self) -> bool:
        if self.used_at is not None:
            return False
        if self.expires_at:
            now = datetime.now(timezone.utc)
            exp = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=timezone.utc)
            if exp < now:
                return False
        return True


class TwoFactorAuthentication(db.Model):
    __tablename__ = 'two_factor_authentication'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, index=True, nullable=False)
    secret_encrypted = db.Column(db.String(128), nullable=False)
    enabled = db.Column(db.Boolean, default=False)
    temp_secret = db.Column(db.String(128), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class RecoveryCode(db.Model):
    __tablename__ = 'recovery_code'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    code_hash = db.Column(db.String(64), nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class TrustedDevice(db.Model):
    __tablename__ = 'trusted_device'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True, nullable=False)
    device_token_hash = db.Column(db.String(64), unique=True, index=True, nullable=False)
    device_name = db.Column(db.String(100), nullable=True)
    browser = db.Column(db.String(50), nullable=True)
    os = db.Column(db.String(50), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    last_used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def is_valid(self) -> bool:
        if self.expires_at:
            now = datetime.now(timezone.utc)
            exp = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=timezone.utc)
            if exp < now:
                return False
        return True

    def to_dict(self):
        return {
            'id': self.id,
            'device_name': self.device_name or 'Güvenilir Cihaz',
            'browser': self.browser or '',
            'os': self.os or '',
            'ip_address': self.ip_address or '',
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class UsernameHistory(db.Model):
    __tablename__ = 'username_history'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True, nullable=False)
    old_username = db.Column(db.String(30), nullable=False)
    new_username = db.Column(db.String(30), nullable=False)
    changed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


# -------------------------------------------------------------------
# 2. Friendships & Blocked Users
# -------------------------------------------------------------------

class Friendship(db.Model):
    __tablename__ = 'friendship'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    friend_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending') # 'pending', 'accepted', 'rejected', 'cancelled'

    # Settings for user_id
    is_close_friend_user = db.Column(db.Boolean, default=False)
    is_favorite_user = db.Column(db.Boolean, default=False)
    is_pinned_user = db.Column(db.Boolean, default=False)
    is_dm_pinned_user = db.Column(db.Boolean, default=False)
    is_dm_closed_user = db.Column(db.Boolean, default=False)
    is_ignored_user = db.Column(db.Boolean, default=False)
    nickname_user = db.Column(db.String(50), nullable=True)
    notify_on_online_user = db.Column(db.Boolean, default=False)
    note_user = db.Column(db.Text, nullable=True)

    # Settings for friend_id
    is_close_friend_friend = db.Column(db.Boolean, default=False)
    is_favorite_friend = db.Column(db.Boolean, default=False)
    is_pinned_friend = db.Column(db.Boolean, default=False)
    is_dm_pinned_friend = db.Column(db.Boolean, default=False)
    is_dm_closed_friend = db.Column(db.Boolean, default=False)
    is_ignored_friend = db.Column(db.Boolean, default=False)
    nickname_friend = db.Column(db.String(50), nullable=True)
    notify_on_online_friend = db.Column(db.Boolean, default=False)
    note_friend = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('friendships_initiated', lazy='dynamic'))
    friend = db.relationship('User', foreign_keys=[friend_id], backref=db.backref('friendships_received', lazy='dynamic'))

    def get_is_close_friend(self, for_user_id: int) -> bool:
        if for_user_id == self.user_id:
            return bool(self.is_close_friend_user)
        return bool(self.is_close_friend_friend)

    def set_is_close_friend(self, for_user_id: int, val: bool):
        if for_user_id == self.user_id:
            self.is_close_friend_user = bool(val)
        else:
            self.is_close_friend_friend = bool(val)

    def get_is_favorite(self, for_user_id: int) -> bool:
        if for_user_id == self.user_id:
            return bool(self.is_favorite_user)
        return bool(self.is_favorite_friend)

    def set_is_favorite(self, for_user_id: int, val: bool):
        if for_user_id == self.user_id:
            self.is_favorite_user = bool(val)
        else:
            self.is_favorite_friend = bool(val)

    def get_is_pinned(self, for_user_id: int) -> bool:
        if for_user_id == self.user_id:
            return bool(self.is_pinned_user)
        return bool(self.is_pinned_friend)

    def set_is_pinned(self, for_user_id: int, val: bool):
        if for_user_id == self.user_id:
            self.is_pinned_user = bool(val)
        else:
            self.is_pinned_friend = bool(val)

    def get_is_dm_pinned(self, for_user_id: int) -> bool:
        if for_user_id == self.user_id:
            return bool(self.is_dm_pinned_user)
        return bool(self.is_dm_pinned_friend)

    def set_is_dm_pinned(self, for_user_id: int, val: bool):
        if for_user_id == self.user_id:
            self.is_dm_pinned_user = bool(val)
        else:
            self.is_dm_pinned_friend = bool(val)

    def get_is_dm_closed(self, for_user_id: int) -> bool:
        if for_user_id == self.user_id:
            return bool(self.is_dm_closed_user)
        return bool(self.is_dm_closed_friend)

    def set_is_dm_closed(self, for_user_id: int, val: bool):
        if for_user_id == self.user_id:
            self.is_dm_closed_user = bool(val)
        else:
            self.is_dm_closed_friend = bool(val)

    def get_is_ignored(self, for_user_id: int) -> bool:
        if for_user_id == self.user_id:
            return bool(self.is_ignored_user)
        return bool(self.is_ignored_friend)

    def set_is_ignored(self, for_user_id: int, val: bool):
        if for_user_id == self.user_id:
            self.is_ignored_user = bool(val)
        else:
            self.is_ignored_friend = bool(val)

    def get_nickname(self, for_user_id: int):
        if for_user_id == self.user_id:
            return self.nickname_user
        return self.nickname_friend

    def set_nickname(self, for_user_id: int, val):
        if for_user_id == self.user_id:
            self.nickname_user = val
        else:
            self.nickname_friend = val

    def get_notify_on_online(self, for_user_id: int) -> bool:
        if for_user_id == self.user_id:
            return bool(self.notify_on_online_user)
        return bool(self.notify_on_online_friend)

    def set_notify_on_online(self, for_user_id: int, val: bool):
        if for_user_id == self.user_id:
            self.notify_on_online_user = bool(val)
        else:
            self.notify_on_online_friend = bool(val)

    def get_note(self, for_user_id: int) -> str:
        if for_user_id == self.user_id:
            return self.note_user or ''
        return self.note_friend or ''

    def set_note(self, for_user_id: int, val):
        if for_user_id == self.user_id:
            self.note_user = val
        else:
            self.note_friend = val

    def to_dict(self, viewer_id: int = None):
        if not viewer_id:
            other_user = self.friend if self.friend else db.session.get(User, self.friend_id)
        elif viewer_id == self.user_id:
            other_user = self.friend if self.friend else db.session.get(User, self.friend_id)
        else:
            other_user = self.user if self.user else db.session.get(User, self.user_id)

        if not other_user:
            return None

        nick = self.get_nickname(viewer_id) if viewer_id else None
        effective_name = nick if nick and nick.strip() else other_user.get_effective_display_name()

        return {
            'id': self.id,
            'friendship_id': self.id,
            'status': self.status,
            'user_id': other_user.id,
            'public_id': other_user.public_id,
            'username': other_user.username,
            'display_name': effective_name,
            'color': other_user.color or '#8b5cf6',
            'avatar': f"/static/uploads/{other_user.avatar}" if other_user.avatar else None,
            'status_mode': other_user.presence_status or 'offline',
            'presence_status': other_user.presence_status or 'offline',
            'custom_status': other_user.get_active_custom_status(),
            'is_close_friend': self.get_is_close_friend(viewer_id) if viewer_id else False,
            'is_favorite': self.get_is_favorite(viewer_id) if viewer_id else False,
            'is_pinned': self.get_is_pinned(viewer_id) if viewer_id else False,
            'is_dm_pinned': self.get_is_dm_pinned(viewer_id) if viewer_id else False,
            'is_dm_closed': self.get_is_dm_closed(viewer_id) if viewer_id else False,
            'is_ignored': self.get_is_ignored(viewer_id) if viewer_id else False,
            'nickname': nick or '',
            'notify_on_online': self.get_notify_on_online(viewer_id) if viewer_id else False,
            'note': self.get_note(viewer_id) if viewer_id else '',
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class BlockedUser(db.Model):
    __tablename__ = 'blocked_user'

    id = db.Column(db.Integer, primary_key=True)
    blocker_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    blocked_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reason = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    blocker = db.relationship('User', foreign_keys=[blocker_id], backref=db.backref('blocked_by_users', lazy='dynamic'))
    blocked = db.relationship('User', foreign_keys=[blocked_id], backref=db.backref('blocking_users', lazy='dynamic'))

    @classmethod
    def is_blocked_between(cls, user_a_id: int, user_b_id: int) -> bool:
        if not user_a_id or not user_b_id:
            return False
        return cls.query.filter(
            ((cls.blocker_id == user_a_id) & (cls.blocked_id == user_b_id)) |
            ((cls.blocker_id == user_b_id) & (cls.blocked_id == user_a_id))
        ).first() is not None

    def to_dict(self):
        target = self.blocked if self.blocked else db.session.get(User, self.blocked_id)
        return {
            'id': self.id,
            'blocker_id': self.blocker_id,
            'blocked_id': self.blocked_id,
            'user_id': self.blocked_id,
            'username': target.username if target else '',
            'display_name': target.get_effective_display_name() if target else '',
            'avatar': f"/static/uploads/{target.avatar}" if target and target.avatar else None,
            'color': target.color if target else '#8b5cf6',
            'reason': self.reason or '',
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# -------------------------------------------------------------------
# 3. Servers, Channels & Emojis
# -------------------------------------------------------------------

class Server(db.Model):
    __tablename__ = 'server'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    invite_code = db.Column(db.String(10), unique=True, nullable=False)
    icon_color = db.Column(db.String(30), nullable=False, default='#8b5cf6')
    description = db.Column(db.Text, nullable=True)
    icon_url = db.Column(db.String(255), nullable=True)
    banner_color = db.Column(db.String(30), nullable=True, default='#8b5cf6')

    owner = db.relationship('User', foreign_keys=[owner_id], backref='owned_servers')
    members = db.relationship('ServerMember', backref='server', lazy=True, cascade='all, delete-orphan')
    channels = db.relationship('Channel', backref='server', lazy=True, cascade='all, delete-orphan')
    emojis = db.relationship('CustomEmoji', backref='server', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'owner_id': self.owner_id,
            'invite_code': self.invite_code,
            'icon_color': self.icon_color or '#8b5cf6',
            'description': self.description or '',
            'icon_url': self.icon_url,
            'banner_color': self.banner_color or '#8b5cf6',
            'member_count': len(self.members) if self.members else 0,
            'channels': [c.to_dict() for c in self.channels] if self.channels else []
        }


class ServerMember(db.Model):
    __tablename__ = 'server_member'

    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    role = db.Column(db.String(20), default='member')

    user = db.relationship('User', foreign_keys=[user_id], backref='server_memberships')

    def to_dict(self):
        return {
            'id': self.id,
            'server_id': self.server_id,
            'user_id': self.user_id,
            'role': self.role or 'member',
            'user': self.user.to_dict() if self.user else None
        }


class Channel(db.Model):
    __tablename__ = 'channel'

    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=True)
    nexus_id = db.Column(db.Integer, db.ForeignKey('nexus.id'), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False, default='text') # 'text', 'voice'

    messages = db.relationship('Message', backref='channel', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'server_id': self.server_id,
            'nexus_id': self.nexus_id,
            'name': self.name,
            'type': self.type or 'text'
        }


class CustomEmoji(db.Model):
    __tablename__ = 'custom_emoji'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    code = db.Column(db.String(60), nullable=False)
    image_url = db.Column(db.String(255), nullable=False)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    creator = db.relationship('User', foreign_keys=[created_by_id], backref='created_emojis')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'image_url': self.image_url,
            'server_id': self.server_id,
            'created_by_id': self.created_by_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# -------------------------------------------------------------------
# 4. Conversations & Direct/Group Messaging
# -------------------------------------------------------------------

class Conversation(db.Model):
    __tablename__ = 'conversation'

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20), default='direct') # 'direct', 'group'
    name = db.Column(db.String(100), nullable=True)
    icon_url = db.Column(db.String(255), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    creator = db.relationship('User', foreign_keys=[created_by_id], backref='created_conversations')
    members = db.relationship('ConversationMember', backref='conversation', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('Message', backref='conversation', lazy=True, cascade='all, delete-orphan')

    def is_member(self, user_id: int) -> bool:
        return any(m.user_id == user_id for m in self.members)

    def get_member_record(self, user_id: int):
        return next((m for m in self.members if m.user_id == user_id), None)

    def get_member_user_ids(self) -> list[int]:
        return [m.user_id for m in self.members]

    def get_display_name(self, viewer_id: int = None) -> str:
        if self.type == 'group':
            return self.name or 'Grup Sohbeti'
        if viewer_id:
            other_m = next((m for m in self.members if m.user_id != viewer_id), None)
            if other_m and other_m.user:
                return other_m.user.get_effective_display_name()
        return self.name or 'Sohbet'

    def to_dict(self, viewer_id: int = None):
        c_name = self.name
        c_icon = self.icon_url
        other_user = None

        if self.type == 'direct' and viewer_id:
            other_m = next((m for m in self.members if m.user_id != viewer_id), None)
            if other_m and other_m.user:
                other_user = other_m.user
                c_name = other_user.get_effective_display_name()
                c_icon = f"/static/uploads/{other_user.avatar}" if other_user.avatar else None

        last_msg = None
        if self.messages:
            sorted_msgs = sorted(self.messages, key=lambda x: x.timestamp or datetime.min)
            if sorted_msgs:
                last_msg = sorted_msgs[-1].to_dict(viewer_id=viewer_id)

        unread_count = 0
        if viewer_id:
            mem = self.get_member_record(viewer_id)
            if mem and mem.last_read_at:
                last_read = mem.last_read_at if mem.last_read_at.tzinfo else mem.last_read_at.replace(tzinfo=timezone.utc)
                unread_count = sum(1 for m in self.messages if m.sender_id != viewer_id and (m.timestamp if m.timestamp.tzinfo else m.timestamp.replace(tzinfo=timezone.utc)) > last_read)
            elif mem:
                unread_count = sum(1 for m in self.messages if m.sender_id != viewer_id)

        return {
            'id': self.id,
            'type': self.type or 'direct',
            'name': c_name or ('Grup Sohbeti' if self.type == 'group' else 'Sohbet'),
            'icon_url': c_icon,
            'created_by_id': self.created_by_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'member_count': len(self.members),
            'members': [m.to_dict() for m in self.members],
            'other_user': other_user.to_dict() if other_user else None,
            'last_message': last_msg,
            'unread_count': unread_count
        }


class ConversationMember(db.Model):
    __tablename__ = 'conversation_member'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    role = db.Column(db.String(20), default='member') # 'owner', 'admin', 'member'
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_read_at = db.Column(db.DateTime, nullable=True)
    last_read_message_id = db.Column(db.Integer, nullable=True)
    is_muted = db.Column(db.Boolean, default=False)

    user = db.relationship('User', foreign_keys=[user_id], backref='conversation_memberships')

    def to_dict(self):
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'user_id': self.user_id,
            'role': self.role or 'member',
            'joined_at': self.joined_at.isoformat() if self.joined_at else None,
            'last_read_at': self.last_read_at.isoformat() if self.last_read_at else None,
            'last_read_message_id': self.last_read_message_id,
            'is_muted': bool(self.is_muted),
            'user': self.user.to_dict() if self.user else None
        }


class Message(db.Model):
    __tablename__ = 'message'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    channel_id = db.Column(db.Integer, db.ForeignKey('channel.id'), nullable=True)
    text = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(30), default='text') # 'text', 'system', 'poll', 'embed'
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    attachment_url = db.Column(db.String(255), nullable=True)
    attachment_type = db.Column(db.String(30), nullable=True)
    attachment_name = db.Column(db.String(255), nullable=True)
    reply_to_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=True)
    forwarded_from_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=True)
    is_pinned = db.Column(db.Boolean, default=False)
    pinned_at = db.Column(db.DateTime, nullable=True)
    pinned_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    poll_data = db.Column(db.Text, nullable=True)
    embed_data = db.Column(db.Text, nullable=True)
    is_edited = db.Column(db.Boolean, default=False)
    edited_at = db.Column(db.DateTime, nullable=True)
    is_deleted_everyone = db.Column(db.Boolean, default=False)
    reactions = db.Column(db.Text, nullable=True)

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_direct_messages')
    pinned_by = db.relationship('User', foreign_keys=[pinned_by_id], backref='pinned_messages')
    reply_to = db.relationship('Message', remote_side=[id], foreign_keys=[reply_to_id], backref=db.backref('replies', lazy='dynamic'))
    forwarded_from = db.relationship('Message', remote_side=[id], foreign_keys=[forwarded_from_id], backref=db.backref('forwards', lazy='dynamic'))
    attachments = db.relationship('MessageAttachment', backref='message', lazy=True, cascade='all, delete-orphan')

    def to_dict(self, viewer_id: int = None):
        is_deleted = bool(self.is_deleted_everyone)
        display_text = "🚫 Bu mesaj silindi." if is_deleted else self.text

        reactions_dict = {}
        if self.reactions:
            try:
                reactions_dict = json.loads(self.reactions)
            except Exception:
                reactions_dict = {}

        poll_dict = None
        if self.poll_data:
            try:
                poll_dict = json.loads(self.poll_data)
            except Exception:
                poll_dict = None

        embed_dict = None
        if self.embed_data:
            try:
                embed_dict = json.loads(self.embed_data)
            except Exception:
                embed_dict = None

        reply_info = None
        if self.reply_to:
            reply_sender = self.reply_to.sender
            reply_info = {
                'id': self.reply_to.id,
                'text': "🚫 Bu mesaj silindi." if self.reply_to.is_deleted_everyone else self.reply_to.text,
                'username': reply_sender.username if reply_sender else '',
                'display_name': reply_sender.get_effective_display_name() if reply_sender else '',
                'color': reply_sender.color if reply_sender else '#8b5cf6'
            }

        forward_info = None
        if self.forwarded_from:
            fwd_sender = self.forwarded_from.sender
            forward_info = {
                'id': self.forwarded_from.id,
                'text': "🚫 Bu mesaj silindi." if self.forwarded_from.is_deleted_everyone else self.forwarded_from.text,
                'username': fwd_sender.username if fwd_sender else '',
                'display_name': fwd_sender.get_effective_display_name() if fwd_sender else '',
                'color': fwd_sender.color if fwd_sender else '#8b5cf6'
            }

        attachments_list = [a.to_dict() for a in self.attachments]
        if not attachments_list and self.attachment_url and not is_deleted:
            attachments_list.append({
                'id': 0,
                'file_url': self.attachment_url,
                'file_name': self.attachment_name or 'attachment',
                'file_size': 0,
                'file_type': self.attachment_type or 'file',
                'is_spoiler': False
            })

        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'channel_id': self.channel_id,
            'sender_id': self.sender_id,
            'receiver_id': self.receiver_id,
            'username': self.sender.username if self.sender else '',
            'display_name': self.sender.get_effective_display_name() if self.sender else '',
            'color': self.sender.color if self.sender else '#8b5cf6',
            'sender': self.sender.to_dict() if self.sender else None,
            'text': display_text,
            'message_type': self.message_type or 'text',
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'created_at': self.timestamp.isoformat() if self.timestamp else None,
            'attachment_url': self.attachment_url if not is_deleted else None,
            'attachment_type': self.attachment_type if not is_deleted else None,
            'attachment_name': self.attachment_name if not is_deleted else None,
            'attachments': attachments_list if not is_deleted else [],
            'reply_to_id': self.reply_to_id,
            'reply_to': reply_info,
            'forwarded_from_id': self.forwarded_from_id,
            'forwarded_from': forward_info,
            'is_pinned': bool(self.is_pinned),
            'pinned_at': self.pinned_at.isoformat() if self.pinned_at else None,
            'pinned_by_id': self.pinned_by_id,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'is_edited': bool(self.is_edited),
            'edited_at': self.edited_at.isoformat() if self.edited_at else None,
            'is_deleted_everyone': is_deleted,
            'reactions': reactions_dict,
            'poll_data': poll_dict,
            'embed_data': embed_dict
        }


class MessageAttachment(db.Model):
    __tablename__ = 'message_attachment'

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=False)
    file_url = db.Column(db.String(255), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer, default=0)
    file_type = db.Column(db.String(30), default='file') # 'image', 'video', 'audio', 'file'
    mime_type = db.Column(db.String(100), nullable=True)
    is_spoiler = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'message_id': self.message_id,
            'file_url': self.file_url,
            'file_name': self.file_name,
            'file_size': self.file_size,
            'file_type': self.file_type or 'file',
            'mime_type': self.mime_type,
            'is_spoiler': bool(self.is_spoiler),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class HiddenMessage(db.Model):
    __tablename__ = 'hidden_message'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', foreign_keys=[user_id], backref='hidden_messages')
    message = db.relationship('Message', foreign_keys=[message_id], backref='hidden_by_users')


class SavedMessage(db.Model):
    __tablename__ = 'saved_message'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=False)
    note = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (db.UniqueConstraint('user_id', 'message_id', name='uq_user_saved_message'),)

    user = db.relationship('User', foreign_keys=[user_id], backref='saved_messages')
    message = db.relationship('Message', foreign_keys=[message_id], backref='saved_instances')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'message_id': self.message_id,
            'note': self.note or '',
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'message': self.message.to_dict() if self.message else None
        }


class ScheduledMessage(db.Model):
    __tablename__ = 'scheduled_message'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=True)
    channel_id = db.Column(db.Integer, db.ForeignKey('channel.id'), nullable=True)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    text = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(30), default='text')
    scheduled_for = db.Column(db.DateTime, nullable=False)
    attachment_url = db.Column(db.String(255), nullable=True)
    attachment_type = db.Column(db.String(30), nullable=True)
    attachment_name = db.Column(db.String(255), nullable=True)
    expires_in_seconds = db.Column(db.Integer, nullable=True)
    poll_data = db.Column(db.Text, nullable=True)
    embed_data = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending') # 'pending', 'sent', 'cancelled', 'failed'
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', foreign_keys=[user_id], backref='scheduled_messages')
    conversation = db.relationship('Conversation', foreign_keys=[conversation_id])
    channel = db.relationship('Channel', foreign_keys=[channel_id])
    receiver = db.relationship('User', foreign_keys=[receiver_id])

    def to_dict(self):
        poll_dict = None
        if self.poll_data:
            try:
                poll_dict = json.loads(self.poll_data)
            except Exception:
                poll_dict = None

        embed_dict = None
        if self.embed_data:
            try:
                embed_dict = json.loads(self.embed_data)
            except Exception:
                embed_dict = None

        return {
            'id': self.id,
            'user_id': self.user_id,
            'conversation_id': self.conversation_id,
            'channel_id': self.channel_id,
            'receiver_id': self.receiver_id,
            'text': self.text,
            'message_type': self.message_type or 'text',
            'scheduled_for': self.scheduled_for.isoformat() if self.scheduled_for else None,
            'attachment_url': self.attachment_url,
            'attachment_type': self.attachment_type,
            'attachment_name': self.attachment_name,
            'expires_in_seconds': self.expires_in_seconds,
            'poll_data': poll_dict,
            'embed_data': embed_dict,
            'status': self.status or 'pending',
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# -------------------------------------------------------------------
# 5. Profile Extensions (Links, Projects, Badges, Achievements)
# -------------------------------------------------------------------

class ProfileLink(db.Model):
    __tablename__ = 'profile_link'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    platform = db.Column(db.String(30), nullable=True)
    title = db.Column(db.String(50), nullable=False)
    url = db.Column(db.String(255), nullable=False)
    icon = db.Column(db.String(30), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'platform': self.platform or '',
            'title': self.title,
            'url': self.url,
            'icon': self.icon or 'link',
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ProfileProject(db.Model):
    __tablename__ = 'profile_project'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    url = db.Column(db.String(255), nullable=True)
    image_url = db.Column(db.String(255), nullable=True)
    is_favorite = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'description': self.description or '',
            'url': self.url or '',
            'image_url': self.image_url or '',
            'is_favorite': bool(self.is_favorite),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Badge(db.Model):
    __tablename__ = 'badge'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), nullable=False, unique=True)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    icon = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(30), nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'description': self.description,
            'icon': self.icon,
            'category': self.category or 'general'
        }


class UserBadge(db.Model):
    __tablename__ = 'user_badge'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True, nullable=False)
    badge_id = db.Column(db.Integer, db.ForeignKey('badge.id'), index=True, nullable=False)
    assigned_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    badge = db.relationship('Badge', foreign_keys=[badge_id])

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'badge_id': self.badge_id,
            'assigned_at': self.assigned_at.isoformat() if self.assigned_at else None,
            'badge': self.badge.to_dict() if self.badge else None
        }


class Achievement(db.Model):
    __tablename__ = 'achievement'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), nullable=False, unique=True)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    icon = db.Column(db.String(50), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'description': self.description,
            'icon': self.icon
        }


class UserAchievement(db.Model):
    __tablename__ = 'user_achievement'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True, nullable=False)
    achievement_id = db.Column(db.Integer, db.ForeignKey('achievement.id'), index=True, nullable=False)
    earned_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    achievement = db.relationship('Achievement', foreign_keys=[achievement_id])

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'achievement_id': self.achievement_id,
            'earned_at': self.earned_at.isoformat() if self.earned_at else None,
            'achievement': self.achievement.to_dict() if self.achievement else None
        }


# -------------------------------------------------------------------
# 6. Nexus Communities & Applications
# -------------------------------------------------------------------

class Nexus(db.Model):
    __tablename__ = 'nexus'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    icon_url = db.Column(db.String(255), nullable=True)
    icon_color = db.Column(db.String(30), default='#8b5cf6')
    banner_url = db.Column(db.String(255), nullable=True)
    banner_color = db.Column(db.String(30), default='#8b5cf6')
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rules = db.Column(db.Text, nullable=True)
    privacy = db.Column(db.String(20), default='public') # 'public', 'private', 'gated'
    requires_application = db.Column(db.Boolean, default=False)
    verification_level = db.Column(db.String(30), default='none') # 'none', 'low', 'medium', 'high'
    age_restricted = db.Column(db.Boolean, default=False)
    min_age = db.Column(db.Integer, default=13)
    category = db.Column(db.String(50), default='general')
    tags = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    owner = db.relationship('User', foreign_keys=[owner_id], backref='owned_nexuses')
    members = db.relationship('NexusMember', backref='nexus', lazy=True, cascade='all, delete-orphan')
    invites = db.relationship('NexusInvite', backref='nexus', lazy=True, cascade='all, delete-orphan')
    applications = db.relationship('NexusApplication', backref='nexus', lazy=True, cascade='all, delete-orphan')
    channels = db.relationship('Channel', backref='nexus', lazy=True, cascade='all, delete-orphan')

    def is_member(self, user_id: int) -> bool:
        if not user_id:
            return False
        return any(m.user_id == user_id for m in self.members)

    def get_member(self, user_id: int):
        if not user_id:
            return None
        return next((m for m in self.members if m.user_id == user_id), None)

    def get_user_role(self, user_id: int):
        if not user_id:
            return None
        if user_id == self.owner_id:
            return 'owner'
        mem = self.get_member(user_id)
        return mem.role if mem else None

    def set_tags(self, tags_data):
        if isinstance(tags_data, list):
            self.tags = json.dumps(tags_data)
        elif isinstance(tags_data, str):
            tags_list = [t.strip() for t in tags_data.split(',') if t.strip()]
            self.tags = json.dumps(tags_list)
        else:
            self.tags = None

    def get_tags(self) -> list:
        if not self.tags:
            return []
        try:
            if self.tags.startswith('['):
                return json.loads(self.tags)
            return [t.strip() for t in self.tags.split(',') if t.strip()]
        except Exception:
            return [t.strip() for t in self.tags.split(',') if t.strip()]

    def to_dict(self, viewer_id: int = None):
        user_role = self.get_user_role(viewer_id) if viewer_id else None
        is_mem = self.is_member(viewer_id) if viewer_id else False

        return {
            'id': self.id,
            'name': self.name,
            'description': self.description or '',
            'icon_url': self.icon_url,
            'icon_color': self.icon_color or '#8b5cf6',
            'banner_url': self.banner_url,
            'banner_color': self.banner_color or '#8b5cf6',
            'owner_id': self.owner_id,
            'rules': self.rules or '',
            'privacy': self.privacy or 'public',
            'requires_application': bool(self.requires_application),
            'verification_level': self.verification_level or 'none',
            'age_restricted': bool(self.age_restricted),
            'min_age': self.min_age or 13,
            'category': self.category or 'general',
            'tags': self.get_tags(),
            'member_count': len(self.members) if self.members else 0,
            'channels': [c.to_dict() for c in self.channels] if self.channels else [],
            'user_role': user_role,
            'is_member': is_mem,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class NexusMember(db.Model):
    __tablename__ = 'nexus_member'

    id = db.Column(db.Integer, primary_key=True)
    nexus_id = db.Column(db.Integer, db.ForeignKey('nexus.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    role = db.Column(db.String(20), default='member') # 'owner', 'admin', 'moderator', 'member'
    permissions = db.Column(db.Text, nullable=True)
    nickname = db.Column(db.String(50), nullable=True)
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', foreign_keys=[user_id], backref='nexus_memberships')

    def to_dict(self):
        return {
            'id': self.id,
            'nexus_id': self.nexus_id,
            'user_id': self.user_id,
            'role': self.role or 'member',
            'nickname': self.nickname or '',
            'joined_at': self.joined_at.isoformat() if self.joined_at else None,
            'user': self.user.to_dict() if self.user else None
        }


class NexusInvite(db.Model):
    __tablename__ = 'nexus_invite'

    id = db.Column(db.Integer, primary_key=True)
    nexus_id = db.Column(db.Integer, db.ForeignKey('nexus.id'), nullable=False)
    code = db.Column(db.String(32), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    max_uses = db.Column(db.Integer, default=0)
    uses_count = db.Column(db.Integer, default=0)
    expires_at = db.Column(db.DateTime, nullable=True)
    is_revoked = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    created_by = db.relationship('User', foreign_keys=[created_by_id], backref='created_nexus_invites')

    def is_valid(self) -> bool:
        if self.is_revoked:
            return False
        if self.expires_at:
            now = datetime.now(timezone.utc)
            exp = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=timezone.utc)
            if exp < now:
                return False
        if self.max_uses and self.max_uses > 0 and self.uses_count >= self.max_uses:
            return False
        return True

    def to_dict(self):
        return {
            'id': self.id,
            'nexus_id': self.nexus_id,
            'code': self.code,
            'created_by_id': self.created_by_id,
            'max_uses': self.max_uses or 0,
            'uses_count': self.uses_count or 0,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'is_revoked': bool(self.is_revoked),
            'is_valid': self.is_valid(),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class NexusApplication(db.Model):
    __tablename__ = 'nexus_application'

    id = db.Column(db.Integer, primary_key=True)
    nexus_id = db.Column(db.Integer, db.ForeignKey('nexus.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    application_text = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending') # 'pending', 'approved', 'rejected'
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    review_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    reviewed_at = db.Column(db.DateTime, nullable=True)

    applicant = db.relationship('User', foreign_keys=[user_id], backref='nexus_applications')
    reviewed_by = db.relationship('User', foreign_keys=[reviewed_by_id], backref='reviewed_nexus_applications')

    def to_dict(self):
        user_obj = self.applicant if self.applicant else db.session.get(User, self.user_id)
        reviewer_obj = self.reviewed_by if self.reviewed_by else (db.session.get(User, self.reviewed_by_id) if self.reviewed_by_id else None)
        return {
            'id': self.id,
            'nexus_id': self.nexus_id,
            'user_id': self.user_id,
            'applicant': user_obj.to_dict() if user_obj else None,
            'application_text': self.application_text,
            'status': self.status or 'pending',
            'reviewed_by_id': self.reviewed_by_id,
            'reviewed_by': reviewer_obj.to_dict() if reviewer_obj else None,
            'review_notes': self.review_notes or '',
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None
        }
