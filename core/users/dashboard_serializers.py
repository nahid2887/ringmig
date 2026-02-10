from rest_framework import serializers
from django.db.models import Count, Sum, Q
from django.contrib.auth import get_user_model
from decimal import Decimal

User = get_user_model()


class DashboardStatsSerializer(serializers.Serializer):
    """Serializer for dashboard statistics."""
    total_users = serializers.IntegerField()
    total_talkers = serializers.IntegerField()
    total_listeners = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    platform_commission = serializers.DecimalField(max_digits=12, decimal_places=2)
    listener_earnings = serializers.DecimalField(max_digits=12, decimal_places=2)


class ChartDataPointSerializer(serializers.Serializer):
    """Serializer for chart data points."""
    month = serializers.CharField()
    total_earned = serializers.DecimalField(max_digits=12, decimal_places=2)
    listener_earnings = serializers.DecimalField(max_digits=12, decimal_places=2)


class EarningsChartSerializer(serializers.Serializer):
    """Serializer for earnings chart data."""
    data = ChartDataPointSerializer(many=True)
    currency = serializers.CharField()


class SubscriptionSplitSerializer(serializers.Serializer):
    """Serializer for subscription split data."""
    talker_count = serializers.IntegerField()
    listener_count = serializers.IntegerField()
    talker_percentage = serializers.FloatField()
    listener_percentage = serializers.FloatField()


class SuperAdminDashboardSerializer(serializers.Serializer):
    """Complete superadmin dashboard data."""
    stats = DashboardStatsSerializer()
    earnings_chart = EarningsChartSerializer()
    subscription_split = SubscriptionSplitSerializer()
