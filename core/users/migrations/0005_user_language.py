# Generated migration for adding language field to User model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0004_user_birthday'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='language',
            field=models.CharField(
                choices=[('en', 'English'), ('sv', 'Swedish')],
                default='en',
                help_text='Preferred language',
                max_length=5
            ),
        ),
    ]
