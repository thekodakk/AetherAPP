import json
from datetime import datetime, timezone, timedelta
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from security_utils import generate_user_public_id

db = SQLAlchemy()

class User(db.Model, UserMixin):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, index=True, default=generate_user_public_id)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    username = db.Column(db.String(30), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(50), nullable=True)
    password_hash = db.Column(db.String(128), nullable=False)
    color = db.Column(db.String(30), default='#8b5cf6')
    
    # Verification & Account Status
    is_verified = db.Column(db.Boolean, default=False)
    email_verified_at = db.Column(db.DateTime, nullable=True)
    account_status = db.Column(db.String(20), default='active')  # active, unverified, disabled, suspended, pending_deletion, deleted
    
    # Profile Customization & Theme
    avatar = db.Column(db.String(255), nullable=True)
    banner = db.Column(db.String(255), nullable=True)
    banner_color = db.Column(db.String(30), default='#6366f1')
    bio = db.Column(db.Text, default='Hey there! I am using AstralPaws.')
    profile_accent_color = db.Column(db.String(30), default='#8b5cf6')
    profile_card_theme = db.Column(db.String(30), default='cyber-glass')  # cyber-glass, neon-glow, minimal-dark, cosmic-aurora, retro-synth
    
    # Portfolio Section
    portfolio_enabled = db.Column(db.Boolean, default=False)
    portfolio_title = db.Column(db.String(100), default='Portföyüm & Çalışmalarım')
    portfolio_description = db.Column(db.Text, default='')
    
    # Presence & Custom Status
    presence_status = db.Column(db.String(20), default='online')  # online, idle, dnd, invisible, offline
    custom_status = db.Column(db.String(100), default='')
    custom_status_emoji = db.Column(db.String(10), default='')
    custom_status_expires_at = db.Column(db.DateTime, nullable=True)
    
    # Privacy & Activity
    last_seen_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen_privacy = db.Column(db.String(20), default='everyone')  # everyone, friends_only, nobody
    hide_communities = db.Column(db.Boolean, default=False)  # Hide joined communities from public profile
    badges = db.Column(db.String(150), default='🌟 Astral Explorer,⚡ Member')
    
    # Account Deletion Grace Period (14 days)
    deletion_requested_at = db.Column(db.DateTime, nullable=True)
    deletion_scheduled_for = db.Column(db.DateTime, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    sessions = db.relationship('Session', backref='user', lazy=True, cascade='all, delete-orphan')
    verification_tokens = db.relationship('EmailVerificationToken', backref='user', lazy=True, cascade='all, delete-orphan')
    reset_tokens = db.relationship('PasswordResetToken', backref='user', lazy=True, cascade='all, delete-orphan')
    two_factor = db.relationship('TwoFactorAuthentication', backref='user', uselist=False, lazy=True, cascade='all, delete-orphan')
    recovery_codes = db.relationship('RecoveryCode', backref='user', lazy=True, cascade='all, delete-orphan')
    trusted_devices = db.relationship('TrustedDevice', backref='user', lazy=True, cascade='all, delete-orphan')
    username_history = db.relationship('UsernameHistory', backref='user', lazy=True, cascade='all, delete-orphan')
    profile_links = db.relationship('ProfileLink', backref='user', lazy=True, cascade='all, delete-orphan', order_by='ProfileLink.id.asc()')
    profile_projects = db.relationship('ProfileProject', backref='user', lazy=True, cascade='all, delete-orphan', order_by='ProfileProject.created_at.desc()')
    user_badges = db.relationship('UserBadge', backref='user', lazy=True, cascade='all, delete-orphan')
    user_achievements = db.relationship('UserAchievement', backref='user', lazy=True, cascade='all, delete-orphan')

    # Backward compatibility properties
    @property
    def status_mode(self):
        return self.presence_status or 'online'

    @status_mode.setter
    def status_mode(self, val):
        self.presence_status = val

    @property
    def verification_code(self):
        for tok in reversed(self.verification_tokens):
            if tok.is_valid():
                return tok.otp_code
        return None

    @verification_code.setter
    def verification_code(self, val):
        if val:
            import security_utils
            self.verification_tokens.append(EmailVerificationToken(
                token_hash=security_utils.hash_token(security_utils.generate_secure_token(32)),
                otp_code=str(val),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=15)
            ))

    @property
    def verification_code_expires_at(self):
        for tok in reversed(self.verification_tokens):
            if tok.is_valid():
                return tok.expires_at
        return None

    @verification_code_expires_at.setter
    def verification_code_expires_at(self, val):
        if val and self.verification_tokens:
            self.verification_tokens[-1].expires_at = val

    def get_effective_display_name(self) -> str:
        return self.display_name if self.display_name and self.display_name.strip() else self.username

    def is_custom_status_active(self) -> bool:
        if not self.custom_status:
            return False
        if self.custom_status_expires_at:
            exp = self.custom_status_expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp:
                return False
        return True

    def get_active_custom_status(self) -> str:
        return self.custom_status if self.is_custom_status_active() else ''

    def get_account_age_badge(self) -> dict:
        """Calculates dynamic account age badge based on creation date."""
        if not self.created_at:
            return {'code': 'account_age_newbie', 'name': 'Yeni Üye', 'description': 'AstralPaws üyesi', 'icon': 'calendar'}
        
        now = datetime.now(timezone.utc)
        created = self.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        
        diff = now - created
        days = diff.days
        
        if days >= 365:
            years = max(1, days // 365)
            return {
                'code': 'account_age_veteran',
                'name': f'Astral Öncüsü ({years}+ Yıl)',
                'description': f'{years} yılı aşkın süredir AstralPaws topluluğunun parçası.',
                'icon': 'shield-check',
                'category': 'system'
            }
        elif days >= 180:
            return {
                'code': 'account_age_senior',
                'name': 'Astral Kıdemli (6+ Ay)',
                'description': '6 aydan uzun süredir aktif AstralPaws üyesi.',
                'icon': 'sparkles',
                'category': 'system'
            }
        elif days >= 30:
            return {
                'code': 'account_age_explorer',
                'name': 'Astral Gezgini (1+ Ay)',
                'description': '1 aydan uzun süredir topluluğun üyesi.',
                'icon': 'compass',
                'category': 'system'
            }
        else:
            return {
                'code': 'account_age_newbie',
                'name': 'Yeni Üye',
                'description': 'AstralPaws evrenine yeni katıldı.',
                'icon': 'sparkle',
                'category': 'system'
            }

    def get_all_badges(self) -> list:
        """Returns structured list of user badges including dynamic account age badge."""
        result = [self.get_account_age_badge()]
        
        # Add assigned badges from user_badges relationship
        for ub in self.user_badges:
            if ub.badge:
                b_dict = ub.badge.to_dict()
                b_dict['assigned_at'] = ub.assigned_at.strftime('%Y-%m-%d') if ub.assigned_at else ''
                # Avoid duplicate codes
                if not any(b['code'] == b_dict['code'] for b in result):
                    result.append(b_dict)

        # Backward compatibility for comma-separated legacy badges field
        if self.badges:
            legacy_names = [b.strip() for b in self.badges.split(',') if b.strip()]
            for name in legacy_names:
                clean_name = name.replace('🌟', '').replace('⚡', '').replace('🤖', '').strip()
                if not any(b['name'].lower() == clean_name.lower() for b in result):
                    result.append({
                        'code': f"legacy_{abs(hash(clean_name)) % 10000}",
                        'name': clean_name,
                        'description': f'{clean_name} Rozeti',
                        'icon': 'award',
                        'category': 'legacy'
                    })
        return result

    def get_all_achievements(self) -> list:
        """Returns list of achievements earned by user."""
        res = []
        for ua in self.user_achievements:
            if ua.achievement:
                a_dict = ua.achievement.to_dict()
                a_dict['earned_at'] = ua.earned_at.strftime('%Y-%m-%d') if ua.earned_at else ''
                res.append(a_dict)
        return res

    def to_dict(self, full: bool = False, viewer: 'User' = None) -> dict:
        """
        Serializes user object safely for API responses.
        NEVER leaks passwords, token secrets, or unauthorized privacy data.
        """
        # Format avatar URL
        avatar_url = f"/static/uploads/{self.avatar}" if self.avatar else None
        banner_url = f"/static/uploads/{self.banner}" if self.banner else None

        active_status = self.presence_status or 'online'
        # If user is in invisible mode and viewer is not themselves, appear offline
        is_self = viewer and viewer.id == self.id
        if active_status == 'invisible' and not is_self and not full:
            active_status = 'offline'

        # Check Last Seen Privacy
        show_last_seen = True
        if not is_self and not full:
            if self.last_seen_privacy == 'nobody':
                show_last_seen = False
            elif self.last_seen_privacy == 'friends_only':
                # Friendship check if viewer provided
                if viewer:
                    is_friend = Friendship.query.filter(
                        ((Friendship.user_id == self.id) & (Friendship.friend_id == viewer.id) & (Friendship.status == 'accepted')) |
                        ((Friendship.user_id == viewer.id) & (Friendship.friend_id == self.id) & (Friendship.status == 'accepted'))
                    ).first() is not None
                    show_last_seen = is_friend
                else:
                    show_last_seen = False

        data = {
            'id': self.id,
            'public_id': self.public_id,
            'username': self.username,
            'display_name': self.get_effective_display_name(),
            'color': self.color or '#8b5cf6',
            'avatar': avatar_url,
            'banner': banner_url,
            'banner_color': self.banner_color or '#6366f1',
            'profile_accent_color': self.profile_accent_color or '#8b5cf6',
            'profile_card_theme': self.profile_card_theme or 'cyber-glass',
            'status_mode': active_status,
            'presence_status': active_status,
            'custom_status': self.get_active_custom_status(),
            'custom_status_emoji': self.custom_status_emoji or '',
            'bio': self.bio or '',
            'badges': [b['name'] for b in self.get_all_badges()],
            'badge_list': self.get_all_badges(),
            'achievements': self.get_all_achievements(),
            'account_age_badge': self.get_account_age_badge(),
            'created_at': self.created_at.strftime('%Y-%m-%d') if self.created_at else '',
            'last_seen_at': self.last_seen_at.isoformat() if (show_last_seen and self.last_seen_at) else None,
            'hide_communities': bool(self.hide_communities),
            'portfolio_enabled': bool(self.portfolio_enabled),
            'portfolio_title': self.portfolio_title or 'Portföyüm & Çalışmalarım',
            'portfolio_description': self.portfolio_description or ''
        }

        if full:
            has_2fa = bool(self.two_factor and self.two_factor.enabled)
            data.update({
                'email': self.email,
                'is_verified': self.is_verified,
                'email_verified_at': self.email_verified_at.isoformat() if self.email_verified_at else None,
                'account_status': self.account_status or 'active',
                'last_seen_privacy': self.last_seen_privacy or 'everyone',
                'two_factor_enabled': has_2fa,
                'is_pending_deletion': self.account_status == 'pending_deletion',
                'deletion_scheduled_for': self.deletion_scheduled_for.isoformat() if self.deletion_scheduled_for else None
            })

        return data


class Session(db.Model):
    __tablename__ = 'session'

    id = db.Column(db.Integer, primary_key=True)
    session_token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
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
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) <= exp

    def to_dict(self, current_token_hash: str = None) -> dict:
        return {
            'id': self.id,
            'device_name': self.device_name or 'Bilinmeyen Cihaz',
            'browser': self.browser or 'Tarayıcı',
            'os': self.os or 'İşletim Sistemi',
            'ip_address': self.ip_address or '127.0.0.1',
            'last_active_at': self.last_active_at.isoformat() if self.last_active_at else '',
            'created_at': self.created_at.isoformat() if self.created_at else '',
            'is_current': bool(current_token_hash and self.session_token_hash == current_token_hash)
        }


class EmailVerificationToken(db.Model):
    __tablename__ = 'email_verification_token'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    otp_code = db.Column(db.String(10), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    resend_count = db.Column(db.Integer, default=1)
    last_sent_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def is_valid(self) -> bool:
        if self.used_at is not None:
            return False
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) <= exp


class PasswordResetToken(db.Model):
    __tablename__ = 'password_reset_token'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def is_valid(self) -> bool:
        if self.used_at is not None:
            return False
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) <= exp


class TwoFactorAuthentication(db.Model):
    __tablename__ = 'two_factor_authentication'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False, index=True)
    secret_encrypted = db.Column(db.String(128), nullable=False)
    enabled = db.Column(db.Boolean, default=False)
    temp_secret = db.Column(db.String(128), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class RecoveryCode(db.Model):
    __tablename__ = 'recovery_code'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    code_hash = db.Column(db.String(64), nullable=False, index=True)
    used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def is_available(self) -> bool:
        return self.used_at is None


class TrustedDevice(db.Model):
    __tablename__ = 'trusted_device'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    device_token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    device_name = db.Column(db.String(100), nullable=True)
    browser = db.Column(db.String(50), nullable=True)
    os = db.Column(db.String(50), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    last_used_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def is_valid(self) -> bool:
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) <= exp

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'device_name': self.device_name or 'Güvenilir Cihaz',
            'browser': self.browser or 'Tarayıcı',
            'os': self.os or 'İşletim Sistemi',
            'ip_address': self.ip_address or '127.0.0.1',
            'created_at': self.created_at.strftime('%Y-%m-%d') if self.created_at else '',
            'expires_at': self.expires_at.strftime('%Y-%m-%d') if self.expires_at else '',
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else ''
        }


class UsernameHistory(db.Model):
    __tablename__ = 'username_history'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    old_username = db.Column(db.String(30), nullable=False)
    new_username = db.Column(db.String(30), nullable=False)
    changed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


# --- Profile System Models (Links, Projects, Badges, Achievements) ---

class ProfileLink(db.Model):
    __tablename__ = 'profile_link'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    platform = db.Column(db.String(30), default='website')  # website, github, youtube, twitch, instagram, twitter, linkedin, discord, other
    title = db.Column(db.String(50), nullable=False)
    url = db.Column(db.String(255), nullable=False)
    icon = db.Column(db.String(30), default='globe')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'platform': self.platform,
            'title': self.title,
            'url': self.url,
            'icon': self.icon or 'globe',
            'created_at': self.created_at.strftime('%Y-%m-%d') if self.created_at else ''
        }


class ProfileProject(db.Model):
    __tablename__ = 'profile_project'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, default='')
    url = db.Column(db.String(255), nullable=True)
    image_url = db.Column(db.String(255), nullable=True)
    is_favorite = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'description': self.description or '',
            'url': self.url or '',
            'image_url': self.image_url,
            'is_favorite': bool(self.is_favorite),
            'created_at': self.created_at.strftime('%Y-%m-%d') if self.created_at else ''
        }


class Badge(db.Model):
    __tablename__ = 'badge'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    icon = db.Column(db.String(50), nullable=False)  # Lucide icon name
    category = db.Column(db.String(30), default='special')  # system, special, staff, premium

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'description': self.description,
            'icon': self.icon,
            'category': self.category
        }


class UserBadge(db.Model):
    __tablename__ = 'user_badge'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    badge_id = db.Column(db.Integer, db.ForeignKey('badge.id'), nullable=False, index=True)
    assigned_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    badge = db.relationship('Badge', lazy='joined')


class Achievement(db.Model):
    __tablename__ = 'achievement'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    icon = db.Column(db.String(50), nullable=False)

    def to_dict(self) -> dict:
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
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    achievement_id = db.Column(db.Integer, db.ForeignKey('achievement.id'), nullable=False, index=True)
    earned_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    achievement = db.relationship('Achievement', lazy='joined')

    def to_dict(self) -> dict:
        data = self.achievement.to_dict() if self.achievement else {}
        data['earned_at'] = self.earned_at.strftime('%Y-%m-%d %H:%M') if self.earned_at else ''
        return data


# --- Existing Models with Full Backward Compatibility ---

class Friendship(db.Model):
    __tablename__ = 'friendship'
    __table_args__ = (db.UniqueConstraint('user_id', 'friend_id', name='_user_friend_uc'),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    friend_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending, accepted, rejected, cancelled

    # Personal flags & preferences for user_id
    is_close_friend_user = db.Column(db.Boolean, default=False)
    is_favorite_user = db.Column(db.Boolean, default=False)
    notify_on_online_user = db.Column(db.Boolean, default=False)
    note_user = db.Column(db.Text, nullable=True)

    # Personal flags & preferences for friend_id
    is_close_friend_friend = db.Column(db.Boolean, default=False)
    is_favorite_friend = db.Column(db.Boolean, default=False)
    notify_on_online_friend = db.Column(db.Boolean, default=False)
    note_friend = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', foreign_keys=[user_id])
    friend = db.relationship('User', foreign_keys=[friend_id])

    def get_other_user(self, viewer_id: int):
        return self.friend if self.user_id == viewer_id else self.user

    def get_is_sender(self, viewer_id: int) -> bool:
        return self.user_id == viewer_id

    def get_is_close_friend(self, viewer_id: int) -> bool:
        return bool(self.is_close_friend_user if self.user_id == viewer_id else self.is_close_friend_friend)

    def set_is_close_friend(self, viewer_id: int, val: bool):
        if self.user_id == viewer_id:
            self.is_close_friend_user = val
        else:
            self.is_close_friend_friend = val

    def get_is_favorite(self, viewer_id: int) -> bool:
        return bool(self.is_favorite_user if self.user_id == viewer_id else self.is_favorite_friend)

    def set_is_favorite(self, viewer_id: int, val: bool):
        if self.user_id == viewer_id:
            self.is_favorite_user = val
        else:
            self.is_favorite_friend = val

    def get_notify_on_online(self, viewer_id: int) -> bool:
        return bool(self.notify_on_online_user if self.user_id == viewer_id else self.notify_on_online_friend)

    def set_notify_on_online(self, viewer_id: int, val: bool):
        if self.user_id == viewer_id:
            self.notify_on_online_user = val
        else:
            self.notify_on_online_friend = val

    def get_note(self, viewer_id: int) -> str:
        note = self.note_user if self.user_id == viewer_id else self.note_friend
        return note or ''

    def set_note(self, viewer_id: int, note_text: str):
        if self.user_id == viewer_id:
            self.note_user = note_text
        else:
            self.note_friend = note_text

    def to_dict(self, viewer_id: int) -> dict:
        other = self.get_other_user(viewer_id)
        if not other:
            return {}

        return {
            'friendship_id': self.id,
            'user_id': other.id,
            'public_id': other.public_id,
            'username': other.username,
            'display_name': other.get_effective_display_name(),
            'color': other.color or '#8b5cf6',
            'avatar': f"/static/uploads/{other.avatar}" if other.avatar else None,
            'banner': f"/static/uploads/{other.banner}" if other.banner else None,
            'banner_color': other.banner_color or '#6366f1',
            'profile_accent_color': other.profile_accent_color or '#8b5cf6',
            'status_mode': other.presence_status or other.status_mode or 'offline',
            'presence_status': other.presence_status or other.status_mode or 'offline',
            'custom_status': other.get_active_custom_status(),
            'bio': other.bio or '',
            'badges': [b['name'] for b in other.get_all_badges()],
            'badge_list': other.get_all_badges(),
            'account_age_badge': other.get_account_age_badge(),
            'status': self.status,
            'is_sender': self.get_is_sender(viewer_id),
            'is_close_friend': self.get_is_close_friend(viewer_id),
            'is_favorite': self.get_is_favorite(viewer_id),
            'notify_on_online': self.get_notify_on_online(viewer_id),
            'note': self.get_note(viewer_id),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else ''
        }


class BlockedUser(db.Model):
    __tablename__ = 'blocked_user'
    __table_args__ = (db.UniqueConstraint('blocker_id', 'blocked_id', name='_blocker_blocked_uc'),)

    id = db.Column(db.Integer, primary_key=True)
    blocker_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    blocked_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    reason = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    blocker = db.relationship('User', foreign_keys=[blocker_id])
    blocked = db.relationship('User', foreign_keys=[blocked_id])

    def to_dict(self) -> dict:
        b = self.blocked
        return {
            'id': self.id,
            'blocked_id': self.blocked_id,
            'public_id': b.public_id if b else f'astral_{self.blocked_id}',
            'username': b.username if b else 'Unknown',
            'display_name': b.get_effective_display_name() if b else 'Unknown',
            'color': b.color if b else '#8b5cf6',
            'avatar': f"/static/uploads/{b.avatar}" if b and b.avatar else None,
            'reason': self.reason or '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else ''
        }

    @classmethod
    def is_blocked_between(cls, user_a_id: int, user_b_id: int) -> bool:
        if not user_a_id or not user_b_id:
            return False
        return cls.query.filter(
            db.or_(
                db.and_(cls.blocker_id == user_a_id, cls.blocked_id == user_b_id),
                db.and_(cls.blocker_id == user_b_id, cls.blocked_id == user_a_id)
            )
        ).first() is not None


class Server(db.Model):
    __tablename__ = 'server'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    invite_code = db.Column(db.String(10), unique=True, nullable=False)
    icon_color = db.Column(db.String(30), nullable=False)
    description = db.Column(db.Text, default='')
    icon_url = db.Column(db.String(255), default='')
    banner_color = db.Column(db.String(30), default='#6366f1')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'owner_id': self.owner_id,
            'invite_code': self.invite_code,
            'icon_color': self.icon_color,
            'description': self.description or '',
            'icon_url': self.icon_url or '',
            'banner_color': self.banner_color or '#6366f1'
        }


class ServerMember(db.Model):
    __tablename__ = 'server_member'
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    role = db.Column(db.String(20), default='member')


class Channel(db.Model):
    __tablename__ = 'channel'
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False, default='text')

    def to_dict(self):
        return {
            'id': self.id,
            'server_id': self.server_id,
            'name': self.name,
            'type': self.type
        }


class Conversation(db.Model):
    __tablename__ = 'conversation'
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20), default='direct')  # 'direct' or 'group'
    name = db.Column(db.String(100), nullable=True)    # Group custom title
    icon_url = db.Column(db.String(255), nullable=True) # Group custom icon
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    creator = db.relationship('User', foreign_keys=[created_by_id])
    members = db.relationship('ConversationMember', backref='conversation', cascade='all, delete-orphan', lazy='joined')
    messages = db.relationship('Message', backref='conversation_rel', cascade='all, delete-orphan', lazy='dynamic')

    def get_member_user_ids(self):
        return [m.user_id for m in self.members]

    def is_member(self, user_id: int) -> bool:
        return any(m.user_id == user_id for m in self.members)

    def get_member_record(self, user_id: int):
        for m in self.members:
            if m.user_id == user_id:
                return m
        return None

    def get_other_member(self, viewer_id: int):
        for m in self.members:
            if m.user_id != viewer_id and m.user:
                return m.user
        return None

    def get_display_name(self, viewer_id: int) -> str:
        if self.type == 'group':
            if self.name:
                return self.name
            names = [m.user.get_effective_display_name() for m in self.members if m.user]
            return ', '.join(names[:3]) + (f' (+{len(names)-3})' if len(names) > 3 else '') if names else 'Grup Sohbeti'
        else:
            other = self.get_other_member(viewer_id)
            return other.get_effective_display_name() if other else 'Direkt Mesaj'

    def get_icon(self, viewer_id: int) -> dict:
        if self.type == 'group':
            return {
                'type': 'group',
                'icon_url': self.icon_url or '',
                'initial': (self.name or 'G').charAt(0).upper() if hasattr(self.name, 'charAt') else (self.name or 'G')[0].upper(),
                'color': '#8b5cf6'
            }
        else:
            other = self.get_other_member(viewer_id)
            if other:
                return {
                    'type': 'direct',
                    'avatar': other.avatar or '',
                    'initial': other.get_effective_display_name()[0].upper() if other.get_effective_display_name() else 'U',
                    'color': other.color or '#8b5cf6',
                    'status_mode': other.status_mode or 'offline'
                }
            return {'type': 'direct', 'avatar': '', 'initial': 'U', 'color': '#8b5cf6', 'status_mode': 'offline'}

    def to_dict(self, viewer_id: int = None):
        last_msg = self.messages.order_by(Message.timestamp.desc()).first() if hasattr(self, 'messages') else None
        
        display_name = self.get_display_name(viewer_id) if viewer_id else (self.name or 'Sohbet')
        icon_info = self.get_icon(viewer_id) if viewer_id else {}
        
        unread_count = 0
        if viewer_id:
            member_rec = self.get_member_record(viewer_id)
            if member_rec and member_rec.last_read_at and hasattr(self, 'messages'):
                unread_count = self.messages.filter(
                    Message.timestamp > member_rec.last_read_at,
                    Message.sender_id != viewer_id
                ).count()

        other_user = self.get_other_member(viewer_id) if viewer_id and self.type == 'direct' else None

        return {
            'id': self.id,
            'type': self.type,
            'name': self.name,
            'display_name': display_name,
            'icon_url': self.icon_url,
            'icon_info': icon_info,
            'created_by_id': self.created_by_id,
            'created_at': self.created_at.isoformat() if self.created_at else '',
            'updated_at': self.updated_at.isoformat() if self.updated_at else '',
            'member_count': len(self.members),
            'members': [m.to_dict() for m in self.members],
            'unread_count': unread_count,
            'other_user': other_user.to_dict() if other_user else None,
            'last_message': last_msg.to_dict(viewer_id) if last_msg else None
        }


class ConversationMember(db.Model):
    __tablename__ = 'conversation_member'
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    role = db.Column(db.String(20), default='member')  # 'owner', 'admin', 'member'
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_read_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_muted = db.Column(db.Boolean, default=False)

    user = db.relationship('User', foreign_keys=[user_id])
    __table_args__ = (db.UniqueConstraint('conversation_id', 'user_id', name='uq_conversation_member'),)

    def to_dict(self):
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'user_id': self.user_id,
            'username': self.user.username if self.user else 'User',
            'display_name': self.user.get_effective_display_name() if self.user else 'User',
            'color': self.user.color if self.user else '#8b5cf6',
            'avatar': self.user.avatar if self.user else '',
            'status_mode': self.user.status_mode if self.user else 'offline',
            'role': self.role,
            'joined_at': self.joined_at.isoformat() if self.joined_at else '',
            'is_muted': self.is_muted
        }


class Message(db.Model):
    __tablename__ = 'message'
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    channel_id = db.Column(db.Integer, db.ForeignKey('channel.id'), nullable=True)
    text = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(30), default='text')  # 'text', 'media', 'code', 'audio', 'system'
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    attachment_url = db.Column(db.String(255), nullable=True)
    attachment_type = db.Column(db.String(30), nullable=True)
    attachment_name = db.Column(db.String(255), nullable=True)
    reply_to_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=True)
    forwarded_from_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=True)
    is_pinned = db.Column(db.Boolean, default=False)
    is_edited = db.Column(db.Boolean, default=False)
    edited_at = db.Column(db.DateTime, nullable=True)
    is_deleted_everyone = db.Column(db.Boolean, default=False)
    reactions = db.Column(db.Text, default='{}')

    sender = db.relationship('User', foreign_keys=[sender_id])
    reply_to = db.relationship('Message', foreign_keys=[reply_to_id], remote_side=[id])
    forwarded_from = db.relationship('Message', foreign_keys=[forwarded_from_id], remote_side=[id])
    attachments = db.relationship('MessageAttachment', backref='message', cascade='all, delete-orphan', lazy='joined')

    def to_dict(self, viewer_id: int = None):
        reply_info = None
        if self.reply_to and not self.reply_to.is_deleted_everyone:
            reply_info = {
                'id': self.reply_to.id,
                'sender_id': self.reply_to.sender_id,
                'username': self.reply_to.sender.username if self.reply_to.sender else 'User',
                'display_name': self.reply_to.sender.get_effective_display_name() if self.reply_to.sender else 'User',
                'color': self.reply_to.sender.color if self.reply_to.sender else '#8b5cf6',
                'text': self.reply_to.text[:80] + ('...' if len(self.reply_to.text) > 80 else ''),
                'attachment_type': self.reply_to.attachment_type,
                'message_type': self.reply_to.message_type
            }

        forward_info = None
        if self.forwarded_from:
            forward_info = {
                'id': self.forwarded_from.id,
                'sender_id': self.forwarded_from.sender_id,
                'username': self.forwarded_from.sender.username if self.forwarded_from.sender else 'User',
                'display_name': self.forwarded_from.sender.get_effective_display_name() if self.forwarded_from.sender else 'User'
            }

        try:
            rx = json.loads(self.reactions) if self.reactions else {}
        except Exception:
            rx = {}

        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'sender_id': self.sender.id if self.sender else 0,
            'username': self.sender.username if self.sender else 'Unknown',
            'display_name': self.sender.get_effective_display_name() if self.sender else 'Unknown',
            'avatar': self.sender.avatar if self.sender else '',
            'color': self.sender.color if self.sender else '#8b5cf6',
            'status_mode': self.sender.status_mode if self.sender else 'offline',
            'badges': [b.strip() for b in (self.sender.badges or '').split(',') if b.strip()] if self.sender else [],
            'text': self.text if not self.is_deleted_everyone else '🚫 Bu mesaj silindi.',
            'message_type': self.message_type,
            'timestamp': self.timestamp.strftime('%H:%M') if self.timestamp else '',
            'date': self.timestamp.strftime('%Y-%m-%d') if self.timestamp else '',
            'created_at': self.timestamp.isoformat() if self.timestamp else '',
            'receiver_id': self.receiver_id,
            'channel_id': self.channel_id,
            'attachment_url': self.attachment_url,
            'attachment_type': self.attachment_type,
            'attachment_name': self.attachment_name,
            'attachments': [a.to_dict() for a in self.attachments] if self.attachments else [],
            'reply_to': reply_info,
            'reply_to_id': self.reply_to_id,
            'forwarded_from': forward_info,
            'forwarded_from_id': self.forwarded_from_id,
            'is_pinned': bool(self.is_pinned),
            'is_edited': bool(self.is_edited or self.edited_at is not None),
            'edited_at': self.edited_at.isoformat() if self.edited_at else None,
            'is_deleted_everyone': bool(self.is_deleted_everyone),
            'reactions': rx,
            'is_mine': (viewer_id is not None and self.sender_id == viewer_id)
        }


class MessageAttachment(db.Model):
    __tablename__ = 'message_attachment'
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=False)
    file_url = db.Column(db.String(255), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer, default=0)
    file_type = db.Column(db.String(30), default='file')  # 'image', 'video', 'audio', 'file'
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
            'file_type': self.file_type,
            'mime_type': self.mime_type,
            'is_spoiler': self.is_spoiler
        }


class HiddenMessage(db.Model):
    __tablename__ = 'hidden_message'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (db.UniqueConstraint('user_id', 'message_id', name='uq_user_hidden_message'),)


class CustomEmoji(db.Model):
    __tablename__ = 'custom_emoji'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    code = db.Column(db.String(60), unique=True, nullable=False)  # e.g. :astral_cat:
    image_url = db.Column(db.String(255), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    creator = db.relationship('User', foreign_keys=[created_by_id])

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'image_url': self.image_url,
            'created_by': self.creator.username if self.creator else None
        }
