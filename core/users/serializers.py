from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _
from .models import OTP

User = get_user_model()


class OTPRequestSerializer(serializers.Serializer):
    """Serializer for requesting OTP during registration."""
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=200)
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    user_type = serializers.ChoiceField(choices=['talker', 'listener'], required=False, default='talker')
    language = serializers.ChoiceField(choices=['en', 'sv'], required=False, default='en')

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({'password_confirm': _('Passwords do not match.')})
        
        # Check if email already exists
        if User.objects.filter(email=attrs['email']).exists():
            raise serializers.ValidationError({'email': _('Email is already registered.')})
        
        return attrs


class OTPVerificationSerializer(serializers.Serializer):
    """Serializer for verifying OTP during registration."""
    email = serializers.EmailField()
    otp_code = serializers.CharField(max_length=6, min_length=6)


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for user registration - full_name, email, password."""
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['full_name', 'email', 'password', 'password_confirm']

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({'password_confirm': 'Passwords do not match.'})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        user = User.objects.create_user(**validated_data)
        return user


class UserLoginSerializer(serializers.Serializer):
    """Serializer for user login - email and password."""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user details."""

    class Meta:
        model = User
        fields = ['id', 'email', 'full_name', 'user_type', 'phone_number', 'birthday', 'language', 'is_active', 'is_verified', 'created_at']
        read_only_fields = ['id', 'email', 'is_active', 'is_verified', 'created_at']


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for password change."""
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': _('Passwords do not match.')})
        return attrs
