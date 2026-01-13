from django.apps import AppConfig


class TalkerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'talker'

    def ready(self):
        import talker.signals

