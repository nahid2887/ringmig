# Quick Start: Messaging System

## Feature Summary

Your Ringmig messaging system now has a **two-phase conversation model**:

### Phase 1: Initial Contact (Pending)
- ✅ **Talker** sends an initial message to a **Listener**
- ✅ Conversation starts in **"pending"** status
- ✅ Only the **talker** can send messages in this phase
- ✅ **Listener** receives a notification and can:
  - Accept the conversation → moves to "active"
  - Reject the conversation → moves to "rejected"

### Phase 2: Conversation (Active)
- ✅ Once **listener accepts**, the conversation becomes "active"
- ✅ **Both users** can now send/receive messages freely
- ✅ They can share files, images, and documents
- ✅ Messages are marked as read/unread

---

## Database Changes

Added 4 new fields to Conversation model:
- `status` - Current state (pending/active/rejected/closed)
- `initial_message` - Talker's first message
- `accepted_at` - When listener accepted
- `rejected_at` - When listener rejected

---

## API Changes

### New Endpoints:
```
POST   /api/chat/conversations/                    - Create conversation (talker only)
POST   /api/chat/conversations/{id}/accept/        - Accept request (listener only)
POST   /api/chat/conversations/{id}/reject/        - Reject request (listener only)
```

### Updated Endpoints:
```
GET    /api/chat/conversations/                    - List conversations (now includes status)
GET    /api/chat/conversations/{id}/                - Get conversation details (includes status)
POST   /api/chat/conversations/{id}/messages/       - Send message (respects status rules)
```

---

## Code Changes Summary

### Models (chat/models.py)
- Added `status` field to Conversation with choices: pending, active, rejected, closed
- Added `initial_message` field to store first message
- Added `accepted_at` and `rejected_at` timestamps
- Added `accept()` and `reject()` methods to Conversation
- Updated Message validation to respect conversation status

### Serializers (chat/serializers.py)
- Updated `ConversationSerializer` to include status, timestamps, and initial_message
- Updated `ConversationListSerializer` to show status
- Updated `ConversationCreateSerializer` to require `initial_message` from talker

### Views (chat/views.py)
- Updated `create()` method to only allow talkers and set status to pending
- Added `@action accept()` to allow listeners to accept conversations
- Added `@action reject()` to allow listeners to reject conversations
- Added validation to Message creation to respect conversation status

---

## Testing the Feature

### 1. Test Creating a Conversation (as Talker)
```bash
curl -X POST http://localhost/api/chat/conversations/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TALKER_TOKEN" \
  -d '{
    "listener_id": 5,
    "initial_message": "Hello! I would like to talk to you."
  }'
```

### 2. List Conversations (as Listener)
```bash
curl -X GET http://localhost/api/chat/conversations/ \
  -H "Authorization: Bearer LISTENER_TOKEN"
```
Look for conversations with `status: "pending"`

### 3. Accept the Conversation (as Listener)
```bash
curl -X POST http://localhost/api/chat/conversations/1/accept/ \
  -H "Authorization: Bearer LISTENER_TOKEN"
```

### 4. Now Both Can Message
**Listener responds:**
```bash
curl -X POST http://localhost/api/chat/conversations/1/messages/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer LISTENER_TOKEN" \
  -d '{
    "conversation": 1,
    "content": "Hi! Great to chat with you.",
    "message_type": "text"
  }'
```

---

## Files Modified

1. **core/chat/models.py**
   - Updated Conversation model with status fields
   - Added accept() and reject() methods
   - Enhanced Message save() validation

2. **core/chat/serializers.py**
   - Enhanced all conversation serializers with status info
   - Updated ConversationCreateSerializer for initial_message

3. **core/chat/views.py**
   - Modified create() to handle talker-only flow
   - Added accept() and reject() actions

4. **Migrations**
   - Created `chat/migrations/0002_conversation_accepted_at_and_more.py`

---

## Important Notes

⚠️ **Conversation Creation Rules:**
- Only **talkers** can create new conversations
- Must provide `listener_id` and `initial_message`
- Listeners **cannot** create conversations; they can only accept/reject

⚠️ **Message Sending Rules:**
- In **pending** status: Only talker can send messages
- In **active** status: Both users can send messages
- In **rejected/closed** status: No messages allowed

⚠️ **Status Transitions:**
```
pending ──→ accept() ──→ active
   ↓
   └──→ reject() ──→ rejected
```

---

## Swagger Documentation

Access the full API documentation at: **http://localhost/swagger/**

All new endpoints are automatically documented there with:
- Request/response examples
- Parameter descriptions
- Error codes and messages

---

## Next Steps

- **WebSocket Integration**: Add real-time message notifications
- **Typing Indicators**: Show when someone is typing
- **Message Reactions**: Add emoji reactions to messages
- **Conversation Archiving**: Archive old conversations
- **Block List**: Allow users to block others

