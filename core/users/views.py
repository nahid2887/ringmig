from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth import authenticate, get_user_model
from django.core.mail import send_mail
from django.utils import timezone
from django.conf import settings
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
import random
import string
import requests
import os
from datetime import timedelta, timezone as datetime_timezone
from rest_framework_simplejwt.authentication import JWTAuthentication

from .serializers import (
    UserRegistrationSerializer,
    UserLoginSerializer,
    UserSerializer,
    ChangePasswordSerializer,
    OTPRequestSerializer,
    OTPVerificationSerializer,
    ForgotPasswordRequestSerializer,
    VerifyPasswordResetOTPSerializer,
    ChangePasswordAfterResetSerializer
)
from .models import OTP, CalUserMapping, PasswordResetOTP
from .serializers import COUNTRY_CHOICES


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


def send_password_reset_otp_email(email, otp_code):
    """Send password reset OTP to user's email."""
    subject = 'Your OTP for Password Reset'
    message = f'''
Hello,

You requested to reset your password. Your One-Time Password (OTP) is:

{otp_code}

This OTP will expire in 10 minutes.

If you did not request this, please ignore this email.

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
    authentication_classes = [] 

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
                user_type=serializer.validated_data.get('user_type', 'talker'),
                language=serializer.validated_data.get('language', 'en'),
                country=serializer.validated_data.get('country', '')
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
    authentication_classes = [] 

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
                    language=otp_obj.language or 'en',
                    is_verified=True,
                    is_active=True
                )

                # If the OTP carried a country selection, persist it to the newly-created
                # listener/talker profile 'location' field so it appears in my_profile.
                try:
                    country = (otp_obj.country or '').strip()
                    if country:
                        if user.user_type == 'listener' and hasattr(user, 'listener_profile'):
                            lp = user.listener_profile
                            lp.location = country
                            lp.save(update_fields=['location'])
                        elif user.user_type == 'talker' and hasattr(user, 'talker_profile'):
                            tp = user.talker_profile
                            tp.location = country
                            tp.save(update_fields=['location'])
                except Exception:
                    # non-fatal: continue registration even if setting location fails
                    pass

                # Persist the selected registration language into the listener profile's
                # languages list so /api/listener/profiles/my_profile/ exposes it.
                try:
                    selected_language = (otp_obj.language or 'en').strip()
                    if user.user_type == 'listener' and hasattr(user, 'listener_profile'):
                        lp = user.listener_profile
                        existing_languages = list(lp.languages or [])
                        if selected_language and selected_language not in existing_languages:
                            existing_languages = [selected_language] + existing_languages
                        lp.languages = existing_languages or [selected_language]
                        lp.save(update_fields=['languages'])
                except Exception:
                    # non-fatal: continue registration even if setting languages fails
                    pass
                
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
    authentication_classes = [] 

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
            # Normalize country value to choice code if provided
            country = serializer.validated_data.get('country', '') if 'country' in serializer.validated_data else ''
            if country and country not in dict(COUNTRY_CHOICES):
                return Response({'country': 'Invalid country selection.'}, status=status.HTTP_400_BAD_REQUEST)
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
                user_type=serializer.validated_data.get('user_type', 'talker'),
                language=serializer.validated_data.get('language', 'en'),
                country=serializer.validated_data.get('country', '')
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
    authentication_classes = [] 

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
                # Check if user account is active (not deleted)
                if not user.is_active:
                    return Response({
                        'error': 'Account deleted',
                        'message': 'This account has been deleted and cannot be used. Please contact support if you believe this is a mistake.'
                    }, status=status.HTTP_403_FORBIDDEN)
                
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


class CountryListView(APIView):
    """Return a list of available countries for registration dropdown."""
    permission_classes = [AllowAny]

    def get(self, request):
        return Response([{'code': code, 'name': name} for code, name in COUNTRY_CHOICES], status=status.HTTP_200_OK)


class ServerTimeView(APIView):
    """Return the current server time."""
    permission_classes = [AllowAny]

    def get(self, request):
        now = timezone.now()
        return Response(
            {
                'server_time': now.isoformat(),
                'server_time_utc': now.astimezone(datetime_timezone.utc).isoformat(),
                'timestamp': int(now.timestamp()),
            },
            status=status.HTTP_200_OK,
        )


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


class ForgotPasswordRequestView(APIView):
    """API endpoint for requesting password reset OTP."""
    permission_classes = [AllowAny]
    authentication_classes = [] 

    @swagger_auto_schema(
        operation_description="Request password reset OTP - send OTP to email",
        request_body=ForgotPasswordRequestSerializer,
        responses={
            200: openapi.Response('Password reset OTP sent successfully to email'),
            400: 'Bad Request - Email not found or validation error'
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = ForgotPasswordRequestSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            
            # Generate OTP
            otp_code = generate_otp()
            
            # Delete any existing valid OTP for this email
            PasswordResetOTP.objects.filter(email=email, is_used=False).delete()
            
            # Create new password reset OTP with 10 minutes expiry
            otp_obj = PasswordResetOTP.objects.create(
                email=email,
                otp_code=otp_code,
                expires_at=timezone.now() + timedelta(minutes=10),
                is_used=False
            )
            
            # Send OTP via email
            if send_password_reset_otp_email(email, otp_code):
                return Response({
                    'message': 'Password reset OTP sent successfully to your email',
                    'email': email
                }, status=status.HTTP_200_OK)
            else:
                otp_obj.delete()
                return Response({
                    'error': 'Failed to send password reset OTP. Please try again.'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VerifyPasswordResetOTPView(APIView):
    """API endpoint for verifying password reset OTP."""
    permission_classes = [AllowAny]
    authentication_classes = [] 

    @swagger_auto_schema(
        operation_description="Verify password reset OTP",
        request_body=VerifyPasswordResetOTPSerializer,
        responses={
            200: openapi.Response('OTP verified successfully'),
            400: 'Bad Request - Invalid or expired OTP'
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = VerifyPasswordResetOTPSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            otp_code = serializer.validated_data['otp_code']
            
            try:
                otp_obj = PasswordResetOTP.objects.get(
                    email=email,
                    otp_code=otp_code,
                    is_used=False
                )
                
                # Check if OTP is expired
                if otp_obj.is_expired():
                    return Response({
                        'error': 'OTP has expired. Please request a new OTP.'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                return Response({
                    'message': 'OTP verified successfully',
                    'email': email
                }, status=status.HTTP_200_OK)
            
            except PasswordResetOTP.DoesNotExist:
                return Response({
                    'error': 'Invalid OTP. Please check and try again.'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordAfterResetView(APIView):
    """API endpoint for changing password after OTP verification."""
    permission_classes = [AllowAny]
    authentication_classes = [] 

    @swagger_auto_schema(
        operation_description="Change password after OTP verification",
        request_body=ChangePasswordAfterResetSerializer,
        responses={
            200: openapi.Response('Password changed successfully'),
            400: 'Bad Request - Validation error'
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = ChangePasswordAfterResetSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            new_password = serializer.validated_data['new_password']
            
            try:
                # Get user
                user = User.objects.get(email=email)
                
                # Check if there is a valid password reset OTP for this email
                otp_obj = PasswordResetOTP.objects.filter(
                    email=email,
                    is_used=False
                ).first()
                
                if not otp_obj:
                    return Response({
                        'error': 'No valid OTP found. Please verify OTP first.'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                if otp_obj.is_expired():
                    return Response({
                        'error': 'OTP has expired. Please request a new OTP.'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                # Update user password
                user.set_password(new_password)
                user.save()
                
                # Mark OTP as used
                otp_obj.is_used = True
                otp_obj.save()
                
                return Response({
                    'message': 'Password changed successfully'
                }, status=status.HTTP_200_OK)
            
            except User.DoesNotExist:
                return Response({
                    'error': 'User not found.'
                }, status=status.HTTP_404_NOT_FOUND)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class OAuth2TokenProxyView(APIView):
    """
    OAuth2 Token Proxy Endpoint
    
    This endpoint accepts a bearer token from an authenticated user and proxies
    the OAuth2 token request to the self-hosted OAuth2 server, enriching the 
    response with listener/talker user information.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="OAuth2 Token Proxy - Get OAuth2 token with user identification",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'grant_type': openapi.Schema(type=openapi.TYPE_STRING, description='OAuth2 grant type'),
                'client_id': openapi.Schema(type=openapi.TYPE_STRING, description='OAuth2 client ID'),
                'client_secret': openapi.Schema(type=openapi.TYPE_STRING, description='OAuth2 client secret'),
                'username': openapi.Schema(type=openapi.TYPE_STRING, description='Username for password grant'),
                'password': openapi.Schema(type=openapi.TYPE_STRING, description='Password for password grant'),
                'refresh_token': openapi.Schema(type=openapi.TYPE_STRING, description='Refresh token for refresh_token grant'),
                'code': openapi.Schema(type=openapi.TYPE_STRING, description='Authorization code for authorization_code grant'),
                'redirect_uri': openapi.Schema(type=openapi.TYPE_STRING, description='Redirect URI for authorization_code grant'),
            },
            required=['grant_type', 'client_id']
        ),
        responses={
            200: openapi.Response(
                description='OAuth2 token response with user information',
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'access_token': openapi.Schema(type=openapi.TYPE_STRING),
                        'token_type': openapi.Schema(type=openapi.TYPE_STRING),
                        'expires_in': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'refresh_token': openapi.Schema(type=openapi.TYPE_STRING),
                        'user_info': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'user_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'email': openapi.Schema(type=openapi.TYPE_STRING),
                                'full_name': openapi.Schema(type=openapi.TYPE_STRING),
                                'user_type': openapi.Schema(type=openapi.TYPE_STRING),
                                'listener_id': openapi.Schema(type=openapi.TYPE_STRING),
                                'talker_id': openapi.Schema(type=openapi.TYPE_STRING),
                            }
                        )
                    }
                )
            ),
            400: 'OAuth2 request failed',
            401: 'Unauthorized - Invalid bearer token'
        }
    )
    def post(self, request):
        """
        Proxy OAuth2 token refresh request with user identification.
        
        Accepts a bearer token which identifies the current user (listener or talker),
        uses refresh_token grant type to get a new access token from the self-hosted 
        OAuth2 server, and enriches the response with user identification information.
        
        The request can include booking data (listener_id, start_time, etc) which will
        be returned in the response for the client to use, but only OAuth2 fields
        are forwarded to the external OAuth2 server.
        """
        try:
            # Get authenticated user from bearer token
            user = request.user
            
            if not user.is_authenticated:
                return Response(
                    {'error': 'Unauthorized - Invalid bearer token'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Extract full payload from request
            full_payload = request.data.copy()
            
            # Extract ONLY OAuth2 relevant fields
            oauth2_payload = {}
            
            # Use refresh_token grant type
            oauth2_payload['grant_type'] = 'refresh_token'
            
            # Add Cal.com OAuth2 credentials
            oauth2_payload['client_id'] = settings.CALCOM_CLIENT_ID
            oauth2_payload['client_secret'] = settings.CALCOM_CLIENT_SECRET
            
            # Use provided refresh_token or use the Cal.com one from settings
            if 'refresh_token' in full_payload and full_payload['refresh_token']:
                oauth2_payload['refresh_token'] = full_payload['refresh_token']
            else:
                # Get refresh token from environment
                refresh_token = os.getenv('CALCOM_REFRESH_TOKEN', '')
                if refresh_token:
                    oauth2_payload['refresh_token'] = refresh_token
                else:
                    return Response(
                        {'error': 'refresh_token is required. Provide it in payload or set CALCOM_REFRESH_TOKEN in environment.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Make request to self-hosted OAuth2 token endpoint
            oauth2_url = settings.OAUTH2_TOKEN_ENDPOINT
            
            # Forward ONLY OAuth2 fields to the external server
            try:
                oauth2_response = requests.post(
                    oauth2_url,
                    data=oauth2_payload,
                    timeout=10
                )
                
                # Check for errors even if status is 400
                if oauth2_response.status_code >= 400:
                    try:
                        error_data = oauth2_response.json()
                        error_msg = error_data.get('error_description', error_data.get('error', oauth2_response.text))
                    except:
                        error_msg = oauth2_response.text
                    
                    return Response(
                        {
                            'error': f'OAuth2 server error: {error_msg}',
                            'status': oauth2_response.status_code,
                            'payload_sent': dict(oauth2_payload)
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                oauth2_response.raise_for_status()
            except requests.exceptions.ConnectionError as e:
                return Response(
                    {'error': f'Cannot connect to OAuth2 server at {oauth2_url}: {str(e)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            except requests.exceptions.RequestException as e:
                return Response(
                    {'error': f'OAuth2 request failed: {str(e)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Parse OAuth2 response
            token_data = oauth2_response.json()
            
            # Save Cal.com user mapping for this authenticated user
            # This stores which local user is connected to which Cal.com account
            try:
                cal_mapping, created = CalUserMapping.objects.update_or_create(
                    user=user,
                    defaults={
                        'cal_access_token': token_data.get('access_token', ''),
                        'cal_refresh_token': token_data.get('refresh_token', ''),
                        'token_expires_at': timezone.now() + timedelta(seconds=token_data.get('expires_in', 3600)),
                        'cal_user_id': user.email,  # Map to local user email
                    }
                )
                status_msg = "created" if created else "updated"
                print(f"✓ Cal.com mapping {status_msg} for User {user.id} ({user.email})")
            except Exception as e:
                print(f"⚠ Warning: Could not save Cal.com mapping: {str(e)}")
            
            # Include only OAuth2 tokens and user info
            response_data = {
                'access_token': token_data.get('access_token'),
                'token_type': token_data.get('token_type', 'Bearer'),
                'expires_in': token_data.get('expires_in'),
                'refresh_token': token_data.get('refresh_token'),
            }
            
            # Add authenticated user information from bearer token
            user_info = {
                'user_id': user.id,
                'email': user.email,
                'full_name': user.full_name,
                'user_type': user.user_type,
            }
            
            # Add listener/talker specific IDs
            if user.user_type == 'listener':
                try:
                    listener_profile = user.listener_profile
                    user_info['listener_id'] = listener_profile.id
                    user_info['listener_name'] = listener_profile.get_full_name()
                except:
                    user_info['listener_id'] = None
            
            elif user.user_type == 'talker':
                try:
                    talker_profile = user.talker_profile
                    user_info['talker_id'] = talker_profile.id
                    user_info['talker_name'] = talker_profile.get_full_name()
                except:
                    user_info['talker_id'] = None
            
            response_data['user'] = user_info
            
            # Include any user context data passed in the request
            user_context = {}
            context_field_names = ['listener_id', 'local_event_type_id', 'start_time', 'timezone', 'notes', 'talker_id']
            for field in context_field_names:
                if field in full_payload:
                    user_context[field] = full_payload[field]
            
            if user_context:
                response_data['user_context'] = user_context
            
            return Response(response_data, status=oauth2_response.status_code)
        
        except Exception as e:
            return Response(
                {'error': f'Internal server error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class UserSchedulingProfileView(APIView):
    """
    Get user's Cal.com scheduling profile and configuration.
    
    This endpoint returns the authenticated user's Cal.com information needed
    to display their booking page using Cal.com Atoms (BookerEmbed).
    
    Each user gets their own separate scheduling profile.
    """
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Get user's Cal.com scheduling profile for Atoms integration",
        responses={
            200: openapi.Response(
                description='User scheduling profile with Cal.com info',
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'user_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'email': openapi.Schema(type=openapi.TYPE_STRING),
                        'full_name': openapi.Schema(type=openapi.TYPE_STRING),
                        'user_type': openapi.Schema(type=openapi.TYPE_STRING),
                        'cal_username': openapi.Schema(type=openapi.TYPE_STRING),
                        'has_cal_token': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'token_expires_at': openapi.Schema(type=openapi.TYPE_STRING),
                        'profile_type': openapi.Schema(type=openapi.TYPE_STRING),
                    }
                )
            ),
            401: 'Unauthorized'
        }
    )
    def get(self, request):
        """
        Returns the authenticated user's scheduling profile.
        
        Frontend can use this info to:
        1. Get the username to pass to Cal.com Atoms
        2. Check if user has valid Cal.com token
        3. Know token expiry for token refresh UI
        """
        try:
            user = request.user
            
            # Get or create Cal.com mapping
            try:
                cal_mapping = user.cal_mapping
                has_token = True
                token_expires_at = cal_mapping.token_expires_at.isoformat()
                cal_username = cal_mapping.cal_user_id or user.email
            except CalUserMapping.DoesNotExist:
                has_token = False
                token_expires_at = None
                cal_username = user.email
            
            response_data = {
                'user_id': user.id,
                'email': user.email,
                'full_name': user.full_name,
                'user_type': user.user_type,
                'cal_username': cal_username,
                'has_cal_token': has_token,
                'token_expires_at': token_expires_at,
                'profile_type': 'talker' if user.user_type == 'talker' else 'listener',
            }
            
            # Add role-specific info
            if user.user_type == 'talker':
                try:
                    talker = user.talker_profile
                    response_data['talker_id'] = talker.id
                    response_data['talker_name'] = talker.get_full_name()
                except:
                    pass
            elif user.user_type == 'listener':
                try:
                    listener = user.listener_profile
                    response_data['listener_id'] = listener.id
                    response_data['listener_name'] = listener.get_full_name()
                except:
                    pass
            
            return Response(response_data, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response(
                {'error': f'Failed to get scheduling profile: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class UserEventTypesView(APIView):
    """
    Get user's Cal.com event types for scheduling.
    
    This endpoint fetches all available event types for the authenticated user
    from the Cal.com server, allowing them to choose which schedule to display.
    """
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Get user's Cal.com event types",
        responses={
            200: openapi.Response(
                description='List of user event types',
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'event_types': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                                    'title': openapi.Schema(type=openapi.TYPE_STRING),
                                    'slug': openapi.Schema(type=openapi.TYPE_STRING),
                                    'description': openapi.Schema(type=openapi.TYPE_STRING),
                                    'length': openapi.Schema(type=openapi.TYPE_INTEGER),
                                }
                            )
                        )
                    }
                )
            ),
            400: 'No Cal.com token found',
            401: 'Unauthorized'
        }
    )
    def get(self, request):
        """
        Fetch event types from Cal.com API for the authenticated user.
        
        Uses the stored Cal.com access token to query the Cal.com server
        for all event types defined by this user.
        """
        try:
            user = request.user
            
            # Check if user has Cal.com token
            try:
                cal_mapping = user.cal_mapping
            except CalUserMapping.DoesNotExist:
                return Response(
                    {'error': 'User has not connected Cal.com account. Please call OAuth2 token endpoint first.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if token is expired
            if cal_mapping.is_token_expired():
                return Response(
                    {'error': 'Cal.com token has expired. Please refresh token.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Fetch event types from Cal.com API
            cal_api_url = settings.CALCOM_API_BASE_URL
            headers = {
                'Authorization': f'Bearer {cal_mapping.cal_access_token}',
                'cal-api-version': '2024-08-06'
            }
            
            try:
                response = requests.get(
                    f'{cal_api_url}/event-types',
                    headers=headers,
                    timeout=10
                )
                
                if response.status_code >= 400:
                    error_msg = response.json().get('message', response.text) if response.text else 'Unknown error'
                    return Response(
                        {'error': f'Cal.com API error: {error_msg}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                event_types_data = response.json()
                
                # Extract relevant fields
                event_types = []
                events = event_types_data.get('data', [])
                
                if isinstance(events, list):
                    for et in events:
                        event_types.append({
                            'id': et.get('id'),
                            'title': et.get('title'),
                            'slug': et.get('slug'),
                            'description': et.get('description', ''),
                            'length': et.get('length'),
                        })
                
                return Response({
                    'user_id': user.id,
                    'email': user.email,
                    'event_types': event_types
                }, status=status.HTTP_200_OK)
            
            except requests.exceptions.RequestException as e:
                return Response(
                    {'error': f'Failed to fetch event types from Cal.com: {str(e)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        except Exception as e:
            return Response(
                {'error': f'Internal server error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )