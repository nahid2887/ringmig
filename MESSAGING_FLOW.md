# Ringmig Messaging System - Talker to Listener Conversation Flow

## Overview
The messaging system implements a two-phase conversation model:
1. **Pending Phase**: Talker sends initial message to Listener
2. **Active Phase**: After Listener accepts, both can send messages freely

---

## API Endpoints

### 1. Create Conversation (Talker Only)
**Endpoint**: `POST /api/chat/conversations/`

**Authentication**: Required (Talker)

**Request Body**:
```json
{
  "listener_id": 123,
  "initial_message": "Hi, I'd like to talk to you about something important."
}
```

**Response** (Status: 201 Created):
```json
{
  "id": 1,
  "listener": {
    "id": 123,
    "email": "listener@example.com",
    "user_type": "listener",
    "full_name": "John Doe"
  },
  "talker": {
    "id": 456,
    "email": "talker@example.com",
    "user_type": "talker",
    "full_name": "Jane Smith"
  },
  "status": "pending",
  "status_display": "Pending",
  "initial_message": "Hi, I'd like to talk to you about something important.",
  "created_at": "2026-01-14T00:00:00Z",
  "accepted_at": null,
  "rejected_at": null,
  "last_message_at": null,
  "last_message": null,
  "unread_count": 0
}
```

---

### 2. List Conversations
**Endpoint**: `GET /api/chat/conversations/`

**Authentication**: Required

**Query Parameters**:
- `status`: Filter by status (pending, active, rejected, closed)
- `ordering`: Order by field (default: -last_message_at)

**Response** (Status: 200 OK):
```json
[
  {
    "id": 1,
    "status": "pending",
    "status_display": "Pending",
    "other_user": {
      "id": 123,
      "email": "listener@example.com",
      "user_type": "listener",
      "full_name": "John Doe"
    },
    "last_message_at": null,
    "last_message_preview": "Hi, I'd like to talk...",
    "unread_count": 0,
    "created_at": "2026-01-14T00:00:00Z"
  }
]
```

---

### 3. Accept Conversation (Listener Only)
**Endpoint**: `POST /api/chat/conversations/{id}/accept/`

**Authentication**: Required (Must be the Listener)

**Request Body**: (Empty)

**Response** (Status: 200 OK):
```json
{
  "id": 1,
  "listener": { ... },
  "talker": { ... },
  "status": "active",
  "status_display": "Active",
  "initial_message": "Hi, I'd like to talk to you about something important.",
  "created_at": "2026-01-14T00:00:00Z",
  "accepted_at": "2026-01-14T00:05:00Z",
  "rejected_at": null,
  "last_message_at": null,
  "last_message": null,
  "unread_count": 0
}
```

---

### 4. Reject Conversation (Listener Only)
**Endpoint**: `POST /api/chat/conversations/{id}/reject/`

**Authentication**: Required (Must be the Listener)

**Request Body**: (Empty)

**Response** (Status: 200 OK):
```json
{
  "id": 1,
  "listener": { ... },
  "talker": { ... },
  "status": "rejected",
  "status_display": "Rejected",
  "initial_message": "Hi, I'd like to talk to you about something important.",
  "created_at": "2026-01-14T00:00:00Z",
  "accepted_at": null,
  "rejected_at": "2026-01-14T00:05:00Z",
  "last_message_at": null,
  "last_message": null,
  "unread_count": 0
}
```

---

### 5. Send Message
**Endpoint**: `POST /api/chat/conversations/{id}/messages/`

**Authentication**: Required

**Requirements**:
- Conversation must be in **"active"** status (or talker in "pending" status)
- In pending status, only the talker can send messages
- After acceptance, both users can send messages

**Request Body**:
```json
{
  "conversation": 1,
  "content": "Thanks for accepting my message! How are you doing?",
  "message_type": "text"
}
```

**Response** (Status: 201 Created):
```json
{
  "id": 1,
  "conversation": 1,
  "sender": {
    "id": 456,
    "email": "talker@example.com",
    "user_type": "talker",
    "full_name": "Jane Smith"
  },
  "content": "Thanks for accepting my message! How are you doing?",
  "message_type": "text",
  "is_read": false,
  "created_at": "2026-01-14T00:10:00Z",
  "file_attachment": null
}
```

---

### 6. Get Conversation Messages
**Endpoint**: `GET /api/chat/conversations/{id}/messages/`

**Authentication**: Required

**Response** (Status: 200 OK):
```json
[
  {
    "id": 1,
    "conversation": 1,
    "sender": { ... },
    "content": "Thanks for accepting my message! How are you doing?",
    "message_type": "text",
    "is_read": false,
    "created_at": "2026-01-14T00:10:00Z",
    "file_attachment": null
  }
]
```

---

### 7. Mark Messages as Read
**Endpoint**: `POST /api/chat/conversations/{id}/mark_read/`

**Authentication**: Required

**Response** (Status: 200 OK):
```json
{
  "success": true,
  "marked_read": 3
}
```

---

### 8. Upload File (To be sent as message)
**Endpoint**: `POST /api/chat/conversations/{id}/upload_file/`

**Authentication**: Required

**Request Body** (multipart/form-data):
- `file`: File to upload
- `content`: Optional description

**Response** (Status: 201 Created):
```json
{
  "id": 2,
  "conversation": 1,
  "sender": { ... },
  "content": "Check this out!",
  "message_type": "file",
  "is_read": false,
  "created_at": "2026-01-14T00:15:00Z",
  "file_attachment": {
    "id": 1,
    "file": "/media/chat_files/2026/01/14/document.pdf",
    "file_url": "http://localhost/media/chat_files/2026/01/14/document.pdf",
    "filename": "document.pdf",
    "file_size": 102400,
    "file_size_display": "100.0 KB",
    "file_type": "application/pdf",
    "uploaded_at": "2026-01-14T00:15:00Z"
  }
}
```

---

## Conversation Status States

| Status | Description | Who Can Send Messages |
|--------|-------------|----------------------|
| `pending` | Talker sent initial message, waiting for listener | Talker only |
| `active` | Listener accepted the conversation | Both users |
| `rejected` | Listener rejected the conversation | None (read-only) |
| `closed` | Conversation ended | None (read-only) |

---

## Conversation Flow Diagram

```
┌──────────────┐
│   Start      │
└──────┬───────┘
       │
       ├─────────────────────────────────────┐
       │                                     │
   Talker sends               Listener receives
   initial message            conversation request
       │                                     │
       v                                     v
   ┌─────────────────────────────────────┐
   │  Conversation Status: PENDING       │
   │  - Only Talker can send messages    │
   │  - Listener can accept/reject       │
   └──────────┬──────────────┬───────────┘
              │              │
         Listener        Listener
         Accepts         Rejects
              │              │
              v              v
       ┌─────────────┐  ┌────────────┐
       │   ACTIVE    │  │  REJECTED  │
       │ Both can    │  │  Closed    │
       │ message     │  │  Read-only │
       └─────────────┘  └────────────┘
```

---

## Example Workflow

### Step 1: Talker Initiates Conversation
```bash
curl -X POST http://localhost/api/chat/conversations/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TALKER_TOKEN" \
  -d '{
    "listener_id": 123,
    "initial_message": "Hi, I need someone to talk to"
  }'
```

### Step 2: Listener Sees Pending Conversation
```bash
curl -X GET http://localhost/api/chat/conversations/ \
  -H "Authorization: Bearer YOUR_LISTENER_TOKEN"
```
Returns conversations with `status: "pending"`

### Step 3a: Listener Accepts Conversation
```bash
curl -X POST http://localhost/api/chat/conversations/1/accept/ \
  -H "Authorization: Bearer YOUR_LISTENER_TOKEN"
```

### Step 3b (Alternative): Listener Rejects Conversation
```bash
curl -X POST http://localhost/api/chat/conversations/1/reject/ \
  -H "Authorization: Bearer YOUR_LISTENER_TOKEN"
```

### Step 4: Both Users Can Now Message (If Accepted)
**Talker sends message:**
```bash
curl -X POST http://localhost/api/chat/conversations/1/messages/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TALKER_TOKEN" \
  -d '{
    "conversation": 1,
    "content": "Thanks for accepting! How are you?",
    "message_type": "text"
  }'
```

**Listener responds:**
```bash
curl -X POST http://localhost/api/chat/conversations/1/messages/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_LISTENER_TOKEN" \
  -d '{
    "conversation": 1,
    "content": "I am good, how can I help?",
    "message_type": "text"
  }'
```

---

## Error Handling

### Unauthorized Talker Tries to Accept
```json
{
  "error": "Only the listener can accept this conversation"
}
```
**Status**: 403 Forbidden

### Listener Tries to Send Message Before Accepting
```json
{
  "error": "Only the talker can send messages in a pending conversation"
}
```
**Status**: 400 Bad Request

### Try to Message in Rejected Conversation
```json
{
  "error": "Cannot send messages in a rejected conversation"
}
```
**Status**: 400 Bad Request

---

## Database Schema

### Conversation Model
- `id` (PK)
- `listener` (FK → User)
- `talker` (FK → User)
- `status` (pending, active, rejected, closed)
- `initial_message` (TextField)
- `created_at` (DateTime)
- `updated_at` (DateTime)
- `accepted_at` (DateTime, nullable)
- `rejected_at` (DateTime, nullable)
- `last_message_at` (DateTime, nullable)

### Message Model
- `id` (PK)
- `conversation` (FK → Conversation)
- `sender` (FK → User)
- `content` (TextField)
- `message_type` (text, file)
- `is_read` (Boolean)
- `created_at` (DateTime)

### FileAttachment Model
- `id` (PK)
- `message` (OneToOne → Message)
- `file` (FileField)
- `filename` (CharField)
- `file_size` (BigInteger)
- `file_type` (CharField)
- `uploaded_at` (DateTime)

---

## Model Permissions & Validation

| Action | Permission | Status | Validation |
|--------|------------|--------|-----------|
| Create Conversation | Talker only | Pending | listener_id + initial_message required |
| Accept Conversation | Listener only | Pending | Must be the listener in conversation |
| Reject Conversation | Listener only | Pending | Must be the listener in conversation |
| Send Message | Any participant | Pending/Active | Talker only in pending; both in active |
| Mark Read | Any participant | Any | Marks other user's messages as read |
| Upload File | Any participant | Pending/Active | Same as Send Message |

