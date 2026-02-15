# Talker Call History & Transaction API Documentation

## Overview
Two new APIs have been added to retrieve talker's complete call history and detailed transaction information. These endpoints provide comprehensive call and payment details for every call made by the talker.

---

## API Endpoints

### 1. Get All Call History
**Retrieve all call history for the authenticated talker**

- **URL**: `/api/talker/profiles/call-history/`
- **Method**: `GET`
- **Authentication**: Required (Bearer Token)
- **Permission**: Must be authenticated as a talker
- **Tags**: `Talker Call History`

#### Request
```bash
curl -X GET "http://localhost:8000/api/talker/profiles/call-history/" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

#### Response (200 OK)
```json
{
  "count": 3,
  "results": [
    {
      "id": 1,
      "listener_id": 5,
      "listener_email": "listener@example.com",
      "listener_name": "Alice Johnson",
      "status": "ended",
      "call_type": "audio",
      "total_minutes_purchased": 30,
      "minutes_used": "28.50",
      "started_at": "2026-02-08T14:30:00Z",
      "ended_at": "2026-02-08T14:58:30Z",
      "end_reason": "Normal completion",
      "duration_in_minutes": 28.5,
      "amount_paid": "14.99",
      "created_at": "2026-02-08T14:30:00Z"
    },
    {
      "id": 2,
      "listener_id": 6,
      "listener_email": "another_listener@example.com",
      "listener_name": "Bob Smith",
      "status": "ended",
      "call_type": "video",
      "total_minutes_purchased": 60,
      "minutes_used": "45.25",
      "started_at": "2026-02-07T10:00:00Z",
      "ended_at": "2026-02-07T10:45:15Z",
      "end_reason": "Time expired",
      "duration_in_minutes": 45.25,
      "amount_paid": "29.99",
      "created_at": "2026-02-07T10:00:00Z"
    }
  ]
}
```

#### Response Fields
| Field | Type | Description |
|-------|------|-------------|
| id | integer | Call session ID |
| listener_id | integer | ID of the listener |
| listener_email | string | Email address of the listener |
| listener_name | string | Full name of the listener |
| status | string | Call status: `connecting`, `active`, `ended`, `timeout`, `failed` |
| call_type | string | Type of call: `audio` or `video` |
| total_minutes_purchased | integer | Total minutes purchased for this call |
| minutes_used | decimal | Actual minutes used during the call |
| started_at | datetime | When the call started (ISO 8601 format) |
| ended_at | datetime | When the call ended (ISO 8601 format) |
| end_reason | string | Reason why the call ended |
| duration_in_minutes | decimal | Calculated call duration |
| amount_paid | decimal | Total amount paid for this call |
| created_at | datetime | When the call session was created |

#### Error Responses
- **401 Unauthorized**: Missing or invalid authentication token
- **403 Forbidden**: User is not authenticated as a talker

---

### 2. Get Call History Details with Transaction Information
**Retrieve detailed information about a specific call including complete transaction details**

- **URL**: `/api/talker/profiles/call-history/{call_session_id}/`
- **Method**: `GET`
- **Authentication**: Required (Bearer Token)
- **Permission**: Must be authenticated as a talker and own the call session
- **Tags**: `Talker Call History`

#### Request
```bash
curl -X GET "http://localhost:8000/api/talker/profiles/call-history/1/" \
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
  "listener_id": 5,
  "listener_email": "listener@example.com",
  "listener_full_name": "Alice Johnson",
  "listener_profile": {
    "id": 5,
    "email": "listener@example.com",
    "full_name": "Alice Johnson",
    "user_type": "listener"
  },
  "status": "ended",
  "call_type": "audio",
  "total_minutes_purchased": 30,
  "minutes_used": "28.50",
  "started_at": "2026-02-08T14:30:00Z",
  "ended_at": "2026-02-08T14:58:30Z",
  "end_reason": "Normal completion",
  "last_warning_sent": true,
  "duration_in_minutes": 28.5,
  "call_package_details": {
    "id": 101,
    "package_name": "30 Minutes Premium Package",
    "duration_minutes": 30,
    "price": "14.99",
    "app_fee": "1.50",
    "listener_amount": "13.49",
    "status": "confirmed"
  },
  "transaction_details": {
    "transaction_id": 101,
    "talker_id": 10,
    "listener_id": 5,
    "amount_paid": "14.99",
    "currency": "USD",
    "app_commission": "1.50",
    "listener_payout": "13.49",
    "payment_status": "confirmed",
    "minutes_purchased": 30,
    "minutes_used": "28.50",
    "created_at": "2026-02-08T14:30:00Z",
    "payment_method": "pm_1234567890",
    "stripe_charge_id": "ch_1234567890"
  },
  "agora_channel_name": "call_session_1_channel",
  "created_at": "2026-02-08T14:30:00Z",
  "updated_at": "2026-02-08T14:58:30Z"
}
```

#### Response Fields - Call Information
| Field | Type | Description |
|-------|------|-------------|
| id | integer | Call session ID |
| listener_id | integer | ID of the listener |
| listener_email | string | Email of the listener |
| listener_full_name | string | Full name of the listener |
| listener_profile | object | Listener profile details |
| status | string | Call status |
| call_type | string | Type of call (`audio` or `video`) |
| total_minutes_purchased | integer | Total minutes purchased |
| minutes_used | decimal | Actual minutes used |
| started_at | datetime | Call start time |
| ended_at | datetime | Call end time |
| end_reason | string | Reason call ended |
| last_warning_sent | boolean | Whether 3-minute warning was sent |
| duration_in_minutes | decimal | Calculated call duration |
| agora_channel_name | string | Agora channel used for the call |

#### Response Fields - Call Package
| Field | Type | Description |
|-------|------|-------------|
| id | integer | Package ID |
| package_name | string | Name of the call package |
| duration_minutes | integer | Duration in minutes |
| price | decimal | Total price in USD |
| app_fee | decimal | Application commission |
| listener_amount | decimal | Amount listener receives |
| status | string | Payment status |

#### Response Fields - Transaction Details ⭐
| Field | Type | Description |
|-------|------|-------------|
| transaction_id | integer | Unique transaction ID |
| talker_id | integer | ID of the talker (your ID) |
| listener_id | integer | ID of the listener |
| amount_paid | decimal | Total amount you paid in USD |
| currency | string | Currency (always USD) |
| app_commission | decimal | Commission kept by the app |
| listener_payout | decimal | Amount listener receives |
| payment_status | string | Payment status: `pending`, `confirmed`, `refunded` |
| minutes_purchased | integer | Minutes purchased for this call |
| minutes_used | decimal | Actual minutes used |
| created_at | datetime | Transaction creation time |
| payment_method | string | Stripe payment method ID |
| stripe_charge_id | string | Stripe charge ID for tracking |

#### Error Responses
- **401 Unauthorized**: Missing or invalid authentication token
- **403 Forbidden**: User is not a talker or not authorized to view this call
- **404 Not Found**: Call session not found or doesn't belong to the authenticated talker

---

## Implementation Details

### Files Modified

1. **[talker/serializers.py](talker/serializers.py#L6-L160)**
   - Added `TalkerCallHistorySerializer` for listing all call history
   - Added `TalkerCallHistoryDetailSerializer` for detailed call with transaction info

2. **[talker/views.py](talker/views.py#L1-L20)**
   - Updated imports to include Swagger decorators and new serializers
   - Added two new action methods to `TalkerProfileViewSet`:
     - `call_history()` - Get all calls with summary info
     - `call_history_detail()` - Get single call with full transaction details

### Data Models Used
- **CallSession**: Represents an active or completed call session
- **CallPackage**: Purchased call package with payment details
- **User**: Listener information

### Query Optimization
Both endpoints use `select_related()` to optimize database queries:
- `select_related('listener', 'call_package__package')`

---

## Usage Examples

### Example 1: Get all call history
```bash
GET /api/talker/profiles/call-history/
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

Response shows summary of all calls with amount paid for each.

### Example 2: View transaction details for call #42
```bash
GET /api/talker/profiles/call-history/42/
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

Response includes:
- Complete call details
- Listener profile information
- Call package breakdown (price, app fee, listener payout)
- Complete transaction information with Stripe charge IDs

### Example 3: Calculate total earnings
```javascript
// Frontend code to calculate earnings
const response = await fetch('/api/talker/profiles/call-history/');
const data = await response.json();
const totalEarnings = data.results.reduce((sum, call) => {
  if (call.call_package_details) {
    return sum + parseFloat(call.call_package_details.listener_amount);
  }
  return sum;
}, 0);
console.log(`Total Earnings: $${totalEarnings.toFixed(2)}`);
```

---

## Transaction Details Explanation

### Payment Breakdown Example
If a talker purchases a 30-minute call package for **$14.99**:

```
Total Amount Paid:        $14.99 (100%)
├── App Commission:       $1.50  (10%)
└── Listener Payout:      $13.49 (90%)
```

The `transaction_details` field includes all this information plus:
- **Stripe charge ID** for payment verification
- **Payment method** used
- **Payment status** (pending, confirmed, or refunded)

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

## Security

- Both endpoints require authentication (Bearer token)
- Talkers can only view their own call history
- Authorization checks prevent access to other talkers' call data
- All queries filtered by `talker=request.user`
- Transaction details are only visible to the talker who made the payment

---

## Testing the APIs

### Using Postman
1. Set Authorization type to "Bearer Token"
2. Paste your JWT token
3. GET `http://localhost:8000/api/talker/profiles/call-history/`
4. GET `http://localhost:8000/api/talker/profiles/call-history/{call_id}/`

### Using cURL
```bash
TOKEN="your_jwt_token"

# Get all call history
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/talker/profiles/call-history/

# Get specific call with transaction details
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/talker/profiles/call-history/1/
```

---

## Performance Considerations

- **All Calls**: O(n) where n = number of calls made by talker
- **Single Call**: O(1) - Direct database lookup by ID
- Database queries use select_related for optimal performance
- Results ordered by most recent first (`-created_at`)

---

## API Response Summary

### Call History List
- **Quick overview** of all calls
- **Amount paid** for each call
- **Duration** in minutes
- **Call status** (completed, failed, etc.)

### Call History Detail
- **Complete call information** including timing
- **Listener profile** information
- **Call package breakdown** with pricing
- **Full transaction details** including:
  - Amount paid and how it's split
  - App commission vs listener payout
  - Stripe payment information for verification

---

## Future Enhancements

Potential improvements:
1. Add filtering by call status, date range, listener
2. Add sorting options (amount, duration, date)
3. Add pagination for large result sets
4. Add earnings summary endpoint
5. Add export to CSV/PDF functionality
6. Add call ratings/reviews history
7. Add refund tracking
8. Add reconciliation reports

---

## Related APIs

For listener perspective, see: [LISTENER_CALL_ATTEMPTS_API.md](LISTENER_CALL_ATTEMPTS_API.md)
