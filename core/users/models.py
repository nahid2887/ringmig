from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils.translation import gettext_lazy as _


class CustomUserManager(BaseUserManager):
    """Custom user manager for User model with email authentication."""
    
    def create_user(self, email, password=None, **extra_fields):
        """Create and save a regular user."""
        if not email:
            raise ValueError(_('The Email field must be set'))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        """Create and save a superuser."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))
        
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom User model with email-based authentication."""
    
    USER_TYPE_CHOICES = [
        ('talker', _('Talker')),
        ('listener', _('Listener')),
    ]
    
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=200, blank=True)
    user_type = models.CharField(
        max_length=20,
        choices=USER_TYPE_CHOICES,
        default='talker'
    )
    phone_number = models.CharField(max_length=20, blank=True)
    birthday = models.DateField(null=True, blank=True)
    language = models.CharField(max_length=10, default='en')
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    objects = CustomUserManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']
    
    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['-created_at']
    
    def __str__(self):
        return self.email
    
    def get_full_name(self):
        return self.full_name
    
    def get_short_name(self):
        return self.full_name.split()[0] if self.full_name else self.email


class OTP(models.Model):
    """Model to store OTP codes for user registration."""
    
    email = models.EmailField(unique=True)
    otp_code = models.CharField(max_length=6)
    full_name = models.CharField(max_length=200, blank=True)
    password = models.CharField(max_length=255, blank=True)
    user_type = models.CharField(
        max_length=20,
        choices=[('talker', 'Talker'), ('listener', 'Listener')],
        default='talker'
    )
    language = models.CharField(max_length=10, default='en')
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = _('OTP')
        verbose_name_plural = _('OTPs')
    
    def __str__(self):
        return f"OTP for {self.email}"
    
    def is_expired(self):
        """Check if OTP has expired."""
        from django.utils import timezone
        return timezone.now() > self.expires_at
