# core/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested.routers import NestedSimpleRouter
from .views import *

router = DefaultRouter()
router.register(r"currencies", CurrencyViewSet, basename="currency")
router.register(r"categories", CategoryViewSet, basename="category")
router.register(r"accounts", AccountViewSet, basename="account")
router.register(r"transactions", TransactionViewSet, basename="transaction")
router.register(r"recurring-bills", RecurringBillViewSet, basename="recurringbill")
router.register(r"budgets", BudgetViewSet, basename="budget")
router.register(r"notifications", NotificationViewSet, basename="notification")
router.register(r"exchange-rates", ExchangeRateViewSet, basename="exchangerate")
router.register(r"audit-logs", AuditLogViewSet, basename="auditlog")

# nested routes
split_router = NestedSimpleRouter(router, r"transactions", lookup="transaction")
split_router.register(r"splits", TransactionSplitViewSet, basename="transaction-splits")
split_router.register(r"attachments", AttachmentViewSet, basename="transaction-attachments")

auth_urls = [
    path("users/register/", register),
    path("users/login/", login),
    path("users/logout/", logout),
    path("users/me/", me),   #  ANIGA
    path("users/reset-password/", reset_password),
    path("users/reset-password-confirm/", reset_password_confirm),
    path("users/google-oauth/", google_oauth),
    path("users/verify-otp/", verify_otp),  # ✅ Add this
    path("users/resend_verification/", resend_verification),  # ✅ Add this
    # path("users/send_verification_otp/",send_verification_otp),
    path("users/verify_email/", verify_email),  # ✅ Add this
    path("users/resend-otp/", resend_otp),
    path("users/change-password/", change_password),  # ✅ Add this
    
    


]





urlpatterns = [
    path("", include(router.urls)),
    path("", include(split_router.urls)),
    *auth_urls
]