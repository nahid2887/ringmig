# Stripe Connect Quick Reference

## URL Endpoints Summary

| Method | Endpoint | Purpose |
|--------|----------|---------|
| **POST** | `/api/payment/listener/connect/` | Create new account or get setup link |
| **GET** | `/api/payment/listener/connect/` | Check account status |
| **POST** | `/api/payment/listener/connect/refresh/` | Get new setup link if interrupted |
| **GET** | `/api/payment/listener/connect/return/` | Called after Stripe onboarding completes |

---

## Quick Start

### 1️⃣ Listener Initiates Account Connection

**POST** `/api/payment/listener/connect/`
```json
Headers:
- Authorization: Bearer {token}
- Content-Type: application/json

Response:
{
  "url": "https://connect.stripe.com/setup/e/acct_1TSq...",
  "account_id": "acct_1TSq...",
  "is_new_account": true
}
```

**Action:** Redirect listener to the `url`

---

### 2️⃣ Listener Completes Stripe Onboarding

**Automatic:** Stripe redirects to `return_url`

**GET** `/api/payment/listener/connect/return/`
```json
Headers:
- Authorization: Bearer {token}

Response:
{
  "success": true,
  "message": "Your Stripe account is set up and verified!",
  "is_verified": true,
  "payouts_enabled": true
}
```

**Action:** Show success message to listener

---

### 3️⃣ Check Status Anytime

**GET** `/api/payment/listener/connect/`
```json
Response:
{
  "has_account": true,
  "is_verified": true,
  "payouts_enabled": true,
  "verification_status": "Complete ✓"
}
```

---

## Implementation Checklist

- [ ] Add STRIPE_SECRET_KEY to environment
- [ ] Add STRIPE_PUBLISHABLE_KEY to environment
- [ ] Update frontend with connect flow
- [ ] Test with sandbox keys
- [ ] Test with production keys
- [ ] Enable webhook notifications
- [ ] Add success/error pages for return URL
- [ ] Document for listeners

---

## Account Status Reference

| Status | is_verified | payouts_enabled | Action |
|--------|-------------|-----------------|--------|
| 🆕 New | ❌ | ❌ | Complete onboarding |
| ⏳ Pending | ❌ | ❌ | Wait for Stripe verification |
| 🔄 Refresh | ❌ | ❌ | Call refresh endpoint |
| ✅ Complete | ✅ | ✅ | Ready for payouts |

---

## Response Status Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200 | Success | Use the returned data |
| 201 | Created | Resource created successfully |
| 400 | Bad Request | Check request format |
| 403 | Forbidden | User type or permissions issue |
| 404 | Not Found | Account doesn't exist |
| 500 | Server Error | Check logs, contact support |

---

## Admin Quick Actions

**Location:** `/admin/payment/stripelisteneraccount/`

1. **View Account** → Click listener email to see details
2. **View Dashboard** → Click "View in Stripe Dashboard" button
3. **Check Status** → Select account → Choose "Check & Update Account Status" → Go
4. **Send Link** → Select account → Choose "Generate Stripe Connect Link" → Go

---

## Frontend State Management

### React Hook Example

```javascript
const [stripeState, setStripeState] = useState({
  hasAccount: false,
  isVerified: false,
  setupUrl: null,
  loading: false,
  error: null
});

const initializeStripeConnect = async () => {
  setStripeState(prev => ({ ...prev, loading: true }));
  try {
    const response = await fetch('/api/payment/listener/connect/', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const data = await response.json();
    
    setStripeState({
      hasAccount: true,
      setupUrl: data.url,
      loading: false,
      error: null
    });
    
    window.location.href = data.url;
  } catch (err) {
    setStripeState(prev => ({ ...prev, loading: false, error: err.message }));
  }
};
```

---

## Common Integration Points

### Get Account Status on App Load
```javascript
useEffect(() => {
  fetch('/api/payment/listener/connect/', { headers })
    .then(r => r.json())
    .then(data => {
      if (data.has_account && data.is_verified) {
        // Show "Account Connected" badge
      } else if (data.has_account) {
        // Show "Verification Pending" badge
      } else {
        // Show "Connect Account" button
      }
    });
}, []);
```

### Show Earnings Dashboard (Only if Verified)
```javascript
if (stripeState.isVerified) {
  return <EarningsDashboard />;
} else if (stripeState.hasAccount) {
  return <VerificationPending />;
} else {
  return <ConnectStripeButton />;
}
```

### Handle Stripe Return
```javascript
// On return_url page
useEffect(() => {
  fetch('/api/payment/listener/connect/return/', { headers })
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        navigate('/account/dashboard');
      } else {
        showNotification('Verification in progress...');
      }
    });
}, []);
```

---

## Testing Checklist

- [ ] Can create new account
- [ ] Redirects to Stripe properly
- [ ] Returns correctly from Stripe
- [ ] Status endpoint shows correct state
- [ ] Refresh link works if interrupted
- [ ] Admin can view all accounts
- [ ] Admin can regenerate links
- [ ] Admin can check status
- [ ] Listener cannot access other accounts
- [ ] Non-listeners get 403 error

---

## Troubleshooting Quick Guide

| Problem | Check | Fix |
|---------|-------|-----|
| Link expired | Created > 24 hours ago | POST refresh endpoint |
| Payouts disabled | Stripe requirements | Complete requirements in Stripe |
| Wrong permissions | Token valid? | Check user type = listener |
| API 500 error | STRIPE_SECRET_KEY set? | Set environment variable |
| Account not found | Wrong user token | Ensure user is logged in |

---

## Support Contacts

- **Stripe Support:** support.stripe.com
- **Backend Issues:** devops@ringmig.com
- **Account Help:** support@ringmig.com

---

**Last Updated:** 2026-05-03
