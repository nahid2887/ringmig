from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from .models import ListenerProfile

User = get_user_model()

class ListenerProfileTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='listener@example.com',
            password='password123',
            user_type='listener'
        )
        self.profile, created = ListenerProfile.objects.get_or_create(user=self.user)
        self.profile.first_name = 'Test'
        self.profile.last_name = 'Listener'
        self.profile.experience_level = 'beginner'
        self.profile.save()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_my_profile_patch_normalization(self):
        url = '/api/listener/profiles/my_profile/'
        data = {
            'specialties[]': ['anxiety', 'depression'],
            'topics': 'social_call, hobby',
            'languages': '["en", "es"]',
            'hourly_rate': 'undefined',
            'is_available': 'null',
            'location': 'New York, USA',
            'bio': 'undefined'
        }
        response = self.client.patch(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Refresh from db
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.specialties, ['anxiety', 'depression'])
        self.assertEqual(self.profile.topics, ['social_call', 'hobby'])
        self.assertEqual(self.profile.languages, ['en', 'es'])
        self.assertEqual(self.profile.location, 'New York, USA')
        self.assertEqual(self.profile.bio, '') # 'undefined' should normalize to ''
