# WebSocket Blocking - Quick Reference

## TL;DR: What Was Fixed

**Problem**: After blocking via `/api/listener/profiles/block_talker/`, blocked talkers could still message via WebSocket.

**Solution**: Added `check_if_blocked()` method to WebSocket handlers to prevent all messaging when blocked.

**Result**: ✅ Blocked users cannot send messages, files, or typing indicators.

---

## 3-Step Verification

### 1. Check the Implementation
```bash
# Verify check_if_blocked() method exists
grep -n "def check_if_blocked" core/chat/consumers.py
# Should output around line 469

# Verify all handlers call it
grep -n "check_if_blocked" core/chat/consumers.py
# Should show 3 calls (in handle_chat_message, handle_file_message, handle_typing)
```

### 2. Run Tests
```bash
python manage.py test chat.tests_blocking
# All tests should pass
```

### 3. Manual Testing via WebSocket
```python
# 1. Create test users
listener = User.objects.create_user(email='listener@test.com', user_type='listener')
talker = User.objects.create_user(email='talker@test.com', user_type='talker')

# 2. Create conversation
conv = Conversation.objects.create(talker=talker, listener=listener, initial_message='test')

# 3. Block the talker
from listener.models import ListenerBlockedTalker
ListenerBlockedTalker.objects.create(listener=listener, talker=talker)

# 4. Try to send message via WebSocket (should get error)
# Client: {"type": "chat_message", "message": "Hello"}
# Server: {"type": "error", "message": "You cannot message this user..."}
```

---

## Files Changed Summary

| File | Changes | Type |
|------|---------|------|
| `core/chat/consumers.py` | Added blocking checks to 3 methods | Modified |
| `core/chat/tests_blocking.py` | New comprehensive test suite | Created |
| `WEBSOCKET_BLOCKING_GUIDE.md` | Full implementation guide | Created |
| `WEBSOCKET_BLOCKING_IMPLEMENTATION.md` | Implementation summary | Created |
| `WEBSOCKET_BLOCKING_ARCHITECTURE.md` | Visual diagrams & flows | Created |

---

## Code Changes at a Glance

### Before (❌ Broken)
```python
async def handle_chat_message(self, data):
    message = await self.save_message(content, 'text')  # No block check!
    await self.channel_layer.group_send(...)
```

### After (✅ Fixed)
```python
async def handle_chat_message(self, data):
    # Check if messaging is blocked
    is_blocked = await self.check_if_blocked()  # NEW
    if is_blocked:
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': 'You cannot message this user because they have blocked you...'
        }))
        return
    
    try:
        message = await self.save_message(content, 'text')
        await self.channel_layer.group_send(...)
    except PermissionError:
        # Handle database-level block check
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': 'You cannot message this user because they have blocked you...'
        }))
```

---

## New Method Added

```python
@database_sync_to_async
def check_if_blocked(self):
    """Check if users are blocked from messaging each other.
    Returns True if the listener has blocked the talker."""
    try:
        conversation = Conversation.objects.get(id=self.conversation_id)
        if ListenerBlockedTalker.objects.filter(
            listener=conversation.listener,
            talker=conversation.talker
        ).exists():
            return True
        return False
    except Conversation.DoesNotExist:
        return False
```

---

## Testing Endpoints

### Block User (API)
```bash
curl -X POST http://127.0.0.1:8005/api/listener/profiles/block_talker/ \
  -H "Authorization: Bearer <listener_jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{"talker_id": 123}'

# Response (201):
# {"message": "Talker with ID 123 has been blocked", "talker_id": 123, "blocked_at": "2026-02-15T..."}
```

### Try to Message (WebSocket) - ❌ Will Fail
```javascript
// Connect as talker (after blocking)
ws = new WebSocket('ws://127.0.0.1:8005/ws/chat/<conversation_id>/?token=<talker_jwt>')

// Send message
ws.send(JSON.stringify({
  type: 'chat_message',
  message: 'Hello'
}))

// Receive error:
// {"type": "error", "message": "You cannot message this user because they have blocked you..."}
```

### Unblock User (API)
```bash
curl -X POST http://127.0.0.1:8005/api/listener/profiles/unblock_talker/ \
  -H "Authorization: Bearer <listener_jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{"talker_id": 123}'

# Response (200):
# {"message": "Talker with ID 123 has been unblocked", "talker_id": 123}
```

### Now Message Works (WebSocket) - ✅ Will Succeed
```javascript
// Same WebSocket command will now work:
ws.send(JSON.stringify({
  type: 'chat_message',
  message: 'Hello'
}))

// Receive success:
// {"type": "new_message", "messages": [...], "latest_message": {...}}
```

---

## Error Messages

| Scenario | Error Message |
|----------|---------------|
| Send text to blocked user | "You cannot message this user because they have blocked you or you have blocked them" |
| Send file to blocked user | "You cannot send files to this user because they have blocked you or you have blocked them" |
| Send typing to blocked user | (Silently ignored - no error) |

---

## What Gets Blocked

| Action | Before | After |
|--------|--------|-------|
| Text messages | ❌ Sent | ✅ Blocked |
| File uploads | ❌ Sent | ✅ Blocked |
| Typing indicators | ❌ Visible | ✅ Hidden |
| Conversation access | ❌ Accessible | ✅ Denied |

---

## Defense Layers

1. **JWT Authentication** - Token validation required
2. **WebSocket Handler** - `check_if_blocked()` early exit
3. **Database Layer** - `PermissionError` raised on save
4. **Conversation Access** - `get_conversation()` returns None

---

## Deployment Checklist

- [x] Code changes made to `core/chat/consumers.py`
- [x] No database migrations required
- [x] Uses existing `ListenerBlockedTalker` model
- [x] Tests created and verified
- [x] No syntax errors
- [x] Backward compatible
- [x] Documentation complete
- [x] Ready to deploy

---

## Support

For questions about:
- **Architecture**: See `WEBSOCKET_BLOCKING_ARCHITECTURE.md`
- **Implementation details**: See `WEBSOCKET_BLOCKING_GUIDE.md`
- **API endpoints**: See `WEBSOCKET_BLOCKING_GUIDE.md` → API Endpoints section
- **Testing**: See `core/chat/tests_blocking.py`

---

## Quick Command Reference

```bash
# Check for syntax errors
python -m py_compile core/chat/consumers.py

# Run blocking tests
python manage.py test chat.tests_blocking

# Check if blocking works in shell
python manage.py shell
# Then:
# >>> from listener.models import ListenerBlockedTalker
# >>> from chat.models import Conversation
# >>> ListenerBlockedTalker.objects.all()  # Should see blocked users
```

---

**Status**: ✅ COMPLETE AND TESTED
