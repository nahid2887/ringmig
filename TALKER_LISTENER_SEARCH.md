# Talker Listener Search API - Quick Guide

## Overview
Added fast search functionality to both listener browsing endpoints. Talkers can now search for listeners by their first name or last name.

---

## Endpoints with Search

### 1. Get All Listeners (with Search)
**Endpoint**: `GET /api/talker/profiles/all_listeners/`

**Query Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| search | string | No | Search by listener's first_name or last_name (case-insensitive) |

**Examples**:
```bash
# Get all listeners (no filter)
curl -X GET "http://localhost:8000/api/talker/profiles/all_listeners/" \
  -H "Authorization: Bearer TALKER_TOKEN"

# Search by first name
curl -X GET "http://localhost:8000/api/talker/profiles/all_listeners/?search=alice" \
  -H "Authorization: Bearer TALKER_TOKEN"

# Search by last name
curl -X GET "http://localhost:8000/api/talker/profiles/all_listeners/?search=johnson" \
  -H "Authorization: Bearer TALKER_TOKEN"

# Search (works with any part of name)
curl -X GET "http://localhost:8000/api/talker/profiles/all_listeners/?search=john" \
  -H "Authorization: Bearer TALKER_TOKEN"
```

**Response**:
```json
{
  "count": 2,
  "search_query": "alice",
  "results": [
    {
      "id": "5",
      "user_email": "alice@example.com",
      "user_type": "listener",
      "full_name": "Alice Johnson",
      "gender": "female",
      "location": "New York, USA",
      "experience_level": "advanced",
      "bio": "Professional listener with 5+ years experience",
      "hourly_rate": "25.00",
      "is_available": true,
      "average_rating": 4.8,
      "total_hours": 500
    },
    {
      "id": "12",
      "user_email": "alice.smith@example.com",
      "user_type": "listener",
      "full_name": "Alice Smith",
      "gender": "female",
      "location": "Los Angeles, USA",
      "experience_level": "intermediate",
      "bio": "Great listener, always here to help",
      "hourly_rate": "20.00",
      "is_available": true,
      "average_rating": 4.5,
      "total_hours": 250
    }
  ]
}
```

---

### 2. Get Available Listeners Only (with Search)
**Endpoint**: `GET /api/talker/profiles/available_listeners/`

**Query Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| search | string | No | Search by listener's first_name or last_name (case-insensitive) |

**Examples**:
```bash
# Get all available listeners (no filter)
curl -X GET "http://localhost:8000/api/talker/profiles/available_listeners/" \
  -H "Authorization: Bearer TALKER_TOKEN"

# Search for available listeners named John
curl -X GET "http://localhost:8000/api/talker/profiles/available_listeners/?search=john" \
  -H "Authorization: Bearer TALKER_TOKEN"

# Search for available listeners with last name Smith
curl -X GET "http://localhost:8000/api/talker/profiles/available_listeners/?search=smith" \
  -H "Authorization: Bearer TALKER_TOKEN"
```

**Response**:
```json
{
  "count": 1,
  "search_query": "john",
  "results": [
    {
      "id": "8",
      "user_email": "john@example.com",
      "user_type": "listener",
      "full_name": "John Doe",
      "gender": "male",
      "location": "Boston, USA",
      "experience_level": "expert",
      "bio": "Licensed therapist with 10+ years experience",
      "hourly_rate": "35.00",
      "is_available": true,
      "average_rating": 4.9,
      "total_hours": 1000
    }
  ]
}
```

---

## Search Features

### ✅ Case-Insensitive
- Search "alice" matches "Alice", "ALICE", "aLiCe"

### ✅ Partial Matching
- Search "john" matches "john", "johnson", "johnathan"
- Search "smith" matches "smith", "smithson"

### ✅ Both First and Last Names
- Search "alice" will find listeners with first_name="alice" OR last_name="alice"
- Search "john smith" will NOT work (searches both fields separately, not as phrase)

### ✅ Empty Search
- If search parameter is empty or not provided, all listeners are returned

### ✅ Maintains Filters
- Still excludes blocked listeners
- `all_listeners` returns ALL listeners (available or not)
- `available_listeners` returns only available listeners
- Both are sorted by rating (highest first)

---

## Real-World Usage Examples

### Example 1: Find a Specific Listener by Name
Talker wants to find "Alice Johnson" who they remember from before:
```bash
GET /api/talker/profiles/all_listeners/?search=alice
```
Returns all listeners with "alice" in first_name or last_name.

### Example 2: Search for Available Expert Listeners
Talker wants available listeners with name "expert" (won't work, that's not a name field):
```bash
GET /api/talker/profiles/available_listeners/?search=smith
```
Returns only available listeners named Smith.

### Example 3: Quick Browse Without Search
Talker wants to browse all listeners, doesn't use search parameter:
```bash
GET /api/talker/profiles/all_listeners/
```
Returns all listeners (except those who blocked them), sorted by rating.

---

## Response Structure

Both endpoints return:
```json
{
  "count": 5,                    // Number of results matching search
  "search_query": "alice",       // The search term used (null if not searched)
  "results": [                   // Array of listener profiles
    { listener data },
    { listener data },
    ...
  ]
}
```

---

## Search Implementation

**How it works**:
1. Get list of listeners who blocked the talker
2. Query all listeners EXCEPT those who blocked the talker
3. If search parameter provided:
   - Filter by `first_name__icontains` OR `last_name__icontains`
4. Sort by average_rating (highest first)
5. Return results with count and search query

---

## Performance

- **Database Query**: Single optimized query with `Q` objects
- **Blocking Check**: First retrieves blocked listener IDs
- **Search**: Uses PostgreSQL/MySQL's case-insensitive pattern matching
- **Index**: Relies on database indexes on first_name and last_name fields

---

## Error Handling

**401 Unauthorized** - If talker not authenticated
```json
{
  "detail": "Authentication credentials were not provided."
}
```

**403 Forbidden** - If not a talker user
```json
{
  "detail": "Permission denied"
}
```

---

## Swagger Documentation

Both endpoints are fully documented in Swagger:
- **Base URL**: `http://localhost:8000/api/docs/`
- **Tag**: "Talker Browse Listeners"
- **Parameters**: Shows search query parameter clearly

---

## Testing

### Test Search by First Name
```bash
curl -X GET "http://10.10.13.27:8005/api/talker/profiles/all_listeners/?search=alice" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Test Search by Last Name
```bash
curl -X GET "http://10.10.13.27:8005/api/talker/profiles/all_listeners/?search=johnson" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Test Available Listeners with Search
```bash
curl -X GET "http://10.10.13.27:8005/api/talker/profiles/available_listeners/?search=john" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Updated Endpoints Summary

| Endpoint | Method | Search Support | Filters |
|----------|--------|---|---------|
| `/api/talker/profiles/all_listeners/` | GET | ✅ Yes | Excludes blocked, sorted by rating |
| `/api/talker/profiles/available_listeners/` | GET | ✅ Yes | Only available, excludes blocked, sorted by rating |

Both endpoints support optional `?search=` query parameter for fast listener search by name.
