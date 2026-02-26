"""
Test script to verify ZIM token integration in call initiation endpoint
"""

import requests
import json


def test_zim_token_endpoint():
    """Test the initiate-from-package endpoint to ensure ZIM tokens are included."""
    
    # API endpoint
    url = "http://10.10.13.27:8005/api/chat/call-sessions/initiate-from-package/"
    
    # You'll need to replace these with actual values from your system
    test_data = {
        "call_package_id": 1  # Replace with actual call package ID
    }
    
    # You'll need to add actual JWT token from authentication
    headers = {
        "Authorization": "Bearer YOUR_JWT_TOKEN_HERE",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=test_data, headers=headers)
        
        if response.status_code == 200 or response.status_code == 201:
            data = response.json()
            
            print("✅ Endpoint Response Success!")
            print(f"Status Code: {response.status_code}")
            
            # Check if ZIM tokens are present
            if 'zim' in data:
                zim_data = data['zim']
                print("\n🔐 ZIM Tokens Found!")
                print(f"App ID: {zim_data.get('app_id')}")
                print(f"Talker User ID: {zim_data.get('talker', {}).get('user_id')}")
                print(f"Talker Token: {zim_data.get('talker', {}).get('token')[:50]}...")
                print(f"Listener User ID: {zim_data.get('listener', {}).get('user_id')}")
                print(f"Listener Token: {zim_data.get('listener', {}).get('token')[:50]}...")
                print(f"Expires At: {zim_data.get('expires_at')}")
            else:
                print("\n❌ ZIM tokens not found in response")
            
            print(f"\n📄 Full Response Structure:")
            print(json.dumps(list(data.keys()), indent=2))
            
        else:
            print(f"❌ Request Failed: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Network Error: {e}")
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")


if __name__ == "__main__":
    print("🧪 Testing ZIM Token Integration")
    print("=" * 50)
    test_zim_token_endpoint()
    print("\n" + "=" * 50)
    print("⚠️  Remember to:")
    print("1. Replace call_package_id with actual ID")
    print("2. Add your JWT authentication token")
    print("3. Ensure you have a confirmed call package")