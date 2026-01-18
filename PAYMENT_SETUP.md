# Payment System Setup Guide

## Overview
This payment system integrates Stripe for booking sessions between talkers and listeners with a 90/10 revenue split.

## Revenue Split
- **Listener receives:** 90% of payment
- **App commission:** 10% of payment

### Examples:
- 20 minutes for $30 → Listener gets $27, App gets $3
- 40 minutes for $50 → Listener gets $45, App gets $5

## Setup Instructions

### 1. Install Dependencies
```bash
cd core
pip install stripe==11.2.0
```

### 2. Configure Environment Variables
Create or update your `.env` file in the project root:

```env
# Stripe Configuration
STRIPE_PUBLISHABLE_KEY=pk_test_your_publishable_key_here
STRIPE_SECRET_KEY=sk_test_your_secret_key_here
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret_here
```

**Get your keys from:** https://dashboard.stripe.com/test/apikeys

### 3. Run Migrations
```bash
python manage.py makemigrations payment
python manage.py migrate
```

### 4. Create Booking Packages
Create packages via Django admin or shell:

```python
python manage.py shell
```

```python
from payment.models import BookingPackage

# Create 20-minute package for $30
BookingPackage.objects.create(
    name="20 Minute Session",
    duration_minutes=20,
    price=30.00,
    app_fee_percentage=10.00,
    description="Quick consultation session",
    is_active=True
)

# Create 40-minute package for $50
BookingPackage.objects.create(
    name="40 Minute Session",
    duration_minutes=40,
    price=50.00,
    app_fee_percentage=10.00,
    description="Extended consultation session",
    is_active=True
)

# Create 60-minute package for $70
BookingPackage.objects.create(
    name="60 Minute Session",
    duration_minutes=60,
    price=70.00,
    app_fee_percentage=10.00,
    description="Full hour consultation",
    is_active=True
)
```

### 5. Configure Stripe Webhook
1. Go to: https://dashboard.stripe.com/test/webhooks
2. Click "Add endpoint"
3. Enter your webhook URL: `https://yourdomain.com/api/payment/stripe/webhook/`
4. Select events to listen to:
   - `payment_intent.succeeded`
   - `payment_intent.payment_failed`
   - `charge.refunded`
5. Copy the webhook signing secret to your `.env` file

## API Endpoints

### Public Endpoints

#### Get Stripe Configuration
```
GET /api/payment/stripe/config/
```
Returns the publishable key for frontend Stripe integration.

#### List Available Packages
```
GET /api/payment/packages/
```
Returns all active booking packages.

### Authenticated Endpoints

#### Create Booking with Payment Intent
```
POST /api/payment/bookings/create_booking/
```
Request body:
```json
{
  "listener_id": 1,
  "package_id": 1,
  "scheduled_at": "2026-01-20T15:00:00Z",
  "notes": "Looking forward to our session"
}
```

Response:
```json
{
  "booking": {
    "id": 1,
    "talker": 2,
    "listener": 1,
    "package": 1,
    "status": "pending",
    "total_amount": "30.00",
    "app_fee": "3.00",
    "listener_amount": "27.00",
    ...
  },
  "payment": {
    "client_secret": "pi_xxx_secret_xxx",
    "payment_intent_id": "pi_xxx",
    "amount": "30.00",
    "currency": "usd"
  }
}
```

#### List User's Bookings
```
GET /api/payment/bookings/
```
Returns bookings filtered by user (talker or listener).

#### Start Booking Session
```
POST /api/payment/bookings/{id}/start_session/
```
Marks booking as "in_progress" and records start time.

#### Complete Booking Session
```
POST /api/payment/bookings/{id}/complete_session/
```
Marks booking as "completed" and calculates actual duration.

#### Cancel Booking
```
POST /api/payment/bookings/{id}/cancel/
```
Request body:
```json
{
  "reason": "Schedule conflict"
}
```

#### List Payments
```
GET /api/payment/payments/
```
View payment history.

#### List Payouts (Listeners only)
```
GET /api/payment/payouts/
```
View payout history.

#### Get Pending Earnings (Listeners only)
```
GET /api/payment/payouts/pending_earnings/
```
Returns:
```json
{
  "pending_earnings": "135.00",
  "total_earned": "540.00"
}
```

### Webhook Endpoint
```
POST /api/payment/stripe/webhook/
```
Handles Stripe webhook events (used by Stripe, not your frontend).

## Frontend Integration

### 1. Install Stripe.js
```bash
npm install @stripe/stripe-js
```

### 2. Create Booking Flow

```javascript
import { loadStripe } from '@stripe/stripe-js';

// Initialize Stripe with your publishable key
const stripePromise = loadStripe('pk_test_your_key');

// Create booking
async function createBooking(listenerId, packageId) {
  const response = await fetch('/api/payment/bookings/create_booking/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${accessToken}`
    },
    body: JSON.stringify({
      listener_id: listenerId,
      package_id: packageId,
      scheduled_at: '2026-01-20T15:00:00Z',
      notes: 'Looking forward to our session'
    })
  });
  
  const data = await response.json();
  return data;
}

// Confirm payment
async function confirmPayment(clientSecret) {
  const stripe = await stripePromise;
  
  const { error, paymentIntent } = await stripe.confirmCardPayment(clientSecret, {
    payment_method: {
      card: cardElement, // Your Stripe card element
      billing_details: {
        email: userEmail
      }
    }
  });
  
  if (error) {
    console.error('Payment failed:', error);
  } else if (paymentIntent.status === 'succeeded') {
    console.log('Payment successful!');
  }
}
```

## Testing

### Test Card Numbers (Stripe Test Mode)
- **Success:** 4242 4242 4242 4242
- **Declined:** 4000 0000 0000 0002
- **Requires authentication:** 4000 0025 0000 3155

Use any future expiry date, any 3-digit CVC, and any postal code.

## Admin Features

Access Django admin at `/admin/` to:
- Create/edit booking packages
- View all bookings
- Manage payments
- Process listener payouts
- Monitor Stripe accounts

## Models Overview

### BookingPackage
Defines pricing tiers (20min/$30, 40min/$50, etc.)

### Booking
Tracks session between talker and listener

### Payment
Stores Stripe payment information

### ListenerPayout
Tracks listener earnings (created automatically when payment succeeds)

### StripeCustomer
Links users to Stripe customer IDs

### StripeListenerAccount
For Stripe Connect (future feature for automated payouts)

## Next Steps

1. **Set up Stripe Connect** for automated listener payouts
2. **Add refund functionality** for cancelled bookings
3. **Implement dispute handling**
4. **Add subscription packages** for recurring bookings
5. **Create payout schedules** (weekly/monthly)

## Support
For Stripe integration help: https://stripe.com/docs
