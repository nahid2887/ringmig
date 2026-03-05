# Tip Payment System Documentation

The Tip Payment System allows talkers to send monetary tips to listeners through Stripe payments. The system automatically handles the 10%/90% commission split and updates listener balances.

## Overview

- **Talkers** can send tips to listeners
- **10%** goes to admin as commission
- **90%** goes directly to listener's balance
- Payments processed through **Stripe**
- Automatic balance updates via webhooks

## API Endpoints

### 1. Create Tip Payment Intent

**Endpoint:** `POST /api/payment/tips/create-payment-intent/`

**Authentication:** Required (JWT Token) - Talker only

**Request Body:**
```json
{
    "listener_id": 5,
    "amount": "25.00",
    "message": "Great conversation! Thanks!"
}
```

**Response:**
```json
{
    "tip_id": 123,
    "stripe_client_secret": "pi_xxx_secret_xxx",
    "stripe_payment_intent_id": "pi_1234567890",
    "amount": "25.00",
    "admin_fee": "2.50",
    "listener_amount": "22.50"
}
```

### 2. View Sent Tips (Talkers)

**Endpoint:** `GET /api/payment/tips/my-sent-tips/`

**Authentication:** Required (JWT Token) - Talker only

**Response:**
```json
[
    {
        "id": 123,
        "listener": 5,
        "amount": "25.00",
        "admin_fee": "2.50",
        "listener_amount": "22.50",
        "status": "succeeded",
        "message": "Great conversation!",
        "created_at": "2026-03-05T10:30:00Z",
        "paid_at": "2026-03-05T10:31:15Z",
        "listener_details": {
            "id": 5,
            "email": "listener@example.com",
            "first_name": "John"
        }
    }
]
```

### 3. View Received Tips (Listeners)

**Endpoint:** `GET /api/payment/tips/my-received-tips/`

**Authentication:** Required (JWT Token) - Listener only

**Response:**
```json
[
    {
        "id": 123,
        "talker": 10,
        "amount": "25.00",
        "admin_fee": "2.50",
        "listener_amount": "22.50",
        "status": "succeeded",
        "message": "Great conversation!",
        "created_at": "2026-03-05T10:30:00Z",
        "paid_at": "2026-03-05T10:31:15Z",
        "talker_details": {
            "id": 10,
            "email": "talker@example.com",
            "first_name": "Jane"
        }
    }
]
```

### 4. Check Listener Balance

**Endpoint:** `GET /api/listener/balance/my-balance/`

**Authentication:** Required (JWT Token) - Listener only

**Response:**
```json
{
    "available_balance": "147.50",
    "total_earned": "200.00",
    "last_updated": "2026-03-05T10:31:15Z"
}
```

## Payment Flow

### 1. Frontend Integration

```javascript
// 1. Create tip payment intent
const response = await fetch('/api/payment/tips/create-payment-intent/', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${jwtToken}`
    },
    body: JSON.stringify({
        listener_id: 5,
        amount: "25.00",
        message: "Thanks for the great conversation!"
    })
});

const { stripe_client_secret, tip_id } = await response.json();

// 2. Use Stripe.js to process payment
const stripe = Stripe('pk_your_publishable_key');
const { error, paymentIntent } = await stripe.confirmCardPayment(
    stripe_client_secret,
    {
        payment_method: {
            card: cardElement,
            billing_details: {
                name: 'Customer Name',
            },
        }
    }
);

if (!error && paymentIntent.status === 'succeeded') {
    // Payment successful - webhook will handle balance update
    console.log('Tip sent successfully!');
}
```

### 2. Backend Processing

1. **Payment Intent Creation:**
   - Validates listener exists and is active
   - Creates Tip record with `pending` status
   - Calculates 10%/90% split automatically
   - Creates Stripe Payment Intent
   - Returns client secret to frontend

2. **Webhook Processing:**
   - Receives `payment_intent.succeeded` event
   - Updates tip status to `succeeded`
   - Adds 90% to listener's balance
   - Logs transaction for admin tracking

3. **Balance Updates:**
   - Automatic via `ListenerBalance.add_earnings()`
   - Thread-safe with database transactions
   - Updates both `available_balance` and `total_earned`

## Commission Split

- **Total Amount:** What talker pays
- **Admin Fee (10%):** Platform commission
- **Listener Amount (90%):** Goes to listener balance

Example for $25.00 tip:
- Total: $25.00
- Admin: $2.50 (10%)
- Listener: $22.50 (90%)

## Database Models

### Tip Model

```python
class Tip(models.Model):
    talker = models.ForeignKey(User, related_name='sent_tips')
    listener = models.ForeignKey(User, related_name='received_tips')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    admin_fee = models.DecimalField(max_digits=10, decimal_places=2)
    listener_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20)  # pending, succeeded, failed
    message = models.TextField(blank=True)
    stripe_payment_intent_id = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
```

### ListenerBalance Model

```python
class ListenerBalance(models.Model):
    listener = models.OneToOneField(User, related_name='balance_account')
    available_balance = models.DecimalField(default=0.00)
    total_earned = models.DecimalField(default=0.00)
    updated_at = models.DateTimeField(auto_now=True)
```

## Error Handling

### Common Errors

1. **403 Forbidden:** Only talkers can send tips
2. **404 Not Found:** Listener doesn't exist or inactive
3. **400 Bad Request:** Invalid amount (minimum $0.01)
4. **500 Internal Error:** Stripe payment processing error

### Payment Failures

- Failed payments update tip status to `failed`
- No balance changes occur for failed payments
- Failure reasons stored for debugging
- Webhooks handle both success and failure cases

## Security Features

- **JWT Authentication:** All endpoints require valid tokens
- **User Type Validation:** Role-based access control
- **Stripe Webhooks:** Secure payment confirmation
- **Database Transactions:** Atomic balance updates
- **Input Validation:** Amount limits and data sanitization

## Testing

Use the provided test script:

```bash
cd /path/to/ringmig
python example_tip_usage.py
```

This will:
- Create a sample tip
- Simulate payment processing
- Verify balance updates
- Show commission split calculation

## Monitoring

Admin dashboard shows:
- All tip transactions
- Commission earnings (10%)
- Payment statuses
- Failed payment reasons
- Revenue tracking

## Integration with Existing System

The tip system integrates seamlessly with:
- Existing Stripe configuration
- Listener balance system
- Webhook infrastructure
- User authentication
- Admin dashboard

Tips appear in the same balance as call earnings and can be withdrawn through the existing payout system.