from rest_framework import viewsets, mixins, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from notifications.tasks import send_notification_task
from payments.models import Payment
from payments.stripe_utils import create_stripe_session

from .models import Book, Borrowing
from .permissions import IsAdminOrReadOnly
from .serializers import (
    BookSerializer,
    BorrowingSerializer,
    BorrowingDetailSerializer,
    BorrowingReturnSerializer,
    BookListSerializer, BookDetailSerializer,
)


class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.all()
    permission_classes = (IsAdminOrReadOnly,)

    def get_serializer_class(self):
        if self.action == "list":
            return BookListSerializer
        if self.action == "retrieve":
            return BookDetailSerializer
        return BookSerializer


class BorrowingViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Borrowing.objects.select_related("book", "user")
    permission_classes = (IsAuthenticated,)

    def get_serializer_class(self):
        if self.action == "retrieve":
            return BorrowingDetailSerializer
        return BorrowingSerializer

    def create(self, request, *args, **kwargs):
        # 1. Забороняємо створення оренди, якщо є непогашені платежі (PENDING)
        has_pending_payments = Payment.objects.filter(
            borrowing__user=request.user,
            status=Payment.StatusChoices.PENDING
        ).exists()

        if has_pending_payments:
            return Response(
                {"error": "You have pending payments. Please pay them before borrowing new books."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            borrowing = serializer.save(user=request.user)

            session, price = create_stripe_session(borrowing, request)

            payment = Payment.objects.create(
                status=Payment.StatusChoices.PENDING,
                type=Payment.TypeChoices.PAYMENT,
                borrowing=borrowing,
                session_url=session.url,
                session_id=session.id,
                money_to_pay=price,
            )

        message = (
            f"<b>📌 NEW BORROWING CREATED!</b>\n\n"
            f"<b>User:</b> {borrowing.user.email}\n"
            f"<b>Book:</b> {borrowing.book.title}\n"
            f"<b>Expected Return:</b> {borrowing.expected_return_date}\n"
            f"<b>Pay here:</b> {payment.session_url}"
        )
        send_notification_task.delay(message)

        response_data = serializer.data
        response_data["payment_url"] = payment.session_url

        headers = self.get_success_headers(serializer.data)
        return Response(response_data, status=status.HTTP_201_CREATED, headers=headers)