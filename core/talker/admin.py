from django.contrib import admin
from .models import TalkerProfile, FavoriteListener, TalkerBalance

@admin.register(TalkerProfile)
class TalkerProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'get_full_name', 'location', 'created_at']
    search_fields = ['user__email', 'first_name', 'last_name']
    
    def get_full_name(self, obj):
        return obj.get_full_name()
    get_full_name.short_description = 'Full Name'


@admin.register(FavoriteListener)
class FavoriteListenerAdmin(admin.ModelAdmin):
    list_display = ['talker', 'listener', 'added_at']
    search_fields = ['talker__email', 'listener__user__email']
    list_filter = ['added_at']
    readonly_fields = ['added_at']


@admin.register(TalkerBalance)
class TalkerBalanceAdmin(admin.ModelAdmin):
    list_display = ['talker', 'available_balance', 'total_earned', 'total_refunded', 'updated_at']
    search_fields = ['talker__email']
    readonly_fields = ['total_earned', 'total_refunded', 'created_at', 'updated_at']
    ordering = ['-available_balance']
