# Stripe Connect Payouts Project

This project implements automatic payouts to talkers' accounts using Stripe Connect for the following APIs:

- `/chat/call-packages/purchase/`
- `/chat/call-sessions/extend-minutes/`
- `/payment/tips/create-payment-intent/`

## Project Structure

```
stripe-connect-payouts
├── config
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── apps
│   ├── chat
│   │   ├── __init__.py
│   │   ├── urls.py
│   │   ├── views.py
│   │   ├── services
│   │   │   ├── __init__.py
│   │   │   └── payouts.py
│   │   └── tests
│   │       └── test_payouts.py
│   ├── payment
│   │   ├── __init__.py
│   │   ├── urls.py
│   │   ├── views.py
│   │   ├── services
│   │   │   ├── __init__.py
│   │   │   └── tips.py
│   │   └── tests
│   │       └── test_tips_payouts.py
│   └── stripe_connect
│       ├── __init__.py
│       ├── client.py
│       ├── transfers.py
│       └── webhooks.py
├── manage.py
├── requirements.txt
├── .env.example
└── README.md
```

## Setup Instructions

1. **Clone the repository:**
   ```
   git clone <repository-url>
   cd stripe-connect-payouts
   ```

2. **Create a virtual environment:**
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install dependencies:**
   ```
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   Copy `.env.example` to `.env` and fill in the required values, including your Stripe API keys.

5. **Run migrations:**
   ```
   python manage.py migrate
   ```

6. **Start the development server:**
   ```
   python manage.py runserver
   ```

## Usage

- Use the `/chat/call-packages/purchase/` endpoint to purchase call packages, which will trigger automatic payouts to the talkers.
- Use the `/chat/call-sessions/extend-minutes/` endpoint to extend call sessions, also triggering payouts.
- Use the `/payment/tips/create-payment-intent/` endpoint to create payment intents for tips, ensuring talkers receive their payouts.

## Testing

Run the tests for the chat and payment functionalities to ensure everything is working as expected:

```
python manage.py test apps/chat/tests
python manage.py test apps/payment/tests
```

## License

This project is licensed under the MIT License. See the LICENSE file for details.