# WebSocket Blocking Implementation Guide

## Overview
This document describes the implementation of blocking functionality for WebSocket chat messaging. When a listener blocks a talker using the API endpoint `/api/listener/profiles/block_talker/`, both users will be prevented from messaging each other via WebSocket.

## Implementation Details

### 1. Block Detection Mechanism

The blocking system uses a new method `check_if_blocked()` in the `ChatConsumer` class:

```python
@database_sync_to_async
def check_if_blocked(self):
    """Check if users are blocked from messaging each other.
    Returns True if the listener has blocked the talker."""
    try:
        conversation = Conversation.objects.get(id=self.conversation_id)
        # Check if the listener has blocked the talker
        if ListenerBlockedTalker.objects.filter(
            listener=conversation.listener,
            talker=conversation.talker
        ).exists():
            return True
        return False
    except Conversation.DoesNotExist:
        return False
```

This method:
- Retrieves the conversation from the WebSocket connection
- Checks if the listener has blocked the talker using the `ListenerBlockedTalker` model
- Returns `True` if a block exists, `False` otherwise
- Handles gracefully if the conversation doesn't exist

### 2. Message Prevention

The blocking check is integrated into three message handler methods:

#### a) `handle_chat_message()` - Text Messages
- Checks if messaging is blocked BEFORE saving the message
- Returns a clear error message to the user if blocked
- Wraps message saving in try-catch to handle `PermissionError` from `save_message()`

```python
async def handle_chat_message(self, data):
    # ... validation code ...
    
    # Check if messaging is blocked between these users
    is_blocked = await self.check_if_blocked()
    if is_blocked:
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': 'You cannot message this user because they have blocked you or you have blocked them'
        }))
        return
    
    try:
        # Save message to database
        message = await self.save_message(content, 'text')
        # ... broadcast message ...
    except PermissionError:
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': 'You cannot message this user because they have blocked you or you have blocked them'
        }))
```

#### b) `handle_file_message()` - File Messages
- Same blocking check as text messages
- Prevents file uploads to blocked users
- Returns appropriate error message

#### c) `handle_typing()` - Typing Indicators
- Checks if messaging is blocked
- Silently ignores typing indicators from blocked users (no error message)
- This prevents the other user from knowing when a blocked user is typing

### 3. Database Layer Safety

The existing `save_message()` and `save_file_message()` methods already include a check:

```python
@database_sync_to_async
def save_message(self, content, message_type):
    """Save message to database."""
    from django.utils import timezone
    conversation = Conversation.objects.get(id=self.conversation_id)
    # Prevent saving messages if listener blocked the talker
    if ListenerBlockedTalker.objects.filter(listener=conversation.listener, talker=conversation.talker).exists():
        raise PermissionError("Messaging is blocked between these users")
    message = Message.objects.create(...)
```

This provides a safety net at the database layer.

### 4. Conversation Access Control

The existing `get_conversation()` method already prevents blocked users from accessing the conversation:

```python
@database_sync_to_async
def get_conversation(self):
    """Get conversation and verify user is a participant."""
    try:
        conversation = Conversation.objects.get(id=self.conversation_id)
        # If listener has blocked the talker, disallow access to the conversation
        if ListenerBlockedTalker.objects.filter(listener=conversation.listener, talker=conversation.talker).exists():
            return None
        if self.user in [conversation.listener, conversation.talker]:
            return conversation
        return None
    except Conversation.DoesNotExist:
        return None
```

## User Flow

### Blocking Flow
1. Listener calls API: `POST /api/listener/profiles/block_talker/` with `{"talker_id": <id>}`
2. `ListenerBlockedTalker` record is created in the database
3. The talker is now blocked from messaging the listener

### Message Attempt After Blocking
1. Talker connects to WebSocket: `ws://domain/ws/chat/<conversation_id>/?token=<jwt_token>`
2. Connection is established (no check on connect)
3. Talker attempts to send a message via WebSocket
4. `handle_chat_message()` is invoked
5. `check_if_blocked()` returns `True`
6. Client receives error: "You cannot message this user because they have blocked you or you have blocked them"
7. Message is NOT saved to the database
8. Message is NOT broadcast to other users

### Unblocking Flow
1. Listener calls API: `POST /api/listener/profiles/unblock_talker/` with `{"talker_id": <id>}`
2. `ListenerBlockedTalker` record is deleted
3. The talker can now message the listener again

## Error Messages

### For Text/File Messages
```
"You cannot message this user because they have blocked you or you have blocked them"
```

### For Typing Indicators
- No error message (silently ignored)
- This prevents the blocked user from knowing their typing is being silently dropped

## Testing

See `tests_blocking.py` for comprehensive test cases covering:
- Blocked talker cannot send messages
- Unblocked talker can send messages
- Blocked talker cannot send files
- Typing indicators are not sent when blocked

## API Endpoints Related to Blocking

### Block a Talker
```
POST /api/listener/profiles/block_talker/
Content-Type: application/json

{
    "talker_id": 5
}

Response (201):
{
    "message": "Talker with ID 5 has been blocked",
    "talker_id": 5,
    "blocked_at": "2026-02-15T12:34:56.789Z"
}
```

### Unblock a Talker
```
POST /api/listener/profiles/unblock_talker/
Content-Type: application/json

{
    "talker_id": 5
}

Response (200):
{
    "message": "Talker with ID 5 has been unblocked",
    "talker_id": 5
}
```

### Get Blocked Talkers
```
GET /api/listener/profiles/blocked_talkers/

Response (200):
{
    "count": 2,
    "results": [
        {
            "talker_id": 5,
            "talker_email": "talker@example.com",
            "blocked_at": "2026-02-15T12:34:56.789Z"
        },
        ...
    ]
}
```

## Files Modified

### `core/chat/consumers.py`
- Updated `handle_chat_message()` to check for blocks before saving
- Updated `handle_file_message()` to check for blocks before saving
- Updated `handle_typing()` to silently ignore typing indicators if blocked
- Added new `check_if_blocked()` method

## Key Features

✅ Prevents text messages from being sent when blocked  
✅ Prevents file uploads from being sent when blocked  
✅ Prevents typing indicators from being sent when blocked  
✅ Clear error messages to users  
✅ Database-level safety checks  
✅ Async/await pattern consistent with existing code  
✅ No breaking changes to existing functionality  

## Security Considerations

- The check happens on both the WebSocket layer AND the database layer (defense in depth)
- Token-based authentication is still required to connect to WebSocket
- Error messages are clear but don't reveal sensitive information
- Typing indicators are silently ignored (no error message) to minimize information leakage

## Future Enhancements

1. Add reverse blocking (talker blocks listener)
2. Add temporary blocking (unblock after X days)
3. Add block list notifications
4. Add blocking analytics/metrics
5. Add UI alerts when blocked while chatting
