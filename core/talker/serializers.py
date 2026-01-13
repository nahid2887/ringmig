from rest_framework import serializers
from .models import TalkerProfile


class TalkerProfileSerializer(serializers.ModelSerializer):
    """Serializer for talker profile personal information."""
    full_name = serializers.SerializerMethodField()
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = TalkerProfile
        fields = ['id', 'user', 'user_email', 'first_name', 'last_name', 'full_name', 'gender', 
                  'profile_image', 'location', 'about_me', 'created_at', 'updated_at']
        read_only_fields = ['user', 'user_email', 'created_at', 'updated_at', 'id']

    def get_full_name(self, obj):
        return obj.get_full_name()
