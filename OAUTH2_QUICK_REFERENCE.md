## OAuth2 Multi-User Proxy - Quick Reference

### New Endpoint
```
POST /api/users/oauth2/token/
```

### What It Does
- Accepts **bearer token** (JWT) from authenticated user
- Proxies OAuth2 token request to your self-hosted server
- **Enriches response** with listener/talker identification
- Returns both OAuth2 token AND user profile info

### Files Modified
1. **[core/users/views.py](core/users/views.py)** - Added `OAuth2TokenProxyView` class
2. **[core/users/urls.py](core/users/urls.py)** - Added URL route
3. **[core/core/settings.py](core/core/settings.py)** - Added `OAUTH2_TOKEN_ENDPOINT` config

### Files Created
1. **[OAUTH2_PROXY_DOCUMENTATION.md](OAUTH2_PROXY_DOCUMENTATION.md)** - Full documentation
2. **[test_oauth2_proxy.py](test_oauth2_proxy.py)** - Test script

### How to Use

**1. Get JWT Bearer Token**
```bash
curl -X POST http://localhost:8000/api/users/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password"}'
# Response: {"access": "eyJ0eXAi...", "refresh": "..."}
```

**2. Use Bearer Token to Get OAuth2 Token**
```bash
curl -X POST http://localhost:8000/api/users/oauth2/token/ \
  -H "Authorization: Bearer eyJ0eXAi..." \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d 'grant_type=client_credentials&client_id=ID&client_secret=SECRET'
```

**3. Response Includes User Info**
```json
{
  "access_token": "...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "user_info": {
    "user_id": 123,
    "email": "user@example.com",
    "user_type": "talker",
    "talker_id": 456
  }
}
```

### Configuration
Add to `.env`:
```bash
OAUTH2_TOKEN_ENDPOINT=http://10.10.13.24:80/v2/auth/oauth2/token
```

### Test
```bash
python test_oauth2_proxy.py
```

### Key Features
✅ **Multi-user support** - Each user gets their own context  
✅ **Bearer token validated** - Only authenticated users can use  
✅ **User ID included** - Enriched with listener/talker identification  
✅ **Self-hosted OAuth2 support** - Works with your custom OAuth2 server  
✅ **Listener & Talker aware** - Different response for each user type  

### Use Case: Multi-User Cal.com Booking
```python
# Each listener/talker can get their own OAuth2 token
# Use the talker_id/listener_id for user-specific calendar scheduling
# Enables different listeners/talkers to have different availability
```

### Security
- ✓ Requires valid JWT bearer token
- ✓ Each user isolated to their own context
- ✓ Production: Use HTTPS only
- ✓ Never expose client_secret in frontend code
