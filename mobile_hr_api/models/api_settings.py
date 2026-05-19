from odoo import api, fields, models
from odoo.orm.table_objects import Constraint


class MobileHrApiSettings(models.Model):
    _name = 'mobile.hr.api.settings'
    _description = 'Mobile HR API — Settings'
    _rec_name = 'company_id'

    company_id = fields.Many2one(
        'res.company', string='Company',
        required=True, ondelete='cascade', index=True,
        default=lambda self: self.env.company,
    )
    is_enabled = fields.Boolean('API Enabled', default=True)
    token_validity_days = fields.Integer(
        'Token Validity (days)', default=30,
        help='Number of days before a mobile authentication token expires.',
    )
    require_gps_validation = fields.Boolean(
        'Require GPS Geofence Validation', default=True,
        help='When enabled, check-in and check-out are blocked if the employee '
             'is outside all active geofence zones for the company.',
    )
    default_geofence_id = fields.Many2one(
        'mobile.hr.api.geofence', string='Default Geofence Zone',
        domain="[('company_id', '=', company_id)]",
    )

    _unique_company = Constraint(
        'UNIQUE(company_id)',
        'Mobile API settings already exist for this company.',
    )

    @api.model
    def get_settings(self, company_id):
        """Return settings for the given company, creating defaults if absent."""
        settings = self.search([('company_id', '=', company_id)], limit=1)
        if not settings:
            settings = self.create({'company_id': company_id})
        return settings
