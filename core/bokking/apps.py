from django.apps import AppConfig


class BokkingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'bokking'
    verbose_name = 'Booking & Availability Management'    
    def ready(self):
        """Import signals when app is ready."""
        import bokking.signals  # noqa