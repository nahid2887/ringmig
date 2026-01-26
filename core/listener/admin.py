from django.contrib import admin
from .models import ListenerProfile, ListenerRating, ListenerBalance


@admin.register(ListenerProfile)
class ListenerProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'get_full_name', 'is_available', 'average_rating', 'total_hours']
    search_fields = ['user__email', 'first_name', 'last_name']
    list_filter = ['is_available', 'experience_level']


@admin.register(ListenerRating)
class ListenerRatingAdmin(admin.ModelAdmin):
    list_display = ['listener', 'talker', 'rating', 'created_at']
    search_fields = ['listener__user__email', 'talker__email']
    list_filter = ['rating']


@admin.register(ListenerBalance)
class ListenerBalanceAdmin(admin.ModelAdmin):
    list_display = ['listener', 'available_balance', 'total_earned', 'updated_at']
    search_fields = ['listener__email']
    readonly_fields = ['total_earned', 'created_at', 'updated_at']
    ordering = ['-available_balance']
