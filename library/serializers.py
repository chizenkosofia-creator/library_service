from rest_framework import serializers
from django.db import transaction
from django.utils import timezone
from .models import Book, Borrowing, Payment


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


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            "id",
            "status",
            "type",
            "borrowing",
            "session_url",
            "session_id",
            "money_to_pay",
        )
        read_only_fields = ("id", "status", "type", "session_url", "session_id", "money_to_pay")


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
