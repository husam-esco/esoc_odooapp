from odoo import fields, models


class MobileHrApiAuditLog(models.Model):
    _name = 'mobile.hr.api.audit.log'
    _description = 'Mobile HR API — Audit Log'
    _rec_name = 'action'
    _order = 'timestamp desc'
    _log_access = False  # Disable Odoo's built-in write/create tracking on this model.

    user_id = fields.Many2one(
        'res.users', string='User', ondelete='set null', index=True, readonly=True,
    )
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', ondelete='set null', index=True, readonly=True,
    )
    action = fields.Char('Action', required=True, index=True, readonly=True)
    endpoint = fields.Char('Endpoint', readonly=True)
    status = fields.Selection(
        [('success', 'Success'), ('error', 'Error')],
        string='Status', index=True, readonly=True,
    )
    ip_address = fields.Char('IP Address', size=45, readonly=True)
    details = fields.Text('Details', readonly=True)
    extra_data = fields.Text('Extra Data (JSON)', readonly=True)
    timestamp = fields.Datetime(
        'Timestamp', default=fields.Datetime.now, index=True, readonly=True,
    )

    # Audit logs are append-only.
    def write(self, vals):
        raise NotImplementedError('Audit log records are immutable.')

    def unlink(self):
        raise NotImplementedError('Audit log records cannot be deleted.')
