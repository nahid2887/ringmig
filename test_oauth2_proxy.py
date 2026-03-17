#!/usr/bin/env python
"""
Test script for OAuth2 Token Proxy Endpoint
Tests multi-user OAuth2 token retrieval with listener/talker identification
"""

import os
import sys
import django
import requests
import json
from pathlib import Path

# Setup Django
sys.path.insert(0, str(Path(__file__).parent / 'core'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

# Configuration
API_BASE_URL = 'http://localhost:8000'
OAUTH2_PROXY_ENDPOINT = f'{API_BASE_URL}/api/users/oauth2/token/'
OAUTH2_EXTERNAL_ENDPOINT = 'http://10.10.13.24:80/v2/auth/oauth2/token'

def get_bearer_token_for_user(user_email):
    """Get JWT bearer token for a user"""
    try:
        user = User.objects.get(email=user_email)
        refresh = RefreshToken.for_user(user)
        return str(refresh.access_token)
    except User.DoesNotExist:
        print(f"User {user_email} not found")
        return None

def test_oauth2_proxy_endpoint():
    """Test the OAuth2 proxy endpoint"""
    print("=" * 80)
    print("Testing OAuth2 Token Proxy Endpoint")
    print("=" * 80)
    
    # Get a test user's bearer token
    # First, check if we have any users
    users = User.objects.filter(is_active=True)[:3]
    
    if not users:
        print("❌ No active users found. Please create a test user first.")
        return False
    
    for user in users:
        print(f"\n\n--- Testing with user: {user.email} (Type: {user.user_type}) ---")
        
        # Get bearer token
        bearer_token = get_bearer_token_for_user(user.email)
        if not bearer_token:
            print(f"❌ Failed to get bearer token for {user.email}")
            continue
        
        print(f"✓ Bearer token obtained: {bearer_token[:50]}...")
        
        # Prepare OAuth2 request payload
        oauth2_payload = {
            'grant_type': 'client_credentials',
            'client_id': 'test_client',
            'client_secret': 'test_secret'
        }
        
        headers = {
            'Authorization': f'Bearer {bearer_token}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        print(f"\nEndpoint: {OAUTH2_PROXY_ENDPOINT}")
        print(f"Payload: {oauth2_payload}")
        
        try:
            # Make request to proxy endpoint
            response = requests.post(
                OAUTH2_PROXY_ENDPOINT,
                data=oauth2_payload,
                headers=headers,
                timeout=10
            )
            
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print("\n✓ Response received successfully!")
                print("\nResponse structure:")
                print(json.dumps(data, indent=2))
                
                # Check for user_info in response
                if 'user_info' in data:
                    print("\n✓ User information successfully added:")
                    user_info = data['user_info']
                    print(f"  - User ID: {user_info.get('user_id')}")
                    print(f"  - Email: {user_info.get('email')}")
                    print(f"  - Full Name: {user_info.get('full_name')}")
                    print(f"  - User Type: {user_info.get('user_type')}")
                    
                    if user_info.get('user_type') == 'listener':
                        print(f"  - Listener ID: {user_info.get('listener_id')}")
                        print(f"  - Listener Name: {user_info.get('listener_name')}")
                    elif user_info.get('user_type') == 'talker':
                        print(f"  - Talker ID: {user_info.get('talker_id')}")
                        print(f"  - Talker Name: {user_info.get('talker_name')}")
                else:
                    print("\n⚠ Warning: user_info not found in response")
            
            elif response.status_code == 401:
                print("❌ Unauthorized - Invalid bearer token")
                print(response.text)
            
            elif response.status_code == 400:
                print("❌ Bad request - OAuth2 endpoint error")
                print(response.text)
            
            else:
                print(f"❌ Unexpected status code: {response.status_code}")
                print(response.text)
        
        except requests.exceptions.ConnectionError:
            print(f"❌ Connection error - Cannot reach {OAUTH2_PROXY_ENDPOINT}")
            print("   Make sure the Django server is running on http://localhost:8000")
        
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {str(e)}")
    
    print("\n" + "=" * 80)
    print("Test completed!")
    print("=" * 80)

def show_instructions():
    """Show usage instructions"""
    print("\n" + "=" * 80)
    print("OAUTH2 PROXY ENDPOINT - USAGE INSTRUCTIONS")
    print("=" * 80)
    print("\n1. URL: POST /api/users/oauth2/token/")
    print("\n2. Authentication: Requires bearer token in Authorization header")
    print("   Header: Authorization: Bearer <JWT_TOKEN>")
    print("\n3. Request Payload (same as OAuth2 token endpoint):")
    print("   {")
    print("     'grant_type': 'client_credentials|password|refresh_token',")
    print("     'client_id': 'your_client_id',")
    print("     'client_secret': 'your_client_secret',")
    print("     // ... other OAuth2 parameters ...")
    print("   }")
    print("\n4. Response: OAuth2 token response + user information:")
    print("   {")
    print("     'access_token': '...',")
    print("     'token_type': 'Bearer',")
    print("     'expires_in': 3600,")
    print("     'refresh_token': '...',")
    print("     'user_info': {")
    print("       'user_id': 123,")
    print("       'email': 'user@example.com',")
    print("       'full_name': 'John Doe',")
    print("       'user_type': 'listener|talker',")
    print("       'listener_id': 456,  // For listener users")
    print("       'talker_id': 789,    // For talker users")
    print("     }")
    print("   }")
    print("\n5. Feature: This endpoint adds the authenticated user's listener/talker ID")
    print("   to the OAuth2 response, enabling multi-user OAuth2 integration.")
    print("\n" + "=" * 80 + "\n")

if __name__ == '__main__':
    show_instructions()
    test_oauth2_proxy_endpoint()
