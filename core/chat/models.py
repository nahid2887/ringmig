from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
import os

User = get_user_model()

# Import call models
from .call_models import CallSession, CallPackage, UniversalCallPackage


class Conversation(models.Model):
    """Represents a chat conversation between a listener and a talker."""
    
    STATUS_CHOICES = [
        ('pending', _('Pending')),  # Talker sent message, waiting for listener to accept
        ('active', _('Active')),    # Listener accepted, both can message
        ('rejected', _('Rejected')), # Listener rejected
        ('closed', _('Closed')),    # Conversation ended
    ]
    
    listener = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='listener_conversations',
        limit_choices_to={'user_type': 'listener'}
    )
    talker = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='talker_conversations',
        limit_choices_to={'user_type': 'talker'}
    )
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending',
        help_text=_('Conversation status')
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    accepted_at = models.DateTimeField(null=True, blank=True, help_text=_('When listener accepted'))
    rejected_at = models.DateTimeField(null=True, blank=True, help_text=_('When listener rejected'))
    last_message_at = models.DateTimeField(null=True, blank=True)
    initial_message = models.TextField(blank=True, help_text=_('Initial message from talker'))
    
    class Meta:
        verbose_name = 'Conversation'
        verbose_name_plural = 'Conversations'
        unique_together = ['listener', 'talker']
        ordering = ['-last_message_at', '-created_at']
        indexes = [
            models.Index(fields=['listener', 'talker']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['-last_message_at']),
        ]
    
    def __str__(self):
        return f"Conversation: {self.listener.email} <-> {self.talker.email} ({self.status})"
    
    def get_other_user(self, user):
        """Get the other participant in the conversation."""
        if user == self.listener:
            return self.talker
        return self.listener
    
    def accept(self):
        """Accept the conversation request."""
        from django.utils import timezone
        self.status = 'active'
        self.accepted_at = timezone.now()
        self.save(update_fields=['status', 'accepted_at'])
    
    def reject(self):
        """Reject the conversation request."""
        from django.utils import timezone
        self.status = 'rejected'
        self.rejected_at = timezone.now()
        self.save(update_fields=['status', 'rejected_at'])


class Message(models.Model):
    """Represents a single message in a conversation."""
    
    MESSAGE_TYPE_CHOICES = [
        ('text', _('Text')),
        ('file', _('File')),
    ]
    
    conversation = models.ForeignKey(
        Conversation, 
        on_delete=models.CASCADE, 
        related_name='messages'
    )
    sender = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='sent_messages'
    )
    content = models.TextField(blank=True, help_text=_('Message content'))
    message_type = models.CharField(
        max_length=10, 
        choices=MESSAGE_TYPE_CHOICES, 
        default='text'
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Message'
        verbose_name_plural = 'Messages'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
            models.Index(fields=['conversation', 'is_read']),
        ]
    
    def __str__(self):
        return f"Message from {self.sender.email} at {self.created_at}"
    
    def save(self, *args, **kwargs):
        """Update conversation's last_message_at when saving a message."""
        # Only allow messages in active conversations or from talker when creating initial conversation
        if self.conversation.status not in ['active', 'pending']:
            raise ValueError(
                _('Cannot send messages in a %(status)s conversation') % 
                {'status': self.conversation.get_status_display()}
            )
        
        # Only talker can message in pending status, after that anyone can
        if self.conversation.status == 'pending' and self.sender != self.conversation.talker:
            raise ValueError(_('Only the talker can send messages in a pending conversation'))
        
        super().save(*args, **kwargs)
        self.conversation.last_message_at = self.created_at
        self.conversation.save(update_fields=['last_message_at'])


class FileAttachment(models.Model):
    """Represents a file attached to a message."""
    
    message = models.OneToOneField(
        Message, 
        on_delete=models.CASCADE, 
        related_name='file_attachment'
    )
    file = models.FileField(upload_to='chat_files/%Y/%m/%d/')
    filename = models.CharField(max_length=255)
    file_size = models.BigIntegerField(help_text=_('File size in bytes'))
    file_type = models.CharField(max_length=100, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'File Attachment'
        verbose_name_plural = 'File Attachments'
    
    def __str__(self):
        return f"File: {self.filename}"
    
    def save(self, *args, **kwargs):
        """Auto-populate filename, file_size, and file_type if not set."""
        if self.file and not self.filename:
            self.filename = os.path.basename(self.file.name)
        if self.file and not self.file_size:
            self.file_size = self.file.size
        if self.file and not self.file_type:
            self.file_type = self.file.content_type if hasattr(self.file, 'content_type') else ''
        super().save(*args, **kwargs)
    
    def get_file_size_display(self):
        """Return human-readable file size."""
        size = self.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
