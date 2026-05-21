import hashlib
import json
import logging
import math
from datetime import date, datetime

from odoo import fields as odoo_fields, http
from odoo.http import Response, request

_logger = logging.getLogger(__name__)

_BASE = '/api/v1/mobile/hr'
_AUTH = '/api/v1/mobile/auth'
_PUSH = '/api/v1/mobile/hr/push'


# ─── Response helpers ──────────────────────────────────────────────────────────

_CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Max-Age': '86400',
}


def _preflight():
    return Response(status=204, headers=_CORS_HEADERS)


def _json_resp(data, status=200):
    return Response(
        json.dumps(data, default=_default_serializer),
        status=status,
        mimetype='application/json',
        headers=_CORS_HEADERS,
    )


def _default_serializer(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f'Object of type {type(obj).__name__} is not JSON serializable')


def _ok(data=None, message=None):
    result = {'success': True}
    if data is not None:
        result['data'] = data
    if message:
        result['message'] = message
    return result


def _err(message, code='ERROR', details=None):
    payload = {'success': False, 'error': {'code': code, 'message': message}}
    if details:
        payload['error']['details'] = details
    return payload


# ─── Geo helpers ───────────────────────────────────────────────────────────────

def _haversine(lat1, lon1, lat2, lon2):
    """Return distance in metres between two WGS-84 coordinates."""
    R = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _coerce_float(value, field_name):
    """Return (float_value, error_string). error_string is None on success."""
    if value is None:
        return None, None
    try:
        return float(value), None
    except (TypeError, ValueError):
        return None, f'{field_name} must be a numeric value'


def _validate_coords(lat, lon):
    """Return error string if lat/lon are out of WGS-84 range, else None."""
    if lat is not None and not (-90 <= lat <= 90):
        return f'latitude {lat} out of range [-90, 90]'
    if lon is not None and not (-180 <= lon <= 180):
        return f'longitude {lon} out of range [-180, 180]'
    return None


# ─── Serialisers ───────────────────────────────────────────────────────────────

def _ser_employee(emp):
    def _ref(rec):
        return {'id': rec.id, 'name': rec.name} if rec else None

    return {
        'id': emp.id,
        'name': emp.name,
        'employee_number': emp.barcode or '',
        'job_title': emp.job_title or '',
        'job_position': _ref(emp.job_id),
        'department': _ref(emp.department_id),
        'company': _ref(emp.company_id),
        'work_location': _ref(emp.work_location_id) if hasattr(emp, 'work_location_id') else None,
        'manager': _ref(emp.parent_id),
        'work_email': emp.work_email or '',
        'work_phone': emp.work_phone or '',
        'mobile_phone': emp.mobile_phone or '',
        'image_url': f'/web/image/hr.employee/{emp.id}/image_128',
    }


def _ser_attendance(att):
    return {
        'id': att.id,
        'check_in': att.check_in.isoformat() if att.check_in else None,
        'check_out': att.check_out.isoformat() if att.check_out else None,
        'worked_hours': round(att.worked_hours or 0.0, 4),
        'is_open': not bool(att.check_out),
        'checkin_latitude': getattr(att, 'checkin_latitude', None) or None,
        'checkin_longitude': getattr(att, 'checkin_longitude', None) or None,
        'checkin_accuracy': getattr(att, 'checkin_accuracy', None) or None,
        'checkin_geofence_valid': getattr(att, 'checkin_geofence_valid', None),
        'checkout_latitude': getattr(att, 'checkout_latitude', None) or None,
        'checkout_longitude': getattr(att, 'checkout_longitude', None) or None,
        'checkout_accuracy': getattr(att, 'checkout_accuracy', None) or None,
        'checkout_geofence_valid': getattr(att, 'checkout_geofence_valid', None),
    }


def _ser_leave(leave):
    state_labels = {
        'draft': 'To Submit',
        'confirm': 'To Approve',
        'validate1': 'Second Approval',
        'validate': 'Approved',
        'refuse': 'Refused',
    }
    refuse_reason = ''
    raw = getattr(leave, 'refuse_reason', None)
    if raw:
        refuse_reason = raw.name if hasattr(raw, 'name') else str(raw)

    return {
        'id': leave.id,
        'name': leave.name or '',
        'leave_type': {
            'id': leave.holiday_status_id.id,
            'name': leave.holiday_status_id.name,
        } if leave.holiday_status_id else None,
        'date_from': leave.date_from.isoformat() if leave.date_from else None,
        'date_to': leave.date_to.isoformat() if leave.date_to else None,
        'number_of_days': getattr(leave, 'number_of_days', None),
        'state': leave.state,
        'state_label': state_labels.get(leave.state, leave.state),
        'refuse_reason': refuse_reason,
    }


def _ser_payslip_summary(slip):
    return {
        'id': slip.id,
        'name': slip.name or '',
        'date_from': slip.date_from.isoformat() if slip.date_from else None,
        'date_to': slip.date_to.isoformat() if slip.date_to else None,
        'state': slip.state,
        'struct': {'id': slip.struct_id.id, 'name': slip.struct_id.name} if slip.struct_id else None,
    }


def _wage_from_lines(slip, category_code):
    """Extract a wage total from payslip lines by salary category code.
    Fallback for payroll modules (e.g. om_hr_payroll) that don't store net_wage/gross_wage
    as direct fields on hr.payslip.
    """
    for line in slip.line_ids:
        cat = line.category_id
        if cat and getattr(cat, 'code', '') == category_code:
            return getattr(line, 'total', 0.0)
    return None


def _ser_payslip_detail(slip):
    salary_lines = []
    for line in slip.line_ids:
        if getattr(line, 'appears_on_payslip', True):
            salary_lines.append({
                'code': line.code,
                'name': line.name,
                'category': {'id': line.category_id.id, 'name': line.category_id.name} if line.category_id else None,
                'quantity': getattr(line, 'quantity', 1.0),
                'rate': getattr(line, 'rate', 100.0),
                'amount': getattr(line, 'total', 0.0),
            })

    worked_days = [
        {
            'code': wd.code,
            'name': wd.name,
            'number_of_days': wd.number_of_days,
            'number_of_hours': wd.number_of_hours,
        }
        for wd in getattr(slip, 'worked_days_line_ids', [])
    ]

    input_lines = [
        {
            'code': il.code,
            'name': il.name,
            'amount': getattr(il, 'amount', 0.0),
        }
        for il in getattr(slip, 'input_line_ids', [])
    ]

    # om_hr_payroll uses version_id (employment version) instead of contract_id.
    contract = getattr(slip, 'version_id', None) or getattr(slip, 'contract_id', None)
    # om_hr_payroll has no net_wage/gross_wage fields — derive from salary lines.
    net_wage = getattr(slip, 'net_wage', None) or _wage_from_lines(slip, 'NET')
    gross_wage = getattr(slip, 'gross_wage', None) or _wage_from_lines(slip, 'GROSS')

    return {
        **_ser_payslip_summary(slip),
        'contract': {
            'id': contract.id,
            'name': contract.name,
        } if contract else None,
        'salary_lines': salary_lines,
        'worked_days': worked_days,
        'input_lines': input_lines,
        'net_wage': net_wage,
        'gross_wage': gross_wage,
    }


# ─── Controller ────────────────────────────────────────────────────────────────

class MobileHrApiController(http.Controller):

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _authenticate(self):
        """Validate Bearer token. Returns (user, employee) or a Response on failure."""
        auth_header = request.httprequest.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            self._audit(None, None, 'auth_failure', request.httprequest.path,
                        'error', 'Missing Authorization header')
            return _json_resp(_err('Authorization header required (Bearer token)', 'UNAUTHORIZED'), 401)

        raw_token = auth_header[7:].strip()
        if not raw_token:
            return _json_resp(_err('Empty token', 'UNAUTHORIZED'), 401)

        user = request.env['mobile.hr.api.token'].sudo().validate_token(raw_token)
        if not user:
            self._audit(None, None, 'auth_failure', request.httprequest.path,
                        'error', 'Invalid or expired token')
            return _json_resp(_err('Invalid or expired token', 'UNAUTHORIZED'), 401)

        employee = request.env['hr.employee'].sudo().search(
            [('user_id', '=', user.id)], limit=1
        )
        if not employee:
            self._audit(user.id, None, 'auth_failure', request.httprequest.path,
                        'error', 'No employee linked to user')
            return _json_resp(_err('No employee record linked to this account', 'FORBIDDEN'), 403)

        return user, employee

    def _audit(self, user_id, employee_id, action, endpoint, status, details=None, extra=None):
        try:
            vals = {
                'user_id': user_id,
                'employee_id': employee_id,
                'action': action,
                'endpoint': endpoint,
                'status': status,
                'ip_address': request.httprequest.remote_addr,
                'details': details or '',
            }
            if extra:
                vals['extra_data'] = json.dumps(extra, default=str)
            request.env['mobile.hr.api.audit.log'].sudo().create(vals)
        except Exception as exc:
            _logger.error('Audit log write failed: %s', exc)

    def _body(self):
        """Parse JSON request body. Returns dict or None on parse error."""
        try:
            raw = request.httprequest.data
            return json.loads(raw) if raw else {}
        except (json.JSONDecodeError, ValueError):
            return None

    def _geofence_check(self, employee, lat, lon, accuracy):
        """
        Validate GPS position against the active geofence for the employee.
        Returns (is_valid: bool, message: str).
        """
        settings = request.env['mobile.hr.api.settings'].sudo().get_settings(
            employee.company_id.id
        )
        if not settings.require_gps_validation:
            return True, 'GPS validation disabled'

        if lat is None or lon is None:
            return False, 'GPS coordinates (latitude, longitude) are required'

        # Work-location-specific fence first, then company-wide fence.
        geofence = None
        wl_id = employee.work_location_id.id if hasattr(employee, 'work_location_id') and employee.work_location_id else False
        if wl_id:
            geofence = request.env['mobile.hr.api.geofence'].sudo().search([
                ('company_id', '=', employee.company_id.id),
                ('work_location_id', '=', wl_id),
                ('is_active', '=', True),
            ], limit=1)

        if not geofence:
            geofence = request.env['mobile.hr.api.geofence'].sudo().search([
                ('company_id', '=', employee.company_id.id),
                ('work_location_id', '=', False),
                ('is_active', '=', True),
            ], limit=1)

        if not geofence:
            return False, 'No active geofence configured for this company'

        if accuracy is not None and geofence.min_accuracy_meters and accuracy > geofence.min_accuracy_meters:
            return False, (
                f'GPS accuracy {accuracy:.0f}m exceeds allowed maximum '
                f'{geofence.min_accuracy_meters:.0f}m'
            )

        dist = _haversine(lat, lon, geofence.latitude, geofence.longitude)
        if dist > geofence.radius_meters:
            return False, (
                f'You are {dist:.0f}m from the allowed zone '
                f'(maximum {geofence.radius_meters:.0f}m)'
            )

        return True, f'Within zone — {dist:.0f}m from centre'

    def _paginate(self, args):
        try:
            page = max(1, int(args.get('page', 1)))
        except (TypeError, ValueError):
            page = 1
        try:
            limit = min(100, max(1, int(args.get('limit', 30))))
        except (TypeError, ValueError):
            limit = 30
        return page, limit, (page - 1) * limit

    def _pages(self, total, limit):
        return math.ceil(total / limit) if limit else 1

    # ── CORS preflight ─────────────────────────────────────────────────────────

    @http.route(
        [f'{_AUTH}/<path:subpath>', f'{_BASE}/<path:subpath>', f'{_PUSH}/<path:subpath>'],
        type='http', auth='none', methods=['OPTIONS'], csrf=False,
    )
    def cors_preflight(self, subpath, **kw):
        return _preflight()

    # ── Authentication ─────────────────────────────────────────────────────────

    @http.route(f'{_AUTH}/login', type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False)
    def login(self, **kw):
        if request.httprequest.method == 'OPTIONS':
            return _preflight()
        payload = self._body()
        if payload is None:
            return _json_resp(_err('Invalid JSON body', 'BAD_REQUEST'), 400)

        login_val = (payload.get('login') or '').strip()
        password = payload.get('password') or ''
        device_name = (payload.get('device_name') or '')[:128]
        device_id = (payload.get('device_id') or '')[:256]

        if not login_val or not password:
            return _json_resp(_err('login and password are required', 'BAD_REQUEST'), 400)

        try:
            credential = {'type': 'password', 'login': login_val, 'password': password}
            auth_info = request.env['res.users'].sudo().authenticate(
                credential, {'interactive': False}
            )
            uid = auth_info.get('uid') if isinstance(auth_info, dict) else auth_info
        except Exception:
            uid = False

        if not uid:
            self._audit(None, None, 'login_failed', f'{_AUTH}/login', 'error',
                        f'Failed login attempt for: {login_val}')
            return _json_resp(_err('Invalid credentials', 'UNAUTHORIZED'), 401)

        user = request.env['res.users'].sudo().browse(uid)

        # Accept portal and internal users (internal user = employee with system account).
        if not (user.has_group('base.group_portal') or user.has_group('base.group_user')):
            return _json_resp(_err('Access denied for this account type', 'FORBIDDEN'), 403)

        employee = request.env['hr.employee'].sudo().search(
            [('user_id', '=', uid)], limit=1
        )
        if not employee:
            return _json_resp(
                _err('No employee record is linked to this account', 'FORBIDDEN'), 403
            )

        settings = request.env['mobile.hr.api.settings'].sudo().get_settings(
            employee.company_id.id
        )
        token_model = request.env['mobile.hr.api.token'].sudo()
        raw_token = token_model.create_token(
            user=user,
            device_name=device_name,
            device_id=device_id,
            ip_address=request.httprequest.remote_addr,
            validity_days=settings.token_validity_days,
        )

        self._audit(uid, employee.id, 'login', f'{_AUTH}/login', 'success')
        return _json_resp(_ok({
            'token': raw_token,
            'employee_name': employee.name,
            'expires_in_days': settings.token_validity_days,
        }))

    @http.route(f'{_AUTH}/logout', type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False)
    def logout(self, **kw):
        if request.httprequest.method == 'OPTIONS':
            return _preflight()
        auth_result = self._authenticate()
        if isinstance(auth_result, Response):
            return auth_result
        user, employee = auth_result

        auth_header = request.httprequest.headers.get('Authorization', '')
        raw_token = auth_header[7:].strip()
        token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()

        token = request.env['mobile.hr.api.token'].sudo().search([
            ('token_hash', '=', token_hash),
            ('user_id', '=', user.id),
        ], limit=1)
        if token:
            token.is_active = False

        self._audit(user.id, employee.id, 'logout', f'{_AUTH}/logout', 'success')
        return _json_resp(_ok({}, 'Logged out successfully'))

    # ── Employee profile ───────────────────────────────────────────────────────

    @http.route(f'{_BASE}/me', type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False)
    def get_profile(self, **kw):
        if request.httprequest.method == 'OPTIONS':
            return _preflight()
        auth_result = self._authenticate()
        if isinstance(auth_result, Response):
            return auth_result
        user, employee = auth_result

        self._audit(user.id, employee.id, 'profile_view', f'{_BASE}/me', 'success')
        return _json_resp(_ok(_ser_employee(employee)))

    # ── Attendance ─────────────────────────────────────────────────────────────

    @http.route(
        f'{_BASE}/attendance/check-in',
        type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False,
    )
    def attendance_checkin(self, **kw):
        if request.httprequest.method == 'OPTIONS':
            return _preflight()
        auth_result = self._authenticate()
        if isinstance(auth_result, Response):
            return auth_result
        user, employee = auth_result

        payload = self._body()
        if payload is None:
            return _json_resp(_err('Invalid JSON body', 'BAD_REQUEST'), 400)

        lat, lat_err = _coerce_float(payload.get('latitude'), 'latitude')
        lon, lon_err = _coerce_float(payload.get('longitude'), 'longitude')
        acc, acc_err = _coerce_float(payload.get('accuracy'), 'accuracy')

        for err in (lat_err, lon_err, acc_err):
            if err:
                return _json_resp(_err(err, 'BAD_REQUEST'), 400)

        coord_err = _validate_coords(lat, lon)
        if coord_err:
            return _json_resp(_err(coord_err, 'BAD_REQUEST'), 400)

        geo_ok, geo_msg = self._geofence_check(employee, lat, lon, acc)
        if not geo_ok:
            self._audit(
                user.id, employee.id, 'checkin_rejected',
                f'{_BASE}/attendance/check-in', 'error', geo_msg,
                {'latitude': lat, 'longitude': lon},
            )
            return _json_resp(_err(geo_msg, 'GEOFENCE_VIOLATION'), 403)

        hr_att = request.env(user=user.id)['hr.attendance'].sudo()
        open_att = hr_att.search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False),
        ], limit=1)
        if open_att:
            return _json_resp(
                _err('Already checked in — please check out first.', 'ALREADY_CHECKED_IN'), 409
            )

        vals = {
            'employee_id': employee.id,
            'check_in': odoo_fields.Datetime.now(),
            'in_mode': 'mobile',
        }
        if lat is not None:
            vals.update({
                'checkin_latitude': lat,
                'checkin_longitude': lon,
                'checkin_accuracy': acc or 0.0,
                'checkin_geofence_valid': True,
            })

        device_meta = payload.get('device_meta') or {}
        if isinstance(device_meta, dict):
            vals['checkin_device_id'] = str(device_meta.get('device_id', ''))[:256]

        attendance = hr_att.create(vals)
        self._audit(
            user.id, employee.id, 'checkin',
            f'{_BASE}/attendance/check-in', 'success', geo_msg,
            {'attendance_id': attendance.id, 'latitude': lat, 'longitude': lon},
        )
        return _json_resp(_ok({
            'attendance_id': attendance.id,
            'check_in': attendance.check_in.isoformat() if attendance.check_in else None,
            'geofence_message': geo_msg,
        }), 201)

    @http.route(
        f'{_BASE}/attendance/check-out',
        type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False,
    )
    def attendance_checkout(self, **kw):
        if request.httprequest.method == 'OPTIONS':
            return _preflight()
        auth_result = self._authenticate()
        if isinstance(auth_result, Response):
            return auth_result
        user, employee = auth_result

        payload = self._body()
        if payload is None:
            return _json_resp(_err('Invalid JSON body', 'BAD_REQUEST'), 400)

        lat, lat_err = _coerce_float(payload.get('latitude'), 'latitude')
        lon, lon_err = _coerce_float(payload.get('longitude'), 'longitude')
        acc, acc_err = _coerce_float(payload.get('accuracy'), 'accuracy')

        for err in (lat_err, lon_err, acc_err):
            if err:
                return _json_resp(_err(err, 'BAD_REQUEST'), 400)

        coord_err = _validate_coords(lat, lon)
        if coord_err:
            return _json_resp(_err(coord_err, 'BAD_REQUEST'), 400)

        geo_ok, geo_msg = self._geofence_check(employee, lat, lon, acc)
        if not geo_ok:
            self._audit(
                user.id, employee.id, 'checkout_rejected',
                f'{_BASE}/attendance/check-out', 'error', geo_msg,
                {'latitude': lat, 'longitude': lon},
            )
            return _json_resp(_err(geo_msg, 'GEOFENCE_VIOLATION'), 403)

        hr_att = request.env(user=user.id)['hr.attendance'].sudo()
        open_att = hr_att.search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False),
        ], limit=1)
        if not open_att:
            return _json_resp(
                _err('No open check-in found — please check in first.', 'NOT_CHECKED_IN'), 409
            )

        checkout_vals = {'check_out': odoo_fields.Datetime.now(), 'out_mode': 'mobile'}
        if lat is not None:
            checkout_vals.update({
                'checkout_latitude': lat,
                'checkout_longitude': lon,
                'checkout_accuracy': acc or 0.0,
                'checkout_geofence_valid': True,
            })

        open_att.write(checkout_vals)
        worked_hours = round(open_att.worked_hours or 0.0, 4)

        self._audit(
            user.id, employee.id, 'checkout',
            f'{_BASE}/attendance/check-out', 'success', geo_msg,
            {'attendance_id': open_att.id, 'worked_hours': worked_hours},
        )
        return _json_resp(_ok({
            'attendance_id': open_att.id,
            'check_in': open_att.check_in.isoformat() if open_att.check_in else None,
            'check_out': open_att.check_out.isoformat() if open_att.check_out else None,
            'worked_hours': worked_hours,
            'geofence_message': geo_msg,
        }))

    @http.route(
        f'{_BASE}/attendance/check-in-pin',
        type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False,
    )
    def attendance_check_in_pin(self, **kw):
        if request.httprequest.method == 'OPTIONS':
            return _preflight()
        auth_result = self._authenticate()
        if isinstance(auth_result, Response):
            return auth_result
        user, employee = auth_result
        body = self._body() or {}
        pin = (body.get('pin') or '').strip()
        if not pin or employee.sudo().pin != pin:
            return _json_resp(_err('Invalid PIN.', 'INVALID_PIN'), 401)
        return self.attendance_checkin(**kw)

    @http.route(
        f'{_BASE}/attendance/check-out-pin',
        type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False,
    )
    def attendance_check_out_pin(self, **kw):
        if request.httprequest.method == 'OPTIONS':
            return _preflight()
        auth_result = self._authenticate()
        if isinstance(auth_result, Response):
            return auth_result
        user, employee = auth_result
        body = self._body() or {}
        pin = (body.get('pin') or '').strip()
        if not pin or employee.sudo().pin != pin:
            return _json_resp(_err('Invalid PIN.', 'INVALID_PIN'), 401)
        return self.attendance_checkout(**kw)

    @http.route(
        f'{_BASE}/attendance/history',
        type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False,
    )
    def attendance_history(self, **kw):
        if request.httprequest.method == 'OPTIONS':
            return _preflight()
        auth_result = self._authenticate()
        if isinstance(auth_result, Response):
            return auth_result
        user, employee = auth_result

        args = request.httprequest.args
        page, limit, offset = self._paginate(args)

        domain = [('employee_id', '=', employee.id)]
        for param, field in (('date_from', 'check_in >='), ('date_to', 'check_in <=')):
            raw = args.get(param)
            if raw:
                try:
                    dt = datetime.fromisoformat(raw)
                    domain.append((field.split()[0], field.split()[1], dt))
                except ValueError:
                    return _json_resp(
                        _err(f'Invalid {param} — use ISO 8601 format', 'BAD_REQUEST'), 400
                    )

        AttModel = request.env['hr.attendance'].sudo()
        total = AttModel.search_count(domain)
        records = AttModel.search(domain, order='check_in desc', limit=limit, offset=offset)

        return _json_resp(_ok({
            'total': total,
            'page': page,
            'limit': limit,
            'pages': self._pages(total, limit),
            'records': [_ser_attendance(r) for r in records],
        }))

    # ── Leaves ─────────────────────────────────────────────────────────────────

    @http.route(f'{_BASE}/leaves/types', type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False)
    def leave_types(self, **kw):
        if request.httprequest.method == 'OPTIONS':
            return _preflight()
        auth_result = self._authenticate()
        if isinstance(auth_result, Response):
            return auth_result
        user, employee = auth_result

        leave_types = request.env(user=user.id)['hr.leave.type'].sudo().search([
            ('company_id', 'in', [employee.company_id.id, False]),
            ('active', '=', True),
        ])
        data = []
        for lt in leave_types:
            data.append({
                'id': lt.id,
                'name': lt.name,
                'request_unit': getattr(lt, 'request_unit', 'day'),
                'requires_allocation': getattr(lt, 'requires_allocation', False),
                'color': getattr(lt, 'color_name', '') or '',
            })
        return _json_resp(_ok(data))

    @http.route(f'{_BASE}/leaves', type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False)
    def create_leave(self, **kw):
        if request.httprequest.method == 'OPTIONS':
            return _preflight()
        auth_result = self._authenticate()
        if isinstance(auth_result, Response):
            return auth_result
        user, employee = auth_result

        payload = self._body()
        if payload is None:
            return _json_resp(_err('Invalid JSON body', 'BAD_REQUEST'), 400)

        leave_type_id = payload.get('leave_type_id')
        date_from_str = payload.get('date_from')
        date_to_str = payload.get('date_to')
        description = (payload.get('description') or '').strip()
        request_unit = (payload.get('request_unit') or 'day').lower()

        if request_unit not in ('day', 'half_day', 'hour'):
            return _json_resp(
                _err('request_unit must be "day", "half_day", or "hour"', 'BAD_REQUEST'), 400
            )

        if not leave_type_id or not date_from_str:
            return _json_resp(
                _err('leave_type_id and date_from are required', 'BAD_REQUEST'), 400
            )
        if request_unit == 'day' and not date_to_str:
            return _json_resp(
                _err('date_to is required for day-unit leaves', 'BAD_REQUEST'), 400
            )

        try:
            date_from_dt = datetime.fromisoformat(date_from_str)
            date_to_dt = datetime.fromisoformat(date_to_str) if date_to_str else date_from_dt
        except ValueError:
            return _json_resp(
                _err('Invalid date format — use ISO 8601 (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)',
                     'BAD_REQUEST'), 400
            )

        if request_unit == 'day' and date_from_dt > date_to_dt:
            return _json_resp(_err('date_from must not be after date_to', 'BAD_REQUEST'), 400)

        try:
            lt_id = int(leave_type_id)
        except (TypeError, ValueError):
            return _json_resp(_err('leave_type_id must be an integer', 'BAD_REQUEST'), 400)

        user_env = request.env(user=user.id)
        leave_type = user_env['hr.leave.type'].sudo().browse(lt_id)
        if not leave_type.exists():
            return _json_resp(_err('Leave type not found', 'NOT_FOUND'), 404)

        # Build create values per request_unit.
        # request_date_* drive _compute_date_from_to; omitting them defaults both to today.
        if request_unit == 'half_day':
            period = (payload.get('period') or 'am').lower()
            if period not in ('am', 'pm'):
                return _json_resp(_err('period must be "am" or "pm"', 'BAD_REQUEST'), 400)
            create_vals = {
                'employee_id': employee.id,
                'holiday_status_id': lt_id,
                'request_unit_half': True,
                'request_date_from': date_from_dt.date(),
                'request_date_to': date_from_dt.date(),
                'request_date_from_period': period,
                'name': description or f'Leave — {employee.name}',
            }
        elif request_unit == 'hour':
            hour_from = payload.get('hour_from')
            hour_to = payload.get('hour_to')
            if hour_from is None or hour_to is None:
                return _json_resp(
                    _err('hour_from and hour_to are required for hour-unit leaves', 'BAD_REQUEST'),
                    400,
                )
            try:
                hour_from = float(hour_from)
                hour_to = float(hour_to)
            except (TypeError, ValueError):
                return _json_resp(
                    _err('hour_from and hour_to must be numbers (e.g. 9.0, 12.5)', 'BAD_REQUEST'),
                    400,
                )
            if not (0 <= hour_from <= 24 and 0 <= hour_to <= 24 and hour_from < hour_to):
                return _json_resp(
                    _err('hour_from must be < hour_to and both in range [0, 24]', 'BAD_REQUEST'),
                    400,
                )
            create_vals = {
                'employee_id': employee.id,
                'holiday_status_id': lt_id,
                'request_unit_hours': True,
                'request_date_from': date_from_dt.date(),
                'request_date_to': date_to_dt.date(),
                'request_hour_from': hour_from,
                'request_hour_to': hour_to,
                'name': description or f'Leave — {employee.name}',
            }
        else:  # day
            create_vals = {
                'employee_id': employee.id,
                'holiday_status_id': lt_id,
                'request_date_from': date_from_dt.date(),
                'request_date_to': date_to_dt.date(),
                'date_from': date_from_dt,
                'date_to': date_to_dt,
                'name': description or f'Leave — {employee.name}',
            }

        try:
            leave = user_env['hr.leave'].sudo().with_context(
                mail_create_nolog=True,
                mail_notrack=True,
                leave_fast_create=True,
            ).create(create_vals)
            request.env.cr.flush()  # surface deferred Odoo constraints now
        except Exception as exc:
            request.env.cr.rollback()
            _logger.exception('Leave creation failed for employee %s', employee.id)
            self._audit(
                user.id, employee.id, 'leave_create_failed',
                f'{_BASE}/leaves', 'error', str(exc)
            )
            return _json_resp(_err(str(exc), 'VALIDATION_ERROR'), 422)

        self._audit(
            user.id, employee.id, 'leave_created',
            f'{_BASE}/leaves', 'success', None, {'leave_id': leave.id}
        )
        return _json_resp(_ok(_ser_leave(leave)), 201)

    @http.route(f'{_BASE}/leaves/history', type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False)
    def leave_history(self, **kw):
        if request.httprequest.method == 'OPTIONS':
            return _preflight()
        auth_result = self._authenticate()
        if isinstance(auth_result, Response):
            return auth_result
        user, employee = auth_result

        args = request.httprequest.args
        page, limit, offset = self._paginate(args)
        state = args.get('state')

        domain = [('employee_id', '=', employee.id)]
        valid_states = {'draft', 'confirm', 'validate1', 'validate', 'refuse'}
        if state:
            if state not in valid_states:
                return _json_resp(
                    _err(f'Invalid state "{state}" — must be one of: {", ".join(sorted(valid_states))}',
                         'BAD_REQUEST'), 400
                )
            domain.append(('state', '=', state))

        LeaveModel = request.env(user=user.id)['hr.leave'].sudo()
        total = LeaveModel.search_count(domain)
        records = LeaveModel.search(domain, order='date_from desc', limit=limit, offset=offset)

        return _json_resp(_ok({
            'total': total,
            'page': page,
            'limit': limit,
            'pages': self._pages(total, limit),
            'records': [_ser_leave(r) for r in records],
        }))

    # ── Payslips ───────────────────────────────────────────────────────────────

    @http.route(f'{_BASE}/payslips', type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False)
    def payslip_list(self, **kw):
        if request.httprequest.method == 'OPTIONS':
            return _preflight()
        auth_result = self._authenticate()
        if isinstance(auth_result, Response):
            return auth_result
        user, employee = auth_result

        if 'hr.payslip' not in request.env.registry:
            return _json_resp(_err('Payroll module not installed', 'NOT_AVAILABLE'), 503)

        args = request.httprequest.args
        page, limit, offset = self._paginate(args)

        domain = [('employee_id', '=', employee.id)]
        SlipModel = request.env['hr.payslip'].sudo()
        total = SlipModel.search_count(domain)
        records = SlipModel.search(domain, order='date_from desc', limit=limit, offset=offset)

        return _json_resp(_ok({
            'total': total,
            'page': page,
            'limit': limit,
            'pages': self._pages(total, limit),
            'records': [_ser_payslip_summary(r) for r in records],
        }))

    @http.route(
        f'{_BASE}/payslips/<int:payslip_id>',
        type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False,
    )
    def payslip_detail(self, payslip_id, **kw):
        if request.httprequest.method == 'OPTIONS':
            return _preflight()
        auth_result = self._authenticate()
        if isinstance(auth_result, Response):
            return auth_result
        user, employee = auth_result

        if 'hr.payslip' not in request.env.registry:
            return _json_resp(_err('Payroll module not installed', 'NOT_AVAILABLE'), 503)

        slip = request.env['hr.payslip'].sudo().browse(payslip_id)
        if not slip.exists():
            return _json_resp(_err('Payslip not found', 'NOT_FOUND'), 404)

        # Explicit IDOR guard — never trust the URL parameter alone.
        if slip.employee_id.id != employee.id:
            self._audit(
                user.id, employee.id, 'payslip_idor_attempt',
                f'{_BASE}/payslips/{payslip_id}', 'error',
                f'Employee {employee.id} attempted to access payslip {payslip_id} '
                f'belonging to employee {slip.employee_id.id}',
            )
            return _json_resp(_err('Access denied', 'FORBIDDEN'), 403)

        self._audit(user.id, employee.id, 'payslip_view',
                    f'{_BASE}/payslips/{payslip_id}', 'success')
        return _json_resp(_ok(_ser_payslip_detail(slip)))

    # ── Meta ───────────────────────────────────────────────────────────────────

    @http.route(f'{_BASE}/version', type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False)
    def version(self, **kw):
        if request.httprequest.method == 'OPTIONS':
            return _preflight()
        return _json_resp(_ok({
            'module': 'mobile_hr_api',
            'module_version': '1.0.0',
            'api_version': 'v1',
            'odoo_series': '19.0',
        }))

    @http.route(f'{_BASE}/config', type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False)
    def config(self, **kw):
        if request.httprequest.method == 'OPTIONS':
            return _preflight()
        auth_result = self._authenticate()
        if isinstance(auth_result, Response):
            return auth_result
        user, employee = auth_result

        settings = request.env['mobile.hr.api.settings'].sudo().get_settings(
            employee.company_id.id
        )
        geofences = request.env['mobile.hr.api.geofence'].sudo().search([
            ('company_id', '=', employee.company_id.id),
            ('is_active', '=', True),
        ])

        return _json_resp(_ok({
            'require_gps_validation': settings.require_gps_validation,
            'token_validity_days': settings.token_validity_days,
            'geofences': [
                {
                    'id': g.id,
                    'name': g.name,
                    'radius_meters': g.radius_meters,
                    'min_accuracy_meters': g.min_accuracy_meters,
                }
                for g in geofences
            ],
        }))

    # ── Push notifications ──────────────────────────────────────────────────────

    @http.route(f'{_PUSH}/vapid-key', type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False)
    def push_vapid_key(self, **kw):
        if request.httprequest.method == 'OPTIONS':
            return _preflight()
        auth_result = self._authenticate()
        if isinstance(auth_result, Response):
            return auth_result

        icp = request.env['ir.config_parameter'].sudo()
        public_key = icp.get_param('mobile_hr_api.vapid_public_key', '')
        if not public_key:
            return _json_resp(_err(
                'VAPID public key not configured — set ir.config_parameter '
                '"mobile_hr_api.vapid_public_key"', 'NOT_CONFIGURED',
            ), 503)
        return _json_resp(_ok({'vapid_public_key': public_key}))

    @http.route(f'{_PUSH}/subscribe', type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False)
    def push_subscribe(self, **kw):
        if request.httprequest.method == 'OPTIONS':
            return _preflight()
        auth_result = self._authenticate()
        if isinstance(auth_result, Response):
            return auth_result
        user, employee = auth_result

        body = self._body() or {}
        platform = (body.get('platform') or 'web').lower()
        if platform not in ('web', 'android', 'ios'):
            return _json_resp(_err('platform must be "web", "android", or "ios"', 'BAD_REQUEST'), 400)

        device_id = (body.get('device_id') or '').strip()
        if not device_id:
            return _json_resp(_err('device_id is required', 'BAD_REQUEST'), 400)

        PushSub = request.env['mobile.hr.api.push.sub'].sudo()
        existing = PushSub.search([
            ('employee_id', '=', employee.id),
            ('device_id', '=', device_id),
        ], limit=1)

        vals = {
            'platform': platform,
            'is_active': True,
            'endpoint': body.get('endpoint') or '',
            'p256dh': body.get('p256dh') or '',
            'auth_key': body.get('auth') or '',
            'push_token': body.get('push_token') or '',
        }
        if existing:
            existing.write(vals)
            sub_id = existing.id
        else:
            vals.update({'employee_id': employee.id, 'device_id': device_id})
            sub_id = PushSub.create(vals).id

        return _json_resp(_ok({'id': sub_id, 'device_id': device_id}), 201)

    @http.route(f'{_PUSH}/unsubscribe', type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False)
    def push_unsubscribe(self, **kw):
        if request.httprequest.method == 'OPTIONS':
            return _preflight()
        auth_result = self._authenticate()
        if isinstance(auth_result, Response):
            return auth_result
        user, employee = auth_result

        body = self._body() or {}
        device_id = (body.get('device_id') or '').strip()
        if not device_id:
            return _json_resp(_err('device_id is required', 'BAD_REQUEST'), 400)

        PushSub = request.env['mobile.hr.api.push.sub'].sudo()
        subs = PushSub.search([
            ('employee_id', '=', employee.id),
            ('device_id', '=', device_id),
        ])
        if subs:
            subs.write({'is_active': False})
        return _json_resp(_ok({}, 'Unsubscribed successfully'))
