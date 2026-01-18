from django.contrib import admin
from .models import (
    BookingPackage, 
    Booking, 
    Payment, 
    ListenerPayout,
    StripeCustomer,
    StripeListenerAccount
)


@admin.register(BookingPackage)
class BookingPackageAdmin(admin.ModelAdmin):
    list_display = ['name', 'duration_minutes', 'price', 'app_fee', 'listener_amount', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['id', 'talker', 'listener', 'package', 'status', 'total_amount', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['talker__email', 'listener__email']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['talker', 'listener']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'booking', 'amount', 'status', 'stripe_payment_intent_id', 'created_at']
    list_filter = ['status', 'payment_method', 'created_at']
    search_fields = ['stripe_payment_intent_id', 'stripe_charge_id', 'booking__talker__email']
    readonly_fields = ['created_at', 'updated_at', 'paid_at', 'refunded_at']


@admin.register(ListenerPayout)
class ListenerPayoutAdmin(admin.ModelAdmin):
    list_display = ['id', 'listener', 'booking', 'amount', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['listener__email', 'stripe_transfer_id']
    readonly_fields = ['created_at', 'updated_at', 'paid_at']
    raw_id_fields = ['listener', 'booking']


@admin.register(StripeCustomer)
class StripeCustomerAdmin(admin.ModelAdmin):
    list_display = ['user', 'stripe_customer_id', 'created_at']
    search_fields = ['user__email', 'stripe_customer_id']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(StripeListenerAccount)
class StripeListenerAccountAdmin(admin.ModelAdmin):
    list_display = ['listener', 'stripe_account_id', 'is_verified', 'is_enabled', 'created_at']
    list_filter = ['is_verified', 'is_enabled']
    search_fields = ['listener__email', 'stripe_account_id']
    readonly_fields = ['created_at', 'updated_at']
