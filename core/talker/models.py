from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import timedelta

User = get_user_model()

# Import for FavoriteListener model
from listener.models import ListenerProfile


class TalkerProfile(models.Model):
    """Profile for users with talker role."""
    
    GENDER_CHOICES = [
        ('male', _('Male')),
        ('female', _('Female')),
        ('other', _('Other')),
        ('prefer_not_to_say', _('Prefer not to say')),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='talker_profile')
    
    # Personal Information
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, blank=True)
    profile_image = models.ImageField(upload_to='talker_profiles/', null=True, blank=True)
    location = models.CharField(max_length=255, blank=True, help_text=_('City, Country'))
    about_me = models.TextField(blank=True, help_text=_('Tell listeners about yourself'))
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Talker: {self.user.email}"
    
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.user.email

    class Meta:
        verbose_name = 'Talker Profile'
        verbose_name_plural = 'Talker Profiles'


class FavoriteListener(models.Model):
    """Model to store talker's favorite listeners."""
    
    talker = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorite_listeners')
    listener = models.ForeignKey(ListenerProfile, on_delete=models.CASCADE, related_name='favorited_by_talkers')
    added_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('talker', 'listener')
        verbose_name = 'Favorite Listener'
        verbose_name_plural = 'Favorite Listeners'
        ordering = ['-added_at']
    
    def __str__(self):
        return f"{self.talker.email} favorites {self.listener.get_full_name()}"


class TalkerReport(models.Model):
    """Model to store reports against talkers by listeners."""
    
    REPORT_REASON_CHOICES = [
        ('harassment', _('Harassment or Abuse')),
        ('inappropriate_content', _('Inappropriate Content')),
        ('scam', _('Scam or Fraud')),
        ('hate_speech', _('Hate Speech')),
        ('threatening', _('Threatening Behavior')),
        ('fake_profile', _('Fake Profile')),
        ('other', _('Other')),
    ]
    
    STATUS_CHOICES = [
        ('pending', _('Pending Review')),
        ('reviewed', _('Reviewed')),
        ('resolved', _('Resolved')),
        ('dismissed', _('Dismissed')),
    ]
    
    talker = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='reports_against_talker',
        limit_choices_to={'user_type': 'talker'}
    )
    
    reporter = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='talker_reports_filed',
        limit_choices_to={'user_type': 'listener'}
    )
    
    reason = models.CharField(
        max_length=50,
        choices=REPORT_REASON_CHOICES,
        help_text=_('Reason for reporting')
    )
    
    description = models.TextField(
        help_text=_('Detailed description of the issue'),
        blank=True
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='talker_reports_reviewed'
    )
    
    class Meta:
        verbose_name = 'Talker Report'
        verbose_name_plural = 'Talker Reports'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['talker', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]
    
    def __str__(self):
        return f"Report: {self.reporter.email} reported {self.talker.email} - {self.reason}"


class TalkerSuspension(models.Model):
    """Model to track talker suspensions."""
    
    SUSPENSION_REASON_CHOICES = [
        ('reports', _('Multiple Reports')),
        ('violation', _('Account Violation')),
        ('manual', _('Manual Suspension')),
    ]
    
    talker = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='suspension',
        limit_choices_to={'user_type': 'talker'}
    )
    
    reason = models.CharField(
        max_length=50,
        choices=SUSPENSION_REASON_CHOICES,
        default='reports'
    )
    
    suspended_at = models.DateTimeField(auto_now_add=True)
    resume_at = models.DateTimeField(
        help_text=_('When the suspension will be lifted')
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text=_('Whether suspension is currently active')
    )
    
    days_suspended = models.IntegerField(
        default=7,
        help_text=_('Number of days the account is suspended')
    )
    
    notes = models.TextField(
        blank=True,
        help_text=_('Admin notes about the suspension')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Talker Suspension'
        verbose_name_plural = 'Talker Suspensions'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Suspension: {self.talker.email} until {self.resume_at.date()}"
    
    def is_suspension_active(self):
        """Check if suspension is still active."""
        return self.is_active and timezone.now() < self.resume_at
    
    def get_remaining_days(self):
        """Get number of remaining suspension days."""
        if not self.is_suspension_active():
            return 0
        remaining = self.resume_at - timezone.now()
        days = remaining.days + (1 if remaining.seconds > 0 else 0)
        return max(0, days)

