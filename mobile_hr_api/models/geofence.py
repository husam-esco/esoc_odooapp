from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MobileHrApiGeofence(models.Model):
    _name = 'mobile.hr.api.geofence'
    _description = 'Mobile HR API — Geofence Zone'
    _rec_name = 'name'
    _order = 'company_id, name'

    name = fields.Char('Zone Name', required=True)
    company_id = fields.Many2one(
        'res.company', string='Company',
        required=True, ondelete='cascade', index=True,
        default=lambda self: self.env.company,
    )
    # When set, this zone applies only to employees whose work location matches.
    # When blank, the zone is the company-wide fallback.
    work_location_id = fields.Many2one(
        'hr.work.location', string='Work Location (optional)',
        domain="[('company_id', '=', company_id)]",
        help='Leave empty to create a company-wide fallback zone.',
    )
    latitude = fields.Float(
        'Centre Latitude', digits=(10, 7), required=True,
        help='WGS-84 decimal degrees.',
    )
    longitude = fields.Float(
        'Centre Longitude', digits=(10, 7), required=True,
        help='WGS-84 decimal degrees.',
    )
    radius_meters = fields.Float(
        'Radius (metres)', required=True, default=200.0,
        help='Employees must be within this radius to check in or out.',
    )
    min_accuracy_meters = fields.Float(
        'Max Allowed GPS Inaccuracy (metres)', default=100.0,
        help='Requests with worse GPS accuracy than this value are rejected. '
             'Set to 0 to disable accuracy enforcement.',
    )
    is_active = fields.Boolean('Active', default=True)
    notes = fields.Text('Notes')

    @api.constrains('radius_meters')
    def _check_radius(self):
        for rec in self:
            if rec.radius_meters <= 0:
                raise ValidationError('Radius must be greater than zero.')

    @api.constrains('latitude')
    def _check_latitude(self):
        for rec in self:
            if not (-90.0 <= rec.latitude <= 90.0):
                raise ValidationError('Latitude must be between -90 and 90.')

    @api.constrains('longitude')
    def _check_longitude(self):
        for rec in self:
            if not (-180.0 <= rec.longitude <= 180.0):
                raise ValidationError('Longitude must be between -180 and 180.')
