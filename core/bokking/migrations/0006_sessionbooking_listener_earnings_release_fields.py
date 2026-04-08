from django.db import migrations, models
from django.utils import timezone


def mark_historical_completed_bookings_as_released(apps, schema_editor):
    SessionBooking = apps.get_model('bokking', 'SessionBooking')
    now = timezone.now()
    SessionBooking.objects.filter(status='completed').update(
        listener_earnings_released=True,
        listener_earnings_released_at=now,
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('bokking', '0005_sessionbooking_reminder_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='sessionbooking',
            name='listener_earnings_released',
            field=models.BooleanField(
                default=False,
                help_text='Whether listener earnings were added to available balance after session end',
            ),
        ),
        migrations.AddField(
            model_name='sessionbooking',
            name='listener_earnings_released_at',
            field=models.DateTimeField(
                blank=True,
                help_text='When listener earnings were released to balance',
                null=True,
            ),
        ),
        migrations.RunPython(mark_historical_completed_bookings_as_released, noop_reverse),
    ]
