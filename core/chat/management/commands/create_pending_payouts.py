"""
Management command to create payouts for all confirmed call packages that don't have payouts.
"""

from django.core.management.base import BaseCommand
from chat.call_models import CallPackage, ListenerPayout
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Create payouts for confirmed call packages without payouts'

    def handle(self, *args, **options):
        # Find all confirmed call packages without payouts
        confirmed_packages = CallPackage.objects.filter(
            status__in=['confirmed', 'in_progress', 'completed']
        ).exclude(
            payouts__isnull=False
        )
        
        created_count = 0
        skipped_count = 0
        error_count = 0
        
        self.stdout.write(f"Found {confirmed_packages.count()} confirmed packages without payouts")
        
        for package in confirmed_packages:
            try:
                # Check if payout already exists
                if ListenerPayout.objects.filter(call_package=package).exists():
                    skipped_count += 1
                    continue
                
                listener_amount = package.listener_amount
                
                if listener_amount > Decimal('0.00'):
                    payout = ListenerPayout.objects.create(
                        listener=package.listener,
                        call_package=package,
                        amount=listener_amount,
                        status='earned' if package.status == 'completed' else 'processing',
                        notes=f'Earned from call with {package.talker.email}'
                    )
                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✓ Created payout for {package.listener.email}: ${listener_amount} ({payout.status})'
                        )
                    )
                else:
                    skipped_count += 1
            
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f'✗ Error creating payout for package {package.id}: {str(e)}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\nSummary:\n'
                f'  Created: {created_count}\n'
                f'  Skipped: {skipped_count}\n'
                f'  Errors: {error_count}'
            )
        )
