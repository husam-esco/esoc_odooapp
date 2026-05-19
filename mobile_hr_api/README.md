# mobile_hr_api

Secure mobile self-service API backend for **Odoo 19 Community Edition**.

Employees access their own HR data — attendance, leaves, payslips — through a mobile app. Portal user accounts are used, avoiding internal-user licence costs.

---

## Features

- Token-based authentication (Bearer, no session cookies)
- Portal users only — no internal-user licences needed
- GPS-enforced attendance check-in/check-out with configurable geofence zones
- Full attendance history with GPS metadata
- Leave request submission and history
- Payslip list and full payslip detail (OCA payroll compatible)
- Per-company configurable settings
- Append-only audit log for every significant API action
- Versioned REST-like JSON API (`/api/v1/mobile/hr/...`)
- Admin back-end views: settings, geofences, tokens, audit logs

---

## Assumptions

The following assumptions were made where the specification was silent:

| Topic | Assumption |
|-------|-----------|
| Payroll module | OCA `hr_payroll` or any module exposing `hr.payslip` is required for payslip endpoints. If absent, those endpoints return `HTTP 503`. |
| Token storage | Tokens are stored **hashed** (SHA-256). The raw token is returned once at login and never stored. |
| Leave workflow | Leaves are created in draft state and immediately confirmed (`action_confirm()`). Manager approval follows the standard Odoo Time Off workflow. |
| GPS required when enabled | If `require_gps_validation = True` and the client omits coordinates, check-in/out is rejected. |
| Date/time format | All datetime inputs must be ISO 8601 (`YYYY-MM-DDTHH:MM:SS`). UTC is assumed when no timezone offset is supplied. |
| Multi-company | Each company has independent settings and geofence zones. Employees are resolved to their primary company. |

---

## Installation

### Prerequisites

- Odoo 19 CE running in container `odoo19-6` (port `19006`)
- Python packages: all standard — no extra pip installs needed
- OCA `hr_payroll` if payslip endpoints are required

### Steps

1. Place this module directory in your addons path:
   ```
   /addons/odoo19-6/mobile_hr_api/
   ```

2. Restart Odoo:
   ```bash
   docker restart odoo19-6
   ```

3. Activate developer mode in Odoo settings.

4. Navigate to **Apps**, search for `mobile_hr_api`, install.

5. Navigate to **Employees → Mobile API → Configuration → API Settings** to confirm the default settings were created.

6. If payroll is not installed, remove `hr_payroll` from `__manifest__.py` `depends` before installing.

---

## Security Model

### Authentication flow

```
Mobile App
  → POST /api/v1/mobile/auth/login  (login + password)
  ← { token: "..." }

Subsequent requests:
  → Authorization: Bearer <token>
  Server: hash(token) → match in mobile.hr.api.token
          → resolve res.users
          → resolve hr.employee (by user_id)
          → all queries filtered by that employee.id
```

### Why portal users?

Odoo charges licence fees per internal user. Employees who only need mobile self-service are created as **portal users** (`base.group_portal`). The module accepts both portal and internal users at login, but no internal-user-only features (HR manager functions) are exposed through this API.

### IDOR prevention

The client **never** supplies an employee ID. Every controller endpoint:
1. Validates the Bearer token.
2. Resolves the employee from the authenticated user server-side.
3. Filters every ORM query explicitly with `('employee_id', '=', employee.id)`.

The payslip detail endpoint additionally performs an explicit ownership check after the database read and logs the attempt if it fails.

### Why `sudo()` in controllers?

Portal users do not have model-level access grants on `hr.attendance`, `hr.leave`, or `hr.payslip` by default. Rather than granting broad model access, the module uses `sudo()` for all ORM operations and enforces employee isolation at the controller level. This keeps the permission surface small and the isolation logic explicit.

### Audit log

All significant actions are appended to `mobile.hr.api.audit.log`. The model blocks `write()` and `unlink()`, making it append-only. HR Managers can view logs via the back-end. Logs include: user, employee, action, endpoint, IP address, status, and optional JSON extra data.

---

## GPS / Geofence Setup

1. Go to **Employees → Mobile API → Configuration → Geofence Zones**.
2. Create a zone:
   - **Company**: your company
   - **Work Location**: leave blank for a company-wide fallback, or pick a specific work location
   - **Centre Latitude / Longitude**: the GPS coordinates of the allowed zone centre (e.g. office building centroid)
   - **Radius (metres)**: employees must be within this distance to check in/out
   - **Max Allowed GPS Inaccuracy**: reject requests where the device reports worse accuracy than this (0 = disabled)
3. Enable GPS validation in **API Settings** (`Require GPS Geofence Validation`).

**Zone resolution order:**
1. Active zone matching employee's **work location** and company
2. Active zone matching **company only** (work_location = blank)
3. If no zone is found and GPS validation is on → check-in/out is rejected

**Accuracy note:** Phone GPS accuracy varies. A max of 100 m is a reasonable default. Tighten to 50 m for stricter enforcement or relax to 0 to disable.

---

## API Usage Overview

### Base URL

```
http://<host>:19006
```

### Quick start

```bash
# 1. Login
curl -X POST http://localhost:19006/api/v1/mobile/auth/login \
  -H "Content-Type: application/json" \
  -d '{"login":"emp@company.com","password":"pass"}'

# 2. Use token
TOKEN="<token from login response>"

# 3. Get profile
curl http://localhost:19006/api/v1/mobile/hr/me \
  -H "Authorization: Bearer $TOKEN"

# 4. Check in
curl -X POST http://localhost:19006/api/v1/mobile/hr/attendance/check-in \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"latitude":25.2048,"longitude":55.2708,"accuracy":12}'
```

See `docs/api_endpoints.md` for the full endpoint reference.

---

## Portal User Setup

1. Go to **Settings → Users → New User**.
2. Set Portal as the user type.
3. Go to **Employees**, create or open the employee record.
4. In the **HR Settings** tab, set the **Related User** to the portal user you created.
5. The employee can now log in via the mobile app.

---

## Upgrade Notes

- `mobile.hr.api.token` tokens are stored hashed — upgrading does not invalidate existing tokens.
- `mobile.hr.api.audit.log` records are append-only and survive upgrades.
- `mobile.hr.api.settings` uses `noupdate=1` in `default_settings.xml` — your customised settings are not overwritten on upgrade.
- New GPS fields on `hr.attendance` (`checkin_latitude`, etc.) default to `0.0` for existing records — no data migration needed.
- Module version follows Odoo convention: `19.0.<major>.<minor>.<patch>`.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `401 UNAUTHORIZED` on every request | Token expired or revoked | Login again to get a new token |
| `403 FORBIDDEN` — no employee | Portal user not linked to an hr.employee | Set `Related User` on the employee record |
| `403 GEOFENCE_VIOLATION` — no active geofence | No geofence zone configured for company | Create one in **Mobile API → Configuration → Geofence Zones** |
| `503 NOT_AVAILABLE` on payslip endpoints | `hr_payroll` module not installed | Install OCA payroll or remove payslip dependency |
| `422 VALIDATION_ERROR` on leave creation | Leave type has allocation restrictions or conflicting dates | Check leave balance and Odoo Time Off rules |
| Module not visible in Apps | Already installed — Apps list filters to uninstalled by default | Remove the "Apps" filter tag in the search bar |
| GPS accuracy rejection | Device GPS accuracy worse than `min_accuracy_meters` | Increase `min_accuracy_meters` in the geofence zone or set to 0 |
| Login page shows database selector | `db_filter` not set in `odoo.conf` | Add `db_filter = ^<dbname>$` and `list_db = False` to `odoo.conf`, restart |
| Login page blank — logo only, no form | Filestore not volume-mounted; JS bundles lost on restart | Mount `/var/lib/odoo` as named volume; clear stale `ir_attachment` asset records |
| `OwlError: Cannot read properties of undefined` | Stale JS bundle after adding new selection field value | Clear asset bundles from `ir_attachment` and restart container |
| Attendance mode shows "Manual" not "Mobile API" | Module not upgraded after `in_mode` selection_add change | Run `-u mobile_hr_api` then restart container |
