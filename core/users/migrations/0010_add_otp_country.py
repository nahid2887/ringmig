# Generated migration to add country field to OTP model
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0009_user_admin_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='otp',
            name='country',
            field=models.CharField(default='', max_length=100, blank=True, help_text='User selected country during registration'),
        ),
    ]
