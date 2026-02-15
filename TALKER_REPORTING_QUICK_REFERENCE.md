# Talker Reporting System - Quick Reference

## Single API Endpoint

### Report a Talker
```
POST /api/listener/profiles/report-talker/
Authorization: Bearer LISTENER_TOKEN
Content-Type: application/json

{
  "talker_id": 10,
  "reason": "harassment",
  "description": "Detailed reason here (optional)"
}
```

**Possible Reasons**:
- `harassment` - Harassment or Abuse
- `inappropriate_content` - Inappropriate Content
- `scam` - Scam or Fraud
- `hate_speech` - Hate Speech
- `threatening` - Threatening Behavior
- `fake_profile` - Fake Profile
- `other` - Other

---

## Response Status Codes

### 201 Created - Report Submitted
```json
{
  "message": "Report submitted successfully",
  "total_reports_for_talker": 1,
  "suspension_triggered": false
}
```

### 201 Created - Suspension Triggered (3+ Reports)
```json
{
  "message": "Report submitted. Talker account suspended for 7 days due to 3 reports.",
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

### 400 Bad Request
- Duplicate report: "You have already reported this talker for this reason"
- Missing fields: Field validation errors
- Invalid talker ID

### 401 Unauthorized
- Missing authentication token
- Invalid token

### 403 Forbidden
- User is not a listener

### 404 Not Found
- Talker with given ID doesn't exist

---

## Suspension System

### When Suspension Activates
- **Trigger**: 3 or more reports on same talker
- **Automatic**: No manual approval needed
- **Immediate**: Takes effect right away

### What Happens to Talker
1. ✅ Automatically logged out from all devices
2. ✅ All auth tokens deleted
3. ✅ All sessions terminated
4. ✅ Cannot login for 7 days

### Talker Login During Suspension
```
POST /api/users/login/

Response (403 Forbidden):
{
  "error": "Account suspended",
  "message": "Your account is suspended and will be available again in 5 days.",
  "suspension_details": {
    "remaining_days": 5,
    "suspended_at": "2026-02-08T15:45:00Z",
    "resume_at": "2026-02-15T15:45:00Z"
  }
}
```

### After Suspension Ends
- After 7 days, account automatically becomes available
- Talker can login with normal credentials
- No manual unsuspension needed

---

## Testing Quick Steps

### 1. First Report (Use Listener 1)
```bash
curl -X POST "http://localhost:8000/api/listener/profiles/report-talker/" \
  -H "Authorization: Bearer LISTENER_TOKEN_1" \
  -d '{"talker_id": 5, "reason": "harassment"}'
```
Expected: `"suspension_triggered": false`

### 2. Second Report (Use Listener 2)
```bash
curl -X POST "http://localhost:8000/api/listener/profiles/report-talker/" \
  -H "Authorization: Bearer LISTENER_TOKEN_2" \
  -d '{"talker_id": 5, "reason": "scam"}'
```
Expected: `"suspension_triggered": false`

### 3. Third Report - Suspension! (Use Listener 3)
```bash
curl -X POST "http://localhost:8000/api/listener/profiles/report-talker/" \
  -H "Authorization: Bearer LISTENER_TOKEN_3" \
  -d '{"talker_id": 5, "reason": "inappropriate_content"}'
```
Expected: `"suspension_triggered": true` + `"message": "...suspended for 7 days..."`

### 4. Verify Suspension - Try Talker Login
```bash
curl -X POST "http://localhost:8000/api/users/login/" \
  -d '{"email": "talker@example.com", "password": "password"}'
```
Expected: **403** error with remaining days message

---

## Database Tables

### TalkerReport
- Stores each report submission
- Fields: talker, reporter, reason, description, status, created_at

### TalkerSuspension
- Tracks active suspensions
- Fields: talker, reason, suspended_at, resume_at, is_active, days_suspended

---

## Rules

1. **Multiple Listeners**: Reports from different listeners all count toward the 3-report limit
2. **Same Reason Limit**: Listener cannot report same talker for same reason twice
3. **Different Reasons OK**: Same listener can report same talker for different reasons
4. **Auto-Logout**: Happens immediately, talker doesn't get warning
5. **Time-based Release**: After 7 days, account automatically available (no action needed)

---

## Error Messages to Expect

| Scenario | Error |
|----------|-------|
| Duplicate report | "You have already reported this talker for this reason" |
| Talker doesn't exist | "Talker with ID {id} not found" |
| Not a listener | "Only listeners can report talkers" |
| Suspended login | "Account suspended - {X} days remaining" |
| Missing fields | "This field is required" |
| Unauthorized | "Authentication credentials were not provided" |

---

## Key Points

✅ **Single Endpoint**: One API for all reporting
✅ **Auto-Suspension**: At 3 reports, automatic 7-day suspension
✅ **Immediate Logout**: All devices logged out instantly
✅ **Login Blocked**: Cannot login during 7-day period
✅ **Shows Days**: Error message displays remaining suspension days
✅ **Auto-Release**: After 7 days, can login normally
✅ **Reports Tracked**: All reports stored for admin review
✅ **Duplicate Prevention**: Can't report same reason twice

---

## Swagger/OpenAPI

Access full documentation:
- **URL**: `http://localhost:8000/api/docs/`
- **Search for**: "report-talker" or "Listener Report Talker"
- **Also check**: "User Login" for suspension error details

