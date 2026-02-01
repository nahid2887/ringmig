from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

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

