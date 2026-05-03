from django.shortcuts import render
from django.http import JsonResponse
from .services.payouts import handle_payout

def purchase_call_package(request):
    if request.method == 'POST':
        # Logic to handle call package purchase
        # Assuming the request contains necessary data
        talker_id = request.POST.get('talker_id')
        amount = request.POST.get('amount')
        
        # Call the payout handling function
        payout_response = handle_payout(talker_id, amount)
        
        return JsonResponse(payout_response)

def extend_minutes(request):
    if request.method == 'POST':
        # Logic to handle extending minutes
        talker_id = request.POST.get('talker_id')
        amount = request.POST.get('amount')
        
        # Call the payout handling function
        payout_response = handle_payout(talker_id, amount)
        
        return JsonResponse(payout_response)

def create_payment_intent(request):
    if request.method == 'POST':
        # Logic to handle creating a payment intent for tips
        talker_id = request.POST.get('talker_id')
        amount = request.POST.get('amount')
        
        # Call the payout handling function
        payout_response = handle_payout(talker_id, amount)
        
        return JsonResponse(payout_response)