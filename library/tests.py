from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from library.models import Book, Borrowing

User = get_user_model()


class BorrowingApiTests(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            email="user1@example.com", password="password123"
        )
        self.user2 = User.objects.create_user(
            email="user2@example.com", password="password123"
        )
        self.admin = User.objects.create_superuser(
            email="admin@example.com", password="password123"
        )

        self.book = Book.objects.create(
            title="Clean Code",
            author="Robert C. Martin",
            inventory=2,
            daily_fee=10.00,
        )

        self.borrowings_url = reverse("library:borrowing-list")

    def _get_results(self, response_data):
        if isinstance(response_data, dict):
            return response_data.get("results", [])
        return response_data

    def test_user_cannot_see_other_users_borrowings(self):
        borrowing_user1 = Borrowing.objects.create(
            user=self.user1,
            book=self.book,
            borrow_date=date.today(),
            expected_return_date=date.today() + timedelta(days=5),
        )
        borrowing_user2 = Borrowing.objects.create(
            user=self.user2,
            book=self.book,
            borrow_date=date.today(),
            expected_return_date=date.today() + timedelta(days=5),
        )

        self.client.force_authenticate(user=self.user1)
        response = self.client.get(self.borrowings_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = self._get_results(response.data)
        borrowing_ids = [b["id"] for b in results]

        self.assertIn(borrowing_user1.id, borrowing_ids)
        self.assertNotIn(borrowing_user2.id, borrowing_ids)

    def test_admin_can_see_all_borrowings_and_filter_by_user_id(self):
        borrowing_user1 = Borrowing.objects.create(
            user=self.user1,
            book=self.book,
            borrow_date=date.today(),
            expected_return_date=date.today() + timedelta(days=5),
        )
        borrowing_user2 = Borrowing.objects.create(
            user=self.user2,
            book=self.book,
            borrow_date=date.today(),
            expected_return_date=date.today() + timedelta(days=5),
        )

        self.client.force_authenticate(user=self.admin)

        response = self.client.get(self.borrowings_url)
        results = self._get_results(response.data)
        self.assertEqual(len(results), 2)

        response_filtered = self.client.get(
            self.borrowings_url, {"user_id": self.user1.id}
        )
        filtered_results = self._get_results(response_filtered.data)
        self.assertEqual(len(filtered_results), 1)
        self.assertEqual(filtered_results[0]["id"], borrowing_user1.id)

    @patch("library.views.send_notification_task.delay")
    @patch("library.views.create_stripe_session")
    def test_create_borrowing_decreases_inventory(
        self, mock_create_stripe, mock_notification
    ):
        class MockStripeSession:
            id = "cs_test_123"
            url = "https://checkout.stripe.com/test"

        mock_create_stripe.return_value = (MockStripeSession(), 50.00)

        self.client.force_authenticate(user=self.user1)
        initial_inventory = self.book.inventory

        payload = {
            "book": self.book.id,
            "expected_return_date": (date.today() + timedelta(days=5)).strftime(
                "%Y-%m-%d"
            ),
        }

        response = self.client.post(self.borrowings_url, payload)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, initial_inventory - 1)

    @patch("library.views.send_notification_task.delay")
    def test_return_borrowing_increases_inventory(self, mock_notification):
        self.book.inventory = 1
        self.book.save()

        borrowing = Borrowing.objects.create(
            user=self.user1,
            book=self.book,
            borrow_date=date.today() - timedelta(days=2),
            expected_return_date=date.today() + timedelta(days=3),
        )

        return_url = reverse("library:borrowing-return-borrowing", args=[borrowing.id])

        self.client.force_authenticate(user=self.user1)
        response = self.client.post(return_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 2)

        borrowing.refresh_from_db()
        self.assertIsNotNone(borrowing.actual_return_date)

    @patch("library.views.send_notification_task.delay")
    def test_double_return_returns_400_bad_request(self, mock_notification):
        borrowing = Borrowing.objects.create(
            user=self.user1,
            book=self.book,
            borrow_date=date.today() - timedelta(days=5),
            expected_return_date=date.today() - timedelta(days=1),
            actual_return_date=date.today(),
        )

        return_url = reverse("library:borrowing-return-borrowing", args=[borrowing.id])

        self.client.force_authenticate(user=self.user1)
        response = self.client.post(return_url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
