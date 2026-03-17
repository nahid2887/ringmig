# Cal.com Booking Payment System Documentation

## Overview
The Cal.com booking system now works exactly like the call-packages purchase system, with integrated Stripe payment and automatic balance splitting.

## Payment Flow

### 1. Payment Split (90/10 Rule)
- **90%** → Credited to listener's balance after booking completes
- **10%** → Platform/admin fee

### 2. Booking Creation with Payment

**Endpoint:** `POST /api/booking/create-booking-with-payment/`

**Request Body:**
```json
{
    "listener_id": 17,
    "local_event_type_id": 2,
    "start_time": "2024-01-20T15:00:00Z",
    "timezone": "UTC",
    "notes": "Looking forward to our session",
    "payment_method_id": "pm_1234567890"  // Optional
}
```

**Response (Immediate Payment Success):**
```json
{
    "success": true,
    "message": "Booking created and payment processed successfully",
    "booking": {
        "id": 123,
        "cal_booking_id": "456",
        "talker": 3,
        "listener": 17,
        "event_type": 2,
        "title": "30 Minute Listening Session",
        "start_time": "2024-01-20T15:00:00Z",
        "end_time": "2024-01-20T15:30:00Z",
        "duration_minutes": 30,
        "timezone": "UTC",
        "meeting_url": "https://meet.google.com/xyz",
        "status": "confirmed",
        "is_paid": true,
        "amount": "25.00",
        "admin_fee": "2.50",
        "listener_amount": "22.50"
    },
    "payment": {
        "id": 789,
        "amount": "25.00",
        "admin_fee": "2.50",
        "listener_amount": "22.50",
        "status": "succeeded",
        "payment_intent_id": "pi_1234567890"
    },
    "meeting_url": "https://meet.google.com/xyz"
}
```

**Response (Payment Requires Action - Like Call Packages):**
```json
{
    "success": true,
    "message": "Booking created. Please complete payment.",
    "booking_id": 123,
    "status": "pending_payment",
    "payment_info": {
        "client_secret": "pi_1234567890_secret_xyz",
        "payment_intent_id": "pi_1234567890",
        "amount": "25.00",
        "admin_fee": "2.50",
        "listener_amount": "22.50",
        "currency": "usd",
        "status": "requires_action"
    },
    "stripe_payment_link": {
        "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_...",
        "dashboard_url": "https://dashboard.stripe.com/test/payments/pi_1234567890",
        "instructions": "Use the checkout_url to complete payment in browser",
        "test_card": "4242 4242 4242 4242"
    },
    "booking": {
        "id": 123,
        "status": "pending",
        "amount": "25.00"
    }
}
```

### 3. Payment Webhook
When payment succeeds (via webhook), the system:
1. Updates booking status to "confirmed"
2. Creates the booking in Cal.com database
3. Stores meeting URL locally

### 4. Booking Completion & Balance Credit

**Endpoint:** `POST /api/booking/complete-booking/{booking_id}/`

**When to call:** After the meeting ends or listener marks it complete

**Who can call:** 
- The listener who received the booking
- Admin users

**Request:** No body required

**Response:**
```json
{
    "success": true,
    "message": "Booking completed and listener balance credited successfully",
    "booking_id": 123,
    "listener_credited": {
        "status": "success",
        "amount_credited": "22.50",
        "new_balance": "145.50",
        "listener_email": "nalodi6236@creteanu.com"
    }
}
```

## Implementation Details

### Database Fields (Booking Model)
```python
# Payment tracking
is_paid = models.BooleanField(default=False)
amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

# Payment splitting (90% to listener, 10% admin fee)
admin_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
listener_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
listener_credited = models.BooleanField(default=False)

# Stripe payment tracking
stripe_payment_intent_id = models.CharField(max_length=255, blank=True)
stripe_customer_id = models.CharField(max_length=255, blank=True)
stripe_charge_id = models.CharField(max_length=255, blank=True)
```

### Payment Functions

#### `create_booking_payment_intent(booking, payment_method_id=None)`
Located in: `booking/booking_payments.py`

Creates Stripe payment intent and checkout session. Automatically calculates:
- Total amount from booking.amount
- Admin fee (10%)
- Listener amount (90%)

Returns payment info with:
- payment_intent_id
- client_secret
- checkout_url (stripe_payment_link)
- payment status

#### `credit_listener_balance_for_booking(booking)`
Located in: `booking/booking_payments.py`

Credits 90% of booking amount to listener's balance. Called when booking is completed.

Requirements:
- Booking status must be "completed"
- Booking must be paid (is_paid=True)
- Not already credited (listener_credited=False)

Updates:
- Listener's available_balance
- Listener's total_earned
- Sets booking.listener_credited = True

## Testing Flow

### 1. Test Booking Creation
```bash
# Create booking with payment
curl -X POST http://10.10.13.27:8005/api/booking/create-booking-with-payment/ \
  -H "Authorization: Bearer <talker_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "listener_id": 17,
    "local_event_type_id": 2,
    "start_time": "2024-01-20T15:00:00Z",
    "timezone": "UTC",
    "notes": "Test booking",
    "payment_method_id": "pm_card_visa"
  }'
```

### 2. Complete Payment
If payment requires action, use the `checkout_url` from response.

Or use test card: `4242 4242 4242 4242`

### 3. Check Booking Status
```bash
curl http://10.10.13.27:8005/api/booking/bookings/{booking_id}/ \
  -H "Authorization: Bearer <token>"
```

### 4. Complete Booking (After Meeting)
```bash
curl -X POST http://10.10.13.27:8005/api/booking/complete-booking/{booking_id}/ \
  -H "Authorization: Bearer <listener_token>"
```

### 5. Check Listener Balance
```bash
curl http://10.10.13.27:8005/api/listener/balance/my-balance/ \
  -H "Authorization: Bearer <listener_token>"
```

## Comparison with Call-Packages

| Feature | Call-Packages | Cal.com Bookings |
|---------|---------------|------------------|
| Payment Split | 90/10 | 90/10 ✓ |
| Stripe Checkout Link | Yes | Yes ✓ |
| Pending Status | Yes | Yes ✓ |
| Balance Credit | On call completion | On booking completion ✓ |
| Payment Webhook | Yes | Yes ✓ |
| Refund Support | Yes | Yes ✓ |

## Files Modified/Created

### Created Files:
1. `booking/booking_payments.py` - Payment helper functions
2. `booking/migrations/0002_add_payment_split_fields.py` - Database migration

### Modified Files:
1. `booking/models.py` - Added payment split fields
2. `booking/payment_booking_views.py` - Updated to match call-packages pattern
3. `booking/urls.py` - Added complete-booking endpoint

## Key Features

✅ **90/10 Payment Split** - Automatic calculation and storage
✅ **Stripe Checkout Link** - Returns payment URL like call-packages
✅ **Pending → Confirmed Flow** - Same as call-packages purchase
✅ **Automatic Balance Credit** - When booking completes, listener gets 90%
✅ **Cal.com Integration** - Booking created in Cal.com database after payment
✅ **Webhook Support** - Handles Stripe payment webhooks
✅ **Refund Support** - Can refund failed bookings

## Notes

- Admin fee is stored but not automatically transferred (manual withdrawal by platform)
- Listener balance is credited AFTER booking completes, not immediately on payment
- Use the complete-booking endpoint to mark meeting as done and credit listener
- Listener balance can be viewed at `/api/listener/balance/my-balance/`
- Payment flow exactly matches call-packages for consistency

## Future Enhancements

- [ ] Automatic booking completion via Cal.com webhook when meeting ends
- [ ] Email notifications for payment confirmation
- [ ] Automatic refund on booking cancellation
- [ ] Support for partial refunds
- [ ] Admin dashboard for fee collection
