import os
import stripe
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from payments.models import Payment
from payments.serializers import PaymentSerializer
from payments.stripe_utils import create_stripe_session
from notifications.tasks import send_notification_task

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")


class PaymentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Payment.objects.select_related("borrowing")
    serializer_class = PaymentSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        queryset = self.queryset
        if not self.request.user.is_staff:
            queryset = queryset.filter(borrowing__user=self.request.user)
        return queryset

    def perform_create(self, serializer):
        borrowing = serializer.validated_data["borrowing"]
        session, price = create_stripe_session(borrowing, self.request)

        serializer.save(
            session_url=session.url,
            session_id=session.id,
            money_to_pay=price,
            payment_type=Payment.TypeChoices.PAYMENT,
        )

    @action(detail=False, methods=["get"], url_path="success")
    def success(self, request):
        """Ендпоінт для підтвердження успішного платежу."""
        session_id = request.query_params.get("session_id")
        if not session_id:
            return Response(
                {"error": "Session ID is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payment = Payment.objects.get(session_id=session_id)
            session = stripe.checkout.Session.retrieve(session_id)

            if session.payment_status == "paid":
                payment.status = Payment.StatusChoices.PAID
                payment.save()

                message = (
                    f"<b>✅ SUCCESSFUL PAYMENT!</b>\n\n"
                    f"<b>Payment ID:</b> {payment.id}\n"
                    f"<b>User:</b> {payment.borrowing.user.email}\n"
                    f"<b>Amount:</b> ${payment.money_to_pay}\n"
                    f"<b>Book:</b> {payment.borrowing.book.title}"
                )
                send_notification_task.delay(message)

                return Response(
                    {"message": "Payment was successful!", "payment_id": payment.id},
                    status=status.HTTP_200_OK,
                )

            return Response(
                {"message": "Payment pending or not completed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Payment.DoesNotExist:
            return Response(
                {"error": "Payment record not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

    @action(detail=False, methods=["get"], url_path="cancel")
    def cancel(self, request):
        return Response(
            {
                "message": (
                    "Payment was cancelled or paused. "
                    "The session remains active for 24 "
                    "hours to complete the payment."
                )
            },
            status=status.HTTP_200_OK,
        )
