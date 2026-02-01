from rest_framework import serializers
from .models import TalkerProfile, FavoriteListener
from listener.models import ListenerProfile


class TalkerProfileSerializer(serializers.ModelSerializer):
    """Serializer for talker profile personal information."""
    full_name = serializers.SerializerMethodField()
    user_email = serializers.CharField(source='user.email', read_only=True)
    profile_image_url = serializers.SerializerMethodField()

    class Meta:
        model = TalkerProfile
        fields = ['id', 'user', 'user_email', 'first_name', 'last_name', 'full_name', 'gender', 
                  'profile_image', 'profile_image_url', 'location', 'about_me', 'created_at', 'updated_at']
        read_only_fields = ['user', 'user_email', 'created_at', 'updated_at', 'id', 'profile_image_url']
        extra_kwargs = {
            'profile_image': {'allow_null': True, 'required': False}
        }

    def get_full_name(self, obj):
        return obj.get_full_name()
    
    def get_profile_image_url(self, obj):
        if obj.profile_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.profile_image.url)
            return obj.profile_image.url
        return None

class FavoriteListenerSerializer(serializers.ModelSerializer):
    """Serializer for favorite listener with listener details."""
    listener_id = serializers.IntegerField(source='listener.user_id', read_only=True)
    full_name = serializers.CharField(source='listener.get_full_name', read_only=True)
    email = serializers.CharField(source='listener.user.email', read_only=True)
    profile_image = serializers.SerializerMethodField()
    gender = serializers.CharField(source='listener.gender', read_only=True)
    location = serializers.CharField(source='listener.location', read_only=True)
    experience_level = serializers.CharField(source='listener.experience_level', read_only=True)
    bio = serializers.CharField(source='listener.bio', read_only=True)
    hourly_rate = serializers.CharField(source='listener.hourly_rate', read_only=True)
    average_rating = serializers.FloatField(source='listener.average_rating', read_only=True)
    total_hours = serializers.FloatField(source='listener.total_hours', read_only=True)
    
    class Meta:
        model = FavoriteListener
        fields = [
            'id', 'listener_id', 'full_name', 'email', 'profile_image', 'gender', 
            'location', 'experience_level', 'bio', 'hourly_rate', 'average_rating', 
            'total_hours', 'added_at'
        ]
        read_only_fields = ['id', 'added_at']
    
    def get_profile_image(self, obj):
        if obj.listener.profile_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.listener.profile_image.url)
            return obj.listener.profile_image.url
        return None


class AddFavoriteListenerSerializer(serializers.Serializer):
    """Serializer for adding a listener to favorites."""
    listener_id = serializers.IntegerField(required=True)
    
    def validate_listener_id(self, value):
        """Validate that the listener exists."""
        try:
            ListenerProfile.objects.get(user_id=value)
        except ListenerProfile.DoesNotExist:
            raise serializers.ValidationError(f"Listener with ID {value} not found.")
        return value