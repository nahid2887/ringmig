from django.contrib import admin
from .models import ListenerAvailability, TimeSlot, UniversalBookingPackage, SessionBooking


class TimeSlotInline(admin.TabularInline):
    """Inline admin for TimeSlots within ListenerAvailability."""
    model = TimeSlot
    extra = 1
    fields = ('day_of_week', 'start_time', 'end_time')


@admin.register(ListenerAvailability)
class ListenerAvailabilityAdmin(admin.ModelAdmin):
    """Admin interface for Listener Availability."""
    list_display = ('listener', 'buffer_time_minutes', 'created_at', 'updated_at')
    search_fields = ('listener__username', 'listener__email')
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [TimeSlotInline]
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'listener', 'buffer_time_minutes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    """Admin interface for Time Slots."""
    list_display = ('get_listener', 'day_of_week', 'start_time', 'end_time', 'created_at')
    list_filter = ('day_of_week', 'availability__listener')
    search_fields = ('availability__listener__username',)
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        ('Time Slot Information', {
            'fields': ('id', 'availability', 'day_of_week', 'start_time', 'end_time')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_listener(self, obj):
        """Display the listener name."""
        return obj.availability.listener.email
    get_listener.short_description = 'Listener'


@admin.register(UniversalBookingPackage)
class UniversalBookingPackageAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'package_type', 'media_type', 'duration', 'price', 'is_active', 'created_at')
    list_filter = ('package_type', 'media_type', 'is_active')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(SessionBooking)
class SessionBookingAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'talker', 'listener', 'booking_date', 'start_time', 'end_time',
        'status', 'price', 'payment_completed_at'
    )
    list_filter = ('status', 'booking_date', 'created_at')
    search_fields = ('talker__email', 'listener__email', 'transaction_id')
    readonly_fields = ('created_at', 'updated_at', 'payment_completed_at')
