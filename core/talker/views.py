from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from .models import TalkerProfile
from .serializers import TalkerProfileSerializer
from listener.models import ListenerProfile, ListenerRating
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
    parser_classes = (MultiPartParser, FormParser)

    def get_queryset(self):
        """Return only the authenticated user's profile."""
        if self.request.user.is_authenticated:
            return TalkerProfile.objects.filter(user=self.request.user)
        return TalkerProfile.objects.none()

    def get_object(self):
        """Get the talker profile for the authenticated user."""
        return get_object_or_404(TalkerProfile, user=self.request.user)

    @action(detail=False, methods=['get', 'put', 'patch'], permission_classes=[IsTalkerUser])
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
            serializer = self.get_serializer(talker_profile)
            return Response(serializer.data)

        elif request.method in ['PUT', 'PATCH']:
            serializer = self.get_serializer(talker_profile, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], permission_classes=[IsTalkerUser])
    def all_listeners(self, request):
        """Get all listeners for talker to browse."""
        listeners = ListenerProfile.objects.all()
        serializer = ListenerListSerializer(listeners, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsTalkerUser])
    def available_listeners(self, request):
        """Get all available listeners only."""
        listeners = ListenerProfile.objects.filter(is_available=True)
        serializer = ListenerListSerializer(listeners, many=True)
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
