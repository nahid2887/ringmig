from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate, get_user_model
from django.core.mail import send_mail
from django.utils import timezone
from django.conf import settings
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
import random
import string
from datetime import timedelta

from .serializers import (
    UserRegistrationSerializer,
    UserLoginSerializer,
    UserSerializer,
    ChangePasswordSerializer,
    OTPRequestSerializer,
    OTPVerificationSerializer
)
from .models import OTP

User = get_user_model()


def send_otp_email(email, otp_code):
    """Send OTP to user's email."""
    subject = 'Your OTP for Registration'
    message = f'''
Hello,

Your One-Time Password (OTP) for registration is:

{otp_code}

This OTP will expire in 10 minutes.

Do not share this OTP with anyone.

Regards,
Ringmig Team
    '''
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


def generate_otp():
    """Generate a 6-digit OTP."""
    return ''.join(random.choices(string.digits, k=6))


class OTPRequestView(APIView):
    """API endpoint for requesting OTP during registration."""
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Request OTP for user registration",
        request_body=OTPRequestSerializer,
        responses={
            200: openapi.Response('OTP sent successfully to email'),
            400: 'Bad Request - Validation Error'
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = OTPRequestSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            
            # Generate OTP
            otp_code = generate_otp()
            
            # Delete any existing OTP for this email
            OTP.objects.filter(email=email).delete()
            
            # Create new OTP record with 10 minutes expiry and store registration data
            otp_obj = OTP.objects.create(
                email=email,
                otp_code=otp_code,
                expires_at=timezone.now() + timedelta(minutes=10),
                full_name=serializer.validated_data['full_name'],
                password=serializer.validated_data['password'],
                user_type=serializer.validated_data.get('user_type', 'talker')
            )
            
            # Send OTP via email
            if send_otp_email(email, otp_code):
                return Response({
                    'message': 'OTP sent successfully to your email',
                    'email': email
                }, status=status.HTTP_200_OK)
            else:
                otp_obj.delete()
                return Response({
                    'error': 'Failed to send OTP email. Please try again.'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class OTPVerificationView(APIView):
    """API endpoint for verifying OTP and completing registration."""
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Verify OTP and complete user registration",
        request_body=OTPVerificationSerializer,
        responses={
            201: openapi.Response('User registered successfully'),
            400: 'Bad Request - Invalid OTP'
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = OTPVerificationSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            otp_code = serializer.validated_data['otp_code']
            
            try:
                otp_obj = OTP.objects.get(email=email, otp_code=otp_code)
                
                # Check if OTP is expired
                if otp_obj.is_expired():
                    return Response({
                        'error': 'OTP has expired. Please request a new OTP.'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                # Create user with verified status using stored data
                user = User.objects.create_user(
                    email=email,
                    password=otp_obj.password,
                    full_name=otp_obj.full_name,
                    user_type=otp_obj.user_type or 'talker',
                    is_verified=True,
                    is_active=True
                )
                
                # Mark OTP as verified and optionally delete it
                otp_obj.is_verified = True
                otp_obj.save()
                # Delete the OTP record after successful verification
                otp_obj.delete()
                
                # Generate JWT tokens
                refresh = RefreshToken.for_user(user)
                
                return Response({
                    'message': 'User registered and verified successfully',
                    'user': UserSerializer(user).data,
                    'tokens': {
                        'refresh': str(refresh),
                        'access': str(refresh.access_token),
                    }
                }, status=status.HTTP_201_CREATED)
            
            except OTP.DoesNotExist:
                return Response({
                    'error': 'Invalid OTP. Please check and try again.'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserRegistrationView(APIView):
    """API endpoint for user registration - sends OTP to email."""
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Register a new user - sends OTP to email",
        request_body=OTPRequestSerializer,
        responses={
            200: openapi.Response('OTP sent successfully to email'),
            400: 'Bad Request - Validation Error'
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = OTPRequestSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            
            # Generate OTP
            otp_code = generate_otp()
            
            # Delete any existing OTP for this email
            OTP.objects.filter(email=email).delete()
            
            # Create new OTP record with 10 minutes expiry and store registration data
            otp_obj = OTP.objects.create(
                email=email,
                otp_code=otp_code,
                expires_at=timezone.now() + timedelta(minutes=10),
                full_name=serializer.validated_data['full_name'],
                password=serializer.validated_data['password'],
                user_type=serializer.validated_data.get('user_type', 'talker')
            )
            
            # Send OTP via email
            if send_otp_email(email, otp_code):
                return Response({
                    'message': 'OTP sent successfully to your email. Please verify to complete registration.',
                    'email': email
                }, status=status.HTTP_200_OK)
            else:
                otp_obj.delete()
                return Response({
                    'error': 'Failed to send OTP email. Please try again.'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserLoginView(APIView):
    """API endpoint for user login."""
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Login with email and password",
        request_body=UserLoginSerializer,
        responses={
            200: openapi.Response('Login successful'),
            401: 'Invalid credentials',
            403: 'Account suspended'
        }
    )
    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            password = serializer.validated_data['password']
            user = authenticate(request, email=email, password=password)
            
            if user is not None:
                # Set user_type to superadmin if user is staff/superuser
                if user.is_staff or user.is_superuser:
                    if user.user_type != 'superadmin':
                        user.user_type = 'superadmin'
                        user.save(update_fields=['user_type'])
                
                # Check if talker account is suspended
                if user.user_type == 'talker':
                    from talker.models import TalkerSuspension
                    
                    suspension = TalkerSuspension.objects.filter(
                        talker=user,
                        is_active=True
                    ).first()
                    
                    if suspension and suspension.is_suspension_active():
                        remaining_days = suspension.get_remaining_days()
                        return Response({
                            'error': 'Account suspended',
                            'message': f'Your account is suspended and will be available again in {remaining_days} day{"s" if remaining_days != 1 else ""}.',
                            'suspension_details': {
                                'reason': suspension.reason,
                                'suspended_at': suspension.suspended_at,
                                'resume_at': suspension.resume_at,
                                'remaining_days': remaining_days,
                                'days_suspended': suspension.days_suspended
                            }
                        }, status=status.HTTP_403_FORBIDDEN)
                    
                    # Auto-unsuspend if suspension period is over
                    if suspension and not suspension.is_suspension_active():
                        suspension.is_active = False
                        suspension.save()
                
                refresh = RefreshToken.for_user(user)
                return Response({
                    'message': 'Login successful',
                    'user': UserSerializer(user).data,
                    'tokens': {
                        'refresh': str(refresh),
                        'access': str(refresh.access_token),
                    }
                }, status=status.HTTP_200_OK)
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserLogoutView(APIView):
    """API endpoint for user logout."""
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Logout and blacklist refresh token",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={'refresh': openapi.Schema(type=openapi.TYPE_STRING)}
        ),
        responses={200: 'Logout successful'}
    )
    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({'message': 'Logout successful'}, status=status.HTTP_200_OK)
        except Exception:
            return Response({'error': 'Invalid token'}, status=status.HTTP_400_BAD_REQUEST)


class UserProfileView(generics.RetrieveUpdateAPIView):
    """API endpoint for viewing and updating user profile."""
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    @swagger_auto_schema(operation_description="Get current user profile")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @swagger_auto_schema(operation_description="Update current user profile")
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)

    @swagger_auto_schema(operation_description="Partially update current user profile")
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)


class ChangePasswordView(APIView):
    """API endpoint for changing user password."""
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Change user password",
        request_body=ChangePasswordSerializer,
        responses={
            200: 'Password changed successfully',
            400: 'Validation error'
        }
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            if not user.check_password(serializer.validated_data['old_password']):
                return Response({'error': 'Old password is incorrect'}, status=status.HTTP_400_BAD_REQUEST)
            
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            return Response({'message': 'Password changed successfully'}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
