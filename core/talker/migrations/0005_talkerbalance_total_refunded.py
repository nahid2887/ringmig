from django.db import migrations, models
from decimal import Decimal


def move_existing_refund_totals(apps, schema_editor):
    TalkerBalance = apps.get_model('talker', 'TalkerBalance')
    for row in TalkerBalance.objects.all():
        if row.total_earned and row.total_earned > 0 and row.total_refunded == 0:
            # Historical data used total_earned for refund credits.
            row.total_refunded = row.total_earned
            row.total_earned = Decimal('0.00')
            row.save(update_fields=['total_refunded', 'total_earned', 'updated_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('talker', '0004_talkerbalance'),
    ]

    operations = [
        migrations.AddField(
            model_name='talkerbalance',
            name='total_refunded',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0.00'),
                help_text='Total refunded credits received from rejected/deleted bookings',
                max_digits=10,
            ),
        ),
        migrations.RunPython(move_existing_refund_totals, migrations.RunPython.noop),
    ]
