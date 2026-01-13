from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from datetime import timedelta


class CustomUserManager(BaseUserManager):
    """Custom user manager for email-based authentication."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom User model with email as the primary identifier."""

    USER_TYPE_CHOICES = [
        ('talker', 'Talker'),
        ('listener', 'Listener'),
    ]

    LANGUAGE_CHOICES = [
        ('en', _('English')),
        ('sv', _('Swedish')),
    ]

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=200, blank=True)
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='talker')
    phone_number = models.CharField(max_length=20, blank=True)
    birthday = models.DateField(null=True, blank=True)
    language = models.CharField(max_length=5, choices=LANGUAGE_CHOICES, default='en', help_text=_('Preferred language'))
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return self.email


class OTP(models.Model):
    """Model to store OTP for email verification during registration."""
    email = models.EmailField()
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_verified = models.BooleanField(default=False)    # Store registration data
    full_name = models.CharField(max_length=200, blank=True)
    password = models.CharField(max_length=255, blank=True)
    user_type = models.CharField(max_length=20, default='talker', blank=True)
    class Meta:
        verbose_name = 'OTP'
        verbose_name_plural = 'OTPs'

    def is_expired(self):
        """Check if OTP has expired."""
        return timezone.now() > self.expires_at

    def __str__(self):
        return self.email

    def get_full_name(self):
        return self.full_name or self.email
