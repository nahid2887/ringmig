# Payout API Implementation

## Overview
Implemented a new `make-payout` API endpoint in the `ListenerPayoutViewSet` that creates direct Stripe transfers to listeners' connected accounts.

## Endpoint Details

**URL:** `POST /api/chat/payouts/make-payout/`

**Endpoint:** `http://10.10.13.27:8005/api/chat/payouts/make-payout/`

## Request Payload

```json
{
  "amount": "100.50"
}
```

**Required Fields:**
- `amount` (string/decimal): The amount to withdraw in USD

## Response Success (HTTP 200)

```json
{
  "message": "Withdrawal successful",
  "amount": "100.50",
  "transfer_id": "tr_1234567890",
  "new_balance": "249.50",
  "status": "completed"
}
```

## Response Errors

### Insufficient Balance (HTTP 400)
```json
{
  "error": "Insufficient balance. Available: $100.00",
  "available_balance": "100.00",
  "requested_amount": "150.00"
}
```

### Account Onboarding Required (HTTP 400)
```json
{
  "error": "Your Stripe account requires onboarding before withdrawals",
  "message": "Complete Stripe onboarding",
  "onboarding_url": "https://connect.stripe.com/...",
  "status": "onboarding_required"
}
```

### Invalid Amount (HTTP 400)
```json
{
  "error": "Amount must be greater than 0"
}
```

### Stripe Error (HTTP 400)
```json
{
  "error": "Stripe error: {error details}"
}
```

### Unauthorized (HTTP 403)
```json
{
  "error": "Only listeners can request payouts"
}
```

## Implementation Details

The `make-payout` method includes the following logic:

### 1. **Validation**
   - Verify user is a listener
   - Validate amount is provided and positive
   - Check available balance is sufficient

### 2. **Stripe Account Management**
   - Retrieve existing Stripe Connect account OR create new Stripe Express account
   - Account creation includes:
     - Individual business type
     - Transfer capability requested
     - User's name and email
   - Save account ID to `StripeListenerAccount` model

### 3. **Account Verification**
   - Retrieve account status from Stripe
   - Check if onboarding is required
   - Return onboarding URL if needed

### 4. **Transfer Creation**
   - Create direct Stripe transfer to listener's account
   - Amount converted to cents for Stripe API
   - Include descriptive transfer message

### 5. **Database Updates** (Atomic Transaction)
   - Mark earned payouts as completed in order
   - Handle partial payouts by splitting records
   - Update listener's available balance
   - Record Stripe transfer ID and completion time

### 6. **Admin Notifications**
   - Notify all super_admins and admins via WebSocket
   - Create notification records
   - Log withdrawal activity

## Key Differences from `create-payout-link`

| Feature | `create-payout-link` | `make-payout` |
|---------|---------------------|---------------|
| **Purpose** | Collect payment method | Direct transfer |
| **Stripe Flow** | Setup mode (payment collection) | Transfer mode (direct transfer) |
| **Balance Update** | Deferred (on webhook) | Immediate (atomic) |
| **Admin Flow** | Requires separate completion | Completes in single request |
| **Use Case** | When listener provides card details | Direct account-to-account transfer |

## Database Models Used

1. **ListenerBalance** - Stores available balance for listener
2. **ListenerPayout** - Individual payout records (earned → completed)
3. **StripeListenerAccount** - Stripe Connect account mapping
4. **NotificationRoom** - Admin notification channels
5. **Notification** - Admin notification messages
6. **AdminRole** - For identifying admin users

## Error Handling

- **Stripe Errors**: Caught and returned with error message
- **Account Creation Failures**: Returns error with context
- **Balance Validation**: Prevents over-withdrawal
- **Onboarding**: Redirects to Stripe onboarding flow when needed
- **Admin Notifications**: Non-blocking (errors logged but don't fail request)

## Logging

All major operations are logged for audit trail:
- Account creation: `Created Stripe Express account for {email}: {account_id}`
- Transfer creation: `Created Stripe transfer {transfer_id} for {email}: ${amount}`
- Balance updates: `Updated balance for {email}: -${amount}, New balance: ${new_balance}`
- Completion: `✓ Payout completed for {email}: ${amount}`

## Security Considerations

1. **Authentication**: Requires `IsAuthenticated` permission
2. **Authorization**: Only listeners can request payouts
3. **Balance Validation**: Prevents withdrawals exceeding available balance
4. **Atomic Transactions**: Ensures database consistency
5. **Stripe Verification**: Validates account status before transfer

## Implementation Location

**File:** [core/chat/call_views.py](core/chat/call_views.py)

**Class:** `ListenerPayoutViewSet`

**Method:** `make_payout` (lines 2670-2896)
