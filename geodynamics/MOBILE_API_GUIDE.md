# Mobile API Guide - Geodynamics

## Table of Contents
1. [Introduction](#introduction)
2. [Authentication Flow](#authentication-flow)
3. [API Endpoints](#api-endpoints)
4. [Error Handling](#error-handling)
5. [Best Practices](#best-practices)

---

## Introduction

This documentation provides detailed instructions on how to integrate Geodynamics API into Mobile Apps (iOS/Android) to:
- Login with portal user accounts
- Retrieve daily work summary information
- Manage sessions and authentication

### Base URL
```
https://your-odoo-instance.com
```

---

## Authentication Flow

### Step 1: Login to Get Session

```
POST /web/session/authenticate
Content-Type: application/json
```

### Step 2: Save Session Cookie

The server will return a `session_id` cookie - you need to save and send it with all subsequent requests.

### Step 3: Call APIs with Session

Use the `session_id` cookie to authenticate API calls.

---

## API Endpoints

### 1. Login API

#### Endpoint
```
POST /web/session/authenticate
```

#### Headers
```
Content-Type: application/json
```

#### Request Body
```json
{
  "jsonrpc": "2.0",
  "params": {
    "db": "your_database_name",
    "login": "portal_user@example.com",
    "password": "user_password"
  }
}
```

**Note:** 
- `db` can be left empty `""` if the server has only 1 database
- `login` is the email or username of the portal user
- `password` is the password

#### Response Success (200 OK)
```json
{
  "jsonrpc": "2.0",
  "id": null,
  "result": {
    "uid": 123,
    "name": "Portal User Name",
    "username": "portal_user@example.com",
    "session_id": "abc123def456..."
  }
}
```

#### Response Error (200 OK with error)
```json
{
  "jsonrpc": "2.0",
  "id": null,
  "error": {
    "code": 100,
    "message": "Odoo Server Error",
    "data": {
      "name": "odoo.exceptions.AccessDenied",
      "message": "Access Denied"
    }
  }
}
```

**IMPORTANT:** Save the session_id cookie to use for subsequent API calls!

---

### 2. Employee Profile API

#### Endpoint
```
GET /api/geodynamics/employee/profile
```

#### Headers
```
Cookie: session_id=abc123def456...
```

#### Response Success
```json
{
  "success": true,
  "user": {
    "id": 123,
    "name": "John Doe",
    "login": "john.doe@example.com",
    "email": "john.doe@example.com"
  },
  "employee": {
    "id": 789,
    "name": "John Doe",
    "work_email": "john@company.com",
    "work_phone": "+32123456789",
    "job_title": "Technical Staff",
    "department": "Operations"
  }
}
```

---

### 3. Daily Summary API

#### Endpoint
```
GET /api/geodynamics/employee/daily_summary
```

#### Headers
```
Cookie: session_id=abc123def456...
```

#### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| start_date | string | No | 30 days ago | Start date (YYYY-MM-DD) |
| end_date | string | No | Today | End date (YYYY-MM-DD) |

#### Example URLs

Get data for last 30 days (default):
```
GET /api/geodynamics/employee/daily_summary
```

Get data for specific date range:
```
GET /api/geodynamics/employee/daily_summary?start_date=2024-11-01&end_date=2024-11-30
```

#### Response Success (200 OK)
```json
{
  "success": true,
  "employee_id": 123,
  "employee_name": "John Doe",
  "data": [
    {
      "date": "2024-11-01",
      "total_hours": 8.5,
      "worked_total": 7.0,
      "hours_driving_total": 1.0,
      "hours_pause": 0.5,
      "total_km_driven": 45.5
    }
  ]
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| success | boolean | true if successful, false if error |
| employee_id | integer | Employee ID |
| employee_name | string | Employee name |
| data | array | Array of daily summaries |

#### Daily Data Fields

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| date | string | - | Date (YYYY-MM-DD) |
| total_hours | float | hours | Total working hours |
| worked_total | float | hours | Hours spent working |
| hours_driving_total | float | hours | Hours spent driving |
| hours_pause | float | hours | Hours on break |
| total_km_driven | float | km | Total kilometers driven |

---

## Code Examples
## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| "Access Denied" | Wrong credentials | Check email and password |
| "No employee found" | User not linked | Admin needs to link user |
| "Invalid date format" | Wrong format | Use YYYY-MM-DD |
| 401/403 Error | Session expired | Login again |

---

## Best Practices

### Session Management
- Save session after successful login
- Check session before each API call
- Auto-refresh if session expires
- Clear session on logout

### Security
- Don't store password in plain text
- Use HTTPS (SSL/TLS)
- Encrypt sensitive data
- Implement certificate pinning

### Performance
- Cache data when possible
- Use background threads for network calls
- Implement retry logic
- Handle offline mode

---

## Complete Flow

```
1. App Launch
   - Check saved session
   - Valid session? Go to main screen
   - No session? Show login screen

2. Login
   - Call /web/session/authenticate
   - Save session_id cookie
   - Navigate to main screen

3. Load Data
   - Call /api/geodynamics/employee/daily_summary
   - Display data
   - Cache for offline use

4. Logout
   - Clear session
   - Clear cached data
   - Show login screen
```

---

## Debugging

### Test with cURL

```bash
# Login
curl -c cookies.txt -X POST https://your-instance.com/web/session/authenticate \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","params":{"db":"","login":"user@example.com","password":"pass"}}'

# Get profile
curl -b cookies.txt https://your-instance.com/api/geodynamics/employee/profile

# Get daily summary
curl -b cookies.txt "https://your-instance.com/api/geodynamics/employee/daily_summary?start_date=2024-11-01&end_date=2024-11-10"
```

---
