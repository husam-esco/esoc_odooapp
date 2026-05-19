# Changelog

All notable changes to `mobile_hr_api` are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows Odoo convention: `<series>.<major>.<minor>.<patch>` — e.g. `19.0.1.0.0`.

---

## [19.0.1.1.0] — 2026-05-14

### Fixed

**Authentication**
- `res.users.authenticate()` signature changed in Odoo 19 — now takes `credential` dict `{'type':'password','login':...,'password':...}` and returns `auth_info` dict instead of uid integer. Login endpoint updated accordingly.

**Attendance**
- `in_mode` / `out_mode` selection extended to include `'mobile'` (`Mobile API`) via `selection_add` in `hr_attendance_extension.py`. API check-in now sets `in_mode='mobile'` and check-out sets `out_mode='mobile'` so records are distinguishable from manual/kiosk entries in the Odoo Attendance UI.

**Container / Deployment**
- Login page showing only "Manage Databases" with no login fields — fixed by adding `db_filter = ^odoo19-6$` and `list_db = False` to `/etc/odoo/odoo.conf`.
- Blank login page (logo only, no form fields) after container restart — caused by compiled JS/CSS asset bundles stored in filestore but filestore not volume-mounted. Fix: mount `/var/lib/odoo` as a named volume; clear stale `ir_attachment` records where `url LIKE '/web/assets/%'` to force regeneration.
- API routes returning 404 after restart — Odoo process started without `--addons-path`. Fix: create `/etc/odoo/odoo.conf` with `addons_path` set; container's `/entrypoint.sh` reads this file via `$ODOO_RC`.
- Frontend `OwlError: Cannot read properties of undefined (reading '1')` after adding new selection value — stale JS bundle cached old selection list. Fix: clear asset attachments from DB and restart.

---

## [19.0.1.0.0] — 2026-05-12

Initial release.

### Added

**Authentication**
- Bearer token login (`POST /api/v1/mobile/auth/login`) with device rotation support
- Logout / token revocation (`POST /api/v1/mobile/auth/logout`)
- SHA-256 hashed token storage — raw token is returned once and never stored
- Configurable token validity (default 30 days per company)
- Portal user support — no internal-user licence required

**Employee profile**
- `GET /api/v1/mobile/hr/me` — full employee profile with department, manager, work location

**Attendance**
- `POST /api/v1/mobile/hr/attendance/check-in` with GPS capture and geofence validation
- `POST /api/v1/mobile/hr/attendance/check-out` with GPS capture and geofence validation
- `GET /api/v1/mobile/hr/attendance/history` — paginated, date-filtered history
- GPS fields added to `hr.attendance` via model inheritance: latitude, longitude, accuracy, geofence_valid for both check-in and check-out

**Geofence**
- `mobile.hr.api.geofence` model — per-company, per-work-location configurable zones
- Haversine distance calculation (WGS-84)
- GPS accuracy threshold enforcement
- Zone resolution: work-location-specific first, company-wide fallback
- Admin views for geofence zone management

**Leaves**
- `GET /api/v1/mobile/hr/leaves/types` — available leave types for the employee's company
- `POST /api/v1/mobile/hr/leaves` — submit leave request (created in `confirm` state)
- `GET /api/v1/mobile/hr/leaves/history` — paginated, state-filtered history

**Payslips** *(requires `hr_payroll` or compatible module)*
- `GET /api/v1/mobile/hr/payslips` — paginated payslip list
- `GET /api/v1/mobile/hr/payslips/{id}` — full payslip detail with salary lines, worked days, inputs
- IDOR guard: ownership verified server-side before returning detail

**Security**
- All ORM queries use `sudo()` with explicit `employee_id` filter — client never supplies an ID
- CORS preflight handler for all API routes
- Record rules blocking portal users from direct RPC access to settings and geofences
- Audit log tokens restricted to own user

**Settings**
- `mobile.hr.api.settings` model — per-company: API enabled, token validity, GPS validation flag, default geofence
- Default settings record created on module install for the main company (`noupdate=1`)
- Admin menu under **Employees → Mobile API**

**Audit log**
- `mobile.hr.api.audit.log` — append-only (write/unlink blocked at model level)
- Records: user, employee, action, endpoint, IP address, status, details, extra JSON data
- Viewable by HR Managers via **Employees → Mobile API → Reporting → Audit Logs**

**Meta**
- `GET /api/v1/mobile/hr/version` — module + API version, no auth required
- `GET /api/v1/mobile/hr/config` — company settings for mobile app startup

**Documentation**
- `docs/api_endpoints.md` — full endpoint reference with request/response examples
- `docs/deployment.md` — production deployment and configuration guide
- `postman/mobile_hr_api_collection.json` — importable Postman v2.1 collection
- `postman/mobile_hr_api_environment.json` — Postman environment template

**Tests**
- `tests/test_api.py` — TransactionCase suite covering token lifecycle, settings, geofence validation, employee isolation, audit log immutability
