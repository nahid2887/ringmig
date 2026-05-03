import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

@pytest.mark.django_db
class TestPayouts:
    def setup_method(self):
        self.client = APIClient()
        self.talker_account_id = "acct_test_talker"  # Replace with a valid account ID for testing

    def test_purchase_payout(self):
        response = self.client.post(reverse('chat:purchase'), {
            'amount': 1000,
            'talker_account_id': self.talker_account_id,
        })
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'success'

    def test_extend_minutes_payout(self):
        response = self.client.post(reverse('chat:extend_minutes'), {
            'minutes': 10,
            'talker_account_id': self.talker_account_id,
        })
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'success'

    def test_create_payment_intent_payout(self):
        response = self.client.post(reverse('payment:create_payment_intent'), {
            'amount': 500,
            'talker_account_id': self.talker_account_id,
        })
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'success'