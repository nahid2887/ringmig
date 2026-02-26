# ZIM Token Integration - Accept Call Endpoint

## Updated: Accept Call Endpoint

**Endpoint:** `POST /api/chat/call-sessions/accept/`

**Purpose:** Listener accepts an incoming call and starts the timer

### Request
```json
{
    "call_session_id": 56
}
```

### Response with ZIM Tokens
```json
{
    "message": "Call accepted successfully. Timer started.",
    "accepted": true,
    "session": {
        "id": 56,
        "talker": 16,
        "listener": 15,
        "status": "active",
        "total_minutes_purchased": 30,
        // ... other session fields
    },
    "zim": {
        "app_id": 1247203967,
        "talker": {
            "user_id": "16",
            "username": "talker@example.com",
            "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
        },
        "listener": {
            "user_id": "15",
            "username": "listener@example.com",
            "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
        },
        "expires_at": 1772089518,
        "expire_time_seconds": 7200
    },
    "agora": {},
    "talker_notified": true,
    "timer_started": true,
    "remaining_minutes": 30.0,
    "started_at": "2026-02-26T12:34:56.789Z"
}
```

---

## Both Endpoints Now Include ZIM Tokens

### 1. **Initiate Call from Package**
- **Endpoint:** `POST /api/chat/call-sessions/initiate-from-package/`
- **When Used:** Talker initiates a call
- **ZIM Tokens:** ✅ Included in response
- **Token Expiration:** 2 hours (7200 seconds)

### 2. **Accept Incoming Call**
- **Endpoint:** `POST /api/chat/call-sessions/accept/`
- **When Used:** Listener accepts a call
- **ZIM Tokens:** ✅ Included in response
- **Token Expiration:** 2 hours (7200 seconds)

---

## Frontend Usage Flow

### Step 1: Talker Initiates Call
```javascript
const initiateResponse = await fetch('/api/chat/call-sessions/initiate-from-package/', {
    method: 'POST',
    headers: {
        'Authorization': 'Bearer TALKER_JWT_TOKEN',
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        call_package_id: 123
    })
});

const initiateData = await initiateResponse.json();
const zimTokens = initiateData.zim;
const sessionId = initiateData.session.id;

// Initialize ZIM SDK as Talker
const zimSDK = new ZIM({
    appID: zimTokens.app_id,
    userID: zimTokens.talker.user_id,
    username: zimTokens.talker.username
});
await zimSDK.login(zimTokens.talker.token);
```

### Step 2: Listener Receives Call
Listener gets notification via WebSocket and displays incoming call screen

### Step 3: Listener Accepts Call
```javascript
const acceptResponse = await fetch('/api/chat/call-sessions/accept/', {
    method: 'POST',
    headers: {
        'Authorization': 'Bearer LISTENER_JWT_TOKEN',
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        call_session_id: sessionId
    })
});

const acceptData = await acceptResponse.json();
const listenerZimTokens = acceptData.zim;

// Initialize ZIM SDK as Listener
const zimSDK = new ZIM({
    appID: listenerZimTokens.app_id,
    userID: listenerZimTokens.listener.user_id,
    username: listenerZimTokens.listener.username
});
await zimSDK.login(listenerZimTokens.listener.token);
```

---

## Key Points

✅ **ZIM tokens generated at both endpoints**
- Talker gets tokens when initiating call
- Listener gets tokens when accepting call
- Both receive same tokens (for consistency)

✅ **Token Structure**
- JWT format with HS256 algorithm
- Includes user ID, username, app ID
- 2-hour expiration window
- Signed with server secret (39949576ffad57ec6cdad1f1602cf7bc)

✅ **Security**
- Each user gets their own token
- Tokens tied to specific user IDs
- Tokens verified by Zego Cloud service
- Server secret never exposed to frontend

---

## Testing

To test the accept endpoint with ZIM tokens:

```bash
# 1. Create a call session (initiates from talker side)
curl -X POST http://10.10.13.27:8005/api/chat/call-sessions/initiate-from-package/ \
  -H "Authorization: Bearer TALKER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"call_package_id": 123}'

# 2. Accept the call (listener side)
curl -X POST http://10.10.13.27:8005/api/chat/call-sessions/accept/ \
  -H "Authorization: Bearer LISTENER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"call_session_id": SESSION_ID}'

# 3. Extract ZIM tokens from response
# tokens are in: response.zim.talker.token and response.zim.listener.token
```

---

## Related Files Updated

- `chat/call_views.py` - Added ZIM token generation to accept_call endpoint
- `chat/zim_utils.py` - Token generation utility (created earlier)
- `ZIM_TOKEN_DOCUMENTATION.md` - General ZIM integration docs