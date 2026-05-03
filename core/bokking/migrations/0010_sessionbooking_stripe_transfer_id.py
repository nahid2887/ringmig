from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bokking', '0009_increase_field_lengths'),
    ]

    operations = [
        migrations.AddField(
            model_name='sessionbooking',
            name='stripe_transfer_id',
            field=models.CharField(blank=True, default='', help_text='Stripe transfer ID for automatic listener payout', max_length=255),
        ),
    ]
