from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.contrib import messages
import stripe
from django.conf import settings
from .models import (
    BookingPackage, 
    Booking, 
    Payment, 
    ListenerPayout,
    StripeCustomer,
    StripeListenerAccount,
    Tip
)

stripe.api_key = settings.STRIPE_SECRET_KEY


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
    list_display = ['listener', 'stripe_account_id', 'verification_status', 'is_enabled', 'get_connect_link', 'created_at']
    list_filter = ['is_verified', 'is_enabled', 'created_at']
    search_fields = ['listener__email', 'stripe_account_id']
    readonly_fields = ['created_at', 'updated_at', 'stripe_account_id', 'account_details', 'get_connect_link']
    actions = ['generate_connect_link', 'verify_account_status', 'disable_account']
    
    def verification_status(self, obj):
        """Display verification status with color coding."""
        if obj.is_verified:
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ Verified</span>'
            )
        return format_html(
            '<span style="color: orange; font-weight: bold;">⚠ Pending</span>'
        )
    verification_status.short_description = 'Status'
    
    def get_connect_link(self, obj):
        """Display Stripe dashboard link."""
        if obj.stripe_account_id:
            url = f"https://dashboard.stripe.com/accounts/{obj.stripe_account_id}"
            return format_html(
                '<a class="button" href="{}" target="_blank">View in Stripe Dashboard</a>', url
            )
        return "No account"
    get_connect_link.short_description = 'Stripe Dashboard'
    
    def account_details(self, obj):
        """Display detailed account information from Stripe."""
        try:
            account = stripe.Account.retrieve(obj.stripe_account_id)
            details = f"""
            <b>Account ID:</b> {account.id}<br>
            <b>Email:</b> {account.email}<br>
            <b>Charges Enabled:</b> {'Yes ✓' if account.charges_enabled else 'No ✗'}<br>
            <b>Payouts Enabled:</b> {'Yes ✓' if account.payouts_enabled else 'No ✗'}<br>
            <b>Details Submitted:</b> {'Yes ✓' if account.details_submitted else 'No ✗'}<br>
            <b>Country:</b> {account.country}<br>
            """
            if account.requirements:
                details += f"<b>Verification Status:</b> {account.requirements.current_deadline}<br>"
            return format_html(details)
        except Exception as e:
            return f"Error fetching details: {str(e)}"
    account_details.short_description = 'Account Details'
    
    def generate_connect_link(self, request, queryset):
        """Generate/regenerate Stripe Connect onboarding link."""
        for obj in queryset:
            try:
                # Point admin-generated links to the frontend so listeners are redirected
                frontend_return = 'https://ring-mig.com/dashboard/listener'
                frontend_refresh = 'https://ring-mig.com/dashboard/listener?connected=pending'
                account_link = stripe.AccountLink.create(
                    account=obj.stripe_account_id,
                    refresh_url=frontend_refresh,
                    return_url=frontend_return,
                    type='account_onboarding',
                )
                
                # Store the link in session for admin to view
                self.message_user(
                    request,
                    f"✓ Connect link generated for {obj.listener.email}.\n"
                    f"Send this link to the listener:\n{account_link.url}",
                    messages.SUCCESS
                )
            except Exception as e:
                self.message_user(
                    request,
                    f"✗ Error generating link for {obj.listener.email}: {str(e)}",
                    messages.ERROR
                )
    generate_connect_link.short_description = "Generate Stripe Connect Link"
    
    def verify_account_status(self, request, queryset):
        """Check and update account verification status from Stripe."""
        for obj in queryset:
            try:
                account = stripe.Account.retrieve(obj.stripe_account_id)
                
                if account.charges_enabled and account.payouts_enabled:
                    obj.is_verified = True
                    obj.save()
                    status_msg = "Verified ✓"
                else:
                    obj.is_verified = False
                    obj.save()
                    status_msg = f"Not verified - Charges: {account.charges_enabled}, Payouts: {account.payouts_enabled}"
                
                self.message_user(
                    request,
                    f"Updated {obj.listener.email}: {status_msg}",
                    messages.SUCCESS
                )
            except Exception as e:
                self.message_user(
                    request,
                    f"Error checking {obj.listener.email}: {str(e)}",
                    messages.ERROR
                )
    verify_account_status.short_description = "Check & Update Account Status"
    
    def disable_account(self, request, queryset):
        """Disable account from receiving payouts."""
        updated = queryset.update(is_enabled=False)
        self.message_user(
            request,
            f"Disabled {updated} account(s).",
            messages.SUCCESS
        )
    disable_account.short_description = "Disable Account"


@admin.register(Tip)
class TipAdmin(admin.ModelAdmin):
    list_display = ['id', 'talker', 'listener', 'amount', 'admin_fee', 'listener_amount', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['talker__email', 'listener__email', 'stripe_payment_intent_id']
    readonly_fields = ['admin_fee', 'listener_amount', 'created_at', 'updated_at', 'paid_at', 'refunded_at']
    raw_id_fields = ['talker', 'listener']
    
    def get_readonly_fields(self, request, obj=None):
        if obj:  # editing an existing object
            return self.readonly_fields + ('talker', 'listener', 'amount')
        return self.readonly_fields
