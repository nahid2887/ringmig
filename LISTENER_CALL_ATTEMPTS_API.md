# Listener Call Attempts API Documentation

## Overview
Two new APIs have been added to retrieve listener's call attempts (previous calls received from talkers). These endpoints provide comprehensive call history information with full details.

---

## API Endpoints

### 1. Get All Call Attempts
**Retrieve all call attempts for the authenticated listener**

- **URL**: `/api/listener/profiles/call-attempts/`
- **Method**: `GET`
- **Authentication**: Required (Bearer Token)
- **Permission**: Must be authenticated as a listener
- **Tags**: `Listener Call Attempts`

#### Request
```bash
curl -X GET "http://localhost:8000/api/listener/profiles/call-attempts/" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

#### Response (200 OK)
```json
{
  "count": 5,
  "results": [
    {
      "id": 1,
      "talker_id": 10,
      "talker_email": "talker@example.com",
      "talker_name": "John Doe",
      "status": "ended",
      "call_type": "audio",
      "total_minutes_purchased": 30,
      "minutes_used": "28.50",
      "started_at": "2026-02-08T10:30:00Z",
      "ended_at": "2026-02-08T10:58:30Z",
      "end_reason": "Normal completion",
      "created_at": "2026-02-08T10:30:00Z"
    },
    {
      "id": 2,
      "talker_id": 11,
      "talker_email": "another_talker@example.com",
      "talker_name": "Jane Smith",
      "status": "ended",
      "call_type": "video",
      "total_minutes_purchased": 15,
      "minutes_used": "15.00",
      "started_at": "2026-02-07T15:20:00Z",
      "ended_at": "2026-02-07T15:35:00Z",
      "end_reason": "Time expired",
      "created_at": "2026-02-07T15:20:00Z"
    }
  ]
}
```

#### Response Fields
| Field | Type | Description |
|-------|------|-------------|
| id | integer | Call session ID |
| talker_id | integer | ID of the talker who initiated the call |
| talker_email | string | Email address of the talker |
| talker_name | string | Full name of the talker |
| status | string | Call status: `connecting`, `active`, `ended`, `timeout`, `failed` |
| call_type | string | Type of call: `audio` or `video` |
| total_minutes_purchased | integer | Total minutes purchased for this call |
| minutes_used | decimal | Actual minutes used during the call |
| started_at | datetime | When the call started (ISO 8601 format) |
| ended_at | datetime | When the call ended (ISO 8601 format) |
| end_reason | string | Reason why the call ended |
| created_at | datetime | When the call session was created |

#### Error Responses
- **401 Unauthorized**: Missing or invalid authentication token
- **403 Forbidden**: User is not authenticated as a listener

---

### 2. Get Call Attempt Details
**Retrieve detailed information about a specific call attempt**

- **URL**: `/api/listener/profiles/call-attempts/{call_session_id}/`
- **Method**: `GET`
- **Authentication**: Required (Bearer Token)
- **Permission**: Must be authenticated as a listener and own the call session
- **Tags**: `Listener Call Attempts`

#### Request
```bash
curl -X GET "http://localhost:8000/api/listener/profiles/call-attempts/1/" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

#### URL Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| call_session_id | integer | ID of the call session (required) |

#### Response (200 OK)
```json
{
  "id": 1,
  "talker_id": 10,
  "talker_email": "talker@example.com",
  "talker_full_name": "John Doe",
  "talker_profile": {
    "id": 10,
    "email": "talker@example.com",
    "full_name": "John Doe",
    "user_type": "talker"
  },
  "status": "ended",
  "call_type": "audio",
  "total_minutes_purchased": 30,
  "minutes_used": "28.50",
  "started_at": "2026-02-08T10:30:00Z",
  "ended_at": "2026-02-08T10:58:30Z",
  "end_reason": "Normal completion",
  "last_warning_sent": true,
  "duration_in_minutes": 28.50,
  "call_package_details": {
    "id": 101,
    "package_name": "30 Minutes Premium Package",
    "duration_minutes": 30,
    "price": "15.99",
    "status": "confirmed"
  },
  "agora_channel_name": "call_session_1_channel",
  "created_at": "2026-02-08T10:30:00Z",
  "updated_at": "2026-02-08T10:58:30Z"
}
```

#### Response Fields
| Field | Type | Description |
|-------|------|-------------|
| id | integer | Call session ID |
| talker_id | integer | ID of the talker |
| talker_email | string | Email of the talker |
| talker_full_name | string | Full name of the talker |
| talker_profile | object | Talker profile details |
| status | string | Call status |
| call_type | string | Type of call (`audio` or `video`) |
| total_minutes_purchased | integer | Total minutes purchased |
| minutes_used | decimal | Actual minutes used |
| started_at | datetime | Call start time |
| ended_at | datetime | Call end time |
| end_reason | string | Reason call ended |
| last_warning_sent | boolean | Whether 3-minute warning was sent |
| duration_in_minutes | decimal | Calculated call duration |
| call_package_details | object | Details of the call package used |
| agora_channel_name | string | Agora channel used for the call |
| created_at | datetime | Session creation time |
| updated_at | datetime | Last update time |

#### Error Responses
- **401 Unauthorized**: Missing or invalid authentication token
- **403 Forbidden**: User is not a listener or not authorized to view this call
- **404 Not Found**: Call session not found or doesn't belong to the authenticated listener

---

## Implementation Details

### Files Modified/Created

1. **[listener/serializers.py](listener/serializers.py#L1-L90)**
   - Added `ListenerCallAttemptSerializer` for listing all call attempts
   - Added `ListenerCallAttemptDetailSerializer` for detailed call information

2. **[listener/views.py](listener/views.py#L1-L20)**
   - Updated imports to include Swagger decorators
   - Added two new action methods to `ListenerProfileViewSet`:
     - `call_attempts()` - Get all calls
     - `call_attempt_detail()` - Get single call details

### Data Models Used
- **CallSession**: Represents an active or completed call session
- **CallPackage**: Purchased call package instance
- **User**: Talker information

### Query Optimization
Both endpoints use `select_related()` to optimize database queries:
- `select_related('talker', 'call_package__package')`

---

## Usage Examples

### Example 1: Get all calls for a listener
```bash
GET /api/listener/profiles/call-attempts/
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Example 2: View details of call #42
```bash
GET /api/listener/profiles/call-attempts/42/
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Example 3: Filter calls by status in frontend
After fetching all calls, filter by status:
```javascript
const activeCalls = response.results.filter(call => call.status === 'active');
const completedCalls = response.results.filter(call => call.status === 'ended');
```

---

## Integration with Swagger/OpenAPI

Both endpoints are fully documented in Swagger with:
- Clear operation descriptions
- Request/response schemas
- Proper HTTP status codes (200, 401, 403, 404)
- Parameter documentation
- Error handling examples

Access the Swagger UI at: `http://localhost:8000/api/docs/`

---

## Pagination

To add pagination support in future updates, modify the endpoints to use Django REST Framework's pagination classes:
```python
from rest_framework.pagination import PageNumberPagination

class CallHistoryPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
```

---

## Security

- Both endpoints require authentication (Bearer token)
- Listeners can only view their own call attempts
- Authorization checks prevent access to other listeners' call data
- All queries filtered by `listener=request.user`

---

## Testing the APIs

### Using Postman
1. Set Authorization type to "Bearer Token"
2. Paste your JWT token
3. GET `http://localhost:8000/api/listener/profiles/call-attempts/`
4. GET `http://localhost:8000/api/listener/profiles/call-attempts/{call_id}/`

### Using cURL
```bash
TOKEN="your_jwt_token"

# Get all call attempts
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/listener/profiles/call-attempts/

# Get specific call details
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/listener/profiles/call-attempts/1/
```

---

## Performance Considerations

- **All Calls**: O(n) where n = number of calls for the listener
- **Single Call**: O(1) - Direct database lookup by ID
- Database queries use select_related for optimal performance
- Results ordered by most recent first (`-created_at`)

---

## Future Enhancements

Potential improvements:
1. Add filtering by call status, date range
2. Add sorting options (duration, date, talker name)
3. Add pagination for large result sets
4. Add call ratings/reviews association
5. Add call transcript/notes if available
6. Add call cost breakdown details
