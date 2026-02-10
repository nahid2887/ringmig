from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from .models import ListenerProfile, ListenerRating, ListenerBlockedTalker


class ListenerCallAttemptSerializer(serializers.Serializer):
    """Serializer for listener call attempts (CallSession)."""
    id = serializers.IntegerField(read_only=True)
    talker_id = serializers.SerializerMethodField(read_only=True)
    talker_email = serializers.SerializerMethodField(read_only=True)
    talker_name = serializers.SerializerMethodField(read_only=True)
    status = serializers.CharField(read_only=True)
    call_type = serializers.CharField(read_only=True)
    total_minutes_purchased = serializers.IntegerField(read_only=True)
    minutes_used = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    started_at = serializers.DateTimeField(read_only=True)
    ended_at = serializers.DateTimeField(read_only=True)
    end_reason = serializers.CharField(read_only=True)
    duration_in_minutes = serializers.SerializerMethodField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    
    def get_talker_id(self, obj):
        """Get talker ID from CallSession object."""
        return obj.talker.id if obj.talker else None
    
    def get_talker_email(self, obj):
        """Get talker email from CallSession object."""
        return obj.talker.email if obj.talker else None
    
    def get_talker_name(self, obj):
        """Get talker full name or email."""
        if obj.talker:
            return obj.talker.full_name or obj.talker.email
        return None
    
    def get_duration_in_minutes(self, obj):
        """Calculate actual call duration."""
        if obj.started_at and obj.ended_at:
            delta = obj.ended_at - obj.started_at
            return round(delta.total_seconds() / 60, 2)
        return 0


class ListenerCallAttemptDetailSerializer(serializers.Serializer):
    """Detailed serializer for a single call attempt."""
    id = serializers.IntegerField(read_only=True)
    talker_id = serializers.SerializerMethodField(read_only=True)
    talker_email = serializers.SerializerMethodField(read_only=True)
    talker_full_name = serializers.SerializerMethodField(read_only=True)
    talker_profile = serializers.SerializerMethodField(read_only=True)
    status = serializers.CharField(read_only=True)
    call_type = serializers.CharField(read_only=True)
    total_minutes_purchased = serializers.IntegerField(read_only=True)
    minutes_used = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    started_at = serializers.DateTimeField(read_only=True)
    ended_at = serializers.DateTimeField(read_only=True)
    end_reason = serializers.CharField(read_only=True)
    last_warning_sent = serializers.BooleanField(read_only=True)
    duration_in_minutes = serializers.SerializerMethodField(read_only=True)
    call_package_details = serializers.SerializerMethodField(read_only=True)
    agora_channel_name = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    
    def get_talker_id(self, obj):
        """Get talker ID from CallSession object."""
        return obj.talker.id if obj.talker else None
    
    def get_talker_email(self, obj):
        """Get talker email from CallSession object."""
        return obj.talker.email if obj.talker else None
    
    def get_talker_full_name(self, obj):
        """Get talker full name or email."""
        if obj.talker:
            return obj.talker.full_name or obj.talker.email
        return None
    
    def get_duration_in_minutes(self, obj):
        """Calculate actual call duration."""
        if obj.started_at and obj.ended_at:
            delta = obj.ended_at - obj.started_at
            return round(delta.total_seconds() / 60, 2)
        return 0
    
    def get_talker_profile(self, obj):
        """Get talker's profile information."""
        if obj.talker:
            return {
                'id': obj.talker.id,
                'email': obj.talker.email,
                'full_name': obj.talker.full_name,
                'user_type': obj.talker.user_type
            }
        return None
    
    def get_call_package_details(self, obj):
        """Get call package details."""
        if obj.call_package:
            try:
                return {
                    'id': obj.call_package.id,
                    'package_name': obj.call_package.package.name,
                    'duration_minutes': obj.call_package.package.duration_minutes,
                    'price': str(obj.call_package.total_amount),
                    'status': obj.call_package.status
                }
            except:
                return None
        return None



class ListenerRatingSerializer(serializers.ModelSerializer):
    """Serializer for rating a listener."""
    talker_email = serializers.CharField(source='talker.email', read_only=True)
    listener_email = serializers.CharField(source='listener.user.email', read_only=True)
    
    class Meta:
        model = ListenerRating
        fields = ['id', 'listener', 'listener_email', 'talker', 'talker_email', 'rating', 'review', 'created_at', 'updated_at']
        read_only_fields = ['id', 'listener', 'listener_email', 'talker', 'talker_email', 'created_at', 'updated_at']


class ListenerReviewDisplaySerializer(serializers.ModelSerializer):
    """Serializer to display listener reviews/ratings in a user-friendly format."""
    talker_name = serializers.SerializerMethodField()
    talker_avatar = serializers.SerializerMethodField()
    time_ago = serializers.SerializerMethodField()
    star_rating = serializers.IntegerField(source='rating', read_only=True)
    
    class Meta:
        model = ListenerRating
        fields = ['id', 'talker_name', 'talker_avatar', 'star_rating', 'review', 'time_ago', 'created_at']
    
    def get_talker_name(self, obj):
        """Get talker's full name or email."""
        return obj.talker.full_name or obj.talker.email
    
    def get_talker_avatar(self, obj):
        """Get talker's avatar if available."""
        if hasattr(obj.talker, 'talker_profile') and obj.talker.talker_profile.profile_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.talker.talker_profile.profile_image.url)
        return None
    
    def get_time_ago(self, obj):
        """Get human-readable time ago."""
        from django.utils.timesince import timesince
        return f"{timesince(obj.created_at)} ago"


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
    reviews = serializers.SerializerMethodField()

    class Meta:
        model = ListenerProfile
        fields = ['id', 'user_email', 'user_type', 'full_name', 'profile_image', 'gender', 'location',
                  'experience_level', 'bio', 'about_me', 'specialties', 'topics', 'languages',
                  'hourly_rate', 'is_available', 'accept_direct_calls', 'total_hours', 'average_rating', 'reviews']

    def get_full_name(self, obj):
        return obj.get_full_name()
    
    def get_profile_image(self, obj):
        if obj.profile_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.profile_image.url)
            return obj.profile_image.url
        return None
    
    def get_reviews(self, obj):
        """Get all reviews for this listener in display format."""
        ratings = obj.ratings.all().order_by('-created_at')[:10]  # Latest 10 reviews
        serializer = ListenerReviewDisplaySerializer(ratings, many=True, context=self.context)
        return {
            'count': obj.ratings.count(),
            'results': serializer.data
        }


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
