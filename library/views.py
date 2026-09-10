from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.utils import timezone
from notifications.tasks import send_notification_task

from .models import Book, Borrowing, Payment
from .permissions import IsAdminOrReadOnly
from .serializers import (
    BookSerializer,
    BorrowingSerializer,
    BorrowingDetailSerializer,
    BorrowingReturnSerializer,
    PaymentSerializer, BookListSerializer, BookDetailSerializer,
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
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        queryset = Borrowing.objects.select_related("book", "user").prefetch_related("payments")
        user = self.request.user
        if not user.is_staff:
            queryset = queryset.filter(user=user)
        user_id = self.request.query_params.get("user_id")
        if user_id and user.is_staff:
            queryset = queryset.filter(user_id=user_id)

        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            if is_active.lower() == "true":
                queryset = queryset.filter(actual_return_date__isnull=True)
            elif is_active.lower() == "false":
                queryset = queryset.filter(actual_return_date__isnull=False)

        return queryset

    def get_serializer_class(self):
        if self.action == "retrieve":
            return BorrowingDetailSerializer
        if self.action == "return_borrowing":
            return BorrowingReturnSerializer
        return BorrowingSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user, borrow_date=timezone.now().date())

    @action(detail=True, methods=["post"], url_path="return")
    def return_borrowing(self, request, pk=None):
        borrowing = self.get_object()

        if borrowing.actual_return_date is not None:
            return Response(
                {"error": "This borrowing has already been returned."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            borrowing.actual_return_date = timezone.now().date()
            borrowing.save()

            book = borrowing.book
            book.inventory += 1
            book.save()

        serializer = self.get_serializer(borrowing)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def perform_create(self, serializer):
        borrowing = serializer.save(
            user=self.request.user, borrow_date=timezone.now().date()
        )

        message = (
            f"<b>📌 NEW BORROWING CREATED!</b>\n\n"
            f"<b>User:</b> {borrowing.user.email}\n"
            f"<b>Book:</b> {borrowing.book.title}\n"
            f"<b>Expected Return:</b> {borrowing.expected_return_date}"
        )
        send_notification_task.delay(message)


class PaymentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = (IsAuthenticated,)
    serializer_class = PaymentSerializer

    def get_queryset(self):
        queryset = Payment.objects.select_related("borrowing")
        if not self.request.user.is_staff:
            return queryset.filter(borrowing__user=self.request.user)
        return queryset
