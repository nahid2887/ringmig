from django.core.management.base import BaseCommand
from listener.models import ListenerProfile
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Fix listener profile names by parsing User.full_name into first_name and last_name'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        
        # Find all listener profiles with empty first_name and last_name
        profiles = ListenerProfile.objects.filter(first_name='', last_name='')
        
        if not profiles.exists():
            self.stdout.write(self.style.SUCCESS('No listener profiles need fixing'))
            return
        
        self.stdout.write(f'Found {profiles.count()} listener profiles to fix')
        
        updated_count = 0
        for profile in profiles:
            user = profile.user
            if not user.full_name or user.full_name.strip() == '':
                continue
            
            # Parse full_name into first_name and last_name
            parts = user.full_name.strip().split(None, 1)
            first_name = parts[0] if parts else ''
            last_name = parts[1] if len(parts) > 1 else ''
            
            if dry_run:
                self.stdout.write(
                    f'  [{profile.id}] {user.email}: full_name="{user.full_name}" -> '
                    f'first_name="{first_name}", last_name="{last_name}"'
                )
            else:
                profile.first_name = first_name
                profile.last_name = last_name
                profile.save(update_fields=['first_name', 'last_name'])
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  ✓ [{profile.id}] {user.email}: "{first_name}" "{last_name}"'
                    )
                )
            
            updated_count += 1
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'DRY RUN: Would update {updated_count} listener profiles. '
                    'Run without --dry-run to apply changes.'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully updated {updated_count} listener profiles')
            )
