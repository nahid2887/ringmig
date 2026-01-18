# WebSocket Chat - File Sending Guide

## Overview
Your chat system already supports **file sharing through WebSocket**! You can send files in real-time without the need for separate HTTP uploads.

## WebSocket Connection

**URL:** `ws://<your-server>/ws/chat/<conversation_id>/?token=YOUR_JWT_TOKEN`

**Example:**
```
ws://localhost/ws/chat/1/?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

## Message Types

### 1. Send Text Message

**Request:**
```json
{
  "type": "chat_message",
  "message": "Hello, how are you?"
}
```

**Response (broadcast to all users in conversation):**
```json
{
  "id": 1,
  "conversation": 1,
  "sender": {
    "id": 5,
    "email": "talker@example.com",
    "user_type": "talker",
    "full_name": "John Talker"
  },
  "content": "Hello, how are you?",
  "message_type": "text",
  "is_read": false,
  "created_at": "2026-01-14T10:00:00Z",
  "file_attachment": null
}
```

---

### 2. Send File Message

**Request (with base64 encoded file):**
```json
{
  "type": "file_message",
  "filename": "document.pdf",
  "file": "JVBERi0xLjQK...",  // base64 encoded file content
  "message": "Here's the document I mentioned"
}
```

**Response (broadcast):**
```json
{
  "id": 2,
  "conversation": 1,
  "sender": {
    "id": 5,
    "email": "talker@example.com",
    "user_type": "talker",
    "full_name": "John Talker"
  },
  "content": "Here's the document I mentioned",
  "message_type": "file",
  "is_read": false,
  "created_at": "2026-01-14T10:05:00Z",
  "file_attachment": {
    "id": 1,
    "file": "/media/chat_files/2026/01/14/document.pdf",
    "file_url": "http://localhost/media/chat_files/2026/01/14/document.pdf",
    "filename": "document.pdf",
    "file_size": 102400,
    "file_size_display": "100.0 KB",
    "file_type": "application/pdf",
    "uploaded_at": "2026-01-14T10:05:00Z"
  }
}
```

---

### 3. Typing Indicator

**Request:**
```json
{
  "type": "typing",
  "is_typing": true
}
```

**Response (to other user):**
```json
{
  "type": "typing",
  "user_id": 5,
  "user_email": "talker@example.com",
  "is_typing": true
}
```

---

### 4. Mark Messages as Read

**Request:**
```json
{
  "type": "mark_read"
}
```

**Response (to other user):**
```json
{
  "type": "read_receipt",
  "user_id": 5
}
```

---

## JavaScript Example

### Connect to WebSocket

```javascript
const token = 'YOUR_JWT_TOKEN';
const conversationId = 1;
const ws = new WebSocket(
  `ws://localhost/ws/chat/${conversationId}/?token=${token}`
);

ws.onopen = function(event) {
  console.log('Connected to chat');
};

ws.onmessage = function(event) {
  const data = JSON.parse(event.data);
  console.log('Message received:', data);
};

ws.onerror = function(error) {
  console.error('WebSocket error:', error);
};

ws.onclose = function(event) {
  console.log('Disconnected from chat');
};
```

### Send Text Message

```javascript
ws.send(JSON.stringify({
  type: 'chat_message',
  message: 'Hello there!'
}));
```

### Send File Message

```javascript
// Read file from input
const fileInput = document.getElementById('fileInput');
const file = fileInput.files[0];

// Convert file to base64
const reader = new FileReader();
reader.onload = function(e) {
  const base64Data = e.target.result.split(',')[1];
  
  ws.send(JSON.stringify({
    type: 'file_message',
    filename: file.name,
    file: base64Data,
    message: 'Check out this file!'
  }));
};
reader.readAsDataURL(file);
```

### Send Typing Indicator

```javascript
// Show typing status
ws.send(JSON.stringify({
  type: 'typing',
  is_typing: true
}));

// Stop typing
ws.send(JSON.stringify({
  type: 'typing',
  is_typing: false
}));
```

### Mark Messages as Read

```javascript
ws.send(JSON.stringify({
  type: 'mark_read'
}));
```

---

## File Upload Limitations

| Parameter | Limit | Notes |
|-----------|-------|-------|
| File Size | No hard limit* | Limited by server memory/settings |
| Filename | 255 chars | Max filename length |
| Base64 Overhead | ~33% increase | File size increases when base64 encoded |
| File Types | All types | Any file type supported |

*Default Django limit: 2.5GB per upload

---

## Error Responses

### Invalid Token
```
Connection closes with code 4001
```

### User Not in Conversation
```
Connection closes with code 4404
```

### Invalid JSON
```json
{
  "type": "error",
  "message": "Invalid JSON"
}
```

### Missing Required Fields
```json
{
  "type": "error",
  "message": "File data and filename are required"
}
```

---

## React Hook Example

```javascript
import { useEffect, useRef, useState } from 'react';

export function ChatComponent({ conversationId, token }) {
  const ws = useRef(null);
  const [messages, setMessages] = useState([]);
  const [isTyping, setIsTyping] = useState(false);
  
  useEffect(() => {
    ws.current = new WebSocket(
      `ws://localhost/ws/chat/${conversationId}/?token=${token}`
    );
    
    ws.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.type === 'connection_established') {
        console.log(data.message);
      } else if (data.id) {
        // It's a message
        setMessages(prev => [...prev, data]);
      } else if (data.type === 'typing') {
        setIsTyping(data.is_typing);
      }
    };
    
    return () => ws.current?.close();
  }, [conversationId, token]);
  
  const sendMessage = (text) => {
    ws.current.send(JSON.stringify({
      type: 'chat_message',
      message: text
    }));
  };
  
  const sendFile = (file) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      ws.current.send(JSON.stringify({
        type: 'file_message',
        filename: file.name,
        file: e.target.result.split(',')[1],
        message: `Shared: ${file.name}`
      }));
    };
    reader.readAsDataURL(file);
  };
  
  return (
    <div>
      <div>
        {messages.map(msg => (
          <div key={msg.id}>
            {msg.message_type === 'file' ? (
              <a href={msg.file_attachment.file_url}>
                📎 {msg.file_attachment.filename}
              </a>
            ) : (
              <p>{msg.content}</p>
            )}
          </div>
        ))}
      </div>
      
      {isTyping && <p>User is typing...</p>}
      
      <input 
        type="text" 
        onKeyPress={(e) => {
          if (e.key === 'Enter') {
            sendMessage(e.target.value);
            e.target.value = '';
          }
        }}
      />
      
      <input 
        type="file"
        onChange={(e) => sendFile(e.target.files[0])}
      />
    </div>
  );
}
```

---

## Features

✅ **Real-time text messaging** - Instant message delivery via WebSocket

✅ **File sharing** - Send any file type through WebSocket

✅ **Typing indicators** - Show when the other user is typing

✅ **Read receipts** - Notify when messages are read

✅ **Base64 encoding** - Automatic file encoding/decoding

✅ **Error handling** - Comprehensive error messages

✅ **Authentication** - JWT token-based WebSocket security

✅ **Multi-user broadcast** - Messages sent to all participants

---

## Setup Notes

1. **Channels installed** - Django Channels configured ✓
2. **WebSocket routes** - Configured in `routing.py` ✓
3. **Redis backend** - Channel layer using Redis ✓
4. **ASGI configured** - Using Daphne server ✓

Everything is ready to use! Start sending files through WebSocket now! 🚀

