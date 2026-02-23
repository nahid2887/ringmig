"""
Management command to synchronize listener balances with earned payouts.

This command recalculates all listener balances based on:
1. Earned payouts from ListenerPayout (excludes extensions)
2. Extension earnings from CallPackage (is_extension=True)
3. Subtracts completed withdrawals

Usage:
python manage.py sync_listener_balances
python manage.py sync_listener_balances --dry-run  # Preview changes only
python manage.py sync_listener_balances --listener-email user@example.com  # Sync specific user
"""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum, Q
from django.contrib.auth import get_user_model
from decimal import Decimal
from listener.models import ListenerBalance
from chat.call_models import ListenerPayout, CallPackage

User = get_user_model()


class Command(BaseCommand):
    help = 'Synchronize listener balances with earned payouts and extension earnings'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )
        parser.add_argument(
            '--listener-email',
            type=str,
            help='Sync balance for specific listener email only',
        )
        parser.add_argument(
            '--fix-negative',
            action='store_true',
            help='Fix negative balances by setting them to zero',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        listener_email = options['listener_email']
        fix_negative = options['fix_negative']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        # Get listeners to process
        if listener_email:
            try:
                listeners = [User.objects.get(email=listener_email, user_type='listener')]
                self.stdout.write(f'Processing single listener: {listener_email}')
            except User.DoesNotExist:
                raise CommandError(f'Listener with email {listener_email} not found')
        else:
            listeners = User.objects.filter(user_type='listener')
            self.stdout.write(f'Processing {listeners.count()} listeners')

        updated_count = 0
        error_count = 0

        for listener in listeners:
            try:
                # Calculate expected balance
                expected_balance = self.calculate_expected_balance(listener)
                expected_total_earned = self.calculate_total_earned(listener)

                # Get or create current balance
                balance, created = ListenerBalance.objects.get_or_create(
                    listener=listener,
                    defaults={
                        'available_balance': expected_balance,
                        'total_earned': expected_total_earned
                    }
                )

                # Check if update is needed
                needs_update = (
                    balance.available_balance != expected_balance or
                    balance.total_earned != expected_total_earned
                )

                if needs_update:
                    old_available = balance.available_balance
                    old_earned = balance.total_earned

                    if fix_negative and expected_balance < 0:
                        self.stdout.write(
                            self.style.WARNING(
                                f'{listener.email}: Fixing negative balance ${expected_balance} -> $0.00'
                            )
                        )
                        expected_balance = Decimal('0.00')

                    self.stdout.write(
                        f'{listener.email}: '
                        f'Available: ${old_available} -> ${expected_balance} '
                        f'(Δ ${expected_balance - old_available}), '
                        f'Total Earned: ${old_earned} -> ${expected_total_earned} '
                        f'(Δ ${expected_total_earned - old_earned})'
                    )

                    if not dry_run:
                        balance.available_balance = expected_balance
                        balance.total_earned = expected_total_earned
                        balance.save(update_fields=['available_balance', 'total_earned', 'updated_at'])
                    
                    updated_count += 1
                else:
                    if listener_email:  # Only show this for single listener lookups
                        self.stdout.write(
                            f'{listener.email}: Balance already correct (Available: ${balance.available_balance}, '
                            f'Total Earned: ${balance.total_earned})'
                        )

            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(f'Error processing {listener.email}: {str(e)}')
                )
                error_count += 1

        # Summary
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'DRY RUN COMPLETE: Would update {updated_count} listeners, {error_count} errors'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'SYNC COMPLETE: Updated {updated_count} listeners, {error_count} errors'
                )
            )

    def calculate_expected_balance(self, listener):
        """Calculate expected available balance for listener."""
        
        # 1. Base earnings from completed calls (non-extension ListenerPayouts with status='earned')
        base_earnings = ListenerPayout.objects.filter(
            listener=listener,
            status='earned',
            is_extension=False
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        # 2. Extension earnings from confirmed extension packages
        extension_earnings = CallPackage.objects.filter(
            listener=listener,
            is_extension=True,
            status__in=['confirmed', 'used', 'completed']
        ).aggregate(total=Sum('listener_amount'))['total'] or Decimal('0.00')

        # 3. Subtract completed withdrawals
        completed_withdrawals = ListenerPayout.objects.filter(
            listener=listener,
            status='completed'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        expected_balance = base_earnings + extension_earnings - completed_withdrawals
        
        return expected_balance

    def calculate_total_earned(self, listener):
        """Calculate total lifetime earnings for listener."""
        
        # Base earnings from all completed calls
        base_earnings = ListenerPayout.objects.filter(
            listener=listener,
            status__in=['earned', 'pending', 'processing', 'completed'],
            is_extension=False
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        # Extension earnings
        extension_earnings = CallPackage.objects.filter(
            listener=listener,
            is_extension=True,
            status__in=['confirmed', 'used', 'completed']
        ).aggregate(total=Sum('listener_amount'))['total'] or Decimal('0.00')

        return base_earnings + extension_earnings