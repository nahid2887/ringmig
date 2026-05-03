from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from .transfers import handle_payment_intent_succeeded, handle_transfer_succeeded

@csrf_exempt
def stripe_webhook(request):
    if request.method == 'POST':
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        endpoint_secret = 'your_endpoint_secret'  # Replace with your actual endpoint secret

        # Verify the webhook signature
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        except ValueError as e:
            return JsonResponse({'error': 'Invalid payload'}, status=400)
        except stripe.error.SignatureVerificationError as e:
            return JsonResponse({'error': 'Invalid signature'}, status=400)

        # Handle the event
        if event['type'] == 'payment_intent.succeeded':
            handle_payment_intent_succeeded(event['data']['object'])
        elif event['type'] == 'transfer.succeeded':
            handle_transfer_succeeded(event['data']['object'])

        return JsonResponse({'status': 'success'}, status=200)

    return JsonResponse({'error': 'Method not allowed'}, status=405)