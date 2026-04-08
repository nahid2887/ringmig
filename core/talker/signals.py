from django.db.models.signals import post_save
from django.dispatch import receiver
from users.models import User
from .models import TalkerProfile
from decimal import Decimal


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


@receiver(post_save, sender=User)
def create_talker_balance(sender, instance, created, **kwargs):
    """Auto-create TalkerBalance when a user with talker role is created."""
    if created and instance.user_type == 'talker':
        from .models import TalkerBalance
        TalkerBalance.objects.get_or_create(
            talker=instance,
            defaults={'available_balance': Decimal('0.00'), 'total_earned': Decimal('0.00')}
        )


@receiver(post_save, sender=User)
def save_talker_balance(sender, instance, **kwargs):
    """Ensure talker balance exists if user changes to talker type."""
    if instance.user_type == 'talker':
        from .models import TalkerBalance
        if not hasattr(instance, 'talker_balance_account'):
            TalkerBalance.objects.get_or_create(
                talker=instance,
                defaults={'available_balance': Decimal('0.00'), 'total_earned': Decimal('0.00')}
            )
