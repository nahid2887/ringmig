from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from .models import ListenerProfile, ListenerRating


class ListenerRatingSerializer(serializers.ModelSerializer):
    """Serializer for rating a listener."""
    talker_email = serializers.CharField(source='talker.email', read_only=True)
    
    class Meta:
        model = ListenerRating
        fields = ['id', 'listener', 'talker', 'talker_email', 'rating', 'review', 'created_at', 'updated_at']
        read_only_fields = ['id', 'talker', 'talker_email', 'created_at', 'updated_at']


class ListenerProfileSerializer(serializers.ModelSerializer):
    """Serializer for listener profile with personal information."""
    full_name = serializers.SerializerMethodField()
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = ListenerProfile
        fields = ['id', 'user', 'user_email', 'first_name', 'last_name', 'full_name', 'gender', 
                  'profile_image', 'location', 'experience_level', 'bio', 'about_me', 'specialties', 
                  'topics', 'languages', 'hourly_rate', 'is_available', 'accept_direct_calls', 
                  'total_hours', 'average_rating', 'created_at', 'updated_at']
        read_only_fields = ['user', 'user_email', 'total_hours', 'average_rating', 'created_at', 'updated_at', 'id']

    def get_full_name(self, obj):
        return obj.get_full_name()


class ListenerListSerializer(serializers.ModelSerializer):
    """Serializer for listing listeners."""
    user_email = serializers.CharField(source='user.email', read_only=True)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = ListenerProfile
        fields = ['id', 'user_email', 'full_name', 'profile_image', 'gender', 'location',
                  'experience_level', 'bio', 'about_me', 'specialties', 'topics', 'languages',
                  'hourly_rate', 'is_available', 'accept_direct_calls', 'total_hours', 'average_rating']

    def get_full_name(self, obj):
        return obj.get_full_name()
