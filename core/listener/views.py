from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from .models import ListenerProfile, ListenerRating
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

    @action(detail=False, methods=['get', 'put', 'patch'], permission_classes=[IsListenerUser])
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
            serializer = self.get_serializer(listener_profile)
            return Response(serializer.data)

        elif request.method in ['PUT', 'PATCH']:
            serializer = self.get_serializer(listener_profile, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
