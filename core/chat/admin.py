from django.contrib import admin
from .models import Conversation, Message, FileAttachment


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['id', 'listener', 'talker', 'last_message_at', 'created_at']
    list_filter = ['created_at', 'last_message_at']
    search_fields = ['listener__email', 'talker__email']
    readonly_fields = ['created_at', 'updated_at', 'last_message_at']


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'conversation', 'sender', 'message_type', 'is_read', 'created_at']
    list_filter = ['message_type', 'is_read', 'created_at']
    search_fields = ['sender__email', 'content']
    readonly_fields = ['created_at']


@admin.register(FileAttachment)
class FileAttachmentAdmin(admin.ModelAdmin):
    list_display = ['id', 'filename', 'file_size', 'file_type', 'uploaded_at']
    list_filter = ['file_type', 'uploaded_at']
    search_fields = ['filename']
    readonly_fields = ['uploaded_at', 'file_size', 'file_type']
