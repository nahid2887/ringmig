from django.contrib import admin
from .models import Conversation, Message, FileAttachment, CallSession, CallPackage, UniversalCallPackage


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['id', 'listener', 'talker', 'last_message_at', 'created_at']
    list_filter = ['created_at', 'last_message_at']
    search_fields = ['listener__email', 'talker__email']
    readonly_fields = ['created_at', 'updated_at', 'last_message_at']


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'conversation', 'sender', 'message_type', 'is_read', 'created_at']
    list_filter = ['message_type', 'is_read', 'created_at']
    search_fields = ['sender__email', 'content']
    readonly_fields = ['created_at']


@admin.register(FileAttachment)
class FileAttachmentAdmin(admin.ModelAdmin):
    list_display = ['id', 'filename', 'file_size', 'file_type', 'uploaded_at']
    list_filter = ['file_type', 'uploaded_at']
    search_fields = ['filename']
    readonly_fields = ['uploaded_at', 'file_size', 'file_type']


@admin.register(UniversalCallPackage)
class UniversalCallPackageAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'package_type', 'duration_minutes', 'price', 'app_fee_percentage', 'display_app_fee', 'display_listener_amount', 'is_active']
    list_filter = ['package_type', 'is_active', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at', 'display_app_fee', 'display_listener_amount']
    fieldsets = (
        ('Package Information', {
            'fields': ('name', 'package_type', 'description', 'is_active')
        }),
        ('Pricing', {
            'fields': ('duration_minutes', 'price', 'app_fee_percentage', 'display_app_fee', 'display_listener_amount')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def display_app_fee(self, obj):
        """Display app fee (safe for unsaved objects)."""
        if obj.pk and obj.price is not None:
            return f"${obj.app_fee}"
        return "-"
    display_app_fee.short_description = 'App Fee'
    
    def display_listener_amount(self, obj):
        """Display listener amount (safe for unsaved objects)."""
        if obj.pk and obj.price is not None:
            return f"${obj.listener_amount}"
        return "-"
    display_listener_amount.short_description = 'Listener Amount'


@admin.register(CallPackage)
class CallPackageAdmin(admin.ModelAdmin):
    list_display = ['id', 'talker', 'listener', 'package', 'total_amount', 'app_fee', 'listener_amount', 'status', 'payment_status', 'purchased_at']
    list_filter = ['status', 'purchased_at', 'package__package_type']
    search_fields = ['talker__email', 'listener__email', 'stripe_payment_intent_id']
    readonly_fields = ['purchased_at', 'created_at', 'updated_at', 'payment_status']
    list_select_related = ['talker', 'listener', 'package', 'call_session']
    fieldsets = (
        ('Participants', {
            'fields': ('talker', 'listener', 'package')
        }),
        ('Pricing Snapshot', {
            'fields': ('total_amount', 'app_fee', 'listener_amount')
        }),
        ('Status & Timing', {
            'fields': ('status', 'started_at', 'ended_at', 'actual_duration_minutes')
        }),
        ('Payment Information', {
            'fields': ('stripe_payment_intent_id', 'stripe_charge_id', 'stripe_customer_id', 'payment_status')
        }),
        ('Additional Info', {
            'fields': ('notes', 'cancellation_reason', 'call_session')
        }),
        ('Timestamps', {
            'fields': ('purchased_at', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(CallSession)
class CallSessionAdmin(admin.ModelAdmin):
    list_display = ['id', 'talker', 'listener', 'status', 'total_minutes_purchased', 'minutes_used', 'started_at']
    list_filter = ['status', 'started_at', 'created_at']
    search_fields = ['talker__email', 'listener__email']
    readonly_fields = ['created_at', 'updated_at', 'started_at', 'ended_at']
    list_select_related = ['talker', 'listener', 'booking', 'call_package']
