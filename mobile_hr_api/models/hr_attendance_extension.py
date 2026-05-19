from odoo import fields, models


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    # Extend in_mode / out_mode selection to include 'mobile'
    in_mode = fields.Selection(
        selection_add=[('mobile', 'Mobile API')],
        ondelete={'mobile': 'set default'},
    )
    out_mode = fields.Selection(
        selection_add=[('mobile', 'Mobile API')],
        ondelete={'mobile': 'set default'},
    )

    checkin_latitude = fields.Float('Check-in Latitude', digits=(10, 7), default=0.0)
    checkin_longitude = fields.Float('Check-in Longitude', digits=(10, 7), default=0.0)
    checkin_accuracy = fields.Float('Check-in GPS Accuracy (m)', default=0.0)
    checkin_geofence_valid = fields.Boolean('Check-in Within Geofence', default=False)
    checkin_device_id = fields.Char('Check-in Device ID', size=256)

    checkout_latitude = fields.Float('Check-out Latitude', digits=(10, 7), default=0.0)
    checkout_longitude = fields.Float('Check-out Longitude', digits=(10, 7), default=0.0)
    checkout_accuracy = fields.Float('Check-out GPS Accuracy (m)', default=0.0)
    checkout_geofence_valid = fields.Boolean('Check-out Within Geofence', default=False)
