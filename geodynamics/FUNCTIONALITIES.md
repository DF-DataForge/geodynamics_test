# Geodynamics Module — Complete Functionalities Reference

**Module:** `geodynamics`
**Version:** 18.0.0.0.6 (upgrading to 19.0.0.0.1)
**Author:** Data Forge (https://www.data-forge.be)
**External API:** Geodynamics / IntelliTracer (`https://api.intellitracer.be/`)
**Dependencies:** `base`, `hr`, `project`, `industry_fsm`, `account`, `hr_timesheet`

---

## Table of Contents

1. [Module Overview](#1-module-overview)
2. [Authentication & API Connection](#2-authentication--api-connection)
3. [Settings & Configuration](#3-settings--configuration)
4. [Employee Integration](#4-employee-integration)
5. [Employee Timesheet Groups](#5-employee-timesheet-groups)
6. [User Integration](#6-user-integration)
7. [Contact / Partner Integration (POI Sync)](#7-contact--partner-integration-poi-sync)
8. [POI Types](#8-poi-types)
9. [Project Integration](#9-project-integration)
10. [Task Integration](#10-task-integration)
11. [Geodynamics Planning](#11-geodynamics-planning)
12. [Geodynamics Clocking Records](#12-geodynamics-clocking-records)
13. [Clocking Error Detection](#13-clocking-error-detection)
14. [Timesheet Line Extensions](#14-timesheet-line-extensions)
15. [Timesheets Analysis Report](#15-timesheets-analysis-report)
16. [Cron Jobs & Scheduled Tasks](#16-cron-jobs--scheduled-tasks)
17. [Synchronization Wizard](#17-synchronization-wizard)
18. [REST API Controller](#18-rest-api-controller)
19. [GeodynamicsHandler (API Client)](#19-geodynamicshandler-api-client)
20. [Menu Structure](#20-menu-structure)
21. [Data Flow](#21-data-flow)
22. [Key Business Logic](#22-key-business-logic)
23. [Geodynamics External API Endpoints Used](#23-geodynamics-external-api-endpoints-used)

---

## 1. Module Overview

The Geodynamics module bridges Odoo with the **Geodynamics / IntelliTracer** external fleet and workforce management platform. It enables:

- **Two-way synchronization** of employee time tracking (clockings) between Geodynamics and Odoo timesheets
- **Planning management** — create, update, and delete work plannings in Geodynamics from Odoo tasks
- **POI (Point of Interest) management** — automatically create/update/delete POIs in Geodynamics from Odoo contacts and tasks
- **Fleet data import** — load vehicle data from Geodynamics
- **Odometer sync** — log kilometers (and running hours) from Geodynamics into the Odoo fleet odometer (`fleet.vehicle.odometer`)
- **Automated daily clocking sync** via cron jobs
- **Commute (woon-werk) detection** and flagging based on vehicle codes
- **Time discrepancy detection** between employees on the same project
- **Post-calculation import** for timesheet events

The module extends several core Odoo models: `hr.employee`, `res.users`, `res.partner`, `project.project`, `project.task`, `project.task.type`, `account.analytic.line`, `timesheets.analysis.report`, and `res.config.settings`.

---

## 2. Authentication & API Connection

**Base URL:** `https://api.intellitracer.be/`

**Authentication:** HTTP Basic Auth
- Format: `Authorization: Basic base64(username|company:password)`
- The `|` character separates the username from the company identifier

**Rate Limits (API-side):**
- 1800 requests per 30 minutes per identity
- 5 bad requests per 60 seconds
- Returns HTTP 429 with `Retry-After` header when exceeded

**Connection Test:** Available via Settings button "Test verbinding" — calls `GET /api/v2/user` to verify credentials work.

**Throttling:** The handler includes a 100ms sleep between API calls (`time.sleep(0.1)`) to avoid hitting rate limits.

---

## 3. Settings & Configuration

**Model:** `res.config.settings` (inherits)
**File:** `models/res_config_settings.py`
**View:** `views/res_config_settings_views.xml`

### Configuration Parameters

| Parameter Key | Field | Type | Description |
|---------------|-------|------|-------------|
| `geodynamics.company` | `geodynamics_company` | Char | Company identifier for API authentication |
| `geodynamics.username` | `geodynamics_login` | Char | API login username |
| `geodynamics.password` | `geodynamics_password` | Char | API password (displayed as password field) |
| `geodynamics.postcalcsource` | `geodynamics_postcalcsource` | Selection | Source for post-calculation data: `timesheet` (TimeSheetEvents) or `postcalculation` (PostCalculationEvents). Default: `postcalculation` |
| `geodynamics.wapp` | `geodynamics_warning_planning_overlap` | Boolean | Show warnings when plannings overlap between tasks. Default: `True` |
| `geodynamics.plandirectly` | `df_plan_directly` | Boolean | When enabled, automatically sends planning to Geodynamics when task dates/employees change |
| `geodynamics.woon_werk_vehicle_codes` | `geodynamics_woon_werk_vehicle_codes` | Char | Comma-separated vehicle codes for commute (woon-werk) detection. Example: `CODE1,CODE2,CODE3`. Empty means all vehicles are considered. |
| `geodynamics.auto_sync_odometer` | `df_geodynamics_auto_sync_odometer` | Boolean | Enable the daily cron that logs vehicle kilometers from Geodynamics into `fleet.vehicle.odometer`. Default: `False` |
| `geodynamics.odometer_days_back` | `df_geodynamics_odometer_days_back` | Integer | For vehicles without any odometer log, how many days of location-status trip data the first sync fetches. Default: `30` |

### Settings Action Buttons

| Button | Method | Description |
|--------|--------|-------------|
| **Test verbinding** | `gd_test_verbinding()` | Tests API connectivity by calling `GET /api/v2/user`. Shows success/danger notification. |
| **Planning laden Geodynamics** | `gd_fetch_planningen()` | Imports all plannings from Geodynamics for all employees with a Geodynamics ID. Fetches in 30-day chunks from 2025-01-01 to 2025-09-30. |
| **POI types laden** | `gd_poitype_to_odoo()` | Imports all POI types from Geodynamics via `GET /api/v1/poitype` and creates `df.geodynamics.poitype` records. |
| **Planningen gebruikers wissen** | `gd_erase_planningen()` | (Stub) Intended to erase all user plannings. Currently only logs. |
| **Zet demo adressen** | `zetDemoAdressen()` | Development utility: fills all `res.partner` records with random Belgian demo addresses. |

### Computed Field

| Field | Description |
|-------|-------------|
| `df_persones_gd_ids` | Computed Many2many showing all `hr.employee` records. Used for reference in the settings form. |

---

## 4. Employee Integration

**Model:** `hr.employee` (inherits)
**File:** `models/employee.py`
**View:** `views/hr.xml` — Adds a "Geodynamics" tab to the employee form

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `df_geodynamics_id` | Char | The external Geodynamics user GUID (e.g., `00000000-0000-0000-0000-000000000000`). This is the key used for all API lookups: clockings, plannings, etc. If empty, the employee is excluded from Geodynamics operations. |
| `timesheet_group_ids` | Many2many → `employee.timesheet.group` | Links the employee to timesheet groups for extra time calculation rules. Relation table: `employee_timesheet_group_rel`. |

### View

The employee form gets a "Geodynamics" notebook page containing:
- `df_geodynamics_id` field
- `timesheet_group_ids` as many2many_tags (visible to `hr.group_hr_user` only)

---

## 5. Employee Timesheet Groups

**Model:** `employee.timesheet.group`
**File:** `models/employee_timesheet_group.py`
**View:** `views/employee_timesheet_group_views.xml`
**Menu:** HR > Configuration > Timesheet Groups

### Purpose

Defines rules for automatically adding extra timesheet lines per employee per working day. Used for scenarios like adding fixed travel time, preparation time, or other standard allowances.

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | Char | Required | Group name. This is also used as the label for generated timesheet lines (e.g., "Reistijd", "Voorbereiding"). |
| `employee_ids` | Many2many → `hr.employee` | | Employees belonging to this group. Relation table: `employee_timesheet_group_rel`. |
| `extra_time` | Integer | 0 | Extra time in **minutes** to add per qualifying working day. |
| `minimum_time` | Integer | 0 | Minimum registered Geodynamics time in **minutes** required before extra time is granted. If set to 0, extra time is always added. |
| `active` | Boolean | True | Whether the group is active. Inactive groups are ignored during processing. |

### Business Logic

During `fetchClockings()` on a project:
1. After computing regular Geodynamics timesheet lines, the system checks each employee's `timesheet_group_ids`.
2. For each active group with `extra_time > 0`:
   - Calculate total registered Geodynamics minutes for the employee on that date
   - If total minutes >= `minimum_time` (or `minimum_time` is 0): create/update a timesheet line with `name = group.name` and `unit_amount = extra_time / 60.0` hours
   - If total minutes < `minimum_time`: skip (no extra time added)
3. Existing lines with the same group name on the same date are updated rather than duplicated.

---

## 6. User Integration

**Model:** `res.users` (inherits)
**File:** `models/users.py`
**View:** `views/users.xml` — Adds a "Geodynamics" tab to the user form

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `df_geodynamics_id` | Char | | Geodynamics key (separate from employee's key; used for user-based operations) |
| `df_task_create_action` | Selection | `auto_plan` | Controls what happens in Geodynamics when a task is created by this user: |

**`df_task_create_action` options:**
- `add_poi` — Creates a POI in Geodynamics for the task (using task name, partner address)
- `auto_plan` — Automatically creates planning entries in Geodynamics for assigned employees

---

## 7. Contact / Partner Integration (POI Sync)

**Model:** `res.partner` (inherits)
**File:** `models/partner.py`
**View:** `views/partner.xml` — Adds a "Geodynamics" tab to the contact form

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `df_geodynamics_poi_id` | Char | POI ID in Geodynamics, automatically set after successful sync |
| `df_geodynamics_error_message` | Char | Last error message from Geodynamics sync (displayed in form if not empty) |

### Actions

**Sync met Geodynamics** (`sync_poi_geodynamics`):
1. If the contact has no `df_geodynamics_poi_id`: creates a new POI via `PUT /api/v1/poi`
2. If the contact already has a POI ID: updates the POI via the same endpoint
3. POI data sent: `Name` (contact name, falls back to parent name), `PoiType` (first available type), `Street`, `City`, `PostalCode`
4. On success: stores the returned POI ID
5. On error: stores the error message for display

---

## 8. POI Types

**Model:** `df.geodynamics.poitype`
**File:** `models/gdpoitype.py`

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `id_geodynamics` | Char | External POI type ID from Geodynamics |
| `Name` | Char | POI type name |
| `Color` | Char | POI type color |

### Import

Imported from `GET /api/v1/poitype` via the Settings "POI types laden" button. Creates records only if the `id_geodynamics` doesn't already exist.

---

## 9. Project Integration

**Model:** `project.project` (inherits)
**File:** `models/project.py`
**Views:** `views/project.xml`

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `df_gd_employee_ids` | Many2many → `hr.employee` | Employees linked to this project for Geodynamics operations. Domain filter: only employees with `df_geodynamics_id != False`. |
| `gd_clocking_ids` | One2many → `geodynamics.clocking` | All clocking records linked to this project (readonly, via `project_id` inverse). |

### View Extensions

The project form gets two new notebook pages:
1. **Geodynamics** — Shows `df_gd_employee_ids` (many2many tags), buttons for "Zet planning Geodynamics", "Laad post calculatie", "Laad clockings"
2. **Geodynamics Clockings** — List view of `gd_clocking_ids` showing date, type, job number, hours, employee

### Key Methods

#### `fetchClockings()` — Main Clocking Synchronization

The primary method for synchronizing Geodynamics clockings with Odoo timesheets. Called from project form button, task buttons, or cron jobs.

**Algorithm:**
1. **Date range computation** (`_compute_geodynamics_clocking_range()`):
   - Start: `project.date_start` or `project.create_date` or today
   - End: `project.date` or max(task deadlines, task create dates) or project create date
   - Guarantees: end >= start, always returns date objects

2. **Job code extraction** (`_extract_project_job_codes()`):
   - Extracts patterns matching `S\d{5}` (e.g., S01117) from the project name
   - Returns a set of uppercase codes

3. **Misassigned clocking repair** (`_gd_fix_misassigned_clockings()`):
   - Finds clockings linked to this project whose `project_code` doesn't match any of the project's job codes
   - Re-assigns them to the correct project (if found by name) or clears the project link

4. **Employee scope collection**:
   - Task employees: all employees from tasks linked to this project (`_collect_task_employees()`)
   - Legacy employees: employees that already have "Registratie Geodynamics" timesheet lines (`_collect_existing_timesheet_employees()`)
   - Scope = union of both, filtered to only those with `df_geodynamics_id`

5. **API data fetch** (`_gd_fetch_raw_clockings_for_employee()`):
   - Fetches raw clocking records in 30-day chunks via `GET /api/v1/Clocking_GetByUserIdDateRange`
   - Extends date range to cover any existing Geodynamics timesheet dates (`_gd_extend_range_with_existing_lines()`)

6. **Clocking filtering** (`_filter_clockings_with_job_codes()`):
   - Enriches records with datetime, type, job token, POI match
   - Per-day carry-forward logic (see [Key Business Logic](#22-key-business-logic))
   - Returns filtered list of accepted records

7. **Interval computation**:
   - Splits selected records into day-bounded segments
   - Computes minutes per segment
   - Creates/updates timesheet lines under a "Registratie Geodynamics" task

8. **Extra time processing** (`_gd_add_group_extra_lines()`):
   - Adds bonus timesheet lines based on employee timesheet group rules

9. **Cleanup** (`_gd_cleanup_redundant_lines()`, `_gd_repair_legacy_lines()`):
   - Removes timesheet lines that no longer match computed intervals
   - Rebuilds legacy lines from fresh intervals

#### `sendPlanningToDGd()` — Send Planning to Geodynamics

Iterates over the project date range and creates a planning in Geodynamics for each employee on each day.

#### `laadPostcalc()` — Load Post-Calculation Data

Fetches post-calculation events from Geodynamics API and creates/updates timesheet entries matching the project name.

---

## 10. Task Integration

**Model:** `project.task` (inherits, class named `Project`)
**File:** `models/task.py`
**View:** `views/task.xml`

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `df_gd_name` | Char (computed) | Task name for Geodynamics display. Currently set to `task.name`. |
| `df_geodynamics_poi_id` | Char (readonly) | POI ID created in Geodynamics for this task. |
| `df_assignees_with_geodynamics_ids` | Many2many → `res.users` (computed) | Users assigned to the task who have a Geodynamics ID. |
| `df_assignees_without_geodynamics_ids` | Many2many → `res.users` (computed) | Users assigned to the task who lack a Geodynamics ID. |
| `employee_ids` | Many2many → `hr.employee` | Employees (painters/workers) assigned to this task. |
| `df_employees_with_geodynamics_ids` | Many2many → `hr.employee` (computed) | Employees with Geodynamics ID. |
| `df_employees_without_geodynamics_ids` | Many2many → `hr.employee` (computed) | Employees without Geodynamics ID (warning display). |
| `df_employees_without_geodynamics_ids_invisible` | Boolean (computed) | Controls visibility of the warning div. |
| `df_workmode` | Selection (computed) | Always returns `'employeemode'`. Used for conditional page visibility. |
| `df_gd_planning_ids` | One2many → `df.geodynamics.planning` | Planning records linked to this task (via `task_id`). |
| `df_gd_planning_ids2` | One2many (computed) | Same as above but via search-based computation. |
| `df_gd_planning_overlapped_ids` | One2many (computed) | Planning records from other tasks that overlap with this task's time range. |
| `df_gd_planning_overlapped_ids_invisible` | Boolean (computed) | Controls visibility of the overlap warning. |

### View Layout

The task form gets:
1. **Buttons near stage field**: "Plan in Geodynamics" (primary), "Fetch Clockings" (secondary)
2. **Geodynamics page 1** (invisible when `df_workmode != 'usermode'`): POI ID, assignees with GD IDs, action buttons
3. **Geodynamics page 2**: POI ID, warnings for employees without GD ID, overlap warnings, planning list (editable), action buttons (Plan in, Haal nacalculatie op, Fetch clockings)

### Key Methods

#### `create()` Override

When a task is created:
1. Determines action based on creator's `df_task_create_action` preference
2. `add_poi`: calls `addPointOfTask()` to create a POI in Geodynamics
3. `auto_plan`: calls `autoPlan()` to create planning entries

#### `write()` Override

When a task is updated:
1. If `add_poi` mode:
   - If task has an existing POI: checks if stage changed to completion (deletes POI)
   - If task has no POI and stage is not completion: creates a POI
2. If `auto_plan` mode:
   - If `planned_date_start`, `date_deadline`, or `employee_ids` changed and both dates exist: calls `autoPlan()`

#### `unlink()` Override

Before deleting a task, removes all associated plannings from both Geodynamics and Odoo.

#### `sendPlanningToDGdWn()` — Send Planning (Employee-based)

1. Validates: checks employees have GD IDs, dates exist
2. If overlap warning enabled and overlaps detected: shows warning notification
3. Calls `handler.createPlanningByTaskWn()` which:
   - Removes existing plannings for the task
   - Splits task date range into workdays (Mon-Fri, 06:00-15:00, excluding holidays)
   - For each employee and workday period: creates a planning in Geodynamics
   - Auto-creates/syncs POI from partner address if needed

#### `autoPlan()` — Automatic Planning

Similar to `sendPlanningToDGdWn()` but called automatically on task write. Deletes overlapping plannings first.

#### `fetchClockings()` — Task-level Clocking Fetch

Fetches clockings for employees linked to this task within the task's date range (`planned_date_start` to `date_deadline`). Filters by project job codes and creates per-day aggregated timesheet lines.

#### `laadPostcalc()` — Load Post-Calculation

For each planning linked to this task:
1. Fetches post-calculation data from Geodynamics
2. Based on `postcalcsource` setting:
   - `timesheet`: processes `TimeSheetEvents` — matches by `JobNumber == task.df_gd_name` and `Type == 5` (Work)
   - `postcalculation`: processes `PostCalculationEvents` — matches by `CostCenter == task.df_gd_name`
3. Creates timesheet lines with start/end times and event type codes

#### Stage Change Handling (`_check_and_update_geo_by_stage()`)

When a task moves to a completion stage (`df_is_completion_stage == True`) and has a POI:
- Deletes the POI from Geodynamics via `DELETE /api/v1/poi`
- Clears the `df_geodynamics_poi_id` field

#### `addPointOfTask()` — Create POI from Task

Creates a POI in Geodynamics using:
- **Name**: Task name (max 50 chars)
- **Code**: `{task_name}-[{task_id}]` (max 500 chars)
- **Description**: URL to the task in Odoo
- **Address**: From shipping partner on sale order, or from project partner
- **POI Type**: First available `df.geodynamics.poitype`

---

## 11. Geodynamics Planning

**Model:** `df.geodynamics.planning`
**File:** `models/gdplanning.py`
**View:** `views/gd_planning.xml`
**Menu:** Geodynamics > Planningen

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `start_datetime` | Datetime | Yes | Planning start time |
| `end_datetime` | Datetime | Yes | Planning end time |
| `id_geodynamics` | Char | Yes | External planning ID in Geodynamics (unique) |
| `user_id_geodynamics` | Char | | External Geodynamics user ID |
| `task_id` | Many2one → `project.task` | | Linked Odoo task |
| `project_id` | Many2one → `project.project` | | Linked Odoo project |
| `employee_id` | Many2one → `hr.employee` | | Linked employee |
| `user_id` | Many2one → `res.users` | | Linked Odoo user |
| `activitynumber` | Char | | Activity number (usually the task/project name) |
| `description` | Char | | Description text |

### Computed Fields

| Field | Description |
|-------|-------------|
| `display_name` | Format: `"Employee Name - DD/MM HH:MM -> DD/MM HH:MM (Task Name)"` (adjusted +2 hours for display) |
| `display_name_with_task` | Format: `"[Task Name] Employee Name - DD/MM HH:MM->DD/MM HH:MM"` |

### Actions

**Verwijder planning** (`removePlanning`):
1. Calls `DELETE /api/v2/planning/{id_geodynamics}` on the API
2. Deletes the local Odoo record

---

## 12. Geodynamics Clocking Records

**Model:** `geodynamics.clocking`
**File:** `models/geodynamics_clocking.py`
**View:** `views/geodynamics_clocking_views.xml`
**Menu:** Geodynamics > Clockings

### Purpose

Stores individual clocking (time registration) records fetched from the Geodynamics API. Each record represents a single event (start work, stop work, start break, etc.).

### Fields

| Field | Type | Index | Description |
|-------|------|-------|-------------|
| `external_id` | Char | Yes | Unique external ID from API (`Id` field). SQL unique constraint. |
| `date_local` | Datetime | Yes | Local timestamp (`DateTimeLocal` from API) |
| `date_utc` | Datetime | Yes | UTC timestamp (`DateTimeUtc` from API) |
| `stop_date_local` | Datetime | Yes | Stop timestamp local (for start-type activities) |
| `stop_date_utc` | Datetime | Yes | Stop timestamp UTC |
| `type` | Integer | | Clocking type code (1=Start work, 2=Stop work, 3=Start activity, etc.) |
| `type_label` | Char | | Human-readable type label |
| `job_number` | Char | | Job/activity number (e.g., `S01117 - Project Name`) |
| `project_code` | Char | Yes | Computed: extracted `S\d{5}` pattern from job_number |
| `description` | Text | | Clocking description |
| `note` | Text | | Additional notes |
| `is_manual` | Boolean | | Whether manually entered |
| `woon_werk` | Boolean | | Commute flag (set by cron for first/last Movement Drive per day) |
| `movement_time_minutes` | Integer | | Activity duration in minutes (computed by cron) |
| `movement_time_hours` | Float | | Activity duration in hours (computed by cron) |
| `movement_distance` | Float | | Movement distance in km (computed from Location Status API) |
| `pause_hours` | Float | | Break time in hours |
| `absence_code` | Char | | Absence code |
| `external_code` | Char | | External code |
| `external_type` | Char | | External type |
| `location` | Json | | Full Location payload from API |
| `pois` | Json | | Full Pois payload from API |
| `user` | Json | | Full User payload from API |
| `user_id_geodynamics` | Char | Yes | External Geodynamics user ID (from `User.Id`) |
| `vehicle` | Json | | Full Vehicle payload from API |
| `vehicle_code` | Char | Yes | Vehicle code (from `Vehicle.Code`) |
| `raw_payload` | Json | | Complete raw API response for this record |
| `project_id` | Many2one → `project.project` | | Linked Odoo project |
| `employee_id` | Many2one → `hr.employee` | | Linked employee |
| `timesheet_line_id` | Many2one → `account.analytic.line` | Yes | Linked timesheet line |
| `need_to_check` | Boolean | Yes | Flag for time discrepancy review |

### Key Methods

#### `create_from_raw(raw, project=None, employee=None)`

Creates or updates a clocking record from a raw API dict:
- Extracts all fields from the dict using both camelCase and PascalCase keys
- Parses datetime strings (ISO 8601 with timezone support)
- Auto-links employee by matching `User.Id` against `hr.employee.df_geodynamics_id`
- Upserts based on `external_id` (updates if exists, creates if new)

#### `_parse_iso_dt(s, assume_utc_if_naive=False)`

Robust ISO datetime parser:
- Handles `Z`, `+02:00`, and naive datetime strings
- Converts timezone-aware datetimes to naive UTC
- Falls back to multiple format patterns

#### `_compute_project_code()`

Stored computed field that extracts the first `S\d{5}` pattern from `job_number`.

### View

**List view**: Shows external_id, dates, woon_werk, movement times, job number, project code, type label, employee, vehicle code, project. Decoration: warning when `need_to_check == True`.

**Form view**: Full detail with JSON widgets for location, user, vehicle, and raw payload.

**Search view**: Filter by date, employee, user ID, vehicle code. Default filter: yesterday. Group by: date local, date UTC, employee, user ID, vehicle code.

---

## 13. Clocking Error Detection

**Model:** `geodynamics.clocking.possible.error`
**File:** `models/geodynamics_clocking_error.py`
**View:** `views/geodynamics_clocking_error_views.xml`
**Menu:** Geodynamics > Clocking Errors

### Purpose

Automatically detects and tracks time tracking anomalies between employees working on the same project on the same day.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | Char (computed, stored) | Format: `"PROJECT_CODE - DATE"` |
| `message` | Char | Default: "Personen hebben afwijkende werktijd registratie" |
| `error_date` | Date | Date of the anomaly |
| `project_code` | Char | Project code (S-code) |
| `employee_details` | Text | Formatted text showing each employee's name and hours/minutes |
| `status` | Selection | `to_check` / `approved` / `fixed` / `ignore` |
| `clocking_ids` | Many2many → `geodynamics.clocking` | Related clocking records |

### SQL Constraint

One error record per project per day: `UNIQUE(error_date, project_code)`

### Detection Logic (in `geodynamics_cron._check_time_discrepancies()`):

1. Fetch all clockings for the date with `project_code != False` and `movement_time_minutes > 0`
2. Group by `project_code`
3. For each project, group by employee and sum total minutes
4. If there are 2+ employees and `(max_time - min_time) / max_time > 5%`:
   - Mark all related clockings with `need_to_check = True`
   - Create/update an error record
5. If difference <= 5%: clear `need_to_check` flags and remove error record

### Actions

**View Day Clockings** (`action_view_day_clockings`):
Opens a list of all clockings for the affected employees on the error date, automatically grouped by employee.

---

## 14. Timesheet Line Extensions

**Model:** `account.analytic.line` (inherits)
**Files:** `models/account_analytic.py`, `models/account_analytic_line.py`
**Views:** `views/task.xml`, `views/account_analytic_line_views.xml`

### Fields from `account_analytic.py`

| Field | Type | Description |
|-------|------|-------------|
| `df_start_time` | Datetime | Precise start time for the timesheet interval |
| `df_end_time` | Datetime | Precise end time for the timesheet interval |
| `df_gd_type` | Selection (0-9) | Geodynamics event type: Absence, Activity, Allowance, Break, Movement, Work, Error, Unpaid, TravelTime, External |
| `df_gd_eventtype` | Selection (0-13) | Detailed event type: Absence paid, Absence unpaid, Activity, Break, Movement driver/passenger/single, Work, Load/Unload, Travel time, External, Unpaid, Allowance, Error |

### Fields from `account_analytic_line.py`

| Field | Type | Description |
|-------|------|-------------|
| `timesheet_type` | Selection | Entry classification: `work` (Werkuren), `drive` (Onderweg), `drive_work` (Werkverplaatsing), `break` (In pauze). Default: `work`. |
| `geodynamics_clocking_ids` | One2many → `geodynamics.clocking` | Clockings linked to this timesheet line (via `timesheet_line_id`) |
| `gd_purchase_cost` | Monetary (computed, stored) | Total purchase cost from linked clockings (currently 0, prepared for future) |
| `gd_employer_cost` | Monetary (computed, stored) | Total employer cost |
| `gd_backoffice_cost` | Monetary (computed, stored) | Total backoffice cost |
| `gd_total_cost` | Monetary (computed, stored) | Total cost |
| `gd_sales_price` | Monetary (computed, stored) | Total sales price |
| `gd_margin` | Monetary (computed, stored) | Total margin (sales - cost) |
| `gd_margin_percentage` | Float (computed, stored) | Margin as percentage |
| `gd_clocking_count` | Integer (computed) | Count of linked clockings |

### View Extensions

1. **Task timesheet page**: Adds df_start_time, df_end_time, df_gd_type, df_gd_eventtype columns (optional show/hide)
2. **Timesheet user list**: Adds `timesheet_type` (column invisible) and `df_start_time` as daterange widget showing start-end
3. **Timesheet grid (manager)**: Adds `timesheet_type` as row, `df_start_time`/`df_end_time` as invisible rows
4. **Timesheet tree (costs)**: Adds clocking count, total cost, sales price, margin columns with sum totals and clockings button (view inactive by default)
5. **Timesheet form (costs)**: Adds "View Clockings" button in header and a Geodynamics Costs notebook page with cost breakdown and linked clockings list (view inactive by default)

### Actions

**View Geodynamics Clockings** (`action_view_geodynamics_clockings`):
Opens list/form view of all `geodynamics.clocking` records linked to this timesheet line.

---

## 15. Timesheets Analysis Report

**Model:** `timesheets.analysis.report` (inherits)
**File:** `models/timesheets_analysis_report.py`
**View:** `views/timesheets_analysis_report_views.xml`

### Extensions

| Field | Type | Description |
|-------|------|-------------|
| `df_start_time` | Datetime | Start time from the underlying `account.analytic.line` |
| `df_end_time` | Datetime | End time from the underlying `account.analytic.line` |

The `_select()` method is extended to include `A.df_start_time` and `A.df_end_time` in the SQL view.

### View Extension

Adds to the timesheet analysis list view (after `unit_amount`):
- `df_start_time` (optional hide)
- `df_end_time` (optional hide)
- **Open Line** button: navigates to the source `account.analytic.line` form view

---

## 16. Cron Jobs & Scheduled Tasks

**Model:** `geodynamics.cron`
**File:** `models/geodynamics_cron.py`
**Cron Definition:** `data/ir_cron_geodynamics.xml`

### Scheduled Cron

| Cron | Schedule | Description |
|------|----------|-------------|
| **Geodynamics: fetch yesterday clockings** | Daily at 07:00 UTC | Calls `cron_fetch_yesterday_clockings()` |

### Key Methods

#### `cron_fetch_yesterday_clockings()`

Entry point for the daily cron. Calculates yesterday's date and calls `fetch_clockings_by_date()`.

#### `fetch_clockings_by_date(target_date)`

Full daily synchronization pipeline:

1. **Fetch from API**: `GET /api/v1/clocking_getbydaterange` for the full day (00:00:00 to 23:59:59)
2. **Group by (User.Id, date)** using local datetime
3. **Per group processing**:
   - **Woon-werk marking**: For Type==12 (Movement Drive) records, marks the first and last as `woon_werk=True` (only for vehicles with allowed codes)
   - **Activity duration computation**: For each start-type record, finds the next end-type or start-type to compute duration in minutes/hours. Sets `movement_time_minutes`, `movement_time_hours`, `Stop`, `StopDateTimeLocal`
   - **Movement distance computation** (`_compute_movement_distance_for_type12()`): Calls `GET /api/v1/location/status` for each vehicle, finds overlapping bars, sums `MileageDriven`
   - **Break time computation** (`_compute_break_time_for_type5()`): Computes pause/break durations
4. **Persist all records**: Calls `geodynamics.clocking.create_from_raw()` for each record
5. **Project assignment** (`_assign_projects_for_date()`):
   - Matches clockings to projects using job code and POI logic
   - Per-day carry-forward within same employee/day group
   - Consolidation: propagates most common project to unassigned clockings in the same group
   - Fallback: inherits project from previous day for the same employee
6. **Trigger project fetchClockings**: For each project that received clockings, calls `project.fetchClockings()` to update timesheets
7. **Time discrepancy check** (`_check_time_discrepancies()`): Detects >5% time differences between employees

#### `backfill_movement_for_date_range(start_date, end_date=None)`

Manual backfill utility for historical data:
- Re-processes existing `geodynamics.clocking` records for a date range
- Recomputes: woon_werk flags, activity durations, movement distances, break times
- Does not re-fetch from API; works on already-persisted records

#### Helper Methods

| Method | Description |
|--------|-------------|
| `_get_credentials()` | Reads API credentials from `ir.config_parameter` |
| `_get_woon_werk_vehicle_codes()` | Gets allowed vehicle codes from settings |
| `_is_vehicle_allowed_for_woon_werk(vehicle_data)` | Checks if vehicle code is in allowed list |
| `_compute_movement_distance_for_type12()` | Computes km driven using Location Status API bars |
| `_compute_break_time_for_type5()` | Computes break durations |
| `_assign_projects_for_date()` | Links clockings to projects using job code/POI matching |

---

## 17. Synchronization Wizard

**Model:** `geodynamics.synch.wizard` (TransientModel)
**File:** `wizard/geodynamics_synch_wizard.py`
**View:** `views/geodynamics_synch_wizard_views.xml`
**Menu:** Geodynamics > Synchronize Clockings

### Purpose

Provides a user-friendly wizard for manually synchronizing clockings over a date range, useful for initial setup or catching up on missed days.

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `date_from` | Date | 7 days ago | Start date of sync range |
| `date_to` | Date | Today | End date of sync range |

### Action (`action_sync()`)

1. Validates `date_from <= date_to`
2. Iterates through each day in the range
3. Calls `geodynamics.cron.fetch_clockings_by_date()` for each day
4. Tracks success/failure counts per day
5. Shows a sticky notification with results:
   - Period synced
   - Total days processed
   - Successfully synced count
   - Failed days (if any)

---

## 18. REST API Controller

**File:** `controllers/controllers.py`

### Endpoints

All endpoints require user authentication (`auth='user'`).

#### `GET /api/geodynamics/employee/profile`

Returns the current user's profile and linked employee information.

**Response fields:**
- `user`: id, name, login, email, partner_id
- `employee`: id, name, work_email, work_phone, mobile_phone, job_title, department, geodynamics_id

**Employee lookup**: Searches by `user_id`, `user_partner_id`, or `work_contact_id`.

#### `GET /api/geodynamics/employee/daily_summary`

Returns daily time tracking summary for the current user's employee.

**Query parameters:**
- `start_date` (optional): Format `YYYY-MM-DD`. Default: 30 days ago
- `end_date` (optional): Format `YYYY-MM-DD`. Default: today

**Response structure:**
```json
{
  "success": true,
  "employee_id": 1,
  "employee_name": "John Doe",
  "data": [
    {
      "date": "2025-01-15",
      "total_hours": 8.5,
      "worked_total": 7.0,
      "hours_driving_total": 1.0,
      "hours_pause": 0.5,
      "total_km_driven": 45.0
    }
  ]
}
```

**Categorization logic:**
- If `type_label` contains "drive", "driving", or "rijden" → `hours_driving_total`
- If `type_label` contains "pause", "break", or "pauze" → `hours_pause`
- Everything else → `worked_total`
- All categories contribute to `total_hours`
- `total_km_driven` from `movement_distance`

---

## 19. GeodynamicsHandler (API Client)

**File:** `models/gdhandler.py`

The central API communication class. All HTTP calls to the Geodynamics API go through this handler.

### Constructor

```python
GeodynamicsHandler(gd_login, gd_password, gd_company, environ)
```
- Sets base URL to `https://api.intellitracer.be/api/v2`
- Creates `HTTPBasicAuth` with format `login|company:password`

### API Methods

| Method | HTTP | API Endpoint | Description |
|--------|------|-------------|-------------|
| `test()` | GET | `/api/v2/user` | Test connectivity |
| `getClockingsByUserDateRange(userId, from, to)` | GET | `/api/v1/Clocking_GetByUserIdDateRange` | Fetch clockings for one user in date range |
| `getClockingsByDateRange(from, to)` | GET | `/api/v1/clocking_getbydaterange` | Fetch all clockings in date range |
| `createPlanning(userId, from, to, activityNumber, poiId)` | PUT | `/api/v3/planning` | Create a planning entry. Deletes existing plannings for user in range first. |
| `removePlanning(planningId)` | DELETE | `/api/v2/planning/{id}` | Delete a single planning |
| `deletePlanningUser(userId, from, to)` | DELETE | `/api/v1/byuseriddaterange` | Delete all plannings for user in date range |
| `laadPlanning(userId, from, to)` | GET | `/api/v1/byuseriddaterange` | Load plannings for a user |
| `laadAllPlanning()` | Multiple GET | `/api/v1/byuseriddaterange` | Load all plannings for all employees in 30-day chunks |
| `laadPoiTypes()` | GET | `/api/v1/poitype` | Import POI types |
| `addPoi(contact)` | PUT | `/api/v1/poi` | Create POI from contact address |
| `addPoiFromTask(task)` | PUT | `/api/v1/poi` | Create POI from task (with URL in description) |
| `addPoiData(poiData)` | PUT | `/api/v1/poi` | Create POI from raw dict |
| `deletePoi(poiId)` | DELETE | `/api/v1/poi` | Delete POI by ID |
| `laadPostcalc(userId, date)` | POST | `/api/v2/postcalculation/export` | Fetch post-calculation events |
| `getLocationsByResourcesAndDate(ids, day)` | POST | `/api/v1/location/position` | Fetch positions for resources |
| `getLocationStatus(resourceId, from, to)` | GET | `/api/v1/location/status` | Fetch location status timeline |
| `getResourceMileage(resourceId, from, to)` | GET | `/api/v1/location/status` | Sum `MileageDriven` km + driving hours from status Bars (30-day chunks) |

### Planning Methods

| Method | Description |
|--------|-------------|
| `createPlanningByTask(task)` | Creates planning for all assigned users on the task |
| `createPlanningByTaskWn(task)` | Creates planning for all employees, splits into workdays, handles POI |
| `removePlanning_emp(taskId, empId)` | Removes planning for specific employee on task |
| `removePlanning_task(task)` | Removes all plannings for task |
| `deletePlanning(record)` | Removes plannings for employees no longer assigned |
| `split_into_workdays(start, end)` | Splits datetime range into workday periods (6:00-15:00, Mon-Fri, excluding holidays) |
| `isWeekendOrHoliday(date)` | Checks if date is weekend or holiday |

### Clocking Type Constants

```python
CLOCKING_TYPE_MAP = {
    1: 'Start work',      2: 'Stop work',
    3: 'Start activity',  4: 'Stop activity',
    5: 'Start break',     6: 'Stop break',
    12: 'Start movement driver',
    13: 'Start movement passenger',
    14: 'Stop movement',
    19: 'Start travel time', 20: 'Stop travel time'
}

ACTIVITY_START_TYPES = {1, 3, 12, 19}
ACTIVITY_END_TYPES = {2, 4, 5, 6, 14, 20}
```

### Duration Computation (`compute_clocking_activity_durations()`)

Computes active duration from raw clocking records:
- Start types open a period, end types close it
- If a new start occurs before an end, the previous start is discarded (same-day dedup)
- Returns: `{ intervals: [...], total_minutes: n, total_hours: n.nn }`

### Utility Methods

| Method | Description |
|--------|-------------|
| `convert_to_utc(dt)` | Formats datetime as `YYYY-MM-DDTHH:MM:SS` |
| `convert_to_datetime(s)` | Parses `YYYY-MM-DDTHH:MM:SS` string to datetime |
| `sleep()` | Sleeps 100ms between API calls |
| `subtract_two_hours(dt)` | Subtracts 2 hours from datetime (timezone offset utility) |
| `_parse_input_dt(value)` | Parses datetime input (string or datetime) with validation |
| `_parse_input_date(value)` | Parses date input with validation |
| `_annotate_clocking_records(records)` | Adds human-readable `TypeLabel` to clocking dicts |
| `_extract_clock_dt(rec)` | Extracts datetime from clocking record (priority: DateTimeLocal, then fallbacks) |

---

## 20. Menu Structure

```
Project
└── Configuration
    └── Geodynamics (menu_geodynamics_root)
        ├── Settings (geodynamics_config_settings_action)
        ├── Planningen (action_df_geodynamics)
        ├── Synchronize Clockings (action_geodynamics_synch_wizard)
        ├── Clockings (action_geodynamics_clocking)
        └── Clocking Errors (action_geodynamics_clocking_error)

HR
└── Configuration
    └── Timesheet Groups (action_employee_timesheet_group)
```

---

## 21. Data Flow

```
                    Geodynamics API (api.intellitracer.be)
                              │
              ┌───────────────┼───────────────┐
              │               │               │
         Clockings API    Planning API     POI API
              │               │               │
              ▼               ▼               ▼
     GeodynamicsHandler (gdhandler.py)
              │
    ┌─────────┼─────────┬─────────────────┐
    │         │         │                 │
    ▼         ▼         ▼                 ▼
geodynamics  df.geodynamics  df.geodynamics  res.partner
 .clocking    .planning       .poitype       (poi_id)
    │
    ├──────────────────────────┐
    │                          │
    ▼                          ▼
account.analytic.line    geodynamics.clocking
(timesheets)             .possible.error
    │
    ▼
project.task
("Registratie Geodynamics")
    │
    ▼
project.project
```

### Sync Flow: Daily Cron

1. **07:00 UTC**: `cron_fetch_yesterday_clockings()` triggers
2. **Fetch**: All clockings from API for yesterday
3. **Enrich**: Compute woon_werk, activity durations, movement distances, break times
4. **Persist**: Create/update `geodynamics.clocking` records
5. **Assign projects**: Match clockings to projects via job codes and POIs
6. **Update timesheets**: Trigger `project.fetchClockings()` for affected projects
7. **Check discrepancies**: Detect time differences between employees

### Sync Flow: Manual (Project)

1. User clicks "Laad clockings" on project form
2. `project.fetchClockings()` is called
3. For each employee: fetch clockings from API in 30-day chunks
4. Filter by job codes and POIs
5. Compute intervals and create/update timesheet lines
6. Apply extra time rules
7. Clean up redundant lines

---

## 22. Key Business Logic

### Job Code Matching

- **Extraction**: Project names contain job codes matching pattern `S\d{5}` (e.g., S01117, S00577)
- **Normalization**: `JobNumber` values like `"S01117 - Project Name"` are normalized to `"S01117"` (take prefix before ` - `, uppercase)
- **Filtering rules** (in `_filter_clockings_with_job_codes()`):
  1. Only start-type clockings are evaluated for acceptance
  2. A start is accepted if its token matches a project job code OR its POI matches the project
  3. **Per-day carry-forward**: Within the same day, if a valid token was seen earlier, it carries to tokenless starts
  4. **Retro-accept**: When a provider (token or POI) appears later in a day, all earlier tokenless starts on that same day are retroactively accepted
  5. **No cross-day carry**: Tokens do NOT carry across day boundaries
  6. Stop-type clockings are accepted only when there's an open (accepted) start

### Woon-Werk (Commute) Detection

1. Configured via `geodynamics.woon_werk_vehicle_codes` setting
2. During cron processing, Type==12 (Movement Drive) records are identified
3. Only vehicles with codes in the allowed list are considered
4. The **first** and **last** allowed Movement Drive records per employee per day are flagged as `woon_werk = True`
5. Empty vehicle code list = all vehicles allowed

### Movement Distance Calculation

1. For each Type==12 (Movement Drive) record:
2. Call `GET /api/v1/location/status` for the vehicle on that day
3. Parse `StatusResults[].Bars[]` to find bars overlapping with the movement's start/stop time
4. Sum `MileageDriven` values from overlapping bars
5. Store as `movement_distance` on the clocking record

### Odometer Sync (fleet.vehicle.odometer)

Logs vehicle kilometers from Geodynamics into the standard Odoo fleet odometer:

1. For each `fleet.vehicle` linked via `df_geodynamics_id`:
2. Fetch `GET /api/v1/vehicle` and try to read a **total km counter** from the raw payload (candidate keys: `Mileage`, `Odometer`, `Kilometers`, … — checked top-level and one nested dict deep); running hours (`RunningHours`, `OperatingHours`, …) go to `df_gd_running_hours`
3. **Fallback** when no counter exists in the payload: `getResourceMileage()` reads `location/status` Bars since the last sync (`df_gd_odometer_last_sync`). Absolute odometer counters on the Bars (`MileageStop`, `MileageStart`, `Odometer`, …) win — they match the vehicle total shown in Geodynamics; otherwise the summed `MileageDriven` is added to the last logged odometer value
4. A `fleet.vehicle.odometer` record is created for today (updated in place on re-sync the same day; values are converted to miles when the vehicle's odometer unit is miles; a value lower than the last log is never written; **zero-value records are ignored entirely** — a manual `0,00` entry neither blocks the sync nor counts as a starting value)

Triggers: form/list button on the vehicle ("Sync Odometer from Geodynamics"), the "Sync Odometers Now" button in Settings, or the daily cron `Geodynamics: sync vehicle odometers` (gated by `geodynamics.auto_sync_odometer`).

### Workday Splitting

When creating plannings, work is split into standard workday periods:
- **Work hours**: 06:00 to 15:00
- **Working days**: Monday through Friday
- **Holidays**: Configurable (currently only Christmas 2025 as example)
- Multi-day tasks are split into individual workday periods

### Project Assignment (Cron)

After persisting clockings, the cron assigns projects using multiple strategies:
1. **Direct match**: Job code token matches a project's extracted codes
2. **POI match**: Clocking's POI list matches a project's task POIs
3. **Consolidation**: Within an employee/day group, propagate the most common project to unassigned clockings
4. **Previous day fallback**: If no project found, inherit from previous day's clockings for the same employee

### Error Detection

- After each sync, the system checks for time discrepancies
- Groups clockings by project code and date
- For projects with 2+ employees: calculates `(max - min) / max * 100`
- If > 5%: creates/updates a `geodynamics.clocking.possible.error` record
- If <= 5%: removes any existing error record for that project/date

---

## 23. Geodynamics External API Endpoints Used

### Clockings

| Method | Endpoint | Usage |
|--------|----------|-------|
| GET | `/api/v1/Clocking_GetByUserIdDateRange?userId=&fromDate=&toDate=` | Fetch clockings for specific user |
| GET | `/api/v1/clocking_getbydaterange?fromDate=&toDate=&includeClockingsWithoutUser=` | Fetch all clockings in range |

### Planning

| Method | Endpoint | Usage |
|--------|----------|-------|
| PUT | `/api/v3/planning` | Create planning |
| DELETE | `/api/v2/planning/{id}` | Delete specific planning |
| GET | `/api/v1/byuseriddaterange?userId=&fromDate=&toDate=` | Load plannings for user |
| DELETE | `/api/v1/byuseriddaterange?userId=&fromDate=&toDate=` | Delete plannings for user in range |

### POI

| Method | Endpoint | Usage |
|--------|----------|-------|
| PUT | `/api/v1/poi` | Create POI |
| DELETE | `/api/v1/poi` | Delete POI (body: `{Id: poiId}`) |
| GET | `/api/v1/poitype` | List all POI types |

### Location

| Method | Endpoint | Usage |
|--------|----------|-------|
| POST | `/api/v1/location/position?from=&to=` | Fetch positions for resources (body: array of GUIDs) |
| GET | `/api/v1/location/status?resourceId=&from=&to=` | Fetch location status timeline for resource |

### Post-Calculation

| Method | Endpoint | Usage |
|--------|----------|-------|
| POST | `/api/v2/postcalculation/export` | Fetch post-calculation events |

### Users / Connectivity

| Method | Endpoint | Usage |
|--------|----------|-------|
| GET | `/api/v2/user` | Test connection / list users |

---

## 24. Project Stage Integration

**Model:** `project.task.type` (inherits)
**File:** `models/project_stage.py`
**View:** `views/project.xml`

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `df_is_completion_stage` | Boolean | False | Marks this stage as a completion stage. When a task moves to this stage, its POI is deleted from Geodynamics. |

### View

Adds the `df_is_completion_stage` field after the `name` field in the task type (stage) form view.

---

## 25. Security

**File:** `security/ir.model.access.csv`

Defines access control for custom models:
- `geodynamics.geodynamics`
- `df.geodynamics.planning`
- `df.geodynamics.poitype`
- `employee.timesheet.group`
- `geodynamics.clocking`
- `geodynamics.clocking.possible.error`
- `geodynamics.cron`
- `geodynamics.synch.wizard`
