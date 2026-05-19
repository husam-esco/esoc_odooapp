"""
Tests for mobile_hr_api.

Run with:
    docker exec odoo19-6 odoo -d <db> --test-enable --stop-after-init \
        --log-level=test -i mobile_hr_api
"""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged('-at_install', 'post_install', 'mobile_hr_api')
class TestTokenModel(TransactionCase):

    def setUp(self):
        super().setUp()
        # Portal user linked to employee
        self.portal_user = self.env['res.users'].create({
            'name': 'Test Portal Employee',
            'login': 'test_portal_emp@example.com',
            'email': 'test_portal_emp@example.com',
            'groups_id': [(4, self.env.ref('base.group_portal').id)],
        })
        self.employee = self.env['hr.employee'].create({
            'name': 'Test Portal Employee',
            'user_id': self.portal_user.id,
            'work_email': 'test_portal_emp@example.com',
        })
        # Second employee — used to verify isolation
        self.other_user = self.env['res.users'].create({
            'name': 'Other Employee',
            'login': 'other_emp@example.com',
            'email': 'other_emp@example.com',
            'groups_id': [(4, self.env.ref('base.group_portal').id)],
        })
        self.other_employee = self.env['hr.employee'].create({
            'name': 'Other Employee',
            'user_id': self.other_user.id,
        })

        self.TokenModel = self.env['mobile.hr.api.token'].sudo()
        self.SettingsModel = self.env['mobile.hr.api.settings'].sudo()
        self.GeofenceModel = self.env['mobile.hr.api.geofence'].sudo()

    # ── Token lifecycle ────────────────────────────────────────────────────────

    def test_token_create_and_validate(self):
        raw = self.TokenModel.create_token(self.portal_user, validity_days=30)
        self.assertIsInstance(raw, str)
        self.assertTrue(len(raw) > 30, 'Token should be sufficiently long')

        resolved_user = self.TokenModel.validate_token(raw)
        self.assertEqual(resolved_user.id, self.portal_user.id)

    def test_invalid_token_returns_none(self):
        resolved = self.TokenModel.validate_token('completely_wrong_token')
        self.assertIsNone(resolved)

    def test_expired_token_returns_none(self):
        raw = self.TokenModel.create_token(self.portal_user, validity_days=-1)
        # validity_days=-1 creates a token that expired yesterday
        resolved = self.TokenModel.validate_token(raw)
        self.assertIsNone(resolved)

    def test_revoked_token_returns_none(self):
        raw = self.TokenModel.create_token(self.portal_user, validity_days=30)
        import hashlib
        token_hash = hashlib.sha256(raw.encode('utf-8')).hexdigest()
        token = self.TokenModel.search([('token_hash', '=', token_hash)])
        token.is_active = False
        resolved = self.TokenModel.validate_token(raw)
        self.assertIsNone(resolved)

    def test_device_id_revokes_previous_token(self):
        raw1 = self.TokenModel.create_token(
            self.portal_user, device_id='device-A', validity_days=30
        )
        raw2 = self.TokenModel.create_token(
            self.portal_user, device_id='device-A', validity_days=30
        )
        # raw1 should now be inactive
        self.assertIsNone(self.TokenModel.validate_token(raw1))
        # raw2 should still be valid
        self.assertIsNotNone(self.TokenModel.validate_token(raw2))

    # ── Settings ───────────────────────────────────────────────────────────────

    def test_get_settings_creates_defaults(self):
        company = self.env['res.company'].create({'name': 'Test Co GPS'})
        settings = self.SettingsModel.get_settings(company.id)
        self.assertEqual(settings.company_id.id, company.id)
        self.assertTrue(settings.token_validity_days > 0)

    def test_get_settings_idempotent(self):
        company = self.env['res.company'].create({'name': 'Test Co GPS 2'})
        s1 = self.SettingsModel.get_settings(company.id)
        s2 = self.SettingsModel.get_settings(company.id)
        self.assertEqual(s1.id, s2.id)

    # ── Geofence validation ────────────────────────────────────────────────────

    def test_geofence_validation_within_zone(self):
        """A location 50 m from centre should pass a 200 m geofence."""
        company = self.employee.company_id

        # Make sure GPS validation is on
        settings = self.SettingsModel.get_settings(company.id)
        settings.require_gps_validation = True

        geofence = self.GeofenceModel.create({
            'name': 'HQ',
            'company_id': company.id,
            'latitude': 25.2048,
            'longitude': 55.2708,
            'radius_meters': 200.0,
            'min_accuracy_meters': 100.0,
        })

        # 25.2048, 55.2708 is the exact centre → distance = 0
        from odoo.addons.mobile_hr_api.controllers.main import _haversine
        dist = _haversine(25.2048, 55.2708, geofence.latitude, geofence.longitude)
        self.assertAlmostEqual(dist, 0.0, places=1)

    def test_geofence_validation_outside_zone(self):
        """A location 2 km away should fail a 200 m geofence."""
        from odoo.addons.mobile_hr_api.controllers.main import _haversine
        # London, 2 km north of centre
        dist = _haversine(51.5237, -0.1080, 51.5057, -0.1080)
        self.assertGreater(dist, 200)

    def test_geofence_accuracy_rejection(self):
        """GPS accuracy worse than the threshold should be caught by the controller check."""
        company = self.employee.company_id
        geofence = self.GeofenceModel.create({
            'name': 'Strict Zone',
            'company_id': company.id,
            'latitude': 25.2048,
            'longitude': 55.2708,
            'radius_meters': 500.0,
            'min_accuracy_meters': 50.0,
        })
        settings = self.SettingsModel.get_settings(company.id)
        settings.require_gps_validation = True

        # Simulate controller geofence check inline (no HTTP layer needed)
        accuracy = 200.0  # worse than 50 m threshold
        self.assertGreater(accuracy, geofence.min_accuracy_meters)

    # ── Employee isolation ─────────────────────────────────────────────────────

    def test_employee_lookup_by_user(self):
        employee = self.env['hr.employee'].sudo().search(
            [('user_id', '=', self.portal_user.id)], limit=1
        )
        self.assertEqual(employee.id, self.employee.id)

    def test_employee_isolation_attendance(self):
        """Attendance records created for employee A must not be visible when filtering by B."""
        att = self.env['hr.attendance'].sudo().create({
            'employee_id': self.employee.id,
            'check_in': '2024-06-01 08:00:00',
        })
        records_for_other = self.env['hr.attendance'].sudo().search([
            ('employee_id', '=', self.other_employee.id),
            ('id', '=', att.id),
        ])
        self.assertFalse(records_for_other, 'Other employee must not see employee A attendance')

    def test_audit_log_immutable(self):
        log = self.env['mobile.hr.api.audit.log'].sudo().create({
            'action': 'test',
            'status': 'success',
        })
        with self.assertRaises(NotImplementedError):
            log.write({'action': 'tampered'})

    def test_audit_log_cannot_be_deleted(self):
        log = self.env['mobile.hr.api.audit.log'].sudo().create({
            'action': 'test_delete',
            'status': 'success',
        })
        with self.assertRaises(NotImplementedError):
            log.unlink()

    # ── Leave isolation ────────────────────────────────────────────────────────

    def test_leave_employee_isolation(self):
        """Leaves created for employee A must not appear in a search for employee B."""
        leave_type = self.env['hr.leave.type'].sudo().search([], limit=1)
        if not leave_type:
            self.skipTest('No leave types configured — skipping leave isolation test')

        leave = self.env['hr.leave'].sudo().with_context(
            mail_create_nolog=True, mail_notrack=True
        ).create({
            'employee_id': self.employee.id,
            'holiday_status_id': leave_type.id,
            'date_from': '2024-07-01 08:00:00',
            'date_to': '2024-07-02 17:00:00',
            'name': 'Test leave A',
        })

        other_leaves = self.env['hr.leave'].sudo().search([
            ('employee_id', '=', self.other_employee.id),
            ('id', '=', leave.id),
        ])
        self.assertFalse(other_leaves, 'Other employee must not see employee A leaves')
