from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

User = get_user_model()


@receiver(post_save, sender=User)
def create_listener_profile(sender, instance, created, **kwargs):
    """
    Automatically create a ListenerProfile when a user with user_type='listener' is created.
    """
    if created and instance.user_type == 'listener':
        from .models import ListenerProfile
        ListenerProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def save_listener_profile(sender, instance, **kwargs):
    """
    Ensure listener profile is updated if user changes to listener type.
    """
    if instance.user_type == 'listener':
        from .models import ListenerProfile
        if not hasattr(instance, 'listener_profile'):
            ListenerProfile.objects.get_or_create(user=instance)
