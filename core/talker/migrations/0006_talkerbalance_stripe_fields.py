from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('talker', '0005_talkerbalance_total_refunded'),
    ]

    operations = [
        migrations.AddField(
            model_name='talkerbalance',
            name='stripe_account_id',
            field=models.CharField(blank=True, default='', help_text='Stripe Connect account id used for payouts', max_length=255),
        ),
        migrations.AddField(
            model_name='talkerbalance',
            name='stripe_account_verified',
            field=models.BooleanField(default=False, help_text='Whether Stripe Connect account is verified for payouts'),
        ),
    ]
