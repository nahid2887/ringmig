from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import get_object_or_404
from .models import TalkerProfile, FavoriteListener
from .serializers import TalkerProfileSerializer, FavoriteListenerSerializer, AddFavoriteListenerSerializer
from listener.models import ListenerProfile, ListenerRating, ListenerBlockedTalker
from listener.serializers import ListenerListSerializer, ListenerRatingSerializer


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

    @action(detail=False, methods=['get'], permission_classes=[IsTalkerUser])
    def all_listeners(self, request):
        """Get all listeners for talker to browse.
        
        Excludes listeners who have blocked this talker.
        """
        # Get list of listener IDs that have blocked this talker
        blocked_by = ListenerBlockedTalker.objects.filter(
            talker=request.user
        ).values_list('listener_id', flat=True)
        
        # Get all listeners except those who have blocked this talker
        listeners = ListenerProfile.objects.exclude(
            user_id__in=blocked_by
        ).order_by('-average_rating')
        
        serializer = ListenerListSerializer(listeners, many=True, context={'request': request})
        return Response({
            'count': listeners.count(),
            'results': serializer.data
        })

    @action(detail=False, methods=['get'], permission_classes=[IsTalkerUser])
    def available_listeners(self, request):
        """Get all available listeners only.
        
        Excludes listeners who have blocked this talker.
        """
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
        
        serializer = ListenerListSerializer(listeners, many=True, context={'request': request})
        return Response({
            'count': listeners.count(),
            'results': serializer.data
        })
    
    def listener_detail_by_id(self, request, listener_id=None):
        """Get detailed information about a specific listener by user ID.
        
        URL: /api/talker/profiles/all_listeners/<user_id>/
        Example: /api/talker/profiles/all_listeners/4/
        
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
        
        from listener.serializers import ListenerListSerializer
        serializer = ListenerListSerializer(listener, context={'request': request})
        return Response(serializer.data)
    
    def available_listener_detail(self, request, listener_id=None):
        """Get detailed information about an available listener by user ID.
        
        URL: /api/talker/profiles/available_listeners/<user_id>/
        Example: /api/talker/profiles/available_listeners/4/
        
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
            listener = ListenerProfile.objects.get(user_id=listener_id, is_available=True)
        except ListenerProfile.DoesNotExist:
            return Response(
                {'error': f'Available listener with user ID {listener_id} not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        from listener.serializers import ListenerListSerializer
        serializer = ListenerListSerializer(listener, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['post'], permission_classes=[IsTalkerUser])
    def rate_listener(self, request):
        """Rate a listener."""
        listener_id = request.data.get('listener_id')
        if not listener_id:
            return Response(
                {'error': 'listener_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            listener_profile = ListenerProfile.objects.get(id=listener_id)
        except ListenerProfile.DoesNotExist:
            return Response(
                {'error': 'Listener not found'},
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