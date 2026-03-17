# Complete Booking Flow with Stripe Payment

## 🎯 Complete API Flow

---

## PART 1: STRIPE PAYMENT SETUP (One-Time per User)

### Step 1: Create Stripe SetupIntent
**Endpoint:** `POST /api/booking/stripe/setup-intent/`

**Headers:**
```
Authorization: Bearer <talker_jwt_token>
```

**Response:**
```json
{
  "client_secret": "seti_1234567890_secret_abcdefghijklmn",
  "customer_id": "cus_ABC123XYZ",
  "setup_intent_id": "seti_1234567890"
}
```

### Step 2: Frontend - Collect Card with Stripe.js
```html
<!DOCTYPE html>
<html>
<head>
    <script src="https://js.stripe.com/v3/"></script>
</head>
<body>
    <form id="payment-form">
        <div id="card-element"></div>
        <button type="submit">Save Card</button>
    </form>

    <script>
        const stripe = Stripe('pk_test_YOUR_PUBLISHABLE_KEY');
        const elements = stripe.elements();
        const cardElement = elements.create('card');
        cardElement.mount('#card-element');

        const form = document.getElementById('payment-form');
        form.addEventListener('submit', async (event) => {
            event.preventDefault();

            // Get client_secret from your API
            const response = await fetch('http://10.10.13.27:8005/api/booking/stripe/setup-intent/', {
                method: 'POST',
                headers: {
                    'Authorization': 'Bearer YOUR_JWT_TOKEN'
                }
            });
            const {client_secret} = await response.json();

            // Confirm card setup
            const {setupIntent, error} = await stripe.confirmCardSetup(client_secret, {
                payment_method: {
                    card: cardElement,
                    billing_details: {
                        name: 'John Talker',
                        email: 'talker@example.com'
                    }
                }
            });

            if (error) {
                console.error(error);
            } else {
                // Save payment method ID
                const payment_method_id = setupIntent.payment_method;
                console.log('Payment Method ID:', payment_method_id); // pm_1234567890
                
                // Attach to customer
                await fetch('http://10.10.13.27:8005/api/booking/stripe/attach-card/', {
                    method: 'POST',
                    headers: {
                        'Authorization': 'Bearer YOUR_JWT_TOKEN',
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        payment_method_id: payment_method_id,
                        set_as_default: true
                    })
                });
            }
        });
    </script>
</body>
</html>
```

### Step 3: Get Saved Cards
**Endpoint:** `GET /api/booking/stripe/saved-cards/`

**Headers:**
```
Authorization: Bearer <talker_jwt_token>
```

**Response:**
```json
{
  "payment_methods": [
    {
      "id": "pm_1234567890",
      "brand": "visa",
      "last4": "4242",
      "exp_month": 12,
      "exp_year": 2026,
      "is_default": true
    }
  ],
  "customer_id": "cus_ABC123XYZ"
}
```

---

## PART 2: LISTENER CREATES EVENT TYPES

### Option A: Create Event via API (Recommended)
**Endpoint:** `POST /api/booking/listener/create-event/`

**Headers:**
```
Authorization: Bearer <listener_jwt_token>
Content-Type: application/json
```

**Payload:**
```json
{
  "title": "30 Minute Consultation",
  "slug": "30-min-consultation",
  "description": "A 30-minute one-on-one consultation session",
  "duration_minutes": 30,
  "price": 30.00,
  "location_type": "zoom",
  "buffer_before": 0,
  "buffer_after": 5
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "listener": 4,
  "listener_email": "listener@example.com",
  "listener_name": "John Listener",
  "cal_event_type_id": "123456",
  "title": "30 Minute Consultation",
  "slug": "30-min-consultation",
  "description": "A 30-minute one-on-one consultation session",
  "duration_minutes": 30,
  "price": "30.00",
  "is_active": true,
  "created_at": "2026-03-06T10:00:00Z",
  "updated_at": "2026-03-06T10:00:00Z"
}
```

### Option B: Sync from Cal.com
**Endpoint:** `POST /api/booking/event-types/sync_from_calcom/`

(If listener created events directly in Cal.com dashboard)

---

## PART 3: TALKER BOOKS AND PAYS

### Step 1: Browse Available Event Types
**Endpoint:** `GET /api/booking/listeners/4/event-types/`

**Headers:**
```
Authorization: Bearer <talker_jwt_token>
```

**Response:**
```json
[
  {
    "id": 1,
    "title": "30 Minute Consultation",
    "duration_minutes": 30,
    "price": "30.00",
    "description": "A 30-minute consultation"
  },
  {
    "id": 2,
    "title": "60 Minute Session",
    "duration_minutes": 60,
    "price": "50.00",
    "description": "A full hour session"
  }
]
```

### Step 2: Check Availability (Optional)
**Endpoint:** `GET /api/booking/availability/`

**Query Params:**
```
?listener_id=4&local_event_type_id=1&start_date=2026-03-07&end_date=2026-03-14&timezone=America/New_York
```

**Response:**
```json
{
  "slots": [
    {
      "time": "2026-03-07T09:00:00-05:00",
      "available": true
    },
    {
      "time": "2026-03-07T10:00:00-05:00",
      "available": true
    }
  ]
}
```

### Step 3: Create Booking with Payment
**Endpoint:** `POST /api/booking/create-booking-with-payment/`

**Headers:**
```
Authorization: Bearer <talker_jwt_token>
Content-Type: application/json
```

**Payload:**
```json
{
  "listener_id": 4,
  "local_event_type_id": 1,
  "start_time": "2026-03-07T09:00:00-05:00",
  "timezone": "America/New_York",
  "notes": "Looking forward to our session!",
  "payment_method_id": "pm_1234567890"
}
```

**Success Response (201 Created):**
```json
{
  "success": true,
  "message": "Booking created and payment processed successfully",
  "booking": {
    "id": 1,
    "cal_booking_id": "78901234",
    "cal_booking_uid": "abc123def456",
    "talker": 1,
    "talker_email": "talker@example.com",
    "talker_name": "Jane Talker",
    "listener": 4,
    "listener_email": "listener@example.com",
    "listener_name": "John Listener",
    "event_type": 1,
    "event_type_title": "30 Minute Consultation",
    "title": "30 Minute Consultation",
    "start_time": "2026-03-07T14:00:00Z",
    "end_time": "2026-03-07T14:30:00Z",
    "duration_minutes": 30,
    "timezone": "America/New_York",
    "meeting_url": "https://zoom.us/j/123456789",
    "location": "Zoom Video Call",
    "status": "confirmed",
    "is_paid": true,
    "amount": "30.00",
    "created_at": "2026-03-06T11:00:00Z"
  },
  "payment": {
    "id": 1,
    "amount": "30.00",
    "status": "succeeded",
    "payment_intent_id": "pi_1234567890"
  },
  "meeting_url": "https://zoom.us/j/123456789"
}
```

**Error Response (400 Bad Request):**
```json
{
  "error": "Payment failed: Your card was declined"
}
```

---

## 📋 SUMMARY OF ALL ENDPOINTS

### Stripe Payment Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/booking/stripe/setup-intent/` | POST | Create SetupIntent to save card |
| `/api/booking/stripe/saved-cards/` | GET | Get user's saved cards |
| `/api/booking/stripe/attach-card/` | POST | Attach payment method to customer |

### Listener Event Management
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/booking/listener/create-event/` | POST | Create event type |
| `/api/booking/listener/event/{id}/` | PATCH | Update event type |
| `/api/booking/listener/event/{id}/` | DELETE | Delete/deactivate event |
| `/api/booking/event-types/sync_from_calcom/` | POST | Sync from Cal.com |

### Booking Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/booking/listeners/{id}/event-types/` | GET | Browse listener's events |
| `/api/booking/availability/` | GET | Check available slots |
| `/api/booking/create-booking-with-payment/` | POST | Book + Pay in one call |
| `/api/booking/bookings/` | GET | Get my bookings |
| `/api/booking/bookings/{id}/cancel/` | POST | Cancel booking |

---

## 🔧 cURL Examples

### Save Card
```bash
# Step 1: Get SetupIntent
curl -X POST http://10.10.13.27:8005/api/booking/stripe/setup-intent/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Step 2: Use Stripe.js in frontend (see HTML example above)

# Step 3: Attach card
curl -X POST http://10.10.13.27:8005/api/booking/stripe/attach-card/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "payment_method_id": "pm_1234567890",
    "set_as_default": true
  }'
```

### Listener Creates Event
```bash
curl -X POST http://10.10.13.27:8005/api/booking/listener/create-event/ \
  -H "Authorization: Bearer LISTENER_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "30 Minute Consultation",
    "description": "A consultation session",
    "duration_minutes": 30,
    "price": 30.00,
    "buffer_after": 5
  }'
```

### Book with Payment
```bash
curl -X POST http://10.10.13.27:8005/api/booking/create-booking-with-payment/ \
  -H "Authorization: Bearer TALKER_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "listener_id": 4,
    "local_event_type_id": 1,
    "start_time": "2026-03-07T09:00:00-05:00",
    "timezone": "America/New_York",
    "notes": "Looking forward!",
    "payment_method_id": "pm_1234567890"
  }'
```

---

## ⚡ Quick Test Sequence

```bash
# 1. Listener creates event
POST /api/booking/listener/create-event/
{
  "title": "30 Min Session",
  "duration_minutes": 30,
  "price": 30.00,
  "buffer_after": 5
}

# 2. Talker saves card (use Stripe.js in frontend)
POST /api/booking/stripe/setup-intent/

# 3. Talker books and pays
POST /api/booking/create-booking-with-payment/
{
  "listener_id": 4,
  "local_event_type_id": 1,
  "start_time": "2026-03-07T09:00:00-05:00",
  "timezone": "America/New_York",
  "payment_method_id": "pm_1234567890"
}
```

Done! 🎉
