from odoo import fields, models


class MobileHrApiPushSub(models.Model):
    _name = 'mobile.hr.api.push.sub'
    _description = 'Mobile HR API — Push Subscription'
    _rec_name = 'device_id'
    _order = 'write_date desc'

    employee_id = fields.Many2one(
        'hr.employee', required=True, ondelete='cascade', index=True,
    )
    device_id = fields.Char('Device ID', required=True, index=True)
    platform = fields.Selection(
        [('web', 'Web Push'), ('android', 'Android (FCM)'), ('ios', 'iOS (APNs)')],
        default='web',
    )
    # Web Push fields
    endpoint = fields.Char('Push Endpoint')
    p256dh = fields.Char('p256dh Key')
    auth_key = fields.Char('Auth Key')
    # Native push (FCM / APNs)
    push_token = fields.Char('FCM / APNs Token')

    is_active = fields.Boolean(default=True)

    _sql_constraints = [
        ('unique_employee_device',
         'UNIQUE(employee_id, device_id)',
         'Push subscription already exists for this device.'),
    ]
