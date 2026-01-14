from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Conversation, Message, FileAttachment

User = get_user_model()


class UserBasicSerializer(serializers.ModelSerializer):
    """Basic user information for chat participants."""
    
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'email', 'user_type', 'full_name']
    
    def get_full_name(self, obj):
        """Get full name from appropriate profile."""
        if obj.user_type == 'listener' and hasattr(obj, 'listener_profile'):
            return obj.listener_profile.get_full_name()
        elif obj.user_type == 'talker' and hasattr(obj, 'talker_profile'):
            return obj.talker_profile.get_full_name()
        return obj.email


class FileAttachmentSerializer(serializers.ModelSerializer):
    """Serializer for file attachments."""
    
    file_url = serializers.SerializerMethodField()
    file_size_display = serializers.CharField(source='get_file_size_display', read_only=True)
    
    class Meta:
        model = FileAttachment
        fields = [
            'id', 'file', 'file_url', 'filename', 
            'file_size', 'file_size_display', 'file_type', 'uploaded_at'
        ]
        read_only_fields = ['id', 'uploaded_at', 'file_size', 'file_type']
    
    def get_file_url(self, obj):
        """Get absolute URL for the file."""
        request = self.context.get('request')
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return None


class MessageSerializer(serializers.ModelSerializer):
    """Serializer for chat messages."""
    
    sender = UserBasicSerializer(read_only=True)
    file_attachment = FileAttachmentSerializer(read_only=True)
    
    class Meta:
        model = Message
        fields = [
            'id', 'conversation', 'sender', 'content', 
            'message_type', 'is_read', 'created_at', 'file_attachment'
        ]
        read_only_fields = ['id', 'sender', 'created_at']
    
    def validate(self, data):
        """Validate that text messages have content."""
        if data.get('message_type') == 'text' and not data.get('content'):
            raise serializers.ValidationError("Text messages must have content.")
        return data


class ConversationSerializer(serializers.ModelSerializer):
    """Detailed serializer for conversations."""
    
    listener = UserBasicSerializer(read_only=True)
    talker = UserBasicSerializer(read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'listener', 'talker', 'status', 'status_display',
            'created_at', 'updated_at', 'accepted_at', 'rejected_at',
            'last_message_at', 'last_message', 'unread_count', 'initial_message'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'accepted_at', 'rejected_at', 'last_message_at']
    
    def get_last_message(self, obj):
        """Get the last message in the conversation."""
        last_msg = obj.messages.order_by('-created_at').first()
        if last_msg:
            return MessageSerializer(last_msg, context=self.context).data
        return None
    
    def get_unread_count(self, obj):
        """Get count of unread messages for the current user."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.messages.filter(is_read=False).exclude(sender=request.user).count()
        return 0


class ConversationListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for conversation lists."""
    
    other_user = serializers.SerializerMethodField()
    last_message_preview = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'status', 'status_display', 'other_user', 'last_message_at', 
            'last_message_preview', 'unread_count', 'created_at'
        ]
    
    def get_other_user(self, obj):
        """Get the other participant in the conversation."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            other_user = obj.get_other_user(request.user)
            return UserBasicSerializer(other_user).data
        return None
    
    def get_last_message_preview(self, obj):
        """Get a preview of the last message."""
        last_msg = obj.messages.order_by('-created_at').first()
        if last_msg:
            if last_msg.message_type == 'file':
                return f"📎 {last_msg.file_attachment.filename if hasattr(last_msg, 'file_attachment') else 'File'}"
            return last_msg.content[:50] + ('...' if len(last_msg.content) > 50 else '')
        return obj.initial_message[:50] + ('...' if len(obj.initial_message) > 50 else '') if obj.initial_message else 'No messages yet'
    
    def get_unread_count(self, obj):
        """Get count of unread messages for the current user."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.messages.filter(is_read=False).exclude(sender=request.user).count()
        return 0


class ConversationCreateSerializer(serializers.Serializer):
    """Serializer for creating a new conversation with initial message."""
    
    listener_id = serializers.IntegerField(required=False)
    initial_message = serializers.CharField(required=True, max_length=10000)
    
    def validate(self, data):
        """Validate that listener_id is provided."""
        if not data.get('listener_id'):
            raise serializers.ValidationError("listener_id is required to start a conversation.")
        if not data.get('initial_message') or not data['initial_message'].strip():
            raise serializers.ValidationError("initial_message cannot be empty.")
        return data
