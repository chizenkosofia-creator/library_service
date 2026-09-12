from django.db import models

from library_service import settings


class Book(models.Model):
    class CoverChoices(models.TextChoices):
        HARD = "HARD", "Hardcover"  # Тверда обкладинка
        SOFT = "SOFT", "Softcover"
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=200)
    cover = models.CharField(
        max_length=10,
        choices=CoverChoices.choices,
        default=CoverChoices.HARD,
    )
    inventory = models.IntegerField()
    daily_fee = models.FloatField()

    @property
    def money(self):
        return f"{self.daily_fee:.2f}$"

    def __str__(self):
        return self.title


class Borrowing(models.Model):
    borrow_date = models.DateField(auto_now_add=True)
    expected_return_date = models.DateField()
    actual_return_date = models.DateField(null=True, blank=True)
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='borrowings')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='borrowings')

    def __str__(self):
        return f"Borrowing book#{self.book_id} by User #{self.user_id}"
