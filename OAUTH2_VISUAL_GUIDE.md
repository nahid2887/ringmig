# OAuth2 Multi-User Integration - Visual Guide

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         RINGMIG APPLICATION                         │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ DATABASE                                                     │  │
│  │ ┌─────────────┐  ┌──────────────┐  ┌──────────────┐        │  │
│  │ │  User       │  │ Listener     │  │ Talker       │        │  │
│  │ │ Model       │  │ Profile      │  │ Profile      │        │  │
│  │ ├─────────────┤  ├──────────────┤  ├──────────────┤        │  │
│  │ │ id=123      │  │ id=456       │  │ id=789       │        │  │
│  │ │ email       │  │ listener_id→ │  │ talker_id→  │        │  │
│  │ │ user_type   │  │ user_id=123  │  │ user_id=123 │        │  │
│  │ │ full_name   │  │ name         │  │ name        │        │  │
│  │ └─────────────┘  └──────────────┘  └──────────────┘        │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ REST API ENDPOINTS                                           │  │
│  │                                                              │  │
│  │ ✓ POST /api/users/login/                                   │  │
│  │   → Returns: {access: JWT, refresh: JWT}                   │  │
│  │                                                              │  │
│  │ ✓ POST /api/users/oauth2/token/        [NEW ENDPOINT]      │  │
│  │   Header: Authorization: Bearer JWT                         │  │
│  │   Body: {grant_type, client_id, client_secret, ...}        │  │
│  │   → Returns: {access_token, user_info, ...}                │  │
│  │                                                              │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ OAuth2TokenProxyView (views.py)                             │  │
│  │                                                              │  │
│  │  1. Extract JWT from Authorization header                  │  │
│  │  2. Validate JWT signature                                 │  │
│  │  3. Get user_id from JWT claims                            │  │
│  │  4. Fetch User from database                               │  │
│  │  5. Determine user_type (listener/talker)                 │  │
│  │  6. Fetch listener/talker profile if exists               │  │
│  │  7. Extract OAuth2 payload from request body              │  │
│  │  8. Forward request to external OAuth2 server             │  │
│  │  9. Parse OAuth2 response                                 │  │
│  │ 10. Enrich response with user_info                        │  │
│  │ 11. Return combined response                              │  │
│  │                                                              │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                              ↓↑
                (Network Request)
┌─────────────────────────────────────────────────────────────────────┐
│                  SELF-HOSTED OAuth2 SERVER                          │
│              http://10.10.13.24:80/v2/auth/oauth2/token            │
│                                                                     │
│  Receives:                                                          │
│  - grant_type: 'client_credentials'                                │
│  - client_id: 'your_client_id'                                     │
│  - client_secret: 'your_client_secret'                             │
│                                                                     │
│  Returns:                                                           │
│  {                                                                  │
│    "access_token": "eyJ...",                                       │
│    "token_type": "Bearer",                                         │
│    "expires_in": 3600,                                             │
│    "refresh_token": "eyJ..."                                       │
│  }                                                                  │
└─────────────────────────────────────────────────────────────────────┘
```

## Request/Response Flow Sequence

```
CLIENT (Listener/Talker)
       │
       │ 1. POST /api/users/login/
       │    {email, password}
       ↓
   ┌──────────────────────┐
   │ Ringmig Auth         │
   │ (JWT Generation)     │
   └──────────────────────┘
       │
       │ ✓ Returns JWT Bearer Token
       │ {access: "eyJ...", refresh: "eyJ..."}
       ↓
   [Token stored by client]
       │
       │ 2. POST /api/users/oauth2/token/
       │    Header: Authorization: Bearer eyJ...
       │    Body: {
       │      grant_type: "client_credentials",
       │      client_id: "ID",
       │      client_secret: "SECRET"
       │    }
       ↓
   ┌──────────────────────────────────────────────┐
   │ OAuth2TokenProxyView                         │
   │                                              │
   │ Step 1: Validate Bearer Token                │
   │ ✓ Extract JWT from header                    │
   │ ✓ Decode and verify signature                │
   │ ✓ Get user_id from token payload             │
   │                                              │
   │ Step 2: Authenticate User                    │
   │ ✓ Query User model with user_id              │
   │ ✓ Check user.is_authenticated                │
   │ (Return 401 if invalid)                      │
   │                                              │
   │ Step 3: Determine User Role                  │
   │ ✓ Check user.user_type                       │
   │ - "listener" → Fetch ListenerProfile         │
   │ - "talker" → Fetch TalkerProfile             │
   │                                              │
   │ Step 4: Forward OAuth2 Request               │
   │ ✓ Extract OAuth2 payload from request body   │
   │ ✓ Make HTTP POST to external OAuth2 server   │
   │ POST http://10.10.13.24:80/v2/auth/oauth2/token
   │ (Return 400 if OAuth2 server error)          │
   │                                              │
   │ Step 5: Build Response                       │
   │ ✓ Parse OAuth2 response                      │
   │ ✓ Extract access_token, refresh_token, etc.  │
   │ ✓ Build user_info object:                    │
   │   {                                          │
   │     user_id: 123,                            │
   │     email: "user@example.com",               │
   │     full_name: "John Doe",                   │
   │     user_type: "talker",                     │
   │     talker_id: 789,                          │
   │     talker_name: "John D."                   │
   │   }                                          │
   │                                              │
   │ Step 6: Return Enriched Response             │
   └──────────────────────────────────────────────┘
       │
       │ ✓ Returns Combined Response:
       │ {
       │   "access_token": "eyJ...",
       │   "token_type": "Bearer",
       │   "expires_in": 3600,
       │   "refresh_token": "eyJ...",
       │   "user_info": {
       │     "user_id": 123,
       │     "email": "talker@example.com",
       │     "full_name": "John Talker",
       │     "user_type": "talker",
       │     "talker_id": 789,
       │     "talker_name": "John T."
       │   }
       │ }
       ↓
   [Client receives combined response]
```

## User Flow: Listener vs Talker

```
LISTENER USER                              TALKER USER
═══════════════════════════════════════════════════════════════════

1. LOGIN
┌─────────────────────┐                ┌─────────────────────┐
│ Email: alice@ex.com │                │ Email: bob@ex.com   │
│ Password: pass123   │                │ Password: pass456   │
└─────────────────────┘                └─────────────────────┘
         ↓                                      ↓
    JWT Token                              JWT Token
    user_id=100                            user_id=200
         │                                      │
         └──────────────────┬───────────────────┘
                            ↓
                    2. OAuth2 PROXY
                    (Same endpoint)
                            │
                ┌───────────┴────────────┐
                ↓                        ↓
         Listener Branch          Talker Branch
         ═══════════════          ════════════
         
         user_type="listener"     user_type="talker"
                ↓                        ↓
         Query DB:                  Query DB:
         ListenerProfile            TalkerProfile
         listener_id=50             talker_id=75
                ↓                        ↓
         ┌─────────────────────┐   ┌─────────────────────┐
         │ user_info returned: │   │ user_info returned: │
         ├─────────────────────┤   ├─────────────────────┤
         │ user_id: 100        │   │ user_id: 200        │
         │ email: alice@ex.com │   │ email: bob@ex.com   │
         │ user_type: listener │   │ user_type: talker   │
         │ listener_id: 50     │   │ talker_id: 75       │
         │ listener_name: Alice│   │ talker_name: Bob    │
         └─────────────────────┘   └─────────────────────┘
                ↓                        ↓
         Can use listener_id for  Can use talker_id for
         booking/scheduling       event management
```

## Response Structure Variations

```
┌─────────────────────────────────────────────────────────────────┐
│ SUCCESSFUL RESPONSE (200)                                       │
├─────────────────────────────────────────────────────────────────┤
│ {                                                               │
│   "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1...",     │
│   "token_type": "Bearer",                                       │
│   "expires_in": 3600,                                           │
│   "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1...",   │
│   "user_info": {                                                │
│     "user_id": 123,                                             │
│     "email": "user@example.com",                                │
│     "full_name": "Full Name",                                   │
│     "user_type": "listener" | "talker",                         │
│     "listener_id": 456,          ← Only for listener            │
│     "listener_name": "Display Name",  ← Only for listener      │
│     "talker_id": 789,            ← Only for talker              │
│     "talker_name": "Display Name"    ← Only for talker         │
│   }                                                             │
│ }                                                               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ UNAUTHORIZED (401)                                              │
├─────────────────────────────────────────────────────────────────┤
│ {                                                               │
│   "error": "Unauthorized - Invalid bearer token"                │
│ }                                                               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ OAUTH2 ERROR (400)                                              │
├─────────────────────────────────────────────────────────────────┤
│ {                                                               │
│   "error": "OAuth2 request failed: ..."                         │
│ }                                                               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ SERVER ERROR (500)                                              │
├─────────────────────────────────────────────────────────────────┤
│ {                                                               │
│   "error": "Internal server error: ..."                         │
│ }                                                               │
└─────────────────────────────────────────────────────────────────┘
```

## Multi-User Use Case: Calendar Scheduling

```
Multiple Users → Multiple Independent Calendars
═══════════════════════════════════════════════

Scenario: Different talkers need different availability

User A (Talker)                    User B (Talker)
  │                                  │
  │ 1. Get OAuth2 token             │ 1. Get OAuth2 token
  │    with talker_id=100           │    with talker_id=200
  │    ↓                            │    ↓
  │ 2. Access Cal.com API           │ 2. Access Cal.com API
  │    for user 100's calendar      │    for user 200's calendar
  │    ↓                            │    ↓
  │ 3. Set availability:            │ 3. Set availability:
  │    Mon-Fri 9am-5pm              │    Tue-Thu 6pm-8pm
  │    ↓                            │    ↓
  │ Listeners book with User A      │ Listeners book with User B
  │ when available                  │ when available
  │                                 │
  └─────────────┬───────────────────┘
                │
          RINGMIG DATABASE
          ┌─────────────────────────────────────┐
          │ Booking Records:                    │
          ├─────────────────────────────────────┤
          │ talker_id=100, listener_id=50       │
          │ talker_id=100, listener_id=60       │
          │ talker_id=200, listener_id=50       │
          │ talker_id=200, listener_id=70       │
          └─────────────────────────────────────┘
          
          Each booking correctly associates
          with the right talker's calendar
```

## Configuration & Setup

```
PROJECT STRUCTURE
=================

ringmig/
  ├── .env
  │   └── OAUTH2_TOKEN_ENDPOINT=http://10.10.13.24:80/v2/auth/oauth2/token
  │
  ├── core/
  │   ├── core/
  │   │   └── settings.py
  │   │       └── OAUTH2_TOKEN_ENDPOINT setting
  │   │
  │   └── users/
  │       ├── views.py
  │       │   └── OAuth2TokenProxyView (NEW)
  │       └── urls.py
  │           └── path('oauth2/token/', ...) (NEW)
  │
  ├── test_oauth2_proxy.py (NEW)
  │
  ├── OAUTH2_PROXY_DOCUMENTATION.md (NEW)
  ├── OAUTH2_QUICK_REFERENCE.md (NEW)
  └── IMPLEMENTATION_SUMMARY_OAUTH2.md (NEW)
```

## Error Flow Diagram

```
Request to /api/users/oauth2/token/
         │
         ↓
┌──────────────────┐
│ JWT Bearer Valid?│
└──────────────────┘
    No │   │ Yes
       │   ↓
       │ ┌──────────────┐
       │ │ User Exists? │
       │ └──────────────┘
       │   No │   │ Yes
       │      │   ↓
       │      │ ┌──────────────────────┐
       │      │ │ OAuth2 Forward OK?   │
       │      │ └──────────────────────┘
       │      │   No │   │ Yes
       │      │      │   ↓
       │      │      │ ┌──────────────────┐
       │      │      │ │ Parse Response?  │
       │      │      │ └──────────────────┘
       │      │      │   No │   │ Yes
       │      │      │      │   ↓
       │      │      │      │ ┌────────────────┐
       │      │      │      │ │ Profile Lookup?│
       │      │      │      │ └────────────────┘
       │      │      │      │   No │   │ Yes
       │      │      │      │      │   ↓
       │      │      │      │      │ ✓ SUCCESS
       │      │      │      │      │ (200)
       │      │      │      │      │ Enriched
       │      │      │      │      │ Response
       │      │      │      │      │
       ↓      ↓      ↓      ↓      ↓
    ❌401 ❌401 ❌400 ❌500 ✓200
    Unauth  User   OAuth   Server Success
             Not    Error   Error
             Found

Error responses include:
- error: "Error message"
- HTTP status code
- No sensitive data in error
```

## Implementation Files Map

```
Changes Summary
═══════════════

✏️ Modified Files:
  1. core/users/views.py
     └── + OAuth2TokenProxyView class (108 lines)
     └── + imports (requests, AccessToken, TokenError)
  
  2. core/users/urls.py
     └── + OAuth2TokenProxyView import
     └── + oauth2/token/ URL route
  
  3. core/core/settings.py
     └── + OAUTH2_TOKEN_ENDPOINT configuration

📄 New Files:
  1. test_oauth2_proxy.py
     └── Automated testing script
  
  2. OAUTH2_PROXY_DOCUMENTATION.md
     └── Complete API documentation
  
  3. OAUTH2_QUICK_REFERENCE.md
     └── Quick start guide
  
  4. IMPLEMENTATION_SUMMARY_OAUTH2.md
     └── Implementation details
  
  5. OAUTH2_VISUAL_GUIDE.md (this file)
     └── Visual diagrams and flows
```
