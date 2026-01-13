from django.db.models.signals import post_save
from django.dispatch import receiver
from users.models import User
from .models import TalkerProfile


@receiver(post_save, sender=User)
def create_talker_profile(sender, instance, created, **kwargs):
    """Auto-create TalkerProfile when a new user with talker role is created."""
    if created and instance.user_type == 'talker':
        TalkerProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def update_or_create_talker_profile(sender, instance, created, **kwargs):
    """Auto-create or update TalkerProfile when user_type changes to talker."""
    if not created and instance.user_type == 'talker':
        TalkerProfile.objects.get_or_create(user=instance)
