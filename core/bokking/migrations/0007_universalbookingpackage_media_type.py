from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bokking', '0006_sessionbooking_listener_earnings_release_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='universalbookingpackage',
            name='media_type',
            field=models.CharField(choices=[('audio', 'Audio'), ('video', 'Video')], default='audio', help_text='Meeting media type', max_length=20),
        ),
    ]
