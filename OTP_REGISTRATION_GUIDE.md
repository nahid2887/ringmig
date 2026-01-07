~# OTP Email Verification Registration Guide

## Overview
The user registration system now includes OTP (One-Time Password) email verification. When a user registers, they receive a 6-digit OTP on their email. After verifying the OTP, their account is activated.

## Registration Flow

### Step 1: Request OTP
**Endpoint:** `POST /api/users/register/request-otp/`

Send the following JSON payload:
```json
{
    "email": "user@example.com",
    "full_name": "John Doe",
    "password": "SecurePassword123!",
    "password_confirm": "SecurePassword123!",
    "user_type": "talker"  // optional, defaults to "talker"
}
```

**Response (Success - 200):**
```json
{
    "message": "OTP sent successfully to your email",
    "email": "user@example.com"
}
```

**Response (Error - 400):**
```json
{
    "email": ["This field may not be blank."],
    "password": ["This password is too common."]
}
```

**Valid user_type values:** `talker` or `listener`

---

### Step 2: Verify OTP and Complete Registration
**Endpoint:** `POST /api/users/register/verify-otp/`

Once the user receives the OTP in their email, send it along with their email:
```json
{
    "email": "user@example.com",
    "otp_code": "123456"
}
```

**Response (Success - 201):**
```json
{
    "message": "User registered and verified successfully",
    "user": {
        "id": 1,
        "email": "user@example.com",
        "full_name": "John Doe",
        "user_type": "talker",
        "phone_number": "",
        "is_active": true,
        "is_verified": true,
        "created_at": "2026-01-06T10:30:00Z"
    },
    "tokens": {
        "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc...",
        "access": "eyJ0eXAiOiJKV1QiLCJhbGc..."
    }
}
```

**Response (Error - 400):**
```json
{
    "error": "Invalid OTP. Please check and try again."
}
```

---

## Key Features

### OTP Expiration
- OTP codes expire after **10 minutes**
- If the OTP expires, the user must request a new one
- Previous OTPs are automatically deleted when a new one is requested

### Security
- 6-digit random OTP codes
- Passwords stored securely using Django's password hashing
- Email-based verification prevents fake account creation

### Data Storage
- User credentials are stored in the OTP record during the request phase
- Upon verification, the user account is created with `is_verified=True`
- OTP records are deleted after successful verification

---

## Email Configuration

### Development Setup (Console Output)
The default configuration prints emails to the console:
```python
# In core/settings.py
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
```

When you request an OTP, check your Django console output to see the OTP code.

### Production Setup (Gmail SMTP)
To send real emails via Gmail:

1. **Enable 2-Factor Authentication** on your Gmail account
2. **Generate an App Password** (not your regular password)
3. **Update settings.py:**
```python
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@gmail.com'
EMAIL_HOST_PASSWORD = 'your-app-password'  # 16-character app password
DEFAULT_FROM_EMAIL = 'your-email@gmail.com'
```

### Production Setup (Other Providers)
For other email providers (SendGrid, AWS SES, etc.):
- Update `EMAIL_HOST` and `EMAIL_PORT` according to the provider
- Set credentials in `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD`
- Set `DEFAULT_FROM_EMAIL` to your verified sender email

---

## API Usage Examples

### Using cURL

**Request OTP:**
```bash
curl -X POST http://localhost:8000/api/users/register/request-otp/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "john@example.com",
    "full_name": "John Doe",
    "password": "SecurePass123!",
    "password_confirm": "SecurePass123!",
    "user_type": "talker"
  }'
```

**Verify OTP:**
```bash
curl -X POST http://localhost:8000/api/users/register/verify-otp/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "john@example.com",
    "otp_code": "123456"
  }'
```

### Using Python (requests library)

```python
import requests

# Step 1: Request OTP
otp_response = requests.post(
    'http://localhost:8000/api/users/register/request-otp/',
    json={
        "email": "john@example.com",
        "full_name": "John Doe",
        "password": "SecurePass123!",
        "password_confirm": "SecurePass123!",
        "user_type": "talker"
    }
)
print(otp_response.json())

# Step 2: Verify OTP (user enters the OTP from email)
verify_response = requests.post(
    'http://localhost:8000/api/users/register/verify-otp/',
    json={
        "email": "john@example.com",
        "otp_code": "123456"
    }
)
print(verify_response.json())

# Extract tokens for authenticated requests
tokens = verify_response.json()['tokens']
access_token = tokens['access']
```

---

## Validation Rules

### Email
- Must be a valid email format
- Must not already exist in the database
- Case-insensitive for uniqueness (user@example.com == USER@EXAMPLE.COM)

### Password
- Minimum 8 characters
- Cannot be entirely numeric
- Cannot be a common password
- Must not be too similar to the email or full_name
- Passwords must match in both fields

### Full Name
- Required, maximum 200 characters

### User Type
- Optional, defaults to "talker"
- Valid values: "talker" or "listener"

---

## Error Handling

| Error | Status | Cause | Solution |
|-------|--------|-------|----------|
| Email is already registered | 400 | Email exists in database | Use a different email |
| OTP has expired | 400 | More than 10 minutes passed | Request a new OTP |
| Invalid OTP | 400 | Wrong OTP code | Check email and try again |
| Passwords do not match | 400 | password != password_confirm | Ensure passwords match |
| Failed to send OTP email | 500 | Email service error | Check email configuration |

---

## Database Models

### User Model Changes
- Added `is_verified` field (Boolean, default=False)
- Set to `True` after successful OTP verification
- `is_active` still controls account login ability

### OTP Model
```python
class OTP(models.Model):
    email = models.EmailField()
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_verified = models.BooleanField(default=False)
    full_name = models.CharField(max_length=200)
    password = models.CharField(max_length=255)  # Hashed
    user_type = models.CharField(max_length=20)
```

---

## URLs

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/users/register/request-otp/` | POST | Request OTP for registration |
| `/api/users/register/verify-otp/` | POST | Verify OTP and create account |
| `/api/users/register/` | POST | Direct registration (original, without OTP) |
| `/api/users/login/` | POST | Login with email and password |
| `/api/users/logout/` | POST | Logout and blacklist token |
| `/api/users/profile/` | GET/PUT/PATCH | View/update user profile |
| `/api/users/change-password/` | POST | Change password |
| `/api/users/token/refresh/` | POST | Refresh JWT token |

---

## Next Steps

1. **Test the OTP flow** with the examples above
2. **Configure email** for your environment (development or production)
3. **Monitor logs** for any email sending errors
4. **Update frontend** to integrate with the new OTP endpoints
5. **Add rate limiting** to prevent OTP request abuse (optional)

