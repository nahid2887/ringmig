# Stripe Connect API Guide - Listener Payout System

## Overview

This guide explains how to integrate Stripe Connect into your application, allowing listeners to connect their Stripe accounts and receive payouts.

---

## System Architecture

### Account Types
- **Express Account**: Used for listeners - simpler onboarding, Stripe handles compliance
- **Custom Account**: Not used in this system (more complex)

### Payment Flow
```
Listener Account Connection → Stripe Verification → Payout Enabled → Funds Transfer
```

---

## API Endpoints

### 1. **Create/Get Stripe Connect Setup Link**

**Endpoint:** `POST /api/payment/listener/connect/`

**Purpose:** Create a new Stripe Connect account or generate an onboarding link for an existing one

**Authentication:** Required (Bearer token)

**Request:**
```json
{
  "Content-Type": "application/json"
}
```

**Response (Success - 200):**
```json
{
  "success": true,
  "url": "https://connect.stripe.com/setup/e/acct_1TSqAMAxCCHEibaN/wQ3rOmorgIa0",
  "account_id": "acct_1TSqAMAxCCHEibaN",
  "type": "account_onboarding",
  "expires_at": 1706260000,
  "message": "Complete your Stripe account setup using the link above",
  "is_new_account": true,
  "instructions": [
    "1. Click the URL above or copy it to your browser",
    "2. Accept the Stripe Service Agreement",
    "3. Provide your personal information and business details",
    "4. Add your banking information for payouts",
    "5. Agree to the Stripe Connected Account Agreement",
    "6. You will be redirected back when complete"
  ]
}
```

**Response (Error - 403):**
```json
{
  "error": "Only listeners can create payout accounts"
}
```

**Response (Error - 400):**
```json
{
  "error": "Failed to create payout account",
  "details": "Stripe error message here"
}
```

**Example Usage:**
```bash
curl -X POST https://dev.backend.ring-mig.com/api/payment/listener/connect/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

---

### 2. **Get Stripe Connect Account Status**

**Endpoint:** `GET /api/payment/listener/connect/`

**Purpose:** Check the current status of a listener's Stripe Connect account

**Authentication:** Required (Bearer token)

**Response (Account Exists - 200):**
```json
{
  "has_account": true,
  "account_id": "acct_1TSqAMAxCCHEibaN",
  "email": "listener@example.com",
  "is_verified": true,
  "details_submitted": true,
  "payouts_enabled": true,
  "charges_enabled": true,
  "verification_status": "Complete ✓",
  "requirements": null,
  "country": "US",
  "created_at": "2026-01-25T10:00:00Z",
  "updated_at": "2026-01-25T10:00:00Z",
  "type": "express",
  "business_profile": {
    "url": "https://example.com"
  },
  "next_steps": [
    "✓ Your account is fully set up and verified"
  ]
}
```

**Response (No Account - 200):**
```json
{
  "has_account": false,
  "message": "No payout account created yet",
  "next_step": "Call POST endpoint to create a Stripe Connect account"
}
```

**Example Usage:**
```bash
curl -X GET https://dev.backend.ring-mig.com/api/payment/listener/connect/ \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

### 3. **Refresh Stripe Connect Setup Link**

**Endpoint:** `POST /api/payment/listener/connect/refresh/`

**Purpose:** Get a new onboarding link if the listener left the setup process incomplete

**Authentication:** Required (Bearer token)

**Response (Success - 200):**
```json
{
  "success": true,
  "url": "https://connect.stripe.com/setup/e/acct_1TSqAMAxCCHEibaN/wQ3rOmorgIa0",
  "message": "Continue your Stripe account setup using the link above",
  "expires_at": 1706260000
}
```

**Example Usage:**
```bash
curl -X POST https://dev.backend.ring-mig.com/api/payment/listener/connect/refresh/ \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

### 4. **Handle Stripe Return (After Onboarding Completion)**

**Endpoint:** `GET /api/payment/listener/connect/return/`

**Purpose:** Called after listener completes Stripe onboarding (redirect from Stripe)

**Authentication:** Required (Bearer token)

**Response (Verification Complete - 200):**
```json
{
  "success": true,
  "message": "Your Stripe account is set up and verified!",
  "is_verified": true,
  "payouts_enabled": true,
  "charges_enabled": true,
  "details_submitted": true,
  "account_id": "acct_1TSqAMAxCCHEibaN",
  "next_steps": [
    "✓ Your account is connected",
    "✓ You can start receiving payouts",
    "✓ Earnings from bookings will be transferred to your bank account"
  ]
}
```

**Response (Verification Pending - 200):**
```json
{
  "success": false,
  "message": "Your Stripe account setup is in progress.",
  "is_verified": false,
  "payouts_enabled": false,
  "charges_enabled": false,
  "details_submitted": false,
  "account_id": "acct_1TSqAMAxCCHEibaN",
  "next_steps": [
    "⏳ Complete verification (required by: 2026-02-25)",
    "⚠ Some account details are pending",
    "⚠ Payouts not yet enabled"
  ]
}
```

---

## Frontend Implementation Guide

### React/Vue Example

```javascript
// 1. Get or create Stripe Connect link
async function initiateStripeConnect() {
  const response = await fetch('/api/payment/listener/connect/', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });

  const data = await response.json();
  
  if (data.success) {
    // Redirect to Stripe Connect
    window.location.href = data.url;
  } else {
    console.error('Failed to create connect account:', data.error);
  }
}

// 2. Check account status
async function checkAccountStatus() {
  const response = await fetch('/api/payment/listener/connect/', {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });

  const data = await response.json();
  
  if (data.has_account) {
    console.log('Account Status:', data.verification_status);
    console.log('Payouts Enabled:', data.payouts_enabled);
  }
}

// 3. Handle redirect from Stripe (on return_url page)
useEffect(() => {
  // This is called after user completes Stripe onboarding
  fetch('/api/payment/listener/connect/return/', {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        // Show success message and next steps
        console.log('Account verified!', data.next_steps);
      } else {
        // Show pending message
        console.log('Still verifying...', data.next_steps);
      }
    });
}, [token]);
```

---

## Account Verification Status

### Status Stages

1. **Not Started**
   - Account created but no details submitted
   - User needs to complete onboarding
   - `details_submitted: false`

2. **Pending ⏳**
   - User completed initial setup
   - Stripe reviewing the information
   - `details_submitted: true`
   - `payouts_enabled: false`

3. **Complete ✓**
   - All requirements met
   - Payouts enabled
   - `payouts_enabled: true`
   - `charges_enabled: true`

### Checking Verification Status

Use the **GET** endpoint to check real-time status from Stripe:

```bash
curl -X GET https://dev.backend.ring-mig.com/api/payment/listener/connect/ \
  -H "Authorization: Bearer YOUR_TOKEN" | jq '.verification_status'
```

---

## Admin Dashboard Features

Navigate to: `https://dev.backend.ring-mig.com/admin/payment/stripelisteneraccount/`

### Available Actions

1. **View Stripe Dashboard Link**
   - Click the button to see detailed account info in Stripe Dashboard

2. **Generate Stripe Connect Link** (Bulk Action)
   - Send setup/refresh links to listeners
   - Useful for manual account creation

3. **Check & Update Account Status** (Bulk Action)
   - Verify current status from Stripe
   - Update is_verified flag
   - Check for pending requirements

4. **Disable Account** (Bulk Action)
   - Prevent listener from receiving payouts
   - Used for account issues or policy violations

### Admin Display Information

- **Listener Email**: Listener account email
- **Stripe Account ID**: Connected account ID
- **Verification Status**: Visual indicator (✓ Verified / ⚠ Pending)
- **Is Enabled**: Account active/inactive status
- **Stripe Dashboard**: Direct link to Stripe Dashboard
- **Account Details**: Real-time account info from Stripe

---

## Payout Processing

Once a listener's account is verified, payouts can be processed:

### Process Payout (Admin Only)

**Endpoint:** `POST /api/payment/listener/connect/payout/{payout_id}/`

**Requirements:**
- Listener must have `is_verified: true`
- Must be admin/staff user
- Booking must be completed
- Payout status must be 'pending'

---

## Error Handling

### Common Errors and Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| "Only listeners can create payout accounts" | Non-listener user | Use listener account |
| "Failed to create payout account" | Stripe API error | Check STRIPE_SECRET_KEY is set |
| "No payout account found" | User hasn't created account | Call POST endpoint first |
| Payout not available | Account not verified | Complete Stripe onboarding |

### Error Response Format

```json
{
  "error": "Error message",
  "details": "Detailed error from Stripe (if applicable)"
}
```

---

## Security Considerations

### API Security
- All endpoints require authentication (except webhooks)
- Only listeners can access their own accounts
- Admin-only endpoints require staff status
- Stripe webhook signature verification included

### Account Security
- Stripe handles sensitive data (bank details)
- No sensitive data stored in database
- Account IDs are masked in logs
- PII protected per GDPR/CCPA

---

## Testing Guide

### Test with cURL

**1. Create Account:**
```bash
curl -X POST https://dev.backend.ring-mig.com/api/payment/listener/connect/ \
  -H "Authorization: Bearer YOUR_BEARER_TOKEN" \
  -H "Content-Type: application/json"
```

**2. Check Status:**
```bash
curl -X GET https://dev.backend.ring-mig.com/api/payment/listener/connect/ \
  -H "Authorization: Bearer YOUR_BEARER_TOKEN"
```

**3. Refresh Link:**
```bash
curl -X POST https://dev.backend.ring-mig.com/api/payment/listener/connect/refresh/ \
  -H "Authorization: Bearer YOUR_BEARER_TOKEN"
```

### Test with Python

```python
import requests

TOKEN = "your_bearer_token"
BASE_URL = "https://dev.backend.ring-mig.com/api"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# Create connect account
response = requests.post(f"{BASE_URL}/payment/listener/connect/", headers=HEADERS)
print(response.json())

# Get account status
response = requests.get(f"{BASE_URL}/payment/listener/connect/", headers=HEADERS)
print(response.json())
```

---

## Troubleshooting

### The Stripe link doesn't work
- Check if STRIPE_SECRET_KEY is set correctly in settings
- Verify the link hasn't expired (links expire after 24 hours)
- Request a new link using the refresh endpoint

### Account shows as pending forever
- Check Stripe Dashboard for any requirements
- Some verifications take up to 24-48 hours
- Reach out to Stripe support if requirements are unclear

### Payouts not processing
- Verify `payouts_enabled: true` in account status
- Check that banking information is provided
- Ensure booking status is 'completed'

---

## API Rate Limits

- Stripe API: 100 requests/second
- Database queries: No limit
- Recommended: Cache account status for 5 minutes per user

---

## Database Schema

### StripeListenerAccount Model

```python
class StripeListenerAccount(models.Model):
    listener = OneToOneField(User)  # Unique connection
    stripe_account_id = CharField(max_length=255, unique=True)
    is_verified = BooleanField(default=False)
    is_enabled = BooleanField(default=True)
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)
```

---

## Configuration

### Required Settings

```python
# settings.py
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
STRIPE_CURRENCY = 'usd'
```

### Environment Variables

```bash
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

---

## Related Documentation

- [Stripe Connect Express Documentation](https://stripe.com/docs/connect/express-accounts)
- [Stripe Account Object Reference](https://stripe.com/docs/api/accounts)
- [Stripe Payout Guide](https://stripe.com/docs/payouts)

---

## Support

For issues or questions:
1. Check this guide first
2. Review Stripe Dashboard for account details
3. Check server logs: `/var/log/django.log`
4. Contact support with:
   - Listener email
   - Stripe account ID
   - Error message
   - Screenshots if applicable

---

**Last Updated:** 2026-05-03  
**Version:** 1.0  
**Status:** Production Ready
