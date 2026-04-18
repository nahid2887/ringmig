# Automatic Booking Refund Guide

## Overview

When a listener deletes a booking before the session starts, the refund is automatically processed in two ways:

1. **Direct Stripe Refund**: Money is instantly refunded to the original payment card
2. **Talker Balance Credit**: The talker receives the refund amount as available balance

---

## How It Works

### Deletion Workflow

1. **Delete Request**: Listener calls `DELETE /api/bokking/session-bookings/{ID}/`
2. **Validation**: System checks if booking can be deleted (must be before session start time)
3. **Stripe Refund**: If payment was completed, automatically processes refund to card
4. **Balance Updates**:
   - Talker gets refund credited to available balance
   - Listener earnings (if released) are reversed from listener balance
5. **Notifications**: Both users receive WebSocket notifications

---

## API Endpoint

### Delete Booking (with Auto Refund)

**Endpoint**: `DELETE /api/bokking/session-bookings/{ID}/`

**Authentication**: Required (Bearer token)

**Response** (200 OK):
```json
{
  "message": "Booking deleted successfully.",
  "booking_id": "550e8400-e29b-41d4-a716-446655440000",
  "refund": {
    "stripe_refund": {
      "success": true,
      "refund_id": "re_1234567890",
      "amount": 25.00,
      "currency": "usd"
    },
    "stripe_refund_id": "re_1234567890",
    "amount_refunded_to_card": "25.00",
    "amount_credited_to_talker_balance": "25.00",
    "talker_balance": {
      "available_balance": "150.00",
      "total_earned": "500.00",
      "total_refunded": "25.00"
    },
    "listener_balance_reversed": "0.00"
  }
}
```

**Error** (400 Bad Request - Session Already Started):
```json
{
  "error": "Booking cannot be deleted after the meeting has started. Delete is allowed only before start time.",
  "booking_id": "550e8400-e29b-41d4-a716-446655440000",
  "start_time": "2026-04-20T14:30:00Z"
}
```

---

## Refund Details Explained

### Response Fields

**Stripe Refund**:
- `success`: Whether Stripe refund was processed successfully
- `refund_id`: Stripe refund transaction ID
- `amount`: Amount refunded in USD
- `currency`: Currency code (usd)

**Talker Balance Updates**:
- `available_balance`: New available balance after refund credit
- `total_earned`: Lifetime earnings (unchanged)
- `total_refunded`: Total amount refunded to this talker

**Listener Balance Changes**:
- `listener_balance_reversed`: If listener earnings were already released, this shows the reversal amount (usually 0 if earnings not yet released)

### Refund Flow Diagram

```
Listener Deletes Booking
        ↓
Check if can delete (before start time)
        ↓
If payment_completed_at exists:
    ├─→ Process Stripe refund to payment card
    ├─→ Store stripe_refund_id, refund_amount, refunded_at
    ├─→ Credit talker balance with refund_amount
    └─→ Reverse listener earnings if already released
        ↓
Delete booking from database
        ↓
Broadcast WebSocket notifications
        ↓
Return 200 with refund details
```

---

## Example Usage

### Delete a Booking with Python/Requests

```python
import requests
import json

BASE_URL = "http://10.10.13.27:8005/api"
BOOKING_ID = "550e8400-e29b-41d4-a716-446655440000"
TOKEN = "your_bearer_token"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

response = requests.delete(
    f"{BASE_URL}/bokking/session-bookings/{BOOKING_ID}/",
    headers=headers
)

if response.status_code == 200:
    data = response.json()
    print(f"Booking deleted successfully!")
    print(f"Stripe Refund ID: {data['refund']['stripe_refund_id']}")
    print(f"Refund Amount: ${data['refund']['amount_refunded_to_card']}")
    print(f"Talker New Balance: ${data['refund']['talker_balance']['available_balance']}")
else:
    print(f"Error: {response.json()}")
```

### Delete a Booking with cURL

```bash
curl -X DELETE \
  "http://10.10.13.27:8005/api/bokking/session-bookings/550e8400-e29b-41d4-a716-446655440000/" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

### Delete a Booking with JavaScript/Fetch

```javascript
const bookingId = "550e8400-e29b-41d4-a716-446655440000";
const token = "your_bearer_token";

const response = await fetch(
  `http://10.10.13.27:8005/api/bokking/session-bookings/${bookingId}/`,
  {
    method: "DELETE",
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json"
    }
  }
);

const data = await response.json();
if (response.ok) {
  console.log("Booking deleted successfully!");
  console.log(`Stripe Refund ID: ${data.refund.stripe_refund_id}`);
  console.log(`Refund Amount: $${data.refund.amount_refunded_to_card}`);
} else {
  console.error("Error:", data.error);
}
```

---

## What Gets Refunded

### Full Refund Amount
- **Amount**: Full booking price (talker paid amount)
- **Destination**: Original payment card (via Stripe)
- **Talker Balance**: Also receives the full amount as available balance credit

### Example
```
Booking Price:        $25.00
App Fee:              $2.50
Listener Gets:        $22.50

When Deleted:
├─ Stripe refunds:    $25.00 to card
└─ Talker receives:   $25.00 credit to available balance
```

### Important Notes
- If listener earnings were already released (session completed, earnings credited), the refund amount is **deducted** from listener's available balance
- Talker always receives the full refund amount in their balance
- Refund to payment card happens automatically via Stripe API

---

## Refund Status Tracking

### Check Booking Refund Status

**Endpoint**: `GET /api/bokking/session-bookings/{ID}/`

**Response**: Includes refund information

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "cancelled",
  "stripe_refund_id": "re_1234567890",
  "refund_amount": "25.00",
  "refunded_at": "2026-04-20T13:55:00Z",
  ...
}
```

### Fields Explained

| Field | Meaning |
|-------|---------|
| `stripe_refund_id` | Stripe refund transaction ID (null if not refunded) |
| `refund_amount` | Amount that was refunded |
| `refunded_at` | DateTime when refund was processed |
| `status` | Should be "cancelled" after deletion |

---

## Error Handling

### Scenario 1: Session Already Started

**You cannot delete a booking after it has started.**

```json
{
  "error": "Booking cannot be deleted after the meeting has started. Delete is allowed only before start time.",
  "booking_id": "550e8400-e29b-41d4-a716-446655440000",
  "start_time": "2026-04-20T14:30:00Z"
}
```

**Solution**: Only delete before the session start time

---

### Scenario 2: No Payment Completed

If a booking is deleted before payment was completed, no refund is processed:

```json
{
  "message": "Booking deleted successfully.",
  "booking_id": "550e8400-e29b-41d4-a716-446655440000",
  "refund": {
    "stripe_refund": null,
    "stripe_refund_id": null,
    "amount_refunded_to_card": "0.00",
    "amount_credited_to_talker_balance": "0.00",
    "talker_balance": {...},
    "listener_balance_reversed": "0.00"
  }
}
```

**Reason**: Payment wasn't completed, so nothing to refund

---

### Scenario 3: Stripe Error

If there's a Stripe API error during refund:

```json
{
  "message": "Booking deleted successfully.",
  "booking_id": "550e8400-e29b-41d4-a716-446655440000",
  "refund": {
    "stripe_refund": null,
    "stripe_refund_id": null,
    "error": "Stripe error: Invalid PaymentIntent ID"
  }
}
```

**Note**: Booking is still deleted, but check Stripe dashboard for refund status

---

## WebSocket Notifications

Both talker and listener receive real-time notifications:

### Talker Notification
```json
{
  "type": "booking_deleted_notification",
  "booking_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Booking {ID} was deleted. Refund processed: $25.00",
  "refund_amount": "25.00",
  "deleted_by_user_id": 5
}
```

### Listener Notification
```json
{
  "type": "booking_deleted_notification",
  "booking_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Booking {ID} was deleted.",
  "refund_amount": "25.00",
  "deleted_by_user_id": 8
}
```

---

## Database Schema

### SessionBooking Fields (New)

```sql
stripe_refund_id    VARCHAR(255)       -- Stripe refund transaction ID
refund_amount       DECIMAL(10,2)      -- Amount refunded  
refunded_at         DATETIME           -- When refund was processed
```

### Migration

Applied migration: `bokking/migrations/0008_sessionbooking_refund_amount_and_more.py`

---

## Summary

✅ **Automatic**: Refunds happen instantly when booking is deleted  
✅ **Safe**: Only allowed before session starts  
✅ **Transparent**: Full details returned in response  
✅ **Notified**: Both users receive real-time notifications  
✅ **Tracked**: Refund information stored in database for audit trail  

**Maximum Refund Window**: Until the booking's start_datetime  
**Refund Destination**: Original payment card (Stripe)  
**Secondary Credit**: Talker's available balance  
