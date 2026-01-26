from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from decimal import Decimal
from .models import ListenerProfile, ListenerRating, ListenerBalance
from .serializers import ListenerProfileSerializer, ListenerListSerializer, ListenerRatingSerializer


class IsListenerUser(IsAuthenticated):
    """Custom permission to ensure user has listener role."""
    
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.user_type == 'listener'


class IsTalkerUser(IsAuthenticated):
    """Custom permission to ensure user has talker role."""
    
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.user_type == 'talker'


class ListenerProfileViewSet(viewsets.ModelViewSet):
    """ViewSet for listener profile management."""
    queryset = ListenerProfile.objects.all()
    serializer_class = ListenerProfileSerializer
    parser_classes = (MultiPartParser, FormParser)

    def get_permissions(self):
        """
        Return the appropriate permission based on the action.
        - list, retrieve: AllowAny
        - my_profile, create, update, partial_update, destroy: IsListenerUser
        """
        if self.action in ['list', 'retrieve']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsListenerUser]
        return [permission() for permission in permission_classes]

    def get_serializer_class(self):
        if self.action == 'list':
            return ListenerListSerializer
        return ListenerProfileSerializer

    def get_serializer_class(self):
        if self.action in ['list', 'available_listeners', 'all_listeners']:
            return ListenerListSerializer
        elif self.action == 'rate_listener':
            return ListenerRatingSerializer
        return ListenerProfileSerializer

    def get_object(self):
        """Get the listener profile for the authenticated user or retrieve by pk."""
        if self.action == 'my_profile':
            return get_object_or_404(ListenerProfile, user=self.request.user)
        return super().get_object()
    
    def get_queryset(self):
        """Filter queryset based on action."""
        if self.action == 'available_listeners':
            return ListenerProfile.objects.filter(is_available=True)
        return ListenerProfile.objects.all()

    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def available(self, request):
        """Get all available listeners."""
        listeners = ListenerProfile.objects.filter(is_available=True).order_by('-average_rating')
        serializer = ListenerListSerializer(listeners, many=True, context={'request': request})
        return Response({
            'count': listeners.count(),
            'results': serializer.data
        })

    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def details(self, request, pk=None):
        """Get detailed information about a specific listener (public endpoint for talkers)."""
        try:
            listener = ListenerProfile.objects.get(user_id=pk)
        except ListenerProfile.DoesNotExist:
            return Response(
                {'error': f'Listener with ID {pk} not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = ListenerProfileSerializer(listener, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get', 'put', 'patch'], permission_classes=[IsListenerUser], parser_classes=[MultiPartParser, FormParser])
    def my_profile(self, request):
        """Get or update the authenticated listener user's profile."""
        try:
            listener_profile = ListenerProfile.objects.get(user=request.user)
        except ListenerProfile.DoesNotExist:
            return Response(
                {'error': 'Listener profile not found. Please ensure you are registered as a listener.'},
                status=status.HTTP_404_NOT_FOUND
            )

        if request.method == 'GET':
            serializer = self.get_serializer(listener_profile, context={'request': request})
            return Response(serializer.data)

        elif request.method in ['PUT', 'PATCH']:
            serializer = self.get_serializer(listener_profile, data=request.data, partial=True, context={'request': request})
            if serializer.is_valid():
                serializer.save()
                # Refresh to get updated image
                listener_profile.refresh_from_db()
                response_data = serializer.data
                # Ensure profile_image_url is included
                if listener_profile.profile_image:
                    response_data['profile_image_url'] = request.build_absolute_uri(listener_profile.profile_image.url)
                return Response(response_data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ListenerBalanceViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing listener balance (read-only)."""
    
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Only show balance for current listener."""
        user = self.request.user
        if user.user_type == 'listener':
            return ListenerBalance.objects.filter(listener=user)
        return ListenerBalance.objects.none()
    
    @action(detail=False, methods=['get'], url_path='my-balance')
    def my_balance(self, request):
        """Get current user's balance."""
        user = request.user
        
        if user.user_type != 'listener':
            return Response(
                {'error': 'Only listeners can view balance'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get or create balance account
        balance, created = ListenerBalance.objects.get_or_create(
            listener=user,
            defaults={'available_balance': Decimal('0.00'), 'total_earned': Decimal('0.00')}
        )
        
        return Response({
            'available_balance': str(balance.available_balance),
            'total_earned': str(balance.total_earned),
            'last_updated': balance.updated_at
        })
