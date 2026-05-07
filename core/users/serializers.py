from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _
from .models import OTP, PasswordResetOTP

User = get_user_model()

# Language choices - 50+ languages for user selection
LANGUAGE_CHOICES = [
    ('en', 'English'),
    ('es', 'Español (Spanish)'),
    ('fr', 'Français (French)'),
    ('de', 'Deutsch (German)'),
    ('it', 'Italiano (Italian)'),
    ('pt', 'Português (Portuguese)'),
    ('ru', 'Русский (Russian)'),
    ('ja', '日本語 (Japanese)'),
    ('zh', '中文 (Chinese)'),
    ('ko', '한국어 (Korean)'),
    ('ar', 'العربية (Arabic)'),
    ('hi', 'हिन्दी (Hindi)'),
    ('bn', 'বাংলা (Bengali)'),
    ('pa', 'ਪੰਜਾਬੀ (Punjabi)'),
    ('te', 'తెలుగు (Telugu)'),
    ('mr', 'मराठी (Marathi)'),
    ('ta', 'தமிழ் (Tamil)'),
    ('gu', 'ગુજરાતી (Gujarati)'),
    ('kn', 'ಕನ್ನಡ (Kannada)'),
    ('ml', 'മലയാളം (Malayalam)'),
    ('th', 'ไทย (Thai)'),
    ('vi', 'Tiếng Việt (Vietnamese)'),
    ('id', 'Bahasa Indonesia (Indonesian)'),
    ('ms', 'Bahasa Melayu (Malay)'),
    ('tl', 'Tagalog (Filipino)'),
    ('tr', 'Türkçe (Turkish)'),
    ('pl', 'Polski (Polish)'),
    ('uk', 'Українська (Ukrainian)'),
    ('cs', 'Čeština (Czech)'),
    ('ro', 'Română (Romanian)'),
    ('hu', 'Magyar (Hungarian)'),
    ('el', 'Ελληνικά (Greek)'),
    ('sv', 'Svenska (Swedish)'),
    ('no', 'Norsk (Norwegian)'),
    ('da', 'Dansk (Danish)'),
    ('fi', 'Suomi (Finnish)'),
    ('nl', 'Nederlands (Dutch)'),
    ('be', 'Белорусский (Belarusian)'),
    ('bg', 'Български (Bulgarian)'),
    ('hr', 'Hrvatski (Croatian)'),
    ('sk', 'Slovenčina (Slovak)'),
    ('sl', 'Slovenščina (Slovenian)'),
    ('et', 'Eesti (Estonian)'),
    ('lv', 'Latviešu (Latvian)'),
    ('lt', 'Lietuvių (Lithuanian)'),
    ('he', 'עברית (Hebrew)'),
    ('fa', 'فارسی (Persian)'),
    ('ur', 'اردو (Urdu)'),
    ('sw', 'Kiswahili (Swahili)'),
    ('af', 'Afrikaans'),
    ('sq', 'Shqip (Albanian)'),
    ('hy', 'Հայերեն (Armenian)'),
    ('ka', 'ქართული (Georgian)'),
]


class OTPRequestSerializer(serializers.Serializer):
    """Serializer for requesting OTP during registration."""
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=200)
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    user_type = serializers.ChoiceField(choices=['talker', 'listener'], required=False, default='talker')
    language = serializers.ChoiceField(choices=LANGUAGE_CHOICES, required=False, default='en')

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
    profile_image = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'full_name', 'user_type', 'phone_number', 'birthday', 'language', 'profile_image', 'is_active', 'is_verified', 'created_at']
        read_only_fields = ['id', 'email', 'is_active', 'is_verified', 'created_at']

    def get_profile_image(self, obj):
        """Return absolute URL for the user's profile image from role profile."""
        image_field = None

        if hasattr(obj, 'talker_profile') and obj.talker_profile and obj.talker_profile.profile_image:
            image_field = obj.talker_profile.profile_image
        elif hasattr(obj, 'listener_profile') and obj.listener_profile and obj.listener_profile.profile_image:
            image_field = obj.listener_profile.profile_image

        if not image_field:
            return None

        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(image_field.url)
        return image_field.url


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for password change."""
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': _('Passwords do not match.')})
        return attrs


class ForgotPasswordRequestSerializer(serializers.Serializer):
    """Serializer for forgot password - request OTP by email."""
    email = serializers.EmailField()
    
    def validate_email(self, value):
        """Check if email exists in the system."""
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError(_('Email is not registered.'))
        return value


class VerifyPasswordResetOTPSerializer(serializers.Serializer):
    """Serializer for verifying password reset OTP."""
    email = serializers.EmailField()
    otp_code = serializers.CharField(max_length=6, min_length=6)


class ChangePasswordAfterResetSerializer(serializers.Serializer):
    """Serializer for changing password after OTP verification."""
    email = serializers.EmailField()
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': _('Passwords do not match.')})
        
        if not User.objects.filter(email=attrs['email']).exists():
            raise serializers.ValidationError({'email': _('Email is not registered.')})
        
        return attrs
