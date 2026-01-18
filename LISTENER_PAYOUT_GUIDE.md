# 💰 Listener Payout Setup Guide

## How Listener Payments Work

### You DON'T Need:
- ❌ Listener's card number
- ❌ Listener's credit card details
- ❌ Card to receive money

### You DO Need:
- ✅ Listener's **bank account** information
- ✅ **Stripe Connect** account (recommended)
- ✅ Identity verification

---

## Payment Flow

```
Talker pays with card ($30)
         ↓
Your Stripe Account receives $30
         ↓
App keeps 10% ($3)
         ↓
Listener receives 90% ($27) → Bank Account
```

---

## Setup Options

### Option 1: Stripe Connect (Recommended) 🌟

**Listeners connect their own bank accounts through Stripe:**

#### For Listeners:
1. Navigate to payout settings
2. Click "Connect Payout Account"
3. Complete Stripe onboarding (5 minutes)
4. Provide:
   - Bank account details (routing + account number)
   - Tax information (SSN/EIN for US)
   - Identity verification
5. Receive automatic payouts!

#### API Endpoints:

**Create/Get Connect Account:**
```http
POST /api/payment/listener/connect/
Authorization: Bearer {listener_token}
```

Response:
```json
{
  "url": "https://connect.stripe.com/setup/...",
  "account_id": "acct_xxx"
}
```

**Check Account Status:**
```http
GET /api/payment/listener/connect/
Authorization: Bearer {listener_token}
```

Response:
```json
{
  "has_account": true,
  "is_verified": true,
  "payouts_enabled": true,
  "charges_enabled": true
}
```

**Process Payout (Admin Only):**
```http
POST /api/payment/payouts/{payout_id}/process/
Authorization: Bearer {admin_token}
```

---

### Option 2: Manual Bank Transfer

**Collect listener bank info and process manually:**

1. Listener provides:
   - Bank name
   - Account holder name
   - Routing number (for US)
   - Account number
   - IBAN (for international)

2. Admin processes payouts through Stripe Dashboard

---

## Frontend Integration

### Listener Onboarding Flow

```javascript
// 1. Check if listener has payout account
async function checkPayoutAccount() {
  const response = await fetch('/api/payment/listener/connect/', {
    headers: {
      'Authorization': `Bearer ${listenerToken}`
    }
  });
  
  const data = await response.json();
  
  if (!data.has_account) {
    // Need to create account
    return createPayoutAccount();
  } else if (!data.is_verified) {
    // Account exists but not verified
    return 'Complete verification';
  } else {
    // All good!
    return 'Can receive payouts';
  }
}

// 2. Create payout account
async function createPayoutAccount() {
  const response = await fetch('/api/payment/listener/connect/', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${listenerToken}`
    }
  });
  
  const data = await response.json();
  
  // Redirect listener to Stripe onboarding
  window.location.href = data.url;
}

// 3. After return from Stripe
// User is redirected to: /api/payment/listener/connect/return/
// You can show success message
```

---

## Admin Payout Processing

### Manual Payout Process:

1. **View Pending Payouts:**
   ```http
   GET /api/payment/payouts/
   ```

2. **Verify Booking Completed:**
   - Check booking status is "completed"
   - Verify session actually happened

3. **Process Payout:**
   ```http
   POST /api/payment/payouts/{payout_id}/process/
   ```

4. **Money Transfer:**
   - Stripe automatically transfers to listener's bank
   - Usually takes 2-7 business days

---

## Testing with Your Keys

Your Stripe Test Keys are now configured:
```
Publishable: pk_test_51LNtvVGNuHFmwqJX...
Secret: sk_test_51LNtvVGNuHFmwqJX...
```

### Test Mode Features:
- No real money transfers
- Instant "bank account" verification
- Can test full flow without actual banks

### Test Bank Account (US):
```
Routing: 110000000
Account: 000123456789
```

---

## Complete Example: End-to-End

### 1. Talker Books Session:
```bash
# Talker pays $30
POST /api/payment/bookings/create_booking/
{
  "listener_id": 1,
  "package_id": 1  # 20 min for $30
}
# Payment Intent created
```

### 2. Payment Succeeds:
```bash
# Stripe webhook triggers
# Booking confirmed
# ListenerPayout created ($27)
```

### 3. Session Completed:
```bash
POST /api/payment/bookings/{id}/complete_session/
# Session marked complete
```

### 4. Admin Processes Payout:
```bash
POST /api/payment/payouts/{id}/process/
# $27 transferred to listener's bank
```

### 5. Listener Receives Money:
```bash
# Money arrives in listener's bank account
# 2-7 business days
```

---

## Important Notes

### For Listeners:
- Need valid bank account (not card!)
- Must verify identity with Stripe
- Can track earnings in app
- Payouts processed after session completion

### For You (Platform Owner):
- Hold funds until session completes
- Can implement auto-payout or manual approval
- Stripe handles all bank transfers
- 10% commission stays in your account

### Tax & Legal:
- Listeners are independent contractors
- Issue 1099 forms (US) for earnings
- Listeners responsible for own taxes
- Keep records of all payouts

---

## Webhook for Automated Payouts

You can automate payouts when booking completes:

```python
# In payment/signals.py
@receiver(post_save, sender=Booking)
def auto_process_payout(sender, instance, **kwargs):
    if instance.status == 'completed':
        payout = instance.listener_payout
        if payout.status == 'pending':
            # Auto-trigger payout
            process_payout(payout)
```

---

## Security Best Practices

1. **Never store bank account numbers**
   - Let Stripe handle storage
   - Use Connect accounts

2. **Verify session completion**
   - Don't pay for cancelled sessions
   - Check actual duration

3. **Fraud detection**
   - Monitor suspicious patterns
   - Require identity verification

4. **Dispute handling**
   - Hold payouts for 7 days
   - Allow refund window

---

## Common Issues & Solutions

### "Listener not verified"
- Listener needs to complete Stripe onboarding
- Redirect to: `POST /api/payment/listener/connect/`

### "Payout failed"
- Check bank account is valid
- Verify listener account is active
- Check Stripe balance sufficient

### "Cannot process payout"
- Ensure booking status is "completed"
- Verify payment succeeded
- Check listener has verified account

---

## Next Steps

1. ✅ Stripe keys configured in `.env`
2. Run migrations: `python manage.py migrate`
3. Create booking packages
4. Test listener onboarding flow
5. Configure webhook in Stripe Dashboard
6. Test end-to-end payment flow

Need help? Check the Stripe Connect docs:
https://stripe.com/docs/connect
