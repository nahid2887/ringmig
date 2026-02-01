from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from .models import ListenerProfile, ListenerRating, ListenerBlockedTalker


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
    profile_image_url = serializers.SerializerMethodField()

    class Meta:
        model = ListenerProfile
        fields = ['id', 'user', 'user_email', 'first_name', 'last_name', 'full_name', 'gender', 
                  'profile_image', 'profile_image_url', 'location', 'experience_level', 'bio', 'about_me', 'specialties', \
                  'topics', 'languages', 'hourly_rate', 'is_available', 'accept_direct_calls', \
                  'total_hours', 'average_rating', 'created_at', 'updated_at']
        read_only_fields = ['user', 'user_email', 'total_hours', 'average_rating', 'created_at', 'updated_at', 'id', 'profile_image_url']
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


class ListenerListSerializer(serializers.ModelSerializer):
    """Serializer for listing listeners."""
    id = serializers.CharField(source='user.id', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_type = serializers.CharField(source='user.user_type', read_only=True)
    full_name = serializers.SerializerMethodField()
    profile_image = serializers.SerializerMethodField()

    class Meta:
        model = ListenerProfile
        fields = ['id', 'user_email', 'user_type', 'full_name', 'profile_image', 'gender', 'location',
                  'experience_level', 'bio', 'about_me', 'specialties', 'topics', 'languages',
                  'hourly_rate', 'is_available', 'accept_direct_calls', 'total_hours', 'average_rating']

    def get_full_name(self, obj):
        return obj.get_full_name()
    
    def get_profile_image(self, obj):
        if obj.profile_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.profile_image.url)
            return obj.profile_image.url
        return None


class BlockTalkerSerializer(serializers.Serializer):
    """Serializer for blocking a talker."""
    talker_id = serializers.IntegerField(help_text=_('The ID of the talker to block'))
    
    def validate_talker_id(self, value):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user = User.objects.get(id=value, user_type='talker')
        except User.DoesNotExist:
            raise serializers.ValidationError(_('Talker with this ID does not exist'))
        return value


class UnblockTalkerSerializer(serializers.Serializer):
    """Serializer for unblocking a talker."""
    talker_id = serializers.IntegerField(help_text=_('The ID of the talker to unblock'))
    
    def validate_talker_id(self, value):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user = User.objects.get(id=value, user_type='talker')
        except User.DoesNotExist:
            raise serializers.ValidationError(_('Talker with this ID does not exist'))
        return value


class BlockedTalkerListSerializer(serializers.ModelSerializer):
    """Serializer for listing blocked talkers."""
    talker_id = serializers.CharField(source='talker.id', read_only=True)
    talker_email = serializers.CharField(source='talker.email', read_only=True)
    blocked_at = serializers.DateTimeField(read_only=True)
    
    class Meta:
        model = ListenerBlockedTalker
        fields = ['talker_id', 'talker_email', 'blocked_at']
