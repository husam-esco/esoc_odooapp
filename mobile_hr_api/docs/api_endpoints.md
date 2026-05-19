# Mobile HR API — Endpoint Reference

**Base URL:** `http://<host>:19006`
**API prefix:** `/api/v1/mobile`
**Auth prefix:** `/api/v1/mobile/auth`
**Content-Type:** `application/json`

---

## Authentication

All endpoints except `/auth/login` and `/version` require:

```
Authorization: Bearer <token>
```

Tokens are obtained via the login endpoint and expire after the configured validity period (default 30 days).

---

## Response Envelope

### Success
```json
{
  "success": true,
  "data": { ... }
}
```

### Error
```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable description"
  }
}
```

### Error Codes

| Code | Meaning |
|------|---------|
| `UNAUTHORIZED` | Missing or invalid token |
| `FORBIDDEN` | Token valid but access denied |
| `NOT_FOUND` | Resource does not exist |
| `BAD_REQUEST` | Invalid request payload |
| `ALREADY_CHECKED_IN` | Duplicate check-in attempt |
| `NOT_CHECKED_IN` | Check-out with no open attendance |
| `GEOFENCE_VIOLATION` | GPS outside allowed zone |
| `VALIDATION_ERROR` | Odoo-level validation failure |
| `NOT_AVAILABLE` | Required module not installed |

---

## Auth Endpoints

### POST /api/v1/mobile/auth/login

Authenticate and receive a Bearer token.

**Auth required:** No

**Request body:**
```json
{
  "login": "employee@company.com",
  "password": "secret",
  "device_name": "iPhone 15 Pro",
  "device_id": "A1B2C3D4-E5F6-..."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `login` | string | Yes | Odoo user login (email) |
| `password` | string | Yes | User password |
| `device_name` | string | No | Human-readable device label |
| `device_id` | string | No | Unique device identifier. Providing this revokes any existing active token for the same device. |

**Response 200:**
```json
{
  "success": true,
  "data": {
    "token": "xyzABCabc...",
    "employee_name": "John Smith",
    "expires_in_days": 30
  }
}
```

**Errors:** `401 UNAUTHORIZED`, `403 FORBIDDEN`

---

### POST /api/v1/mobile/auth/logout

Revoke the current token.

**Auth required:** Yes

**Request body:** empty `{}`

**Response 200:**
```json
{ "success": true, "message": "Logged out successfully" }
```

---

## Employee Profile

### GET /api/v1/mobile/hr/me

Return the authenticated employee's profile.

**Auth required:** Yes

**Response 200:**
```json
{
  "success": true,
  "data": {
    "id": 42,
    "name": "John Smith",
    "employee_number": "EMP-0042",
    "job_title": "Software Engineer",
    "job_position": { "id": 5, "name": "Developer" },
    "department": { "id": 3, "name": "Engineering" },
    "company": { "id": 1, "name": "ACME Corp" },
    "work_location": { "id": 2, "name": "HQ - Dubai" },
    "manager": { "id": 10, "name": "Jane Doe" },
    "work_email": "john.smith@acme.com",
    "work_phone": "+971 4 000 0000",
    "mobile_phone": "+971 55 000 0000",
    "image_url": "/web/image/hr.employee/42/image_128"
  }
}
```

---

## Attendance

### POST /api/v1/mobile/hr/attendance/check-in

Check in the authenticated employee.

**Auth required:** Yes

**Request body:**
```json
{
  "latitude": 25.2048,
  "longitude": 55.2708,
  "accuracy": 12.5,
  "device_meta": {
    "device_id": "A1B2C3D4",
    "platform": "iOS",
    "app_version": "1.0.0"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `latitude` | float | Conditional* | WGS-84 decimal degrees |
| `longitude` | float | Conditional* | WGS-84 decimal degrees |
| `accuracy` | float | No | GPS horizontal accuracy in metres |
| `device_meta` | object | No | Arbitrary device metadata |

*Required when GPS validation is enabled in settings.

**Response 201:**
```json
{
  "success": true,
  "data": {
    "attendance_id": 101,
    "check_in": "2024-06-01T08:00:00",
    "geofence_message": "Within zone — 42m from centre"
  }
}
```

**Errors:** `403 GEOFENCE_VIOLATION`, `409 ALREADY_CHECKED_IN`

---

### POST /api/v1/mobile/hr/attendance/check-out

Check out the authenticated employee.

**Auth required:** Yes

**Request body:** same as check-in

**Response 200:**
```json
{
  "success": true,
  "data": {
    "attendance_id": 101,
    "check_in": "2024-06-01T08:00:00",
    "check_out": "2024-06-01T17:02:33",
    "worked_hours": 9.0425,
    "geofence_message": "Within zone — 38m from centre"
  }
}
```

**Errors:** `403 GEOFENCE_VIOLATION`, `409 NOT_CHECKED_IN`

---

### GET /api/v1/mobile/hr/attendance/history

Return attendance records for the authenticated employee.

**Auth required:** Yes

**Query parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `date_from` | ISO 8601 | — | Filter check-ins on or after this datetime |
| `date_to` | ISO 8601 | — | Filter check-ins on or before this datetime |
| `page` | int | 1 | Page number |
| `limit` | int | 30 | Records per page (max 100) |

**Response 200:**
```json
{
  "success": true,
  "data": {
    "total": 45,
    "page": 1,
    "limit": 30,
    "pages": 2,
    "records": [
      {
        "id": 101,
        "check_in": "2024-06-01T08:00:00",
        "check_out": "2024-06-01T17:02:33",
        "worked_hours": 9.0425,
        "is_open": false,
        "checkin_latitude": 25.2048,
        "checkin_longitude": 55.2708,
        "checkin_accuracy": 12.5,
        "checkin_geofence_valid": true,
        "checkout_latitude": 25.2049,
        "checkout_longitude": 55.2710,
        "checkout_accuracy": 9.1,
        "checkout_geofence_valid": true
      }
    ]
  }
}
```

---

## Leave Requests

### GET /api/v1/mobile/hr/leaves/types

Return available leave types.

**Auth required:** Yes

**Response 200:**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "name": "Annual Leave",
      "request_unit": "day",
      "requires_allocation": true,
      "color": ""
    }
  ]
}
```

---

### POST /api/v1/mobile/hr/leaves

Submit a leave request.

**Auth required:** Yes

**Request body:**
```json
{
  "leave_type_id": 1,
  "date_from": "2024-07-15T08:00:00",
  "date_to": "2024-07-17T17:00:00",
  "description": "Family event"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `leave_type_id` | int | Yes | ID from `/leaves/types` |
| `date_from` | ISO 8601 datetime | Yes | Leave start |
| `date_to` | ISO 8601 datetime | Yes | Leave end |
| `description` | string | No | Reason for the leave |

**Response 201:**
```json
{
  "success": true,
  "data": {
    "id": 55,
    "name": "Family event",
    "leave_type": { "id": 1, "name": "Annual Leave" },
    "date_from": "2024-07-15T08:00:00",
    "date_to": "2024-07-17T17:00:00",
    "number_of_days": 3.0,
    "state": "confirm",
    "state_label": "To Approve",
    "refuse_reason": ""
  }
}
```

**Errors:** `400 BAD_REQUEST`, `404 NOT_FOUND`, `422 VALIDATION_ERROR`

---

### GET /api/v1/mobile/hr/leaves/history

Return leave history for the authenticated employee.

**Auth required:** Yes

**Query parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `state` | string | — | Filter by state: `draft`, `confirm`, `validate1`, `validate`, `refuse` |
| `page` | int | 1 | Page number |
| `limit` | int | 30 | Records per page (max 100) |

**Response 200:** Same pagination envelope as attendance history, with leave records.

---

## Payslips

### GET /api/v1/mobile/hr/payslips

List payslips for the authenticated employee.

**Auth required:** Yes

**Query parameters:** `page`, `limit` (same as attendance history)

**Response 200:**
```json
{
  "success": true,
  "data": {
    "total": 12,
    "page": 1,
    "limit": 20,
    "pages": 1,
    "records": [
      {
        "id": 201,
        "name": "Salary Slip of John Smith for June 2024",
        "date_from": "2024-06-01",
        "date_to": "2024-06-30",
        "state": "done",
        "struct": { "id": 3, "name": "Monthly Salary" }
      }
    ]
  }
}
```

---

### GET /api/v1/mobile/hr/payslips/{id}

Full payslip detail.

**Auth required:** Yes. Server verifies the slip belongs to the authenticated employee — passing another employee's payslip ID returns `403 FORBIDDEN`.

**Response 200:**
```json
{
  "success": true,
  "data": {
    "id": 201,
    "name": "Salary Slip of John Smith for June 2024",
    "date_from": "2024-06-01",
    "date_to": "2024-06-30",
    "state": "done",
    "struct": { "id": 3, "name": "Monthly Salary" },
    "contract": { "id": 7, "name": "John Smith - June 2024" },
    "gross_wage": 15000.0,
    "net_wage": 12800.0,
    "salary_lines": [
      { "code": "BASIC", "name": "Basic Salary", "category": {"id":1,"name":"Basic"}, "quantity": 1.0, "rate": 100.0, "amount": 15000.0 },
      { "code": "HRA", "name": "Housing Allowance", "category": {"id":2,"name":"Allowance"}, "quantity": 1.0, "rate": 100.0, "amount": 3000.0 },
      { "code": "INCTAX", "name": "Income Tax", "category": {"id":5,"name":"Deduction"}, "quantity": 1.0, "rate": 100.0, "amount": -2200.0 }
    ],
    "worked_days": [
      { "code": "WORK100", "name": "Regular Working Days", "number_of_days": 22.0, "number_of_hours": 176.0 }
    ],
    "input_lines": []
  }
}
```

---

## Meta

### GET /api/v1/mobile/hr/version

Returns module and API version. No auth required.

### GET /api/v1/mobile/hr/config

Returns company settings visible to the employee (GPS requirement, token validity, geofence zone names and radii — **not** coordinates).

---

## HTTP Status Summary

| Status | Meaning |
|--------|---------|
| 200 | OK |
| 201 | Created |
| 204 | No content (CORS preflight) |
| 400 | Bad request (invalid payload) |
| 401 | Unauthorized (bad or missing token) |
| 403 | Forbidden (geofence, IDOR attempt) |
| 404 | Not found |
| 409 | Conflict (duplicate check-in etc.) |
| 422 | Unprocessable entity (Odoo validation error) |
| 503 | Service unavailable (module not installed) |
