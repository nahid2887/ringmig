# Stripe Connect Implementation Examples

## React Component Example

### Complete StripeConnectFlow Component

```jsx
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

const StripeConnectFlow = () => {
  const [state, setState] = useState({
    hasAccount: false,
    isVerified: false,
    setupUrl: null,
    loading: false,
    error: null,
    accountDetails: null
  });

  const [token, setToken] = useState(localStorage.getItem('access_token'));
  const navigate = useNavigate();

  const headers = {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  };

  // Check if account exists when component mounts
  useEffect(() => {
    checkAccountStatus();
  }, [token]);

  // Check account status from API
  const checkAccountStatus = async () => {
    try {
      setState(prev => ({ ...prev, loading: true }));
      
      const response = await fetch(
        'https://dev.backend.ring-mig.com/api/payment/listener/connect/',
        { headers, method: 'GET' }
      );

      if (!response.ok) throw new Error('Failed to check account status');

      const data = await response.json();
      
      setState(prev => ({
        ...prev,
        hasAccount: data.has_account,
        isVerified: data.is_verified || false,
        accountDetails: data,
        loading: false
      }));
    } catch (error) {
      setState(prev => ({
        ...prev,
        error: error.message,
        loading: false
      }));
    }
  };

  // Create new Stripe Connect account
  const handleCreateAccount = async () => {
    try {
      setState(prev => ({ ...prev, loading: true, error: null }));

      const response = await fetch(
        'https://dev.backend.ring-mig.com/api/payment/listener/connect/',
        {
          method: 'POST',
          headers,
          body: JSON.stringify({})
        }
      );

      if (!response.ok) throw new Error('Failed to create account');

      const data = await response.json();

      setState(prev => ({
        ...prev,
        setupUrl: data.url,
        loading: false
      }));

      // Redirect to Stripe
      window.location.href = data.url;
    } catch (error) {
      setState(prev => ({
        ...prev,
        error: error.message,
        loading: false
      }));
    }
  };

  // Handle return from Stripe onboarding
  const handleVerifyAfterReturn = async () => {
    try {
      setState(prev => ({ ...prev, loading: true }));

      const response = await fetch(
        'https://dev.backend.ring-mig.com/api/payment/listener/connect/return/',
        { headers, method: 'GET' }
      );

      const data = await response.json();

      setState(prev => ({
        ...prev,
        isVerified: data.is_verified,
        accountDetails: data,
        loading: false
      }));

      if (data.success) {
        // Account is verified, show success
        showNotification('Account verified successfully!', 'success');
        navigate('/dashboard/earnings');
      } else {
        // Still pending
        showNotification('Account setup in progress, please wait...', 'info');
      }
    } catch (error) {
      setState(prev => ({
        ...prev,
        error: error.message,
        loading: false
      }));
    }
  };

  // Refresh account link if needed
  const handleRefresh = async () => {
    try {
      setState(prev => ({ ...prev, loading: true, error: null }));

      const response = await fetch(
        'https://dev.backend.ring-mig.com/api/payment/listener/connect/refresh/',
        { method: 'POST', headers }
      );

      const data = await response.json();

      if (data.success) {
        setState(prev => ({ ...prev, setupUrl: data.url }));
        window.location.href = data.url;
      }

      setState(prev => ({ ...prev, loading: false }));
    } catch (error) {
      setState(prev => ({
        ...prev,
        error: error.message,
        loading: false
      }));
    }
  };

  const showNotification = (message, type) => {
    console.log(`[${type.toUpperCase()}] ${message}`);
    // Integrate with your notification system (Toast, Snackbar, etc.)
  };

  // Render different states
  if (state.loading) {
    return <div className="loading">Loading account information...</div>;
  }

  if (state.error) {
    return (
      <div className="error-card">
        <h3>Error</h3>
        <p>{state.error}</p>
        <button onClick={checkAccountStatus}>Retry</button>
      </div>
    );
  }

  // No account - show connect button
  if (!state.hasAccount) {
    return (
      <div className="stripe-connect-card">
        <h2>Connect Your Stripe Account</h2>
        <p>
          Start receiving payouts for your sessions by connecting your Stripe account.
        </p>
        <button 
          onClick={handleCreateAccount} 
          className="btn-primary"
          disabled={state.loading}
        >
          Connect to Stripe
        </button>
      </div>
    );
  }

  // Account exists but not verified - show pending state
  if (!state.isVerified) {
    return (
      <div className="stripe-pending-card">
        <h2>Verification In Progress</h2>
        <p>Your Stripe account is being verified. This usually takes 1-2 business days.</p>
        
        <div className="requirements">
          {state.accountDetails?.next_steps?.map((step, idx) => (
            <div key={idx} className="requirement-item">
              {step}
            </div>
          ))}
        </div>

        <div className="actions">
          <button 
            onClick={checkAccountStatus}
            className="btn-secondary"
          >
            Check Status
          </button>
          <button 
            onClick={handleRefresh}
            className="btn-secondary"
          >
            Get New Setup Link
          </button>
        </div>
      </div>
    );
  }

  // Account verified - show success
  return (
    <div className="stripe-verified-card">
      <h2>✓ Account Connected</h2>
      <div className="account-info">
        <p><strong>Account ID:</strong> {state.accountDetails?.account_id}</p>
        <p><strong>Email:</strong> {state.accountDetails?.email}</p>
        <p><strong>Status:</strong> {state.accountDetails?.verification_status}</p>
        <p><strong>Payouts Enabled:</strong> {state.accountDetails?.payouts_enabled ? 'Yes ✓' : 'No'}</p>
      </div>
      <p>Your Stripe account is verified and ready to receive payouts!</p>
      <a 
        href="https://dashboard.stripe.com" 
        target="_blank" 
        rel="noopener noreferrer"
        className="btn-link"
      >
        View in Stripe Dashboard
      </a>
    </div>
  );
};

export default StripeConnectFlow;
```

---

## Return URL Page Handler (React)

```jsx
// pages/stripe-connect-return.jsx
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

const StripeConnectReturn = () => {
  const [status, setStatus] = useState('checking');
  const [data, setData] = useState(null);
  const navigate = useNavigate();
  const token = localStorage.getItem('access_token');

  useEffect(() => {
    verifyConnectCompletion();
  }, []);

  const verifyConnectCompletion = async () => {
    try {
      const response = await fetch(
        'https://dev.backend.ring-mig.com/api/payment/listener/connect/return/',
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      );

      const result = await response.json();
      setData(result);

      if (result.success) {
        setStatus('verified');
        // Redirect after 3 seconds
        setTimeout(() => {
          navigate('/dashboard/account');
        }, 3000);
      } else {
        setStatus('pending');
      }
    } catch (error) {
      setStatus('error');
      setData({ error: error.message });
    }
  };

  return (
    <div className="connect-return-page">
      {status === 'checking' && (
        <div className="spinner">
          <p>Verifying your account...</p>
        </div>
      )}

      {status === 'verified' && (
        <div className="success-message">
          <h1>✓ Success!</h1>
          <p>Your Stripe account has been verified successfully!</p>
          <ul>
            {data?.next_steps?.map((step, idx) => (
              <li key={idx}>{step}</li>
            ))}
          </ul>
          <p>Redirecting to dashboard...</p>
        </div>
      )}

      {status === 'pending' && (
        <div className="info-message">
          <h1>Verification in Progress</h1>
          <p>We're verifying your account details with Stripe.</p>
          <ul>
            {data?.next_steps?.map((step, idx) => (
              <li key={idx}>{step}</li>
            ))}
          </ul>
          <p>This typically takes 1-2 business days.</p>
          <button onClick={() => navigate('/dashboard/account')}>
            Return to Dashboard
          </button>
        </div>
      )}

      {status === 'error' && (
        <div className="error-message">
          <h1>Error</h1>
          <p>{data?.error || 'Something went wrong'}</p>
          <button onClick={() => navigate('/dashboard/account')}>
            Return to Dashboard
          </button>
        </div>
      )}
    </div>
  );
};

export default StripeConnectReturn;
```

---

## Vue.js Example

```vue
<template>
  <div class="stripe-connect">
    <!-- Loading state -->
    <div v-if="loading" class="spinner">
      {{ loadingMessage }}
    </div>

    <!-- Error state -->
    <div v-if="error" class="error-card">
      <h3>Error</h3>
      <p>{{ error }}</p>
      <button @click="checkAccountStatus">Retry</button>
    </div>

    <!-- No account -->
    <div v-if="!hasAccount && !loading" class="connect-card">
      <h2>Connect Your Stripe Account</h2>
      <p>Start receiving payouts for your sessions</p>
      <button @click="createAccount" :disabled="loading">
        Connect to Stripe
      </button>
    </div>

    <!-- Account pending -->
    <div v-if="hasAccount && !isVerified && !loading" class="pending-card">
      <h2>Verification In Progress</h2>
      <div v-for="step in accountDetails?.next_steps" :key="step">
        <p>{{ step }}</p>
      </div>
      <button @click="checkAccountStatus" class="secondary">
        Check Status
      </button>
    </div>

    <!-- Account verified -->
    <div v-if="isVerified && !loading" class="verified-card">
      <h2>✓ Account Connected</h2>
      <p>Your Stripe account is verified and ready!</p>
    </div>
  </div>
</template>

<script>
export default {
  data() {
    return {
      hasAccount: false,
      isVerified: false,
      loading: false,
      error: null,
      accountDetails: null,
      loadingMessage: 'Loading...',
      token: localStorage.getItem('access_token')
    };
  },

  mounted() {
    this.checkAccountStatus();
  },

  methods: {
    async checkAccountStatus() {
      try {
        this.loading = true;
        this.loadingMessage = 'Checking account status...';

        const response = await fetch(
          'https://dev.backend.ring-mig.com/api/payment/listener/connect/',
          {
            headers: {
              'Authorization': `Bearer ${this.token}`,
              'Content-Type': 'application/json'
            }
          }
        );

        const data = await response.json();
        this.hasAccount = data.has_account;
        this.isVerified = data.is_verified;
        this.accountDetails = data;
        this.loading = false;
      } catch (error) {
        this.error = error.message;
        this.loading = false;
      }
    },

    async createAccount() {
      try {
        this.loading = true;
        this.loadingMessage = 'Creating Stripe Connect account...';

        const response = await fetch(
          'https://dev.backend.ring-mig.com/api/payment/listener/connect/',
          {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${this.token}`,
              'Content-Type': 'application/json'
            }
          }
        );

        const data = await response.json();
        window.location.href = data.url;
      } catch (error) {
        this.error = error.message;
        this.loading = false;
      }
    }
  }
};
</script>

<style scoped>
.stripe-connect {
  padding: 20px;
  max-width: 600px;
}

.spinner {
  text-align: center;
  padding: 40px;
}

.error-card {
  background-color: #fee;
  border: 1px solid #f00;
  padding: 20px;
  border-radius: 8px;
  margin-bottom: 20px;
}

.connect-card,
.pending-card,
.verified-card {
  background-color: #fff;
  border: 1px solid #ddd;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

button {
  background-color: #5469d4;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  cursor: pointer;
  font-weight: bold;
}

button:hover {
  background-color: #3d5fa9;
}

button.secondary {
  background-color: #6b7280;
}
</style>
```

---

## Django View Example (for return_url page)

```python
# listeners/views.py
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from payment.models import StripeListenerAccount
import stripe
from django.conf import settings

class StripeConnectReturnView(LoginRequiredMixin, TemplateView):
    """View for handling Stripe Connect return URL."""
    
    template_name = 'listeners/stripe_connect_return.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Only for listeners
        if user.user_type != 'listener':
            context['error'] = 'Only listeners can access this page'
            return context
        
        try:
            listener_account = StripeListenerAccount.objects.get(listener=user)
            stripe.api_key = settings.STRIPE_SECRET_KEY
            account = stripe.Account.retrieve(listener_account.stripe_account_id)
            
            is_verified = account.charges_enabled and account.payouts_enabled
            
            if is_verified:
                listener_account.is_verified = True
                listener_account.save()
            
            context.update({
                'account_verified': is_verified,
                'account_id': listener_account.stripe_account_id,
                'payouts_enabled': account.payouts_enabled,
                'details_submitted': account.details_submitted,
                'next_steps': self._get_next_steps(account, listener_account)
            })
        except StripeListenerAccount.DoesNotExist:
            context['error'] = 'No Stripe account found'
        except stripe.error.StripeError as e:
            context['error'] = f'Stripe error: {str(e)}'
        
        return context
    
    def _get_next_steps(self, account, listener_account):
        steps = []
        if not account.details_submitted:
            steps.append("Complete your information")
        if not account.payouts_enabled:
            steps.append("Add banking information")
        if account.requirements and account.requirements.eventually_due:
            steps.append(f"Complete requirements by {account.requirements.current_deadline}")
        
        return steps if steps else ["✓ Your account is ready!"]
```

---

## HTML Template for Return Page

```html
<!-- templates/listeners/stripe_connect_return.html -->
{% extends "base.html" %}

{% block title %}Stripe Connect - Setup Complete{% endblock %}

{% block content %}
<div class="container stripe-connect-return">
  {% if error %}
    <div class="alert alert-danger">
      <h2>Error</h2>
      <p>{{ error }}</p>
      <a href="{% url 'listener:dashboard' %}" class="btn btn-primary">
        Return to Dashboard
      </a>
    </div>
  {% elif account_verified %}
    <div class="alert alert-success">
      <h2>✓ Account Verified!</h2>
      <p>Your Stripe account is now verified and ready to receive payouts.</p>
      
      <div class="account-info">
        <p><strong>Account ID:</strong> {{ account_id }}</p>
        <p><strong>Payouts Enabled:</strong> {% if payouts_enabled %}Yes ✓{% else %}No{% endif %}</p>
      </div>
      
      <a href="{% url 'listener:dashboard' %}" class="btn btn-primary">
        Go to Dashboard
      </a>
    </div>
  {% else %}
    <div class="alert alert-info">
      <h2>Verification In Progress</h2>
      <p>Your Stripe account setup is underway. Stripe is reviewing your information.</p>
      
      <h3>Next Steps:</h3>
      <ul>
        {% for step in next_steps %}
          <li>{{ step }}</li>
        {% endfor %}
      </ul>
      
      <p><strong>Note:</strong> Verification typically takes 1-2 business days.</p>
      
      <a href="{% url 'listener:dashboard' %}" class="btn btn-secondary">
        Return to Dashboard
      </a>
    </div>
  {% endif %}
</div>
{% endblock %}
```

---

## Testing with cURL

```bash
#!/bin/bash
# Test Stripe Connect API

BASE_URL="https://dev.backend.ring-mig.com"
TOKEN="your_bearer_token_here"

echo "=== Test 1: Check Account Status ==="
curl -X GET "$BASE_URL/api/payment/listener/connect/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" | jq .

echo -e "\n=== Test 2: Create New Account ==="
curl -X POST "$BASE_URL/api/payment/listener/connect/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" | jq .

echo -e "\n=== Test 3: Get Refresh Link ==="
curl -X POST "$BASE_URL/api/payment/listener/connect/refresh/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" | jq .
```

---

## Python Client Example

```python
# client.py
import requests
import json
from typing import Dict, Optional

class StripeConnectClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url
        self.token = token
        self.headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
    
    def create_account(self) -> Dict:
        """Create Stripe Connect account for listener."""
        response = requests.post(
            f'{self.base_url}/api/payment/listener/connect/',
            headers=self.headers
        )
        return response.json()
    
    def get_account_status(self) -> Dict:
        """Get current account status."""
        response = requests.get(
            f'{self.base_url}/api/payment/listener/connect/',
            headers=self.headers
        )
        return response.json()
    
    def refresh_setup_link(self) -> Dict:
        """Get new setup link."""
        response = requests.post(
            f'{self.base_url}/api/payment/listener/connect/refresh/',
            headers=self.headers
        )
        return response.json()
    
    def verify_after_return(self) -> Dict:
        """Verify setup after returning from Stripe."""
        response = requests.get(
            f'{self.base_url}/api/payment/listener/connect/return/',
            headers=self.headers
        )
        return response.json()

# Usage
client = StripeConnectClient(
    'https://dev.backend.ring-mig.com',
    'your_token'
)

# Create account
account = client.create_account()
print(f"Setup URL: {account['url']}")

# Check status
status = client.get_account_status()
print(f"Verified: {status['is_verified']}")
```

---

**Last Updated:** 2026-05-03
