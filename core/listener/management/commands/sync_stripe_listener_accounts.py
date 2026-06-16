"""
Management command to create Stripe Connect accounts for all listeners without one.

Usage:
python manage.py sync_stripe_listener_accounts
python manage.py sync_stripe_listener_accounts --dry-run
python manage.py sync_stripe_listener_accounts --listener-email user@example.com
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.conf import settings
import stripe

from payment.models import StripeListenerAccount

User = get_user_model()
stripe.api_key = settings.STRIPE_SECRET_KEY


def is_connect_disabled_error(exc):
    error_text = str(exc)
    return 'signed up for Connect' in error_text or 'Connect' in error_text


class Command(BaseCommand):
    help = 'Create Stripe Connect accounts for listeners who do not yet have one'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without making changes',
        )
        parser.add_argument(
            '--listener-email',
            type=str,
            help='Create account for a specific listener only',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        listener_email = options['listener_email']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        if listener_email:
            try:
                listeners = [User.objects.get(email=listener_email, user_type='listener')]
            except User.DoesNotExist:
                raise CommandError(f'Listener with email {listener_email} not found')
        else:
            listeners = User.objects.filter(user_type='listener')

        created_count = 0
        skipped_count = 0
        error_count = 0

        for listener in listeners:
            try:
                account = StripeListenerAccount.objects.filter(listener=listener).first()
                if account:
                    skipped_count += 1
                    self.stdout.write(f'SKIP: {listener.email} already has Stripe account {account.stripe_account_id}')
                    continue

                if dry_run:
                    self.stdout.write(f'WOULD CREATE: {listener.email}')
                    created_count += 1
                    continue

                stripe_account = stripe.Account.create(
                    type='express',
                    country='US',
                    email=listener.email,
                    capabilities={
                        'transfers': {'requested': True},
                        'payouts': {'requested': True},
                    },
                    business_type='individual',
                    metadata={'user_id': listener.id, 'user_email': listener.email},
                )

                StripeListenerAccount.objects.create(
                    listener=listener,
                    stripe_account_id=stripe_account.id,
                    is_verified=False,
                    is_enabled=True,
                )
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'CREATED: {listener.email} -> {stripe_account.id}'))

            except stripe.error.StripeError as exc:
                error_count += 1
                if is_connect_disabled_error(exc):
                    self.stderr.write(
                        self.style.ERROR(
                            f'ERROR: {listener.email} -> Stripe Connect is not enabled for the platform account. '
                            'Enable Connect in the Stripe dashboard for the account behind STRIPE_SECRET_KEY.'
                        )
                    )
                    continue

                self.stderr.write(self.style.ERROR(f'ERROR: {listener.email} -> {str(exc)}'))
            except Exception as exc:
                error_count += 1
                self.stderr.write(self.style.ERROR(f'ERROR: {listener.email} -> {str(exc)}'))

        self.stdout.write(
            self.style.SUCCESS(
                f'COMPLETE: created={created_count}, skipped={skipped_count}, errors={error_count}'
            )
        )
