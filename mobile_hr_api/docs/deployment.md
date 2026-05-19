# Deployment Guide

## Prerequisites

| Requirement | Version |
|-------------|---------|
| Odoo Community Edition | 19.0 |
| Python | 3.10+ |
| PostgreSQL | 14+ |
| Docker (if containerised) | 24+ |

No extra pip packages — all dependencies are part of Odoo's standard library.

---

## Container Setup (Docker Compose)

### 1. Mount the addons directory

In your `docker-compose.yml`, mount your addons path into the container:

```yaml
services:
  odoo19-6:
    image: odoo:19.0
    ports:
      - "19006:8069"
    volumes:
      - ./addons/odoo19-6:/mnt/extra-addons
      - ./odoo.conf:/etc/odoo/odoo.conf:ro
      - odoo19-6-filestore:/var/lib/odoo   # required — persists compiled JS/CSS bundles
    depends_on:
      - db

volumes:
  odoo19-6-filestore:
```

> **The `/var/lib/odoo` volume is critical.** Odoo stores compiled JS/CSS asset bundles as files in `/var/lib/odoo/filestore/`. Without this volume, every container restart loses the bundles — the login page renders blank (logo only, no form fields).

### 2. Create `odoo.conf`

Place alongside `docker-compose.yml`:

```ini
[options]
addons_path = /mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons
db_filter = ^odoo19-6$
list_db = False
```

This file is read by the container's `/entrypoint.sh` via the `$ODOO_RC` environment variable (default: `/etc/odoo/odoo.conf`).

> **Without this file, Odoo starts without `--addons-path` and will not find custom modules or register their HTTP routes.**

`db_filter` forces Odoo to target only `odoo19-6` — browser goes straight to the login form instead of the database selector page. `list_db = False` hides the "Manage Databases" link (security best practice).

### 3. Start the stack

```bash
docker compose up -d
```

---

## Module Installation

### Via Odoo UI

1. Enable developer mode: **Settings → General Settings → Developer Tools → Activate**.
2. Go to **Apps**, click **Update Apps List**.
3. Search for `mobile_hr_api`, click **Install**.

### Via CLI (headless / CI)

```bash
docker exec odoo19-6 odoo \
  --db_host=db --db_port=5432 --db_user=odoo --db_password=odoo \
  -d odoo19-6 \
  --addons-path=/mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons \
  -i mobile_hr_api \
  --stop-after-init
```

### Upgrade after code change

```bash
docker exec odoo19-6 odoo \
  --db_host=db --db_port=5432 --db_user=odoo --db_password=odoo \
  -d odoo19-6 \
  --addons-path=/mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons \
  -u mobile_hr_api \
  --stop-after-init
```

Then restart the container so the live process picks up the new routes:

```bash
docker restart odoo19-6
```

---

## Post-Install Configuration

### 1. Verify default settings

Navigate to **Employees → Mobile API → Configuration → API Settings**.  
One record should exist for your main company with:
- API Enabled: ✓
- Token Validity: 30 days
- Require GPS Validation: ✓

Adjust as needed per company.

### 2. Create geofence zones (if GPS validation is on)

Navigate to **Employees → Mobile API → Configuration → Geofence Zones → New**:

| Field | Value |
|-------|-------|
| Name | `HQ Office` |
| Company | Your company |
| Work Location | Leave blank for company-wide, or pick a specific location |
| Latitude | Decimal degrees (e.g. `25.2048`) |
| Longitude | Decimal degrees (e.g. `55.2708`) |
| Radius (metres) | `200` — employees must be within this distance |
| Max GPS Inaccuracy | `100` — reject requests where device accuracy > 100 m (0 = disabled) |

> **If GPS validation is on and no geofence is configured, all check-in/check-out attempts are rejected.**

### 3. Create employee portal users

For each employee who will use the mobile app:

1. **Settings → Users → New User** — set type to **Portal**.
2. **Employees** → open or create the employee record → **HR Settings** tab → **Related User** → select the portal user.

Alternatively, use the Odoo API or a batch import script.

---

## Running Tests

```bash
docker exec odoo19-6 odoo \
  --db_host=db --db_port=5432 --db_user=odoo --db_password=odoo \
  -d odoo19-6 \
  --addons-path=/mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons \
  --test-tags mobile_hr_api \
  --stop-after-init
```

---

## Health Check

The `/api/v1/mobile/hr/version` endpoint requires no authentication and is safe to use as a liveness probe:

```bash
curl http://localhost:19006/api/v1/mobile/hr/version
# Expected: {"success": true, "data": {"api_version": "v1", ...}}
```

Docker Compose healthcheck example:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8069/api/v1/mobile/hr/version"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s
```

---

## Troubleshooting

### Routes return 404 after install

The running Odoo process does not reload routes automatically after module install via CLI. Always restart the container:

```bash
docker restart odoo19-6
```

If 404 persists after restart, verify the process has `addons_path` set:

```bash
docker exec odoo19-6 ps aux | grep odoo
# Should NOT be missing --addons-path; if it is, check /etc/odoo/odoo.conf exists
docker exec odoo19-6 cat /etc/odoo/odoo.conf
```

### Login page shows "Manage Databases" only / no login form fields

Two distinct issues — check which applies:

**A — Database selector page (URL is `/web/database/selector`)**

`db_filter` not set. Odoo shows the selector when multiple DBs exist or no filter configured. Fix: add to `odoo.conf`:

```ini
db_filter = ^odoo19-6$
list_db = False
```

Restart container. Browser now goes directly to `/web/login`.

**B — Login page loads but form is blank (logo only, no email/password fields)**

Filestore missing compiled JS bundles. Happens when `/var/lib/odoo` is not volume-mounted and container was restarted/recreated. Fix:

1. Add named volume for filestore in `docker-compose.yml` (permanent fix — see above).
2. Clear stale asset attachment records so Odoo regenerates them:

```bash
docker exec odoo19-6 python3 -c "
import psycopg2
conn = psycopg2.connect(host='db', port=5432, user='odoo', password='odoo', dbname='odoo19-6')
cur = conn.cursor()
cur.execute(\"DELETE FROM ir_attachment WHERE store_fname IS NOT NULL AND url LIKE '/web/assets/%'\")
print('Deleted', cur.rowcount, 'stale asset bundles')
conn.commit()
conn.close()
"
docker restart odoo19-6
```

### `OwlError: Cannot read properties of undefined (reading '1')` in UI

Stale JS bundle cached old field selection values. Occurs after adding new `selection_add` values to existing fields. Fix: clear asset bundles (same command as above) and restart.

### Module not found during install

```
invalid module names, ignored: mobile_hr_api
```

The `--addons-path` does not include the directory containing `mobile_hr_api`. Verify:

```bash
docker exec odoo19-6 ls /mnt/extra-addons/mobile_hr_api/__manifest__.py
```

### `_sql_constraints` error on older Odoo

This module uses Odoo 19's `Constraint` class from `odoo.orm.table_objects`. It is not compatible with Odoo 16 or earlier. Do not backport without replacing `Constraint` with `_sql_constraints`.

### `attrs=` / `<tree>` errors

This module uses Odoo 17+ XML view syntax (`<list>`, inline `invisible=`). Not compatible with Odoo 16 or earlier without view changes.

---

## Security Considerations

- Tokens are SHA-256 hashed before storage. A database breach does not expose raw tokens.
- All controller ORM queries use `sudo()` with an explicit employee filter — no data from other employees is accessible regardless of token.
- Portal users have no direct RPC access to `mobile.hr.api.settings` or `mobile.hr.api.geofence` (record rules enforced).
- The audit log is append-only at the model level — even `SUPERUSER_ID` cannot modify or delete records via ORM.
- GPS coordinates are stored for check-in/check-out but **not** returned in the config endpoint.
- CORS is open (`*`) by default. For production, restrict to your mobile app's origin by modifying the `Access-Control-Allow-Origin` header in `controllers/main.py`.
