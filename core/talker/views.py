from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.db import transaction
from decimal import Decimal, InvalidOperation
import stripe
from users.serializers import COUNTRY_CHOICES
from .models import TalkerProfile, FavoriteListener
from .serializers import (TalkerProfileSerializer, FavoriteListenerSerializer, AddFavoriteListenerSerializer,
                          TalkerCallHistorySerializer, TalkerCallHistoryDetailSerializer,
                          TalkerBalanceSerializer)
from listener.models import ListenerProfile, ListenerRating, ListenerBlockedTalker
from listener.serializers import ListenerListSerializer, ListenerRatingSerializer, ListenerReviewDisplaySerializer
from .models import TalkerBalance

stripe.api_key = settings.STRIPE_SECRET_KEY


class IsTalkerUser(IsAuthenticated):
    """Custom permission to ensure user has talker role."""
    
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.user.user_type == 'talker'
    
    def has_object_permission(self, request, view, obj):
        """Only allow talkers to access their own profile."""
        return obj.user == request.user


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def rate_listener_endpoint(request):
    """Standalone endpoint for listener rating to avoid router/action dispatch issues."""
    if request.user.user_type != 'talker':
        return Response({'error': 'Only talkers can rate listeners'}, status=status.HTTP_403_FORBIDDEN)

    listener_id = request.data.get('listener_id')
    rating = request.data.get('rating')
    review = request.data.get('review', '')

    if not listener_id:
        return Response({'error': 'listener_id is required'}, status=status.HTTP_400_BAD_REQUEST)
    if rating is None:
        return Response({'error': 'rating is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        rating_int = int(rating)
    except (TypeError, ValueError):
        return Response({'error': 'rating must be an integer'}, status=status.HTTP_400_BAD_REQUEST)

    if rating_int < 1 or rating_int > 5:
        return Response({'error': 'rating must be between 1 and 5'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Prefer resolving by user_id (frontend uses user id as `id`), fall back to profile id
        try:
            listener_profile = ListenerProfile.objects.get(user_id=listener_id)
        except ListenerProfile.DoesNotExist:
            listener_profile = ListenerProfile.objects.get(id=listener_id)
    except ListenerProfile.DoesNotExist:
        return Response({'error': f'Listener with ID {listener_id} not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        rating_obj = ListenerRating.objects.filter(listener=listener_profile, talker=request.user).first()

        if rating_obj:
            rating_obj.rating = rating_int
            rating_obj.review = review or ''
            rating_obj.save()
        else:
            rating_obj = ListenerRating.objects.create(
                listener=listener_profile,
                talker=request.user,
                rating=rating_int,
                review=review or ''
            )

        return Response({
            'id': rating_obj.id,
            'listener_id': listener_profile.id,
            'talker_id': request.user.id,
            'rating': rating_obj.rating,
            'review': rating_obj.review,
            'created_at': rating_obj.created_at.isoformat() if rating_obj.created_at else None,
            'updated_at': rating_obj.updated_at.isoformat() if rating_obj.updated_at else None,
            'message': 'Rating saved successfully'
        }, status=status.HTTP_201_CREATED)
    except Exception as exc:
        return Response({'error': str(exc), 'error_type': type(exc).__name__}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TalkerProfileViewSet(viewsets.ModelViewSet):
    """ViewSet for talker profile management and listener interactions."""
    queryset = TalkerProfile.objects.all()
    serializer_class = TalkerProfileSerializer
    permission_classes = [IsTalkerUser]
    parser_classes = (JSONParser, MultiPartParser, FormParser)
    lookup_value_regex = r'\d+'

    def get_queryset(self):
        """Return only the authenticated user's profile."""
        if self.request.user.is_authenticated:
            return TalkerProfile.objects.filter(user=self.request.user)
        return TalkerProfile.objects.none()

    def get_object(self):
        """Get the talker profile for the authenticated user."""
        return get_object_or_404(TalkerProfile, user=self.request.user)

    def _sync_user_full_name(self, talker_profile):
        """Keep the auth user full_name aligned with the profile name fields."""
        combined_name = talker_profile.get_full_name()

        if talker_profile.user.full_name != combined_name:
            talker_profile.user.full_name = combined_name
            talker_profile.user.save(update_fields=['full_name', 'updated_at'])

    def destroy(self, request, *args, **kwargs):
        """Delete talker profile and deactivate the associated user account.
        
        When a talker profile is deleted, the user account is marked as inactive
        so they cannot login again.
        """
        talker_profile = self.get_object()
        user = talker_profile.user
        
        # Delete the profile
        talker_profile.delete()
        
        # Deactivate the user account
        user.is_active = False
        user.save()
        
        return Response(
            {
                'message': f'Talker profile deleted and account deactivated',
                'user_id': user.id,
                'email': user.email
            },
            status=status.HTTP_204_NO_CONTENT
        )

    @action(detail=False, methods=['get', 'put', 'patch'], permission_classes=[IsTalkerUser], parser_classes=[JSONParser, MultiPartParser, FormParser])
    def my_profile(self, request):
        """Get or update the authenticated talker user's profile."""
        try:
            talker_profile = TalkerProfile.objects.get(user=request.user)
        except TalkerProfile.DoesNotExist:
            return Response(
                {'error': 'Talker profile not found. Please ensure you are registered as a talker.'},
                status=status.HTTP_404_NOT_FOUND
            )

        if request.method == 'GET':
            serializer = self.get_serializer(talker_profile, context={'request': request})
            return Response(serializer.data)

        elif request.method in ['PUT', 'PATCH']:
            payload = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
            invalid_tokens = {'undefined', 'null', 'none'}

            for key in ['first_name', 'last_name']:
                if key in payload:
                    value = str(payload.get(key, '')).strip()
                    if value.lower() in invalid_tokens:
                        payload[key] = ''

            full_name_input = str(payload.get('full_name', payload.get('fullname', ''))).strip()
            if full_name_input.lower() in invalid_tokens:
                full_name_input = ''

            if full_name_input:
                parts = full_name_input.split(None, 1)
                first_name = parts[0]
                last_name = parts[1] if len(parts) > 1 else ''

                if first_name.lower() in invalid_tokens:
                    first_name = ''
                if last_name.lower() in invalid_tokens:
                    last_name = ''

                if not str(payload.get('first_name', '')).strip():
                    payload['first_name'] = first_name
                if not str(payload.get('last_name', '')).strip():
                    payload['last_name'] = last_name

            payload.pop('full_name', None)
            payload.pop('fullname', None)

            serializer = self.get_serializer(talker_profile, data=payload, partial=True, context={'request': request})
            if serializer.is_valid():
                talker_profile = serializer.save()
                self._sync_user_full_name(talker_profile)
                talker_profile.refresh_from_db()
                # Return serializer data with full context
                response_data = serializer.data
                # Ensure profile_image_url is included
                if talker_profile.profile_image:
                    response_data['profile_image_url'] = request.build_absolute_uri(talker_profile.profile_image.url)
                return Response(response_data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_description="Get all listeners for talker to browse with optional search, gender filtering, and pagination",
        manual_parameters=[
            openapi.Parameter('search', openapi.IN_QUERY, type=openapi.TYPE_STRING, 
                            description='Search by listener first_name or last_name'),
            openapi.Parameter('gender', openapi.IN_QUERY, type=openapi.TYPE_STRING, 
                            description='Filter by gender: male, female, other, prefer_not_to_say'),
            openapi.Parameter('language', openapi.IN_QUERY, type=openapi.TYPE_STRING, 
                            description='Filter by listener language (e.g., english, bangla). Shows all listeners speaking this language. If not provided, defaults to talker\'s primary language'),
            openapi.Parameter('page', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, 
                            description='Page number (default: 1)'),
            openapi.Parameter('page_size', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, 
                            description='Items per page (default: 8)')
        ],
        responses={200: openapi.Response('Paginated list of listeners')},
        tags=['Talker Browse Listeners']
    )
    @action(detail=False, methods=['get'], permission_classes=[IsTalkerUser])
    def all_listeners(self, request):
        """Get all listeners for talker to browse with pagination.
        
        Filters listeners by language. If language parameter is provided, shows all listeners
        speaking that language. Otherwise, filters by talker's primary language.
        Supports search by first_name or last_name and filtering by gender.
        Excludes listeners who have blocked this talker.
        Returns paginated results (8 per page by default).
        
        Query Parameters:
        - search: Search by first_name or last_name (case-insensitive)
        - gender: Filter by gender (male, female, other, prefer_not_to_say)
        - language: Filter by listener language (e.g., english, bangla). Shows all listeners speaking this language
        - page: Page number (default: 1)
        - page_size: Items per page (default: 8, max: 50)
        
        Example with language: /api/talker/profiles/all_listeners/?language=bangla&page=1&page_size=8
        """
        from rest_framework.pagination import PageNumberPagination
        
        # Get list of listener IDs that have blocked this talker
        blocked_by = ListenerBlockedTalker.objects.filter(
            talker=request.user
        ).values_list('listener_id', flat=True)
        
        # Get all listeners except those who have blocked this talker
        listeners = ListenerProfile.objects.exclude(
            user_id__in=blocked_by
        ).order_by('-average_rating')
        
        # Apply gender filter if provided (via ORM)
        gender = request.query_params.get('gender', '').strip()
        if gender:
            listeners = listeners.filter(gender=gender)
        
        # Get search parameters
        search_query = request.query_params.get('search', '').strip().lower()
        search_language = request.query_params.get('language', '').strip().lower()
        talker_language = request.user.language
        applied_language = search_language if search_language else talker_language
        has_search = bool(search_query or search_language)
        
        # Language code to display name mapping for search matching
        language_names = {
            'en': 'english',
            'sv': 'swedish',
            'es': 'spanish',
            'fr': 'french',
            'de': 'german',
            'it': 'italian',
            'pt': 'portuguese',
            'ru': 'russian',
            'ja': 'japanese',
            'zh': 'chinese',
            'ko': 'korean',
            'ar': 'arabic',
            'hi': 'hindi',
            'nl': 'dutch',
            'pl': 'polish',
            'bn': 'bangla',  # Bengali/Bangla
            'ta': 'tamil',
            'te': 'telugu',
            'kn': 'kannada',
            'ml': 'malayalam',
        }

        country_names = {
            code.lower(): name.lower()
            for code, name in COUNTRY_CHOICES
            if code
        }

        def location_matches(left_value, right_value):
            left_value = (left_value or '').strip().lower()
            right_value = (right_value or '').strip().lower()

            if not left_value or not right_value:
                return False

            if left_value == right_value or left_value in right_value or right_value in left_value:
                return True

            left_name = country_names.get(left_value, '')
            right_name = country_names.get(right_value, '')

            if left_name and (left_name == right_value or left_name in right_value or right_value in left_name):
                return True
            if right_name and (right_name == left_value or right_name in left_value or left_value in right_name):
                return True

            return False
        
        # Determine talker location to also match listeners by location
        talker_location = ''
        try:
            talker_location = (request.user.talker_profile.location or '').strip().lower()
        except Exception:
            talker_location = ''

        # Filter by language and/or location in Python
        # Include listener if: language matches OR location matches (or both).
        filtered_listeners = []
        for listener in listeners:
            # skip if no languages and no location
            if not (listener.languages or listener.location):
                continue

            language_match = False
            name_match = False

            # Compute talker language match (for no-search mode)
            talker_lang_match = (
                talker_language in (listener.languages or []) or
                talker_language in (
                    language_names.get(lang, '')
                    for lang in (listener.languages or [])
                    if lang in language_names
                )
            )

            if not has_search:
                # No search: language match is based on talker's language
                language_match = talker_lang_match
            else:
                # Search mode
                if search_language:
                    language_match = (
                        search_language in (listener.languages or []) or
                        search_language in (
                            language_names.get(lang, '')
                            for lang in (listener.languages or [])
                            if lang in language_names
                        )
                    )
                if search_query:
                    name_match = (
                        search_query in (listener.first_name or '').lower() or
                        search_query in (listener.last_name or '').lower()
                    )
                    # Check if search query matches any language code or display name
                    for lang in (listener.languages or []):
                        if search_query in lang.lower():
                            language_match = True
                            break
                        if lang in language_names and search_query in language_names[lang]:
                            language_match = True
                            break

            # Determine location match
            listener_loc = (listener.location or '').strip().lower()
            location_match = False
            if talker_location and listener_loc:
                if talker_location in listener_loc or listener_loc in talker_location:
                    location_match = True

            # Include listener if language OR location OR name matches
            if not (language_match or location_match or name_match):
                continue

            filtered_listeners.append(listener)
        
        listeners = filtered_listeners
        
        # Paginate results
        paginator = PageNumberPagination()
        paginator.page_size = int(request.query_params.get('page_size', 8))
        paginator.page_size = min(paginator.page_size, 50)  # Max 50 per page
        
        page = paginator.paginate_queryset(listeners, request)
        if page is not None:
            serializer = ListenerListSerializer(page, many=True, context={'request': request})
            # Get paginated response with next/previous links
            paginated_response = paginator.get_paginated_response(serializer.data)
            # Add filters to the response
            paginated_response.data['search_query'] = search_query if search_query else None
            paginated_response.data['gender_filter'] = gender if gender else None
            paginated_response.data['language_filter'] = search_language if search_language else None
            paginated_response.data['applied_language'] = applied_language
            return paginated_response
        
        # Fallback if pagination failed (shouldn't happen)
        serializer = ListenerListSerializer(listeners, many=True, context={'request': request})
        return Response({
            'count': len(listeners),
            'next': None,
            'previous': None,
            'results': serializer.data,
            'search_query': search_query if search_query else None,
            'gender_filter': gender if gender else None,
            'language_filter': search_language if search_language else None,
            'applied_language': filter_language
        })

    @swagger_auto_schema(
        operation_description="Get all available listeners only with optional search and pagination",
        manual_parameters=[
            openapi.Parameter('search', openapi.IN_QUERY, type=openapi.TYPE_STRING, 
                            description='Search by listener first_name or last_name'),
            openapi.Parameter('page', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, 
                            description='Page number (default: 1)'),
            openapi.Parameter('page_size', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, 
                            description='Items per page (default: 8)')
        ],
        responses={200: openapi.Response('Paginated list of available listeners')},
        tags=['Talker Browse Listeners']
    )
    @action(detail=False, methods=['get'], permission_classes=[IsTalkerUser])
    def available_listeners(self, request):
        """Get all available listeners only with pagination.
        
        Filters listeners who speak the same language as the talker.
        Supports search by first_name or last_name.
        Excludes listeners who have blocked this talker.
        Returns paginated results (8 per page by default).
        
        Query Parameters:
        - search: Search by first_name or last_name (case-insensitive)
        - page: Page number (default: 1)
        - page_size: Items per page (default: 8, max: 50)
        
        Example: /api/talker/profiles/available_listeners/?search=john&page=1&page_size=8
        """
        from django.db.models import Q
        from rest_framework.pagination import PageNumberPagination
        
        # Get list of listener IDs that have blocked this talker
        blocked_by = ListenerBlockedTalker.objects.filter(
            talker=request.user
        ).values_list('listener_id', flat=True)
        
        # Get talker's language
        talker_language = request.user.language
        
        # Get available listeners except those who have blocked this talker
        listeners = ListenerProfile.objects.filter(
            is_available=True
        ).exclude(
            user_id__in=blocked_by
        ).order_by('-average_rating')
        
        # Search query
        search_query = request.query_params.get('search', '').strip().lower()

        # Determine talker location to also match listeners by location
        talker_location = ''
        try:
            talker_location = (request.user.talker_profile.location or '').strip().lower()
        except Exception:
            talker_location = ''
        
        # Language code to display name mapping for search matching
        language_names = {
            'en': 'english',
            'sv': 'swedish',
            'es': 'spanish',
            'fr': 'french',
            'de': 'german',
            'it': 'italian',
            'pt': 'portuguese',
            'ru': 'russian',
            'ja': 'japanese',
            'zh': 'chinese',
            'ko': 'korean',
            'ar': 'arabic',
            'hi': 'hindi',
            'nl': 'dutch',
            'pl': 'polish',
            'bn': 'bangla',  # Bengali/Bangla
            'ta': 'tamil',
            'te': 'telugu',
            'kn': 'kannada',
            'ml': 'malayalam',
        }
        
        # Filter by language and/or location in Python.
        # If search is provided, search across all available listeners.
        filtered_listeners = []
        for listener in listeners:
            if not (listener.languages or listener.location):
                continue

            # If search query provided, search across names, languages, and location.
            if search_query:
                name_match = (search_query in (listener.first_name or '').lower() or 
                             search_query in (listener.last_name or '').lower())
                
                # Check if search matches any language (by code or display name)
                language_match = False
                for lang in listener.languages:
                    # Check if search matches the language code
                    if search_query in lang.lower():
                        language_match = True
                        break
                    # Check if search matches the language display name
                    if lang in language_names and search_query in language_names[lang]:
                        language_match = True
                        break

                location_match = location_matches(search_query, listener.location)
                
                # Include listener if search matches name OR language OR location
                if not (name_match or language_match or location_match):
                    continue
            else:
                # No search: include listener if language matches talker language or location matches talker location.
                talker_lang_match = (
                    talker_language in (listener.languages or []) or
                    talker_language in (
                        language_names.get(lang, '')
                        for lang in (listener.languages or [])
                        if lang in language_names
                    )
                )

                location_match = location_matches(talker_location, listener.location)

                if not (talker_lang_match or location_match):
                    continue
            
            filtered_listeners.append(listener)
        
        listeners = filtered_listeners
        
        # Paginate results
        paginator = PageNumberPagination()
        paginator.page_size = int(request.query_params.get('page_size', 8))
        paginator.page_size = min(paginator.page_size, 50)  # Max 50 per page
        
        page = paginator.paginate_queryset(listeners, request)
        if page is not None:
            serializer = ListenerListSerializer(page, many=True, context={'request': request})
            # Get paginated response with next/previous links
            paginated_response = paginator.get_paginated_response(serializer.data)
            # Add search query to the response
            paginated_response.data['search_query'] = search_query if search_query else None
            return paginated_response
        
        # Fallback if pagination failed (shouldn't happen)
        serializer = ListenerListSerializer(listeners, many=True, context={'request': request})
        return Response({
            'count': len(listeners),
            'next': None,
            'previous': None,
            'results': serializer.data,
            'search_query': search_query if search_query else None
        })
    
    @swagger_auto_schema(
        operation_description="Get detailed information about a specific listener from all_listeners",
        responses={200: openapi.Response('Listener detail')},
        tags=['Talker Browse Listeners']
    )
    @action(detail=False, methods=['get'], permission_classes=[IsTalkerUser])
    def all_listeners_detail(self, request):
        """Get detailed information about a specific listener by user ID.
        
        Verifies the listener speaks the same language as the talker.
        
        URL: /api/talker/profiles/all_listeners_detail/?user_id=4
        Example: /api/talker/profiles/all_listeners_detail/?user_id=4
        
        Returns 403 if the listener has blocked this talker or doesn't speak talker's language.
        """
        user_id = request.query_params.get('user_id')
        
        if not user_id:
            return Response(
                {'error': 'user_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if listener has blocked this talker
        is_blocked = ListenerBlockedTalker.objects.filter(
            listener_id=user_id,
            talker=request.user
        ).exists()
        
        if is_blocked:
            return Response(
                {'error': 'This listener has blocked you and is not available'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            listener = ListenerProfile.objects.get(user_id=user_id)
            
            # Check if listener speaks the talker's language
            # Only use ListenerProfile.languages - no fallback to User.language
            talker_language = request.user.language
            if not listener.languages or talker_language not in listener.languages:
                return Response(
                    {'error': 'This listener does not speak your language'},
                    status=status.HTTP_403_FORBIDDEN
                )
        except ListenerProfile.DoesNotExist:
            return Response(
                {'error': f'Listener with user ID {user_id} not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = ListenerListSerializer(listener, context={'request': request})
        return Response(serializer.data)

    def listener_detail_by_id(self, request, listener_id=None):
        """Get detailed information about a specific listener by user ID.

        URL: /api/talker/profiles/all_listeners/<user_id>/
        """
        if not request.user.is_authenticated or request.user.user_type != 'talker':
            return Response(
                {'error': 'Only authenticated talkers can view listener details'},
                status=status.HTTP_403_FORBIDDEN
            )

        is_blocked = ListenerBlockedTalker.objects.filter(
            listener_id=listener_id,
            talker=request.user
        ).exists()

        if is_blocked:
            return Response(
                {'error': 'This listener has blocked you and is not available'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            listener = ListenerProfile.objects.get(user_id=listener_id)
        except ListenerProfile.DoesNotExist:
            return Response(
                {'error': f'Listener with user ID {listener_id} not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ListenerListSerializer(listener, context={'request': request})
        return Response(serializer.data)

    def available_listener_detail(self, request, listener_id=None):
        """Get detailed information about an available listener by user ID.

        URL: /api/talker/profiles/available_listeners/<user_id>/
        """
        if not request.user.is_authenticated or request.user.user_type != 'talker':
            return Response(
                {'error': 'Only authenticated talkers can view listener details'},
                status=status.HTTP_403_FORBIDDEN
            )

        is_blocked = ListenerBlockedTalker.objects.filter(
            listener_id=listener_id,
            talker=request.user
        ).exists()

        if is_blocked:
            return Response(
                {'error': 'This listener has blocked you and is not available'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            listener = ListenerProfile.objects.get(user_id=listener_id, is_available=True)
        except ListenerProfile.DoesNotExist:
            return Response(
                {'error': f'Available listener with user ID {listener_id} not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ListenerListSerializer(listener, context={'request': request})
        return Response(serializer.data)


    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, IsTalkerUser], url_path='favorite_listeners')
    def favorite_listeners(self, request):
        """Get talker's list of favorite listeners.

        URL: /api/talker/profiles/favorite_listeners/
        """
        favorites = FavoriteListener.objects.filter(talker=request.user)
        serializer = FavoriteListenerSerializer(favorites, many=True, context={'request': request})
        return Response({
            'count': favorites.count(),
            'results': serializer.data
        })

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, IsTalkerUser], url_path='add_favorite')
    def add_favorite(self, request):
        """Add a listener to favorites.

        URL: /api/talker/profiles/add_favorite/
        Request body: { "listener_id": 4 }
        """
        serializer = AddFavoriteListenerSerializer(data=request.data)
        if serializer.is_valid():
            listener_id = serializer.validated_data['listener_id']

            try:
                listener = ListenerProfile.objects.get(user_id=listener_id)
            except ListenerProfile.DoesNotExist:
                return Response(
                    {'error': f'Listener with ID {listener_id} not found'},
                    status=status.HTTP_404_NOT_FOUND
                )

            favorite, created = FavoriteListener.objects.get_or_create(
                talker=request.user,
                listener=listener
            )

            if not created:
                return Response(
                    {'message': 'Listener is already in your favorites'},
                    status=status.HTTP_200_OK
                )

            return Response(
                {'message': 'Listener added to favorites', 'data': FavoriteListenerSerializer(favorite, context={'request': request}).data},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, IsTalkerUser], url_path='remove_favorite')
    def remove_favorite(self, request):
        """Remove a listener from favorites.

        URL: /api/talker/profiles/remove_favorite/
        Request body: { "listener_id": 4 }
        """
        serializer = AddFavoriteListenerSerializer(data=request.data)
        if serializer.is_valid():
            listener_id = serializer.validated_data['listener_id']

            try:
                listener = ListenerProfile.objects.get(user_id=listener_id)
            except ListenerProfile.DoesNotExist:
                return Response(
                    {'error': f'Listener with ID {listener_id} not found'},
                    status=status.HTTP_404_NOT_FOUND
                )

            try:
                favorite = FavoriteListener.objects.get(talker=request.user, listener=listener)
                favorite.delete()
                return Response(
                    {'message': 'Listener removed from favorites'},
                    status=status.HTTP_200_OK
                )
            except FavoriteListener.DoesNotExist:
                return Response(
                    {'error': 'This listener is not in your favorites'},
                    status=status.HTTP_404_NOT_FOUND
                )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TalkerBalanceViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing talker balance (read-only)."""

    permission_classes = [IsTalkerUser]
    serializer_class = TalkerBalanceSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or self.request is None:
            return TalkerBalance.objects.none()

        user = self.request.user
        if user.user_type == 'talker':
            return TalkerBalance.objects.filter(talker=user)
        return TalkerBalance.objects.none()

    def list(self, request, *args, **kwargs):
        """Make GET /api/talker/balance/ return the current talker balance payload."""
        return self.my_balance(request)

    @swagger_auto_schema(
        operation_description="Get current talker balance",
        responses={200: TalkerBalanceSerializer},
        tags=['Talker Balance']
    )
    @action(detail=False, methods=['get'], url_path='my-balance')
    def my_balance(self, request):
        """Get current user's talker balance."""
        user = request.user

        if user.user_type != 'talker':
            return Response(
                {'error': 'Only talkers can view balance'},
                status=status.HTTP_403_FORBIDDEN
            )

        balance, created = TalkerBalance.objects.get_or_create(
            talker=user,
            defaults={'available_balance': 0, 'total_earned': 0, 'total_refunded': 0}
        )

        from django.db.models import Sum
        from bokking.models import SessionBooking

        rejected_booking_earnings = SessionBooking.objects.filter(
            talker=user,
            status='cancelled',
        ).aggregate(total=Sum('listener_amount'))['total'] or 0

        return Response({
            'total_earned': str(balance.total_earned),
            'total_refunded': str(balance.total_refunded),
            'last_updated': balance.updated_at,
            'debug_info': {
                'rejected_booking_earnings': str(rejected_booking_earnings),
                'balance_created_now': created,
            }
        })

    @swagger_auto_schema(
        operation_description='Create payout link / process payout for talker balance',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'amount': openapi.Schema(type=openapi.TYPE_STRING, description='Amount to payout'),
            },
            required=['amount']
        ),
        tags=['Talker Balance']
    )
    @action(detail=False, methods=['post'], url_path='create-payout-link')
    def create_payout_link(self, request):
        """Create Stripe Connect onboarding link or transfer payout for talker."""
        user = request.user
        if user.user_type != 'talker':
            return Response(
                {'error': 'Only talkers can request payouts'},
                status=status.HTTP_403_FORBIDDEN
            )

        amount_raw = request.data.get('amount')
        if amount_raw in [None, '']:
            return Response({'error': 'amount is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = Decimal(str(amount_raw))
        except (InvalidOperation, ValueError):
            return Response({'error': 'Invalid amount format'}, status=status.HTTP_400_BAD_REQUEST)

        if amount <= 0:
            return Response({'error': 'Amount must be greater than 0'}, status=status.HTTP_400_BAD_REQUEST)

        balance, _ = TalkerBalance.objects.get_or_create(
            talker=user,
            defaults={'available_balance': Decimal('0.00'), 'total_earned': Decimal('0.00'), 'total_refunded': Decimal('0.00')}
        )

        if amount > balance.available_balance:
            return Response(
                {
                    'error': f'Insufficient balance. Available: ${balance.available_balance}',
                    'available_balance': str(balance.available_balance),
                    'requested_amount': str(amount),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        stripe_account_id = balance.stripe_account_id or ''

        try:
            if not stripe_account_id:
                display_name = user.full_name or user.email
                name_parts = display_name.split(' ', 1)
                first_name = name_parts[0]
                last_name = name_parts[1] if len(name_parts) > 1 else ''

                account = stripe.Account.create(
                    type='express',
                    country='US',
                    email=user.email,
                    capabilities={'transfers': {'requested': True}},
                    business_type='individual',
                    individual={
                        'first_name': first_name,
                        'last_name': last_name,
                    },
                )
                stripe_account_id = account.id
                balance.stripe_account_id = stripe_account_id
                balance.stripe_account_verified = False
                balance.save(update_fields=['stripe_account_id', 'stripe_account_verified', 'updated_at'])

            account = stripe.Account.retrieve(stripe_account_id)
            currently_due = account.get('requirements', {}).get('currently_due') or []
            payouts_enabled = account.get('payouts_enabled', False)

            if currently_due or not payouts_enabled:
                account_link = stripe.AccountLink.create(
                    account=stripe_account_id,
                    refresh_url=f"{getattr(settings, 'BACKEND_URL', 'http://localhost:8000')}/talker/reauth",
                    return_url=f"{getattr(settings, 'BACKEND_URL', 'http://localhost:8000')}/talker/dashboard",
                    type='account_onboarding',
                )
                return Response(
                    {
                        'message': 'Complete Stripe onboarding.',
                        'onboarding_url': account_link.url,
                        'status': 'onboarding_required',
                        'stripe_account_id': stripe_account_id,
                    },
                    status=status.HTTP_200_OK,
                )

            transfer = stripe.Transfer.create(
                amount=int(amount * 100),
                currency='usd',
                destination=stripe_account_id,
                description=f'Payout for talker {user.email}',
            )

            with transaction.atomic():
                locked_balance = TalkerBalance.objects.select_for_update().get(id=balance.id)
                if amount > locked_balance.available_balance:
                    return Response(
                        {'error': f'Insufficient balance. Available: ${locked_balance.available_balance}'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                locked_balance.available_balance -= amount
                locked_balance.stripe_account_verified = True
                locked_balance.save(update_fields=['available_balance', 'stripe_account_verified', 'updated_at'])

            return Response(
                {
                    'detail': 'Talker payout successful.',
                    'transfer_id': transfer.id,
                    'amount': str(amount),
                    'new_balance': str((balance.available_balance - amount).quantize(Decimal('0.01'))),
                },
                status=status.HTTP_201_CREATED,
            )

        except stripe.error.StripeError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @swagger_auto_schema(
        operation_description="Get detailed information about an available listener",
        responses={200: openapi.Response('Available listener detail')},
        tags=['Talker Browse Listeners']
    )
    @action(detail=False, methods=['get'], permission_classes=[IsTalkerUser])
    def available_listeners_detail(self, request):
        """Get detailed information about an available listener by user ID.
        
        Verifies the listener speaks the same language as the talker and is available.
        
        URL: /api/talker/profiles/available_listeners_detail/?user_id=4
        Example: /api/talker/profiles/available_listeners_detail/?user_id=4
        
        Returns 403 if the listener has blocked this talker, doesn't speak talker's language, or is unavailable.
        """
        user_id = request.query_params.get('user_id')
        
        if not user_id:
            return Response(
                {'error': 'user_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if listener has blocked this talker
        is_blocked = ListenerBlockedTalker.objects.filter(
            listener_id=user_id,
            talker=request.user
        ).exists()
        
        if is_blocked:
            return Response(
                {'error': 'This listener has blocked you and is not available'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            listener = ListenerProfile.objects.get(user_id=user_id, is_available=True)
            
            # Check if listener speaks the talker's language
            # Only use ListenerProfile.languages - no fallback to User.language
            talker_language = request.user.language
            if not listener.languages or talker_language not in listener.languages:
                return Response(
                    {'error': 'This listener does not speak your language'},
                    status=status.HTTP_403_FORBIDDEN
                )
        except ListenerProfile.DoesNotExist:
            return Response(
                {'error': f'Available listener with user ID {user_id} not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = ListenerListSerializer(listener, context={'request': request})
        return Response(serializer.data)
    
    def listener_detail_by_id(self, request, listener_id=None):
        """Get detailed information about a specific listener by user ID.
        
        URL: /api/talker/profiles/all_listeners/<user_id>/
        Example: /api/talker/profiles/all_listeners/1/
        
        Returns 403 if the listener has blocked this talker.
        """
        # Check permission
        if not request.user.is_authenticated or request.user.user_type != 'talker':
            return Response(
                {'error': 'Only authenticated talkers can view listener details'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if listener has blocked this talker
        is_blocked = ListenerBlockedTalker.objects.filter(
            listener_id=listener_id,
            talker=request.user
        ).exists()
        
        if is_blocked:
            return Response(
                {'error': 'This listener has blocked you and is not available'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            listener = ListenerProfile.objects.get(user_id=listener_id)
        except ListenerProfile.DoesNotExist:
            return Response(
                {'error': f'Listener with user ID {listener_id} not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = ListenerListSerializer(listener, context={'request': request})
        return Response(serializer.data)
    
    def available_listener_detail(self, request, listener_id=None):
        """Get detailed information about an available listener by user ID.
        
        URL: /api/talker/profiles/available_listeners/<user_id>/
        Example: /api/talker/profiles/available_listeners/1/
        
        Returns 403 if the listener has blocked this talker or is not available.
        """
        # Check permission
        if not request.user.is_authenticated or request.user.user_type != 'talker':
            return Response(
                {'error': 'Only authenticated talkers can view listener details'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if listener has blocked this talker
        is_blocked = ListenerBlockedTalker.objects.filter(
            listener_id=listener_id,
            talker=request.user
        ).exists()
        
        if is_blocked:
            return Response(
                {'error': 'This listener has blocked you and is not available'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            listener = ListenerProfile.objects.get(user_id=listener_id, is_available=True)
        except ListenerProfile.DoesNotExist:
            return Response(
                {'error': f'Available listener with user ID {listener_id} not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = ListenerListSerializer(listener, context={'request': request})
        return Response(serializer.data)

    @swagger_auto_schema(
        operation_description="Rate a listener with a 1-5 star rating",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'listener_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID of the listener (ListenerProfile ID or User ID)'),
                'rating': openapi.Schema(type=openapi.TYPE_INTEGER, description='Rating from 1 to 5'),
                'review': openapi.Schema(type=openapi.TYPE_STRING, description='Optional review comment'),
            },
            required=['listener_id', 'rating'],
        ),
        responses={201: openapi.Response('Rating created successfully')},
        tags=['Talker Rate Listener']
    )
    @action(detail=False, methods=['post'], permission_classes=[IsTalkerUser])
    def rate_listener(self, request):
        """Rate a listener with a 1-5 star rating.
        
        This endpoint allows talkers to rate listeners they have interacted with.
        Each talker can only have one rating per listener (updating overwrites the previous rating).
        
        Request Body:
        - listener_id (required): ID of the listener (can be ListenerProfile ID or User ID)
        - rating (required): Rating from 1 to 5
        - review (optional): Text review comment
        
        Example:
        {
            "listener_id": 10,
            "rating": 5,
            "review": "Great listener, very empathetic!"
        }
        """
        import traceback
        try:
            listener_id = request.data.get('listener_id')
            rating = request.data.get('rating')
            review = request.data.get('review', '')
            
            if not listener_id:
                return Response(
                    {'error': 'listener_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not rating:
                return Response(
                    {'error': 'rating is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate rating is between 1-5
            try:
                rating_int = int(rating)
                if rating_int < 1 or rating_int > 5:
                    return Response(
                        {'error': 'rating must be between 1 and 5'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except (ValueError, TypeError):
                return Response(
                    {'error': 'rating must be an integer'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Frontend list/detail payloads expose the listener's user ID as `id`,
            # so prefer `user_id` first and fall back to the profile primary key.
            listener_profile = None
            try:
                listener_profile = ListenerProfile.objects.get(user_id=listener_id)
            except ListenerProfile.DoesNotExist:
                try:
                    listener_profile = ListenerProfile.objects.get(id=listener_id)
                except ListenerProfile.DoesNotExist:
                    return Response(
                        {'error': f'Listener with ID {listener_id} not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )
            
            # Delete existing rating if it exists
            ListenerRating.objects.filter(
                listener=listener_profile,
                talker=request.user
            ).delete()
            
            # Create new rating
            rating_obj = ListenerRating.objects.create(
                listener=listener_profile,
                talker=request.user,
                rating=rating_int,
                review=review if review else ''
            )

            # Return response
            return Response({
                'id': rating_obj.id,
                'listener_id': listener_profile.id,
                'talker_id': request.user.id,
                'rating': rating_obj.rating,
                'review': rating_obj.review,
                'created_at': rating_obj.created_at.isoformat() if rating_obj.created_at else None,
                'updated_at': rating_obj.updated_at.isoformat() if rating_obj.updated_at else None,
                'message': 'Rating saved successfully'
            }, status=status.HTTP_201_CREATED)
        except Exception as exc:
            error_trace = traceback.format_exc()
            return Response(
                {
                    'error': str(exc),
                    'error_type': type(exc).__name__,
                    'message': 'Check error_type and error fields for details'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @swagger_auto_schema(
        operation_description="Get all reviews/ratings for a listener",
        manual_parameters=[
            openapi.Parameter('listener_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, 
                            description='ID of the listener (ListenerProfile ID or User ID)'),
            openapi.Parameter('page', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, 
                            description='Page number (default: 1)'),
            openapi.Parameter('page_size', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, 
                            description='Items per page (default: 10)'),
        ],
        responses={200: openapi.Response('List of listener reviews')},
        tags=['Talker Rate Listener']
    )
    @action(detail=False, methods=['get'], permission_classes=[IsTalkerUser])
    def listener_reviews(self, request):
        """Get all reviews/ratings for a specific listener.
        
        Displays all 5-star ratings and reviews left by other talkers for a listener.
        Results are paginated and sorted by most recent first.
        
        Query Parameters:
        - listener_id (required): ID of the listener (can be ListenerProfile ID or User ID)
        - page: Page number (default: 1)
        - page_size: Items per page (default: 10, max: 50)
        
        Example: /api/talker/profiles/listener_reviews/?listener_id=10&page=1&page_size=10
        """
        from rest_framework.pagination import PageNumberPagination
        from listener.serializers import ListenerReviewDisplaySerializer
        
        listener_id = request.query_params.get('listener_id')
        
        if not listener_id:
            return Response(
                {'error': 'listener_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Try to get listener by ListenerProfile ID first, then by User ID
        listener_profile = None
        try:
            listener_profile = ListenerProfile.objects.get(id=listener_id)
        except ListenerProfile.DoesNotExist:
            # Try by user_id
            try:
                listener_profile = ListenerProfile.objects.get(user_id=listener_id)
            except ListenerProfile.DoesNotExist:
                return Response(
                    {'error': f'Listener with ID {listener_id} not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Get all ratings for this listener, ordered by most recent first
        ratings = ListenerRating.objects.filter(listener=listener_profile).order_by('-created_at')
        
        # Paginate results
        paginator = PageNumberPagination()
        paginator.page_size = int(request.query_params.get('page_size', 10))
        paginator.page_size = min(paginator.page_size, 50)  # Max 50 per page
        
        page = paginator.paginate_queryset(ratings, request)
        if page is not None:
            serializer = ListenerReviewDisplaySerializer(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)
        
        serializer = ListenerReviewDisplaySerializer(ratings, many=True, context={'request': request})
        return Response({
            'count': ratings.count(),
            'next': None,
            'previous': None,
            'results': serializer.data
        })
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, IsTalkerUser])
    def favorite_listeners(self, request):
        """Get talker's list of favorite listeners.
        
        URL: /api/talker/profiles/favorite_listeners/
        """
        favorites = FavoriteListener.objects.filter(talker=request.user)
        serializer = FavoriteListenerSerializer(favorites, many=True, context={'request': request})
        return Response({
            'count': favorites.count(),
            'results': serializer.data
        })

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, IsTalkerUser], url_path='add_favorite')
    def add_favorite(self, request):
        """Add a listener to favorites.
        
        URL: /api/talker/profiles/add_favorite/
        Request body: { "listener_id": 4 }
        """
        serializer = AddFavoriteListenerSerializer(data=request.data)
        if serializer.is_valid():
            listener_id = serializer.validated_data['listener_id']
            
            try:
                listener = ListenerProfile.objects.get(user_id=listener_id)
            except ListenerProfile.DoesNotExist:
                return Response(
                    {'error': f'Listener with ID {listener_id} not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Check if already in favorites
            favorite, created = FavoriteListener.objects.get_or_create(
                talker=request.user,
                listener=listener
            )
            
            if not created:
                return Response(
                    {'message': 'Listener is already in your favorites'},
                    status=status.HTTP_200_OK
                )
            
            return Response(
                {'message': 'Listener added to favorites', 'data': FavoriteListenerSerializer(favorite, context={'request': request}).data},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, IsTalkerUser], url_path='remove_favorite')
    def remove_favorite(self, request):
        """Remove a listener from favorites.
        
        URL: /api/talker/profiles/remove_favorite/
        Request body: { "listener_id": 4 }
        """
        serializer = AddFavoriteListenerSerializer(data=request.data)
        if serializer.is_valid():
            listener_id = serializer.validated_data['listener_id']
            
            try:
                listener = ListenerProfile.objects.get(user_id=listener_id)
            except ListenerProfile.DoesNotExist:
                return Response(
                    {'error': f'Listener with ID {listener_id} not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            try:
                favorite = FavoriteListener.objects.get(talker=request.user, listener=listener)
                favorite.delete()
                return Response(
                    {'message': 'Listener removed from favorites'},
                    status=status.HTTP_200_OK
                )
            except FavoriteListener.DoesNotExist:
                return Response(
                    {'error': 'This listener is not in your favorites'},
                    status=status.HTTP_404_NOT_FOUND
                )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_description="Get all call history for the authenticated talker",
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'count': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'results': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_OBJECT))
                }
            ),
            401: "Unauthorized",
            403: "Only talkers can access this endpoint"
        },
        tags=['Talker Call History']
    )
    @action(detail=False, methods=['get'], url_path='call-history', permission_classes=[IsTalkerUser])
    def call_history(self, request):
        """
        Get all call history for the authenticated talker.
        Shows all previous calls made to listeners with full details.
        
        Endpoint: GET /api/talker/profiles/call-history/
        
        Returns:
        - List of all call sessions where this talker made calls
        - Includes listener info, call duration, amount paid, status
        - Sorted by most recent first
        """
        from chat.models import CallSession
        
        # Get all call sessions where this user is the talker
        call_sessions = CallSession.objects.filter(
            talker=request.user
        ).select_related('listener', 'call_package__package').order_by('-created_at')
        
        # Pass actual CallSession objects to serializer
        serializer = TalkerCallHistorySerializer(call_sessions, many=True)
        return Response({
            'count': call_sessions.count(),
            'results': serializer.data
        }, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_description="Get detailed information about a specific call session",
        manual_parameters=[
            openapi.Parameter('call_session_id', openapi.IN_PATH, type=openapi.TYPE_INTEGER, 
                            description='ID of the call session')
        ],
        responses={
            200: openapi.Schema(type=openapi.TYPE_OBJECT),
            401: "Unauthorized",
            403: "Not authorized to view this call",
            404: "Call session not found"
        },
        tags=['Talker Call History']
    )
    @action(detail=False, methods=['get'], url_path='call-history/(?P<call_session_id>[0-9]+)', 
            permission_classes=[IsTalkerUser])
    def call_history_detail(self, request, call_session_id=None):
        """
        Get detailed information about a specific call session including transaction details.
        
        Endpoint: GET /api/talker/profiles/call-history/{call_session_id}/
        
        Returns:
        - Complete call details including listener profile
        - Call timing and duration information
        - Call package details with pricing breakdown
        - Transaction details: amount paid, commission, listener payout
        - Call status and end reason
        - Agora channel information
        """
        from chat.models import CallSession
        
        try:
            call_session = CallSession.objects.select_related(
                'listener', 'call_package__package'
            ).get(id=call_session_id, talker=request.user)
        except CallSession.DoesNotExist:
            return Response(
                {'error': 'Call session not found or you are not authorized to view it'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = TalkerCallHistoryDetailSerializer(call_session)
        return Response(serializer.data, status=status.HTTP_200_OK)