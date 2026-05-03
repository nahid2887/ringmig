from django.urls import path
from .views import create_payment_intent, purchase_call_package, extend_minutes

urlpatterns = [
    path('tips/create-payment-intent/', create_payment_intent, name='create_payment_intent'),
    path('call-packages/purchase/', purchase_call_package, name='purchase_call_package'),
    path('call-sessions/extend-minutes/', extend_minutes, name='extend_minutes'),
]