{
    'name': 'Mobile HR API',
    'version': '19.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Secure mobile self-service API for employees (attendance, leaves, payslips)',
    'description': (
        'Token-authenticated REST-like JSON API for employee self-service mobile apps. '
        'Uses portal users only. Enforces GPS geofence for attendance. '
        'Isolates all data strictly to the authenticated employee.'
    ),
    'author': 'Custom',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'hr',
        'hr_attendance',
        'hr_holidays',
        'portal',
        # hr_payroll: uncomment when OCA payroll (or enterprise payroll) is installed.
        # Payslip endpoints return HTTP 503 automatically when the model is absent,
        # so this dependency is optional at the module level.
        # 'hr_payroll',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/record_rules.xml',
        'data/sequence.xml',
        'data/default_settings.xml',
        'views/api_settings_views.xml',
        'views/geofence_views.xml',
        'views/audit_log_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
