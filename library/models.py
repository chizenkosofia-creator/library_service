from django.db import models

from library_service import settings


class Book(models.Model):
    class CoverChoices(models.TextChoices):
        HARD = "HARD", "Hardcover"  # Тверда обкладинка
        SOFT = "SOFT", "Softcover"
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=200)
    cover = models.CharField(
        choices=CoverChoices.choices,
        default=CoverChoices.HARD
    )
    inventory = models.IntegerField()
    daily_fee = models.FloatField()

    @property
    def money(self):
        return self.daily_fee + "$"

    def __str__(self):
        return self.title


class Borrowing(models.Model):
    borrow_date = models.DateField()
    expected_return_date = models.DateField()
    actual_return_date = models.DateField()
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='borrowings')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='borrowings')

    def __str__(self):
        return f"Borrowing book#{self.book_id} by User #{self.user_id}"


class Payment(models.Model):
    class StatusChoices(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"

    class TypeChoices(models.TextChoices):
        PAYMENT = "PAYMENT", "Payment"
        FINE = "FINE", "Fine"

    status = models.CharField(
        max_length=7,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING,
    )
    type = models.CharField(
        max_length=7,
        choices=TypeChoices.choices,
        default=TypeChoices.PAYMENT
    )
    borrowing = models.ForeignKey(Borrowing, on_delete=models.CASCADE, related_name='payments')
    session_url = models.URLField(max_length=500)
    session_id = models.CharField(max_length=255)
    money_to_pay = models.DecimalField(max_digits=8, decimal_places=2)
    
    def __str__(self):
        return f"Payment #{self.id} ({self.status})"
