from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.shortcuts import get_object_or_404
from .models import TalkerProfile, FavoriteListener
from .serializers import (TalkerProfileSerializer, FavoriteListenerSerializer, AddFavoriteListenerSerializer,
                          TalkerCallHistorySerializer, TalkerCallHistoryDetailSerializer)
from listener.models import ListenerProfile, ListenerRating, ListenerBlockedTalker
from listener.serializers import ListenerListSerializer, ListenerRatingSerializer, ListenerReviewDisplaySerializer


class IsTalkerUser(IsAuthenticated):
    """Custom permission to ensure user has talker role."""
    
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.user.user_type == 'talker'
    
    def has_object_permission(self, request, view, obj):
        """Only allow talkers to access their own profile."""
        return obj.user == request.user


class TalkerProfileViewSet(viewsets.ModelViewSet):
    """ViewSet for talker profile management and listener interactions."""
    queryset = TalkerProfile.objects.all()
    serializer_class = TalkerProfileSerializer
    permission_classes = [IsTalkerUser]
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def get_queryset(self):
        """Return only the authenticated user's profile."""
        if self.request.user.is_authenticated:
            return TalkerProfile.objects.filter(user=self.request.user)
        return TalkerProfile.objects.none()

    def get_object(self):
        """Get the talker profile for the authenticated user."""
        return get_object_or_404(TalkerProfile, user=self.request.user)

    @action(detail=False, methods=['get', 'put', 'patch'], permission_classes=[IsTalkerUser], parser_classes=[MultiPartParser, FormParser])
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
            serializer = self.get_serializer(talker_profile, data=request.data, partial=True, context={'request': request})
            if serializer.is_valid():
                serializer.save()
                # Return serializer data with full context
                response_data = serializer.data
                # Ensure profile_image_url is included
                if talker_profile.profile_image:
                    response_data['profile_image_url'] = request.build_absolute_uri(talker_profile.profile_image.url)
                return Response(response_data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_description="Get all listeners for talker to browse with optional search and gender filtering",
        manual_parameters=[
            openapi.Parameter('search', openapi.IN_QUERY, type=openapi.TYPE_STRING, 
                            description='Search by listener first_name or last_name'),
            openapi.Parameter('gender', openapi.IN_QUERY, type=openapi.TYPE_STRING, 
                            description='Filter by gender: male, female, other, prefer_not_to_say')
        ],
        responses={200: openapi.Response('List of listeners')},
        tags=['Talker Browse Listeners']
    )
    @action(detail=False, methods=['get'], permission_classes=[IsTalkerUser])
    def all_listeners(self, request):
        """Get all listeners for talker to browse.
        
        Supports search by first_name or last_name and filtering by gender.
        Excludes listeners who have blocked this talker.
        
        Query Parameters:
        - search: Search by first_name or last_name (case-insensitive)
        - gender: Filter by gender (male, female, other, prefer_not_to_say)
        
        Example: /api/talker/profiles/all_listeners/?search=alice&gender=female
        """
        from django.db.models import Q
        
        # Get list of listener IDs that have blocked this talker
        blocked_by = ListenerBlockedTalker.objects.filter(
            talker=request.user
        ).values_list('listener_id', flat=True)
        
        # Get all listeners except those who have blocked this talker
        listeners = ListenerProfile.objects.exclude(
            user_id__in=blocked_by
        ).order_by('-average_rating')
        
        # Apply search filter if provided
        search_query = request.query_params.get('search', '').strip()
        if search_query:
            listeners = listeners.filter(
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query)
            )
        
        # Apply gender filter if provided
        gender = request.query_params.get('gender', '').strip()
        if gender:
            listeners = listeners.filter(gender=gender)
        
        serializer = ListenerListSerializer(listeners, many=True, context={'request': request})
        return Response({
            'count': listeners.count(),
            'results': serializer.data,
            'search_query': search_query if search_query else None,
            'gender_filter': gender if gender else None
        })

    @swagger_auto_schema(
        operation_description="Get all available listeners only with optional search",
        manual_parameters=[
            openapi.Parameter('search', openapi.IN_QUERY, type=openapi.TYPE_STRING, 
                            description='Search by listener first_name or last_name')
        ],
        responses={200: openapi.Response('List of available listeners')},
        tags=['Talker Browse Listeners']
    )
    @action(detail=False, methods=['get'], permission_classes=[IsTalkerUser])
    def available_listeners(self, request):
        """Get all available listeners only.
        
        Supports search by first_name or last_name.
        Excludes listeners who have blocked this talker.
        
        Query Parameters:
        - search: Search by first_name or last_name (case-insensitive)
        
        Example: /api/talker/profiles/available_listeners/?search=john
        """
        from django.db.models import Q
        
        # Get list of listener IDs that have blocked this talker
        blocked_by = ListenerBlockedTalker.objects.filter(
            talker=request.user
        ).values_list('listener_id', flat=True)
        
        # Get available listeners except those who have blocked this talker
        listeners = ListenerProfile.objects.filter(
            is_available=True
        ).exclude(
            user_id__in=blocked_by
        ).order_by('-average_rating')
        
        # Apply search filter if provided
        search_query = request.query_params.get('search', '').strip()
        if search_query:
            listeners = listeners.filter(
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query)
            )
        
        serializer = ListenerListSerializer(listeners, many=True, context={'request': request})
        return Response({
            'count': listeners.count(),
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
        
        URL: /api/talker/profiles/all_listeners_detail/?user_id=4
        Example: /api/talker/profiles/all_listeners_detail/?user_id=4
        
        Returns 403 if the listener has blocked this talker.
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
        except ListenerProfile.DoesNotExist:
            return Response(
                {'error': f'Listener with user ID {user_id} not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = ListenerListSerializer(listener, context={'request': request})
        return Response(serializer.data)
    
    @swagger_auto_schema(
        operation_description="Get detailed information about an available listener",
        responses={200: openapi.Response('Available listener detail')},
        tags=['Talker Browse Listeners']
    )
    @action(detail=False, methods=['get'], permission_classes=[IsTalkerUser])
    def available_listeners_detail(self, request):
        """Get detailed information about an available listener by user ID.
        
        URL: /api/talker/profiles/available_listeners_detail/?user_id=4
        Example: /api/talker/profiles/available_listeners_detail/?user_id=4
        
        Returns 403 if the listener has blocked this talker or is not available.
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
        listener_id = request.data.get('listener_id')
        rating = request.data.get('rating')
        
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
        
        # Check if talker already rated this listener
        existing_rating = ListenerRating.objects.filter(
            listener=listener_profile, talker=request.user
        ).first()
        
        if existing_rating:
            # Update existing rating
            serializer = ListenerRatingSerializer(existing_rating, data=request.data, partial=True)
        else:
            # Create new rating
            serializer = ListenerRatingSerializer(data=request.data)
        
        if serializer.is_valid():
            if not existing_rating:
                serializer.save(listener=listener_profile, talker=request.user)
            else:
                serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
    
    @action(detail=False, methods=['get'], permission_classes=[IsTalkerUser])
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

    @action(detail=False, methods=['post'], permission_classes=[IsTalkerUser])
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

    @action(detail=False, methods=['post'], permission_classes=[IsTalkerUser])
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