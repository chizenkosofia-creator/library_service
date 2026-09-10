import os
import stripe
from decimal import Decimal
from django.urls import reverse
from payments.models import Payment

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")


def calculate_borrowing_price(borrowing) -> Decimal:
    days = (borrowing.expected_return_date - borrowing.borrow_date).days
    days = max(days, 1)
    return Decimal(days) * borrowing.book.daily_fee


def create_stripe_session(borrowing, request, payment_type=Payment.TypeChoices.PAYMENT):
    """Create Checkout Session in Stripe."""
    price = calculate_borrowing_price(borrowing)
    price_in_cents = int(price * 100)

    success_url = request.build_absolute_uri(reverse("payment-success")) + "?session_id={CHECKOUT_SESSION_ID}"
    cancel_url = request.build_absolute_uri(reverse("payment-cancel"))

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": f"Borrowing: {borrowing.book.title}",
                    },
                    "unit_amount": price_in_cents,
                },
                "quantity": 1,
            }
        ],
        mode="payment",
        success_url=success_url,
        cancel_url=cancel_url,
    )

    return session, price
