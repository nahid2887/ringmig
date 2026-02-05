"""
Agora-based calling API views.
Handles real-time voice and video calling using Agora SDK.

!!! AGORA SYSTEM COMMENTED OUT !!!
"""

# from rest_framework import viewsets, status
# from rest_framework.decorators import action
# from rest_framework.response import Response
# from rest_framework.permissions import IsAuthenticated
# from django.contrib.auth import get_user_model
# from django.utils import timezone
# from django.db import transaction
# from django.shortcuts import get_object_or_404
# from drf_yasg.utils import swagger_auto_schema
# from drf_yasg import openapi
# import logging
# 
# from .call_models import CallPackage, CallSession, UniversalCallPackage
# from .call_serializers import CallSessionSerializer
# from .agora_utils import agora_token_generator, agora_call_manager
# 
# User = get_user_model()
# logger = logging.getLogger(__name__)


# class AgoraCallViewSet(viewsets.GenericViewSet):
#     """API endpoints for Agora-based calling system - COMMENTED OUT."""
#     
#     permission_classes = [IsAuthenticated]
#     serializer_class = CallSessionSerializer
#     
#     def get_queryset(self):
#         """Return call sessions for the current user."""
#         user = self.request.user
#         if user.user_type == 'talker':
#             return CallSession.objects.filter(talker=user)
#         elif user.user_type == 'listener':
#             return CallSession.objects.filter(listener=user)
#         return CallSession.objects.none()
#     
#     @action(detail=False, methods=['post'])
#     def start_call(self, request):
#         """Start a new call session based on purchased call package."""
#         # AGORA SYSTEM COMMENTED OUT
#         pass
#     
#     @action(detail=False, methods=['post'])
#     def join_call(self, request):
#         """Join an existing call session (for listener)."""
#         # AGORA SYSTEM COMMENTED OUT
#         pass