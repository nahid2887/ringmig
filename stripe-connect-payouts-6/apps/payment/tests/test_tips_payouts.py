from django.test import TestCase
from django.urls import reverse
from apps.payment.services.tips import create_payment_intent
from apps.stripe_connect.transfers import create_transfer

class TipsPayoutsTestCase(TestCase):
    def setUp(self):
        self.talker_account_id = "acct_testtalker"
        self.tip_amount = 1000  # Amount in cents

    def test_create_payment_intent(self):
        response = create_payment_intent(self.talker_account_id, self.tip_amount)
        self.assertTrue(response['success'])
        self.assertIn('client_secret', response)

    def test_create_transfer(self):
        response = create_transfer(self.talker_account_id, self.tip_amount)
        self.assertTrue(response['success'])
        self.assertIn('transfer_id', response)

    def test_purchase_endpoint(self):
        response = self.client.post(reverse('purchase'), {'amount': self.tip_amount})
        self.assertEqual(response.status_code, 200)

    def test_extend_minutes_endpoint(self):
        response = self.client.post(reverse('extend_minutes'), {'minutes': 10})
        self.assertEqual(response.status_code, 200)

    def test_create_payment_intent_endpoint(self):
        response = self.client.post(reverse('create_payment_intent'), {'amount': self.tip_amount})
        self.assertEqual(response.status_code, 200)