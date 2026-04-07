from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bokking', '0004_sessionbooking'),
    ]

    operations = [
        migrations.AddField(
            model_name='sessionbooking',
            name='listener_reminder_sent_at',
            field=models.DateTimeField(
                blank=True,
                help_text='When 20-minute reminder email was sent to listener',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='sessionbooking',
            name='talker_reminder_sent_at',
            field=models.DateTimeField(
                blank=True,
                help_text='When 20-minute reminder email was sent to talker',
                null=True,
            ),
        ),
    ]
