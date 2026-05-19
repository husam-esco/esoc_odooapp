import hashlib
import secrets
from datetime import timedelta

from odoo import api, fields, models


class MobileHrApiToken(models.Model):
    _name = 'mobile.hr.api.token'
    _description = 'Mobile HR API — Authentication Token'
    _rec_name = 'user_id'
    _order = 'created_at desc'

    user_id = fields.Many2one(
        'res.users', string='User',
        required=True, ondelete='cascade', index=True,
    )
    token_hash = fields.Char('Token Hash', required=True, index=True)
    device_name = fields.Char('Device Name', size=128)
    device_id = fields.Char('Device ID', size=256, index=True)
    is_active = fields.Boolean('Active', default=True, index=True)
    last_used = fields.Datetime('Last Used')
    expires_at = fields.Datetime('Expires At', index=True)
    created_at = fields.Datetime('Created At', default=fields.Datetime.now, readonly=True)
    ip_address = fields.Char('Issuing IP', size=45)

    @api.model
    def create_token(self, user, device_name=None, device_id=None,
                     ip_address=None, validity_days=30):
        """
        Generate a new token for *user*. Returns the raw (unhashed) token string.
        If *device_id* is supplied, any previous active token for that device is revoked.
        """
        if device_id:
            self.search([
                ('user_id', '=', user.id),
                ('device_id', '=', device_id),
                ('is_active', '=', True),
            ]).write({'is_active': False})

        raw = secrets.token_urlsafe(48)
        self.create({
            'user_id': user.id,
            'token_hash': hashlib.sha256(raw.encode('utf-8')).hexdigest(),
            'device_name': device_name or '',
            'device_id': device_id or '',
            'ip_address': ip_address or '',
            'expires_at': fields.Datetime.now() + timedelta(days=validity_days),
        })
        return raw

    @api.model
    def validate_token(self, raw_token):
        """
        Validate a raw token string. Returns the linked res.users record on success,
        or None when the token is missing, inactive, or expired.
        """
        if not raw_token:
            return None
        token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
        token = self.search([
            ('token_hash', '=', token_hash),
            ('is_active', '=', True),
        ], limit=1)
        if not token:
            return None
        now = fields.Datetime.now()
        if token.expires_at and token.expires_at < now:
            token.is_active = False
            return None
        token.last_used = now
        return token.user_id
