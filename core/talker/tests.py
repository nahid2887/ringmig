from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework import status

from .models import TalkerProfile

User = get_user_model()


class TalkerProfileTestCase(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			email='talker@example.com',
			password='password123',
			user_type='talker'
		)
		self.profile, created = TalkerProfile.objects.get_or_create(user=self.user)
		self.profile.first_name = 'Test'
		self.profile.last_name = 'Talker'
		self.profile.save()
		self.client = APIClient()
		self.client.force_authenticate(user=self.user)

	def test_my_profile_patch_accepts_large_profile_image(self):
		url = '/api/talker/profiles/my_profile/'
		large_image = SimpleUploadedFile(
			'large-profile.jpg',
			b'\xff\xd8\xff\xe0' + b'0' * (6 * 1024 * 1024),
			content_type='image/jpeg'
		)

		response = self.client.patch(
			url,
			{'profile_image': large_image},
			format='multipart'
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.profile.refresh_from_db()
		self.assertTrue(self.profile.profile_image)
