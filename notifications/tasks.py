from celery import shared_task
from django.utils import timezone
from .telegram_utils import send_telegram_message


@shared_task
def send_notification_task(message: str) -> None:
    send_telegram_message(message)


@shared_task
def check_overdue_borrowings() -> None:
    from library.models import Borrowing

    today = timezone.now().date()
    overdue_borrowings = Borrowing.objects.filter(
        expected_return_date__lt=today,
        actual_return_date__isnull=True,
    ).select_related("book", "user")

    if not overdue_borrowings.exists():
        send_telegram_message("No borrowings overdue today!")
        return

    for borrowing in overdue_borrowings:
        text = (
            f"<b>⚠️ OVERDUE BORROWING DETECTED!</b>\n\n"
            f"<b>User:</b> {borrowing.user.email}\n"
            f"<b>Book:</b> {borrowing.book.title}\n"
            f"<b>Expected Return:</b> {borrowing.expected_return_date}\n"
        )
        send_telegram_message(text)
