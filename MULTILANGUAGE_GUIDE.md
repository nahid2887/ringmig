# Multi-Language Support Documentation

## Overview
Ring Mig API now supports multiple languages including **English** and **Swedish**.

## Supported Languages
- **English** (`en`)
- **Swedish** (`sv`)

## Features

### 1. Language Preference Storage
- Users can set their preferred language during registration
- Users can update their language preference anytime
- Preference is stored in the user profile

### 2. Dynamic Language Selection
The API respects language preference in the following order:
1. Query parameter: `?lang=sv` or `?lang=en`
2. User's stored language preference (if authenticated)
3. Accept-Language header from browser
4. Default to English

### 3. Translated Strings
All error messages, validation messages, and responses are automatically translated based on the user's language preference.

## API Usage

### Set Language During Registration
```bash
POST /api/otp-request/
Content-Type: application/json

{
  "email": "user@example.com",
  "full_name": "John Doe",
  "password": "SecurePassword123!",
  "password_confirm": "SecurePassword123!",
  "user_type": "talker",
  "language": "sv"  # Set to Swedish
}
```

### Switch Language via Query Parameter
```bash
GET /api/user/profile/?lang=sv
Authorization: Bearer {token}
```

All responses will be in Swedish.

### Update Language Preference
```bash
PATCH /api/user/profile/
Authorization: Bearer {token}
Content-Type: application/json

{
  "language": "sv"
}
```

### Accept-Language Header
The API also respects the browser's Accept-Language header:
```
Accept-Language: sv-SE, sv;q=0.9, en;q=0.8
```

## Generating Translation Files

To add new translations or update existing ones:

### 1. Mark strings for translation in code
```python
from django.utils.translation import gettext_lazy as _

message = _("Hello, World!")
```

### 2. Extract translatable strings
```bash
cd core
python manage.py makemessages -a
```

### 3. Edit .po files in locale/ directory
- `locale/sv/LC_MESSAGES/django.po` for Swedish
- `locale/en/LC_MESSAGES/django.po` for English

### 4. Compile translations
```bash
python manage.py compilemessages
```

## Example: Swedish API Response

### Request (Swedish)
```bash
POST /api/auth/register/
Content-Type: application/json

{
  "email": "anna@example.com",
  "full_name": "Anna Andersson",
  "password": "SecurePass123!",
  "user_type": "listener",
  "language": "sv"
}
```

### Response (Swedish)
```json
{
  "success": true,
  "message": "OTP skickades framgångsrikt.",
  "user": {
    "id": 1,
    "email": "anna@example.com",
    "full_name": "Anna Andersson",
    "language": "sv"
  }
}
```

## Translation Keys

Common translation strings available:
- `Passwords do not match.` / `Lösenorden matchar inte.`
- `Email is already registered.` / `E-postadressen är redan registrerad.`
- `User not found.` / `Användare hittades inte.`
- `Invalid credentials.` / `Ogiltiga uppgifter.`
- `Password changed successfully.` / `Lösenordet ändrades framgångsrikt.`

## Adding More Languages

To add support for additional languages (e.g., German, French):

1. Update `LANGUAGES` in `core/settings.py`:
```python
LANGUAGES = [
    ('en', 'English'),
    ('sv', 'Swedish'),
    ('de', 'German'),
    ('fr', 'French'),
]
```

2. Create locale directories:
```bash
mkdir -p locale/de/LC_MESSAGES
mkdir -p locale/fr/LC_MESSAGES
```

3. Extract and translate messages:
```bash
python manage.py makemessages -l de
python manage.py makemessages -l fr
```

4. Update User model `LANGUAGE_CHOICES`

5. Compile messages

## Testing Multi-Language Support

### Test Swedish Endpoint
```bash
curl -X GET "http://87.106.74.69/api/user/profile/?lang=sv" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Test Language Preference
```bash
curl -X GET "http://87.106.74.69/swagger/" \
  -H "Accept-Language: sv-SE"
```

## Notes

- All error messages automatically adapt to user's language
- Database stores user's language preference
- Language middleware handles context switching
- Translations use Django's standard `.po` file format
- For production, run `compilemessages` to optimize performance
