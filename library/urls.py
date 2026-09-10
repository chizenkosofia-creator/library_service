from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BookViewSet, BorrowingViewSet, PaymentViewSet

router = DefaultRouter()
router.register("books", BookViewSet, basename="book")
router.register("borrowings", BorrowingViewSet, basename="borrowing")
router.register("payments", PaymentViewSet, basename="payment")

urlpatterns = [
    path("", include(router.urls)),
]

app_name = "library"
