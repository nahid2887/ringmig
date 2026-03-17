# OAuth2 Multi-User Token Proxy Integration

## Overview

The **OAuth2 Token Proxy Endpoint** enables multi-user OAuth2 integration for Ringmig. It allows authenticated users (listeners and talkers) to obtain OAuth2 tokens from your self-hosted OAuth2 server while automatically enriching the response with user identification information.

## Problem Solved

Previously, OAuth2 integration was single-user only. Now, multiple users can:
1. Authenticate with their bearer token
2. Request OAuth2 tokens for their own context
3. Receive enriched response with their listener/talker ID
4. Use this ID for multi-user scheduling/booking operations

## API Endpoint

### URL
```
POST /api/users/oauth2/token/
```

### Authentication
**Required**: Bearer token in Authorization header

```
Authorization: Bearer <JWT_ACCESS_TOKEN>
```

The JWT token must be obtained from:
- `/api/users/login/` - Standard login endpoint
- `/api/users/token/refresh/` - Token refresh endpoint

### Request Payload

The payload is identical to standard OAuth2 token endpoint requests. Forward any OAuth2 grant type parameters:

```json
{
  "grant_type": "client_credentials",
  "client_id": "your_client_id",
  "client_secret": "your_client_secret"
}
```

Or for password grant:
```json
{
  "grant_type": "password",
  "client_id": "your_client_id",
  "client_secret": "your_client_secret",
  "username": "username",
  "password": "password"
}
```

Or for refresh token grant:
```json
{
  "grant_type": "refresh_token",
  "client_id": "your_client_id",
  "client_secret": "your_client_secret",
  "refresh_token": "existing_refresh_token"
}
```

### Response

The endpoint returns the OAuth2 token response **enriched with user information**:

```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "user_info": {
    "user_id": 123,
    "email": "listener@example.com",
    "full_name": "Jane Listener",
    "user_type": "listener",
    "listener_id": 456,
    "listener_name": "Jane L."
  }
}
```

Or for a talker user:

```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "user_info": {
    "user_id": 789,
    "email": "talker@example.com",
    "full_name": "John Talker",
    "user_type": "talker",
    "talker_id": 321,
    "talker_name": "John T."
  }
}
```

## User Information Fields

### For All Users
- `user_id` - Ringmig internal user ID
- `email` - User email address
- `full_name` - User's full name
- `user_type` - Either "listener" or "talker"

### For Listener Users
- `listener_id` - Listener profile ID
- `listener_name` - Listener's display name

### For Talker Users
- `talker_id` - Talker profile ID
- `talker_name` - Talker's display name

## Configuration

Add to your `.env` file:

```bash
# OAuth2 Token Endpoint
OAUTH2_TOKEN_ENDPOINT=http://10.10.13.24:80/v2/auth/oauth2/token
```

Or configure in `core/settings.py`:

```python
OAUTH2_TOKEN_ENDPOINT = os.getenv(
    'OAUTH2_TOKEN_ENDPOINT', 
    'http://10.10.13.24:80/v2/auth/oauth2/token'
)
```

## Usage Examples

### Example 1: Python with requests library

```python
import requests

# Step 1: Get JWT bearer token from Ringmig login
login_response = requests.post(
    'http://localhost:8000/api/users/login/',
    json={
        'email': 'talker@example.com',
        'password': 'password123'
    }
)
bearer_token = login_response.json()['access']

# Step 2: Use bearer token to get OAuth2 token with user info
oauth2_response = requests.post(
    'http://localhost:8000/api/users/oauth2/token/',
    headers={
        'Authorization': f'Bearer {bearer_token}',
        'Content-Type': 'application/x-www-form-urlencoded'
    },
    data={
        'grant_type': 'client_credentials',
        'client_id': 'cal.com_client_id',
        'client_secret': 'cal.com_client_secret'
    }
)

data = oauth2_response.json()
print(f"OAuth2 Token: {data['access_token']}")
print(f"User Type: {data['user_info']['user_type']}")
print(f"Talker ID: {data['user_info'].get('talker_id')}")
```

### Example 2: JavaScript/Fetch

```javascript
// Step 1: Login to get JWT bearer token
const loginRes = await fetch('http://localhost:8000/api/users/login/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    email: 'listener@example.com',
    password: 'password123'
  })
});
const loginData = await loginRes.json();
const bearerToken = loginData.access;

// Step 2: Get OAuth2 token with user info
const oauth2Res = await fetch(
  'http://localhost:8000/api/users/oauth2/token/',
  {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${bearerToken}`,
      'Content-Type': 'application/x-www-form-urlencoded'
    },
    body: new URLSearchParams({
      grant_type: 'client_credentials',
      client_id: 'your_client_id',
      client_secret: 'your_client_secret'
    })
  }
);

const oauth2Data = await oauth2Res.json();
console.log(`Listener ID: ${oauth2Data.user_info.listener_id}`);
```

### Example 3: cURL

```bash
# Step 1: Get JWT bearer token
BEARER=$(curl -X POST http://localhost:8000/api/users/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"talker@example.com","password":"password123"}' \
  | jq -r '.access')

# Step 2: Get OAuth2 token with user info
curl -X POST http://localhost:8000/api/users/oauth2/token/ \
  -H "Authorization: Bearer $BEARER" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d 'grant_type=client_credentials&client_id=your_id&client_secret=your_secret'
```

## Testing

Run the provided test script:

```bash
cd /path/to/ringmig
python test_oauth2_proxy.py
```

This script will:
1. Fetch active users from the database
2. Generate JWT bearer tokens for each user
3. Request OAuth2 tokens from the proxy endpoint
4. Display the enriched response with user information

## Architecture Flow

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ 1. POST /api/users/login/
       │    (email, password)
       ▼
┌─────────────────────────────────┐
│  Django Auth & JWT Generation   │
│  Returns: JWT bearer token      │
└──────┬──────────────────────────┘
       │ 2. POST /api/users/oauth2/token/
       │    + Authorization: Bearer JWT
       │    + OAuth2 payload
       ▼
┌─────────────────────────────────┐
│ OAuth2TokenProxyView            │
│ 1. Validate JWT bearer token    │
│ 2. Extract user from JWT        │
│ 3. Get listener/talker profile  │
└──────┬──────────────────────────┘
       │ 3. POST http://10.10.13.24:80/v2/auth/oauth2/token
       │    + OAuth2 payload (forwarded)
       ▼
┌──────────────────────────────────┐
│ Self-Hosted OAuth2 Server        │
│ Returns: OAuth2 token response   │
└──────┬───────────────────────────┘
       │ 4. Enrich response with user_info
       ▼
┌──────────────────────────────────┐
│ Return to Client:                │
│ {                                │
│   "access_token": "...",         │
│   "token_type": "Bearer",        │
│   "expires_in": 3600,            │
│   "user_info": {                 │
│     "user_id": 123,              │
│     "talker_id": 456,            │
│     ...                          │
│   }                              │
│ }                                │
└──────────────────────────────────┘
```

## Security Considerations

1. **Bearer Token Validation**: Only authenticated users with valid JWT tokens can access this endpoint
2. **User Isolation**: Each user can only get tokens for their own context
3. **HTTPS Required**: In production, always use HTTPS for token endpoints
4. **Token Secrets**: Never expose `client_secret` in client-side code
5. **Token Storage**: Store tokens securely (not in localStorage for sensitive apps)
6. **CORS**: Ensure CORS is properly configured for cross-origin requests

## Integration with Cal.com Atoms

This endpoint enables multi-user Cal.com Atoms booking:

```python
# After getting OAuth2 token with user info
from integrations.calcom import CalAtomsBridge

token_response = requests.post(
    'http://localhost:8000/api/users/oauth2/token/',
    headers={'Authorization': f'Bearer {bearer_token}'},
    data={'grant_type': 'client_credentials', ...}
).json()

# Use user-specific token for booking
bridge = CalAtomsBridge(
    oauth_token=token_response['access_token'],
    user_id=token_response['user_info']['talker_id'],
    user_type=token_response['user_info']['user_type']
)

# Create booking for this specific user
booking = bridge.create_booking(
    event_type_id=123,
    start_time='2026-03-20T10:00:00Z',
    attendee_email='listener@example.com'
)
```

## Troubleshooting

### Error: "Unauthorized - Invalid bearer token"
- Ensure the JWT token is valid and not expired
- Use the token from `/api/users/login/` response
- Pass it as: `Authorization: Bearer <token>`

### Error: "OAuth2 request failed"
- Check that `OAUTH2_TOKEN_ENDPOINT` is reachable
- Verify the OAuth2 server credentials (client_id, client_secret)
- Ensure the OAuth2 payload is valid

### Missing user_info in response
- Ensure the user has a listener or talker profile
- Check database for associated profile records

### 500 Internal Server Error
- Check Django error logs: `tail -f logs/django.log`
- Verify all required fields in the OAuth2 payload

## Environment Variables

Add to `.env`:

```bash
# Required
OAUTH2_TOKEN_ENDPOINT=http://10.10.13.24:80/v2/auth/oauth2/token

# Optional (for logging)
DEBUG=True
```

## Related Files

- [core/users/views.py](core/users/views.py) - OAuth2TokenProxyView implementation
- [core/users/urls.py](core/users/urls.py) - URL routing
- [core/core/settings.py](core/core/settings.py) - Configuration
- [test_oauth2_proxy.py](test_oauth2_proxy.py) - Test script

## Support

For issues or questions, refer to:
1. Test script output: `python test_oauth2_proxy.py`
2. Django logs: Check `core/logs/` directory
3. Swagger API docs: `http://localhost:8000/swagger/`
