# Migration for ListenerProfile with personal information and profile image

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ListenerProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('first_name', models.CharField(blank=True, max_length=100)),
                ('last_name', models.CharField(blank=True, max_length=100)),
                ('gender', models.CharField(blank=True, choices=[('male', 'Male'), ('female', 'Female'), ('other', 'Other'), ('prefer_not_to_say', 'Prefer not to say')], max_length=20)),
                ('profile_image', models.ImageField(blank=True, null=True, upload_to='listener_profiles/')),
                ('location', models.CharField(blank=True, help_text='City, Country', max_length=255)),
                ('experience_level', models.CharField(choices=[('beginner', 'Beginner'), ('intermediate', 'Intermediate'), ('advanced', 'Advanced'), ('expert', 'Expert')], default='beginner', max_length=20)),
                ('bio', models.TextField(blank=True, help_text='Tell talkers about yourself')),
                ('about_me', models.TextField(blank=True, help_text='Additional information about yourself')),
                ('specialties', models.CharField(blank=True, help_text='Comma-separated list of listening specialties', max_length=500)),
                ('topics', models.JSONField(blank=True, default=list, help_text='Topics comfortable talking about')),
                ('hourly_rate', models.DecimalField(decimal_places=2, default=0, help_text='Rate per hour in USD', max_digits=8)),
                ('is_available', models.BooleanField(default=True)),
                ('total_hours', models.IntegerField(default=0, help_text='Total listening hours')),
                ('average_rating', models.FloatField(default=0, help_text='Average rating from talkers')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='listener_profile', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Listener Profile',
                'verbose_name_plural': 'Listener Profiles',
            },
        ),
        migrations.CreateModel(
            name='ListenerAvailability',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('day_of_week', models.IntegerField(choices=[(0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'), (3, 'Thursday'), (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday')])),
                ('start_time', models.TimeField()),
                ('end_time', models.TimeField()),
                ('listener', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='availability', to='listener.listenerprofile')),
            ],
            options={
                'verbose_name': 'Listener Availability',
                'verbose_name_plural': 'Listener Availabilities',
                'unique_together': {('listener', 'day_of_week')},
            },
        ),
    ]
