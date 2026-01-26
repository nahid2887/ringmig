"""
Agora utilities for generating RTC tokens and managing call channels.
"""

import time
import uuid
from agora_token_builder import RtcTokenBuilder
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class AgoraTokenGenerator:
    """Generate Agora RTC tokens for audio and video calls."""
    
    def __init__(self):
        self.app_id = getattr(settings, 'AGORA_APP_ID', '4cd28b722093446199a5db6a89ffda4f')
        self.app_certificate = getattr(settings, 'AGORA_PRIMARY_CERTIFICATE', '197ae79cc31e4d9597982a635cebb3e8')
    
    def generate_channel_name(self, session_id):
        """Generate unique channel name for a call session."""
        return f"call_session_{session_id}_{int(time.time())}"
    
    def generate_rtc_token(self, channel_name, uid=0, role='publisher', expiration_seconds=3600):
        """
        Generate RTC token for joining Agora channel.
        
        Args:
            channel_name (str): Channel name
            uid (int): User ID (0 for auto-assignment)
            role (str): 'publisher' or 'subscriber'
            expiration_seconds (int): Token expiration time in seconds
        
        Returns:
            str: RTC token
        """
        try:
            # Convert role to Agora role constant
            if role == 'publisher':
                agora_role = 1  # RtcTokenBuilder.Role_Publisher
            else:
                agora_role = 2  # RtcTokenBuilder.Role_Subscriber
            
            # Calculate expiration time
            current_timestamp = int(time.time())
            privilege_expired_ts = current_timestamp + expiration_seconds
            
            # Generate token
            token = RtcTokenBuilder.buildTokenWithUid(
                self.app_id,
                self.app_certificate,
                channel_name,
                uid,
                agora_role,
                privilege_expired_ts
            )
            
            logger.info(f"Generated Agora RTC token for channel: {channel_name}, uid: {uid}")
            return token
            
        except Exception as e:
            logger.error(f"Failed to generate Agora token: {str(e)}")
            raise Exception(f"Token generation failed: {str(e)}")
    
    def generate_tokens_for_call(self, session_id, talker_uid=None, listener_uid=None):
        """
        Generate tokens for both participants in a call.
        
        Args:
            session_id (int): Call session ID
            talker_uid (int, optional): Talker's UID
            listener_uid (int, optional): Listener's UID
        
        Returns:
            dict: Contains channel_name, talker_token, listener_token, app_id
        """
        channel_name = self.generate_channel_name(session_id)
        
        # Use user IDs or auto-assign
        talker_uid = talker_uid or 0
        listener_uid = listener_uid or 0
        
        # Generate tokens for both participants (both as publishers)
        talker_token = self.generate_rtc_token(
            channel_name=channel_name,
            uid=talker_uid,
            role='publisher',
            expiration_seconds=7200  # 2 hours
        )
        
        listener_token = self.generate_rtc_token(
            channel_name=channel_name,
            uid=listener_uid,
            role='publisher',
            expiration_seconds=7200  # 2 hours
        )
        
        return {
            'channel_name': channel_name,
            'talker_token': talker_token,
            'listener_token': listener_token,
            'talker_uid': talker_uid,
            'listener_uid': listener_uid,
            'app_id': self.app_id,
            'expires_in': 7200
        }


class AgoraCallManager:
    """Manage Agora call operations."""
    
    @staticmethod
    def get_call_config(package_type):
        """
        Get Agora call configuration based on package type.
        
        Args:
            package_type (str): 'audio', 'video', or 'both'
        
        Returns:
            dict: Call configuration
        """
        configs = {
            'audio': {
                'video_enabled': False,
                'audio_enabled': True,
                'video_profile': None,
                'call_type': 'audio'
            },
            'video': {
                'video_enabled': True,
                'audio_enabled': True,
                'video_profile': '480p_4',  # 640x480, 30fps
                'call_type': 'video'
            },
            'both': {
                'video_enabled': True,
                'audio_enabled': True,
                'video_profile': '720p_5',  # 1280x720, 30fps
                'call_type': 'video'  # Default to video when both
            }
        }
        
        return configs.get(package_type, configs['audio'])
    
    @staticmethod
    def validate_call_requirements(session, user):
        """
        Validate if user can join the call.
        
        Args:
            session: CallSession instance
            user: User instance
        
        Returns:
            tuple: (is_valid, error_message)
        """
        # Check if user is part of this session
        if user not in [session.talker, session.listener]:
            return False, "You are not part of this call session"
        
        # Check if session can be connected
        if not session.can_connect():
            return False, "Call session cannot be connected - check payment status"
        
        # Check if session is in valid state
        if session.status in ['ended', 'timeout', 'failed']:
            return False, f"Call session has already {session.status}"
        
        return True, None


# Global token generator instance
agora_token_generator = AgoraTokenGenerator()
agora_call_manager = AgoraCallManager()