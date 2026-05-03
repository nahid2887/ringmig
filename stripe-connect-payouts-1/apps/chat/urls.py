from django.urls import path
from . import views

urlpatterns = [
    path('purchase/', views.purchase_call_package, name='purchase_call_package'),
    path('extend-minutes/', views.extend_minutes, name='extend_minutes'),
    path('tips/create-payment-intent/', views.create_payment_intent, name='create_payment_intent'),
]