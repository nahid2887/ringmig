# Listener Report Talker API Documentation

## Overview
This API allows listeners to report inappropriate behavior from talkers. When a talker receives 3 or more reports, their account is automatically suspended for 7 days with automatic logout and login prevention.

---

## Automatic Account Suspension System

### Suspension Rules
- **Trigger**: When a talker receives **3 or more reports** from listeners
- **Duration**: **7 days** of automatic suspension
- **Scope**: Reports from any/multiple listeners count toward the total

### Suspension Effects

#### For the Talker
1. **Automatic Logout**: User is immediately logged out from all sessions/devices
2. **Login Prevention**: Cannot login for 7 days
3. **Error Message**: Receives message showing remaining suspension days
4. **Auto-Unsuspend**: After 7 days, can login normally with regular credentials

#### For the Listener
1. Can continue using the platform normally
2. Report status tracked for moderation team

---

## API Endpoint

### Report a Talker
**Submit a report against a talker for inappropriate behavior**

- **URL**: `/api/listener/profiles/report-talker/`
- **Method**: `POST`
- **Authentication**: Required (Bearer Token)
- **Permission**: Must be authenticated as a listener
- **Tags**: `Listener Report Talker`

#### Request
```bash
curl -X POST "http://localhost:8000/api/listener/profiles/report-talker/" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "talker_id": 10,
    "reason": "harassment",
    "description": "The talker was very rude and abusive during the call"
  }'
```

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| talker_id | integer | ✓ | ID of the talker to report |
| reason | string | ✓ | Reason for reporting. Allowed values: |
| | | | - `harassment` - Harassment or Abuse |
| | | | - `inappropriate_content` - Inappropriate Content |
| | | | - `scam` - Scam or Fraud |
| | | | - `hate_speech` - Hate Speech |
| | | | - `threatening` - Threatening Behavior |
| | | | - `fake_profile` - Fake Profile |
| | | | - `other` - Other |
| description | string | ✗ | Detailed description of the issue (max 1000 chars) |

#### Response - Report Submitted (201 Created)
```json
{
  "message": "Report submitted successfully",
  "report": {
    "id": 1,
    "talker_id": 10,
    "talker_email": "talker@example.com",
    "reason": "harassment",
    "status": "pending",
    "created_at": "2026-02-08T15:30:00Z"
  },
  "total_reports_for_talker": 1,
  "suspension_triggered": false
}
```

#### Response - Suspension Triggered (201 Created - 3rd+ Report)
```json
{
  "message": "Report submitted. Talker account suspended for 7 days due to 3 reports.",
  "report": {
    "id": 3,
    "talker_id": 10,
    "talker_email": "talker@example.com",
    "reason": "inappropriate_content",
    "status": "pending",
    "created_at": "2026-02-08T15:45:00Z"
  },
  "total_reports_for_talker": 3,
  "suspension_triggered": true,
  "suspension_info": {
    "reason": "Multiple reports from listeners",
    "days_suspended": 7,
    "talker_will_be_logged_out": true,
    "talker_cannot_login_for_days": 7
  }
}
```

#### Response Fields - Report
| Field | Type | Description |
|-------|------|-------------|
| id | integer | Report ID |
| talker_id | integer | ID of reported talker |
| talker_email | string | Email of reported talker |
| reason | string | Report reason |
| status | string | Status: `pending` (awaiting review) |
| created_at | datetime | When report was created |

#### Response Fields - Suspension
| Field | Type | Description |
|-------|------|-------------|
| reason | string | Why suspension was triggered |
| days_suspended | integer | Number of days account is suspended (always 7) |
| talker_will_be_logged_out | boolean | Talker is being logged out immediately |
| talker_cannot_login_for_days | integer | Days until login is available |

#### Error Responses

**400 Bad Request - Duplicate Report**
```json
{
  "message": "You have already reported this talker for this reason"
}
```

**400 Bad Request - Invalid Data**
```json
{
  "talker_id": ["This field is required."],
  "reason": ["This field is required."]
}
```

**401 Unauthorized**
```json
{
  "detail": "Authentication credentials were not provided."
}
```

**403 Forbidden - Not a Listener**
```json
{
  "detail": "Only listeners can report talkers"
}
```

**404 Not Found**
```json
{
  "error": "Talker with ID 999 not found"
}
```

---

## Login Behavior for Suspended Accounts

### Suspended Account Login Attempt
When a suspended talker tries to login:

**Response (403 Forbidden)**
```json
{
  "error": "Account suspended",
  "message": "Your account is suspended and will be available again in 5 days.",
  "suspension_details": {
    "reason": "reports",
    "suspended_at": "2026-02-08T15:45:00Z",
    "resume_at": "2026-02-15T15:45:00Z",
    "remaining_days": 5,
    "days_suspended": 7
  }
}
```

### After Suspension Expires
After 7 days, the talker can login normally. The suspension is automatically marked as inactive and the user proceeds with normal login.

---

## Database Models

### TalkerReport Model
```
- id: Integer (Primary Key)
- talker: ForeignKey(User)
- reporter: ForeignKey(User) [Listener]
- reason: String (Choice field)
- description: Text
- status: String [pending, reviewed, resolved, dismissed]
- created_at: DateTime (auto)
- updated_at: DateTime (auto)
- reviewed_at: DateTime (nullable)
- reviewed_by: ForeignKey(User) [Admin]
```

### TalkerSuspension Model
```
- id: Integer (Primary Key)
- talker: OneToOneField(User)
- reason: String [reports, violation, manual]
- suspended_at: DateTime (auto)
- resume_at: DateTime
- is_active: Boolean
- days_suspended: Integer (default: 7)
- notes: Text
- created_at: DateTime (auto)
- updated_at: DateTime (auto)
```

---

## Implementation Details

### Session Management
When suspension is triggered:
1. All JWT/authentication tokens for the talker are **deleted**
2. All active HTTP sessions are **deleted**
3. Talker is immediately logged out from all devices
4. Cannot re-authenticate until suspension period ends

### Suspension Lifecycle

```
Report #1 → status: active
Report #2 → status: active
Report #3 → SUSPENSION CREATED
         → is_active = true
         → resume_at = now() + 7 days
         → talker logged out
         → talker tokens deleted

Days 1-6 → Login attempts rejected with remaining days message

Day 7+  → Suspension marked as_active = false
        → talker can login normally
```

---

## Usage Examples

### Example 1: Report for Harassment
```bash
curl -X POST "http://localhost:8000/api/listener/profiles/report-talker/" \
  -H "Authorization: Bearer token123" \
  -H "Content-Type: application/json" \
  -d '{
    "talker_id": 5,
    "reason": "harassment",
    "description": "Called me very mean names during the conversation"
  }'
```

### Example 2: Report for Scam
```bash
curl -X POST "http://localhost:8000/api/listener/profiles/report-talker/" \
  -H "Authorization: Bearer token123" \
  -H "Content-Type: application/json" \
  -d '{
    "talker_id": 8,
    "reason": "scam",
    "description": "Promised to send me something after the call but never did"
  }'
```

### Example 3: Trigger Suspension (3rd Report)
```bash
curl -X POST "http://localhost:8000/api/listener/profiles/report-talker/" \
  -H "Authorization: Bearer token123" \
  -H "Content-Type: application/json" \
  -d '{
    "talker_id": 10,
    "reason": "hate_speech",
    "description": "Used offensive language against my nationality"
  }'
```

Response will include `suspension_triggered: true`

### Example 4: Suspended User Login Attempt
```bash
curl -X POST "http://localhost:8000/api/users/login/" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "suspended_talker@example.com",
    "password": "password123"
  }'
```

Response (403):
```json
{
  "error": "Account suspended",
  "message": "Your account is suspended and will be available again in 6 days.",
  "suspension_details": {
    "remaining_days": 6,
    ...
  }
}
```

---

## Testing the System

### Test Scenario: Trigger Suspension
1. Create/use a talker account (ID: 10)
2. Use 3 different listener accounts to report the same talker
3. After 3rd report, talker account will be suspended
4. Try login with talker account → should get suspension error
5. Check remaining days in error message

### Verification Steps
1. Check TalkerReport table for 3 entries with same talker_id
2. Check TalkerSuspension table for entry with is_active=true
3. Verify talker's auth tokens are deleted
4. Verify talker's sessions are deleted

---

## Security Considerations

1. **Duplicate Prevention**: Listeners cannot report same talker for same reason twice
2. **Authentication Required**: Only logged-in listeners can report
3. **Immediate Enforcement**: Suspension takes effect immediately (auto-logout)
4. **Time-based Auto-Release**: Suspension automatically lifts after 7 days
5. **Admin Audit Trail**: All reports logged with reporter information

---

## Admin Management

### Future Admin Features (Not implemented yet)
- Manual review of reports
- Early suspension lifting
- Dismissing false reports
- Report history for each talker
- Bulk suspension management

---

## Related APIs

- [Listener Call Attempts](LISTENER_CALL_ATTEMPTS_API.md)
- [Talker Call History](TALKER_CALL_HISTORY_API.md)
- User Login/Logout APIs

---

## Error Handling

| Scenario | HTTP Status | Error Message |
|----------|-------------|---------------|
| Valid report submitted | 201 | "Report submitted successfully" |
| 3rd+ report (suspension triggered) | 201 | "Report submitted. Talker account suspended..." |
| Duplicate report | 400 | "You have already reported this talker for this reason" |
| Invalid talker_id | 404 | "Talker with ID {id} not found" |
| Missing required fields | 400 | Field validation errors |
| Not authenticated | 401 | "Authentication credentials were not provided" |
| Listener trying to report another listener | 400/403 | "Can only report talker accounts" |
| Suspended talker login attempt | 403 | "Account suspended - {remaining_days} days remaining" |

---

## Workflow Diagram

```
Listener submits report
    ↓
TalkerReport created (status: pending)
    ↓
Check total reports for talker
    ↓
    ├─ < 3 reports → Report submitted
    │
    └─ >= 3 reports → TalkerSuspension created
                   → is_active = true
                   → Delete all tokens
                   → Delete all sessions
                   → Talker logged out
                   → suspension_triggered = true

Talker attempts login
    ↓
Check for active suspension
    ↓
    ├─ Active → Reject login (403)
    │          Show remaining days
    │
    └─ Inactive/Expired → Allow login normally
                       → Auto-mark as_active = false
```
