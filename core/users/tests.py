from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from .models import PasswordResetOTP

User = get_user_model()

class PasswordResetOTPTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='password123',
            user_type='talker'
        )

    def test_multiple_used_otps_does_not_fail(self):
        # Create first OTP
        otp1 = PasswordResetOTP.objects.create(
            email='test@example.com',
            otp_code='123456',
            expires_at=timezone.now() + timedelta(minutes=10),
            is_used=False
        )
        # Mark first OTP as used
        otp1.is_used = True
        otp1.save()

        # Create second OTP
        otp2 = PasswordResetOTP.objects.create(
            email='test@example.com',
            otp_code='654321',
            expires_at=timezone.now() + timedelta(minutes=10),
            is_used=False
        )
        # Mark second OTP as used (previously threw IntegrityError)
        otp2.is_used = True
        otp2.save()

        # Check that both exist and are used
        self.assertEqual(PasswordResetOTP.objects.filter(email='test@example.com', is_used=True).count(), 2)
