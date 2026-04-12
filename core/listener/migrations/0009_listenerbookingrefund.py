from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('bokking', '0006_sessionbooking_listener_earnings_release_fields'),
        ('listener', '0008_listenerblockedtalker'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ListenerBookingRefund',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('total_refunded', models.DecimalField(decimal_places=2, default=0, help_text='Total amount refunded by listener for this booking', max_digits=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('booking', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='listener_refund_tracker', to='bokking.sessionbooking')),
                ('listener', models.ForeignKey(limit_choices_to={'user_type': 'listener'}, on_delete=django.db.models.deletion.CASCADE, related_name='booking_refunds', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Listener Booking Refund',
                'verbose_name_plural': 'Listener Booking Refunds',
            },
        ),
        migrations.AddIndex(
            model_name='listenerbookingrefund',
            index=models.Index(fields=['listener', 'updated_at'], name='listener_li_listene_4222e8_idx'),
        ),
    ]
