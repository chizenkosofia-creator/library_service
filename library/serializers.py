from datetime import date
from rest_framework import serializers, status
from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response
from notifications.tasks import send_notification_task
from payments.stripe_utils import create_stripe_session
from library.models import Book, Borrowing
from payments.models import Payment
from payments.serializers import PaymentSerializer

FINE_MULTIPLIER = 1.5

class BookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = ("id", "title", "author", "cover", "inventory", "daily_fee")


class BookListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = ("id", "title", "author", "cover", "inventory", "daily_fee")


class BookDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = (
            "id",
            "title",
            "author",
            "cover",
            "inventory",
            "daily_fee",
            "money",
        )


class BorrowingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Borrowing
        fields = (
            "id",
            "borrow_date",
            "expected_return_date",
            "actual_return_date",
            "book",
            "user",
        )
        read_only_fields = ("id", "borrow_date", "actual_return_date", "user")

    def validate(self, attrs):
        book = attrs["book"]
        if book.inventory < 1:
            raise serializers.ValidationError({"book": "This book is currently out of stock."})

        expected = attrs.get("expected_return_date")
        if expected and expected < timezone.now().date():
            raise serializers.ValidationError({"expected_return_date":
                                                   "Expected return date cannot be in the past."})

        return attrs

    def create(self, validated_data):
        with transaction.atomic():
            book = validated_data["book"]
            book.inventory -= 1
            book.save()
            borrowing = Borrowing.objects.create(**validated_data)
            return borrowing

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
                    type=Payment.TypeChoices.FINE,
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
                f"<b>Fine Amount:</b> ${fine_amount}\n"
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


class BorrowingDetailSerializer(BorrowingSerializer):
    book = BookSerializer(read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)

    class Meta(BorrowingSerializer.Meta):
        fields = BorrowingSerializer.Meta.fields + ("payments",)


class BorrowingReturnSerializer(serializers.ModelSerializer):
    class Meta:
        model = Borrowing
        fields = ("id", "actual_return_date")
        read_only_fields = ("id", "actual_return_date")
