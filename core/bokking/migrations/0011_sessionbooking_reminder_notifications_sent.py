from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bokking', '0010_sessionbooking_stripe_transfer_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='sessionbooking',
            name='reminder_notifications_sent',
            field=models.JSONField(blank=True, default=dict, help_text='Tracks sent booking reminders by recipient role and minutes before start'),
        ),
    ]