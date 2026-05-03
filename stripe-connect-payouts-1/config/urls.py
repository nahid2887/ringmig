from django.urls import path
from apps.chat import views as chat_views
from apps.payment import views as payment_views

urlpatterns = [
    path('chat/call-packages/purchase/', chat_views.purchase_call_package, name='purchase_call_package'),
    path('chat/call-sessions/extend-minutes/', chat_views.extend_minutes, name='extend_minutes'),
    path('payment/tips/create-payment-intent/', payment_views.create_payment_intent, name='create_payment_intent'),
]