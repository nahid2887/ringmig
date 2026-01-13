from django.apps import AppConfig


class ListenerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'listener'
    verbose_name = 'Listener Management'

    def ready(self):
        import listener.signals
