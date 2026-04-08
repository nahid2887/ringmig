from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('talker', '0003_talkersuspension_talkerreport'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TalkerBalance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('available_balance', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Current available balance', max_digits=10)),
                ('total_earned', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Total money earned (lifetime)', max_digits=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('talker', models.OneToOneField(limit_choices_to={'user_type': 'talker'}, on_delete=django.db.models.deletion.CASCADE, related_name='talker_balance_account', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Talker Balance',
                'verbose_name_plural': 'Talker Balances',
            },
        ),
    ]
