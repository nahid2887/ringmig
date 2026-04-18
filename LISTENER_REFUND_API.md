# Listener Booking Refund API - Auto Stripe Refund

## Overview

The endpoint `/api/listener/balance/refund-booking/` allows listeners to refund a booking. When refunded:

1. **Stripe Refund**: Money automatically refunded to talker's original payment card
2. **Talker Balance Credit**: Talker also receives refund as available balance
3. **Listener Balance Deduction**: Amount deducted from listener's available balance
4. **Tracking**: All refunds tracked with Stripe refund ID for audit trail

---

## Endpoint Details

### Refund Booking (Auto Stripe Refund)

**Endpoint**: `POST /api/listener/balance/refund-booking/`

**Authentication**: Required (Bearer token - listener only)

**Request Body**:
```json
{
  "booking_id": "550e8400-e29b-41d4-a716-446655440000",
  "refund_amount": "10.00",  // optional - full amount if not provided
  "reason": "Changed my mind" // optional
}
```

**Response** (200 OK):
```json
{
  "message": "Refund processed successfully",
  "booking_id": "550e8400-e29b-41d4-a716-446655440000",
  "refund_amount": "10.00",
  "stripe_refund": {
    "success": true,
    "refund_id": "re_1234567890",
    "amount": 10.00,
    "currency": "usd"
  },
  "already_refunded": "10.00",
  "remaining_refundable": "12.50",
  "listener_balance": {
    "available_balance": "89.99",
    "total_earned": "500.00"
  },
  "talker_balance": {
    "talker_id": 5,
    "available_balance": "160.00",
    "total_earned": "1000.00",
    "total_refunded": "10.00"
  }
}
```

---

## How It Works

### Refund Processing Flow

```
Listener Initiates Refund
    ↓
Validate: Listener owns booking, Payment completed
    ↓
Check: Available balance sufficient for refund
    ↓
Process Stripe Refund
    ├─→ Refund goes to talker's original payment card
    ├─→ Store Stripe refund ID
    └─→ Update booking with refund details
    ↓
Update Balances
    ├─→ Deduct from listener available_balance
    └─→ Credit talker with refund amount + balance
    ↓
Update Refund Tracker
    └─→ Track cumulative refunds (max 100%)
    ↓
Broadcast WebSocket Notifications
    ├─→ Listener: "Refund processed..."
    └─→ Talker: "You received a refund... (processed to your payment card)"
    ↓
Return 200 with Stripe refund details
```

---

## Usage Examples

### Example 1: Full Refund

Listener wants to fully refund a booking:

```bash
curl -X POST "http://10.10.13.27:8005/api/listener/balance/refund-booking/" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "booking_id": "550e8400-e29b-41d4-a716-446655440000"
  }'
```

**Result**: Full listener_amount refunded to talker's card

---

### Example 2: Partial Refund

Listener wants to refund part of a booking:

```bash
curl -X POST "http://10.10.13.27:8005/api/listener/balance/refund-booking/" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "booking_id": "550e8400-e29b-41d4-a716-446655440000",
    "refund_amount": "5.00",
    "reason": "Session shortened"
  }'
```

**Result**: $5.00 refunded to talker's card + balance credit

---

### Example 3: Python Request

```python
import requests
from decimal import Decimal

BASE_URL = "http://10.10.13.27:8005/api"
TOKEN = "your_bearer_token"

response = requests.post(
    f"{BASE_URL}/listener/balance/refund-booking/",
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    },
    json={
        "booking_id": "550e8400-e29b-41d4-a716-446655440000",
        "refund_amount": "10.00",
        "reason": "Talker didn't show up"
    }
)

if response.status_code == 200:
    data = response.json()
    print(f"✅ Refund successful!")
    print(f"Stripe Refund ID: {data['stripe_refund']['refund_id']}")
    print(f"Amount: ${data['refund_amount']}")
    print(f"Listener new balance: ${data['listener_balance']['available_balance']}")
else:
    print(f"❌ Error: {response.json()}")
```

---

## Key Points

### What Gets Refunded

| Item | Amount | Destination |
|------|--------|-------------|
| Talker's Payment Card | Full refund amount | Stripe (original card) |
| Talker Balance Credit | Full refund amount | Internal balance |
| Listener Balance Deduction | Full refund amount | Deducted from available |

### Example Amounts

```
Booking Details:
  Talker Paid:      $25.00
  App Fee:          $2.50
  Listener Got:     $22.50

Listener Refunds $10.00:
  ├─ Stripe refunds to card:  $10.00
  ├─ Talker balance +:        $10.00
  └─ Listener balance -:      $10.00
```

---

## Validation Rules

### When Refund Is Allowed

✅ Listener owns the booking  
✅ Booking payment was completed  
✅ Listener has sufficient balance  
✅ Refund amount > 0  
✅ Total refunded ≤ 100% of listener_amount  

### When Refund Is NOT Allowed

❌ Listener doesn't own booking (403)  
❌ Payment not completed yet (400)  
❌ Insufficient listener balance (400)  
❌ Refund amount ≤ 0 (400)  
❌ Already fully refunded (400)  
❌ Refund exceeds remaining amount (400)  

---

## Error Responses

### 403 Forbidden
```json
{
  "error": "Only listeners can refund booking earnings"
}
```

### 400 Bad Request - Insufficient Balance
```json
{
  "error": "Insufficient listener balance for refund",
  "available_balance": "5.00",
  "required_amount": "10.00"
}
```

### 400 Bad Request - Fully Refunded
```json
{
  "error": "This booking is already fully refunded (100%)",
  "max_refundable": "22.50",
  "already_refunded": "22.50",
  "remaining_refundable": "0.00"
}
```

### 400 Bad Request - Missing Booking ID
```json
{
  "error": "booking_id is required"
}
```

### 404 Not Found
```json
{
  "error": "Booking not found for this listener"
}
```

---

## Response Fields Explained

### Refund Information
- `refund_amount`: Amount refunded (string, USD)
- `stripe_refund`: Stripe API response with success status
- `stripe_refund.refund_id`: Stripe transaction ID
- `stripe_refund.amount`: Refunded amount in dollars
- `stripe_refund.currency`: Currency code (usd)

### Refund Tracking
- `already_refunded`: Cumulative refunded for this booking
- `remaining_refundable`: How much more can be refunded (max 100%)

### Balances
- `listener_balance.available_balance`: Listener's new available balance
- `talker_balance.available_balance`: Talker's new available balance
- `talker_balance.total_refunded`: Talker's lifetime refunds

---

## Real-Time Notifications

### Listener Notification (WebSocket)
```json
{
  "type": "booking_refund_notification",
  "message": "Refund processed for booking {ID}: $10.00",
  "booking_id": "550e8400-e29b-41d4-a716-446655440000",
  "refund_amount": "10.00"
}
```

### Talker Notification (WebSocket)
```json
{
  "type": "booking_refund_notification",
  "message": "You received a refund of $10.00 for booking {ID} (processed to your payment card)",
  "booking_id": "550e8400-e29b-41d4-a716-446655440000",
  "refund_amount": "10.00"
}
```

---

## Database Tracking

### SessionBooking Fields Updated
- `stripe_refund_id`: Stripe refund transaction ID
- `refund_amount`: Amount refunded
- `refunded_at`: When refund was processed

### ListenerBookingRefund Record
- `total_refunded`: Cumulative refund amount (prevents >100%)
- `created_at` / `updated_at`: Timestamps

---

## Stripe Integration

### How Refunds Work

1. **Payment Intent Stored**: Talker's payment creates a Stripe PaymentIntent
2. **Refund Created**: Using `stripe.Refund.create()` with payment_intent ID
3. **Instant Processing**: Money returned to original card immediately
4. **Tracking**: Refund ID stored for verification

### Refund Status

Stripe refunds typically:
- Process immediately (status: `succeeded`)
- Show in talker's card account within 3-5 business days
- Are tracked by Stripe refund ID for disputes

---

## Feature Comparison

| Feature | Booking Deletion (Talker) | Listener Refund | Admin Refund |
|---------|--------------------------|-----------------|--------------|
| Initiator | Talker | Listener | Admin |
| Stripe Refund | ✅ Yes | ✅ Yes | N/A |
| Balance Credit | ✅ Talker | ✅ Talker | N/A |
| Listener Impact | Earnings reversed | Balance deducted | N/A |
| Partial Refund | ❌ No (full only) | ✅ Yes | N/A |
| Max Refund | 100% | 100% per booking | N/A |

---

## Testing the Endpoint

### Test 1: Full Refund
```bash
POST /api/listener/balance/refund-booking/
{
  "booking_id": "550e8400-e29b-41d4-a716-446655440000"
}
```
**Expected**: Full listener_amount refunded

### Test 2: Partial Refund
```bash
POST /api/listener/balance/refund-booking/
{
  "booking_id": "550e8400-e29b-41d4-a716-446655440000",
  "refund_amount": "5.50"
}
```
**Expected**: Partial refund, remaining available for future refunds

### Test 3: Multiple Partial Refunds
```bash
# First refund: $10.00
POST /api/listener/balance/refund-booking/
{
  "booking_id": "550e8400-e29b-41d4-a716-446655440000",
  "refund_amount": "10.00"
}

# Second refund: $12.50 (remaining)
POST /api/listener/balance/refund-booking/
{
  "booking_id": "550e8400-e29b-41d4-a716-446655440000",
  "refund_amount": "12.50"
}
```
**Expected**: Two separate Stripe refunds, cumulative max 100%

---

## Summary

✅ **Automatic Stripe Refunds** - Money goes directly to talker's payment card  
✅ **Dual Credit** - Talker gets card refund + balance credit  
✅ **Flexible Amount** - Full or partial refunds supported  
✅ **Max 100%** - Can't refund more than listener earned  
✅ **Real-time Notifications** - Both parties notified instantly  
✅ **Full Audit Trail** - Stripe refund ID stored for verification  

**When to Use**: Listener wants to compensate talker for any reason while also processing card refund instantly.
