from datetime import date

from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
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

FINE_MULTIPLIER = 1.5


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

    def get_queryset(self):
        user = self.request.user
        queryset = self.queryset

        if not user.is_staff:
            queryset = queryset.filter(user=user)

        is_active = self.request.query_params.get("is_active")
        user_id = self.request.query_params.get("user_id")

        if is_active is not None:
            queryset = queryset.filter(actual_return_date__isnull=(is_active.lower() == "true"))

        if user.is_staff and user_id:
            queryset = queryset.filter(user_id=user_id)

        return queryset.distinct()

    def get_serializer_class(self):
        if self.action == "retrieve":
            return BorrowingDetailSerializer
        if self.action == "return_borrowing":
            return BorrowingReturnSerializer
        return BorrowingSerializer

    def create(self, request, *args, **kwargs):
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
                payment_type=Payment.TypeChoices.PAYMENT,
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

    @action(detail=True, methods=["post"], url_path="return")
    def return_borrowing(self, request, pk=None):
        borrowing = self.get_object()

        if borrowing.actual_return_date is not None:
            return Response(
                {"error": "This borrowing has already been returned."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        today = date.today()

        with transaction.atomic():
            borrowing.actual_return_date = today
            borrowing.save()

            book = borrowing.book
            book.inventory += 1
            book.save()

            payment_url = None
            if today > borrowing.expected_return_date:
                overdue_days = (today - borrowing.expected_return_date).days
                fine_amount = overdue_days * book.daily_fee * FINE_MULTIPLIER

                session, price = create_stripe_session(
                    borrowing, request, fine_amount=fine_amount
                )

                payment = Payment.objects.create(
                    status=Payment.StatusChoices.PENDING,
                    payment_type=Payment.TypeChoices.FINE,
                    borrowing=borrowing,
                    session_url=session.url,
                    session_id=session.id,
                    money_to_pay=price,
                )
                payment_url = payment.session_url

        if payment_url:
            message = (
                f"<b>⚠️ OVERDUE BOOK RETURNED (FINE REQUIRED)!</b>\n\n"
                f"<b>User:</b> {borrowing.user.email}\n"
                f"<b>Book:</b> {book.title}\n"
                f"<b>Fine Amount:</b> ${fine_amount:.2f}\n"
                f"<b>Pay Fine Here:</b> {payment_url}"
            )
        else:
            message = (
                f"<b>✅ BOOK RETURNED ON TIME!</b>\n\n"
                f"<b>User:</b> {borrowing.user.email}\n"
                f"<b>Book:</b> {book.title}"
            )

        send_notification_task.delay(message)

        response_data = {
            "message": "Book returned successfully.",
            "actual_return_date": borrowing.actual_return_date,
        }
        if payment_url:
            response_data["fine_payment_url"] = payment_url

        return Response(response_data, status=status.HTTP_200_OK)
