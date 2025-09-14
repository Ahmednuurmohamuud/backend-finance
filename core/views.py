# core/views.py
from django.shortcuts import render
from django.db.models import Sum, OuterRef, Subquery, F, Value
from django.db.models.functions import Coalesce
from django.utils.timezone import now
from django.db import models
from rest_framework import viewsets, mixins, permissions, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.postgres.search import SearchQuery, SearchRank
# Ku bedel kani:
from core.tasks import send_email_notification_task, test_notification_task  # ✅ KORRECT
from django.db.models import Q
from django.utils import timezone
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from django.contrib.auth import authenticate
from datetime import timedelta
from django.shortcuts import get_object_or_404

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from .models import AuditLog
from .serializers import AuditLogSerializer
from .filters import AuditLogFilter
from .tasks import fetch_exchange_rates
from .models import *
from .serializers import *
from .filters import *
from .permissions import IsOwner
from .signals import create_audit
from .tasks import send_email_notification_task, generate_due_recurring_transactions_task
from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
import random
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.core.mail import send_mail
from django.urls import reverse

signer = TimestampSigner()  # token generator for email verification
EMAIL_TOKEN_MAX_AGE = 60 * 60 * 24  # 24h validity

FRONTEND_URL = "finance-frontend-production-a0b9.up.railway.app"




User = get_user_model()
token_generator = PasswordResetTokenGenerator()




# =========================
# ----- OTP Helpers -------
# =========================
def generate_otp(user):
    otp_code = f"{random.randint(100000, 999999)}" # 6-digit OTP
    OTP.objects.create(user=user, code=otp_code)
    return otp_code


def send_otp_email(user):   
    otp = generate_otp(user)
    send_mail(
        subject="Your OTP Code",
        message=f"Your login OTP code is: {otp}",
        from_email=None,
        recipient_list=[user.email],
        fail_silently=False,
    )

# =========================
# ----- Login View -----
@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def login(request):
    username_or_email = request.data.get("username")
    password = request.data.get("password")

    if not username_or_email or not password:
        return Response({"detail": "Username/email and password required"}, status=400)

    # Hubi user jiritaanka
    try:
        user_obj = User.objects.get(Q(username=username_or_email) | Q(email=username_or_email))
    except User.DoesNotExist:
        return Response({"detail": "Username or email is incorrect"}, status=400)

    # Hubi password
    if not user_obj.check_password(password):
        return Response({"detail": "Password is incorrect"}, status=400)
    
    # Koodhka cusub halkan ku dar si aad u hubiso in akoonku firfirran yahay            
    if not user_obj.is_active:
        send_verification_email(user_obj)  # U dir email firfirroonayn
        return Response(
            {
                "detail": "Your account is not active. A verification email has been sent to your email address.",
                "activation_required": True,
                "user_id": str(user_obj.id)
            },
            status=403
        )

    # Hubi verify
    if not getattr(user_obj, "is_verified", False):
        return Response(
            {
                "detail": "Please verify your account before logging in.",
                "verification_required": True,
                "email": user_obj.email,   # ✅ ku dar emai
                "user_id": str(user_obj.id)
            },
            status=403
        )

    # Authenticate
    user = authenticate(username=user_obj.username, password=password)
    if not user:
        return Response({"detail": "Authentication failed"}, status=400)

    # 2FA
    if getattr(user, "two_factor_enabled", False):
        send_otp_email(user)
        return Response({
            "otp_required": True,
            "user_id": str(user.id),
            "message": "OTP sent to your email"
        })

    # Normal login
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])
    refresh = RefreshToken.for_user(user)
    return Response({
        "otp_required": False,
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "message": f"Welcome {user.username}"
    })
# =========================
# ----- OTP Verify --------
OTP_VALID_MINUTES = 30

@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def verify_otp(request):
    user_id = request.data.get("user_id")
    otp = request.data.get("otp")

    if not user_id or not otp:
        return Response({"detail": "user_id and otp are required"}, status=400)

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({"detail": "User not found"}, status=404)

    try:
        otp_obj = OTP.objects.filter(user=user, code=otp, is_used=False).latest("created_at")
    except OTP.DoesNotExist:
        return Response({"detail": "Invalid OTP"}, status=400)

    if not otp_obj.is_valid(OTP_VALID_MINUTES):
        return Response({"detail": "OTP expired or already used"}, status=400)

    # Mark as used
    otp_obj.is_used = True
    otp_obj.save(update_fields=["is_used"])

    refresh = RefreshToken.for_user(user)
    return Response({
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "message": f"Welcome {user.username}"
    })


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def resend_otp(request):
    user_id = request.data.get("user_id")
    if not user_id:
        return Response({"detail": "user_id required"}, status=400)

    try:
        user = User.objects.get(id=user_id)

        # check OTP requests in last 24h
        now = timezone.now()
        last_24h = now - timedelta(hours=24)
        otp_count = OTP.objects.filter(user=user, created_at__gte=last_24h).count()

        if otp_count >= 3:
            return Response(
                {"detail": "You have reached the maximum of 3 OTP requests in 24 hours."},
                status=429,
            )

        # send OTP
        send_otp_email(user)
        return Response({"detail": "OTP resent"})

    except User.DoesNotExist:
        return Response({"detail": "User not found"}, status=404)

# -------- Auth endpoints --------


# -------- Send verification email --------
def send_verification_email(user):
    token = signer.sign(user.id)  # create signed token
    verification_link = f"{FRONTEND_URL}/verify-email?token={token}"
    send_mail(
        subject="Verify your email",
        message=f"Click this link to verify your email: {verification_link}",
        from_email=None,  # uses DEFAULT_FROM_EMAIL
        recipient_list=[user.email],
        fail_silently=False,
    )

# ----- Resend Verification -----


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def resend_verification(request):
    email = request.data.get("email")
    if not email:
        return Response({"detail": "email is required"}, status=400)

    try:
        user = User.objects.get(email=email)

        if user.is_verified:
            return Response({"detail": "User is already verified"}, status=400)

        # Hubi waqtigii ugu dambeysay ee verification email la diray
        if hasattr(user, "last_verification_sent") and user.last_verification_sent:
            diff = timezone.now() - user.last_verification_sent
            if diff.total_seconds() < 86400:  # 24 saac = 86400 ilbiriqsi
                return Response(
                    {"detail": "Verification email hore ayaa laguu diray. Fadlan sug 24 saac ka hor intaadan mar kale codsan."},
                    status=429
                )

        send_verification_email(user)
        user.last_verification_sent = timezone.now()
        user.save(update_fields=["last_verification_sent"])
        return Response({"detail": "Verification email sent"})

    except User.DoesNotExist:
        return Response({"detail": "User not found"}, status=404)


# -------- Register endpoint --------
@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def register(request):
    ser = RegisterSerializer(data=request.data, context={"request": request})
    ser.is_valid(raise_exception=True)
    user = ser.save()
    user.is_verified = False
    user.save(update_fields=["is_verified"])

    # Send verification email
    send_verification_email(user)

    refresh = RefreshToken.for_user(user)
    return Response({
        "user": UserSerializer(user).data,
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "email_verified": user.is_verified,
        "message": "Please verify your email before using the account. Verification link sent."
    })

@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def google_oauth(request):
    token = request.data.get("id_token")
    client_id = request.data.get("client_id")
    if not token or not client_id:
        return Response({"detail":"id_token and client_id required"}, status=400)

    try:
        info = google_id_token.verify_oauth2_token(
            token, google_requests.Request(), client_id
        )
        email = info["email"]
        gid = info["sub"]
        first_name = info.get("given_name", "")
        last_name = info.get("family_name", "")
        profile_photo = info.get("picture", "")
    

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": email.split("@")[0],
                "google_id": gid,
                "first_name": first_name,
                "last_name": last_name,
                "photo": profile_photo,
                "preferred_currency": Currency.objects.get(code="USD"),
                "is_verified": False,  # always start as unverified
            }
        )

        if not user.google_id:
            user.google_id = gid
            user.save(update_fields=["google_id"])

        # Haddii cusub yahay ama aan la xaqiijin, u dir fariin xaqiijin ah
        if created or not user.is_verified:
            send_verification_email(user)
            # Ku celi jawaab haddii isticmaalaha aan la xaqiijin
            return Response({
                "detail": "Please verify your email before using the account.",
                "email_verified": False,
            }, status=status.HTTP_403_FORBIDDEN)

        # Haddi isticmaalaha la xaqiijiyay, u soo dir tokens-ka
        refresh = RefreshToken.for_user(user)
        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSerializer(user).data,
            "email_verified": user.is_verified,
        })

    except Exception as e:
        return Response({"detail": str(e)}, status=400)

# -------- Verify email endpoint --------
@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def verify_email(request):
    token = request.data.get("token")
    if not token:
        return Response({"error": "Token is required"}, status=400)

    try:
        user_id = signer.unsign(token, max_age=EMAIL_TOKEN_MAX_AGE)
        user = User.objects.get(id=user_id)
        user.is_verified = True
        user.save(update_fields=["is_verified"])
        return Response({"verified": True, "message": "Email verified successfully"})
    except SignatureExpired:
        return Response({"error": "Token expired"}, status=400)
    except (BadSignature, User.DoesNotExist):
        return Response({"error": "Invalid token"}, status=400)


# -------- Logout endpoint --------
@api_view(["POST"])
def logout(request):
    try:
        RefreshToken(request.data.get("refresh")).blacklist()
    except Exception:
        pass
    return Response(status=204)

# -------- User profile endpoints -------- me endpoints
@api_view(["GET","PUT","PATCH","DELETE"])
def me(request):
    user = request.user
    if request.method == "GET":
        return Response(UserSerializer(user).data)
    if request.method in ["PUT","PATCH"]:
        ser = UserSerializer(user, data=request.data, partial=(request.method=="PATCH"))
        ser.is_valid(raise_exception=True); ser.save()
        return Response(ser.data)
    if request.method == "DELETE":
        user.is_active = False
        user.save(update_fields=["is_active"])
        return Response(status=204)

# -------- Reset password --------

@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def reset_password(request):
    email = request.data.get("email")
    if not email:
        return Response({"error": "Email is required"}, status=400)

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=404)

    # Generate token
    token = token_generator.make_token(user)
    reset_link = f"{FRONTEND_URL}/reset-password-confirm?uid={user.id}&token={token}"

    # Console email (tijaabo free)
    send_mail(
        subject="Reset your password",
        message=f"Click this link to reset your password: {reset_link}",
        from_email=None,  # uses DEFAULT_FROM_EMAIL
        recipient_list=[email],
        fail_silently=False,
    )

    return Response({"status": "email_sent"})

# -------- Reset password confirm --------
@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def reset_password_confirm(request):
    uid = request.data.get("uid")
    token = request.data.get("token")
    new_password = request.data.get("password")

    if not uid or not token or not new_password:
        return Response({"error": "uid, token, and password are required"}, status=400)

    try:
        user = User.objects.get(id=uid)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=404)

    if not token_generator.check_token(user, token):
        return Response({"error": "Invalid or expired token"}, status=400)

    user.set_password(new_password)
    user.save()
    return Response({"status": "password_changed"})


# -------- change_password -------- 
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def change_password(request):
    user = request.user
    current_password = request.data.get("current_password")
    new_password = request.data.get("new_password")

    if not current_password or not new_password:
        return Response({"error": "Both current and new passwords are required"}, status=400)

    if not user.check_password(current_password):
        return Response({"error": "Current password is incorrect"}, status=400)

    user.set_password(new_password)
    user.save()
    return Response({"status": "password_changed"})

# -------- Base class for owned objects with soft delete --------
class OwnedModelViewSet(viewsets.ModelViewSet):
    permission_classes = [IsOwner]
    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(user=self.request.user, is_deleted=False) if hasattr(self.queryset.model, "is_deleted") else qs.filter(user=self.request.user)
    @action(detail=False, methods=["get"])
    def archived(self, request):
        qs = self.queryset.filter(user=request.user, is_deleted=True)
        page = self.paginate_queryset(qs)
        ser = self.get_serializer(page, many=True) if page is not None else self.get_serializer(qs, many=True)
        return self.get_paginated_response(ser.data) if page is not None else Response(ser.data)
    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        obj = self.get_object()
        obj.is_deleted = False
        obj.save(update_fields=["is_deleted","updated_at"])
        return Response(self.get_serializer(obj).data)

# -------- Currencies --------
class CurrencyViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Currency.objects.filter(is_active=True).order_by("code")  # ✅ Warning fix
    serializer_class = CurrencySerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "code"

# -------- Categories --------   CRUD categories oo leh OwnedModelViewSet
class CategoryViewSet(OwnedModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    filterset_fields = ["parent"]

# -------- Accounts --------  
class AccountViewSet(viewsets.ModelViewSet):
    serializer_class = AccountSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["type", "is_active"]        # Filtering
    search_fields = ["name"]                        # Search by name
    ordering_fields = ["balance", "name", "created_at"]  # Ordering

    def get_queryset(self):
        # Only show the user's own accounts that are not deleted
        return Account.objects.filter(user=self.request.user, is_deleted=False)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        account = self.get_object()
        account.is_active = False
        account.save(update_fields=["is_active"])
        return Response({"status": "Account deactivated"})
    

# -------- Transactions --------  CRUD transactions
class TransactionViewSet(viewsets.ModelViewSet):
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering_fields = ["transaction_date", "amount"]
    ordering = ["-transaction_date"]
    search_fields = ["description"]

    def get_queryset(self):
        return Transaction.objects.filter(
            user=self.request.user, is_deleted=False
        )

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save(update_fields=["is_deleted"])

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        try:
            transaction = Transaction.objects.get(pk=pk, user=request.user, is_deleted=True)
            transaction.is_deleted = False
            transaction.save(update_fields=["is_deleted"])
            return Response({"detail": "Transaction restored successfully ✅"})
        except Transaction.DoesNotExist:
            return Response({"detail": "Transaction not found ❌"}, status=status.HTTP_404_NOT_FOUND)
    def get_queryset(self):
        show_deleted = self.request.query_params.get('deleted', 'false').lower() == 'true'
        if show_deleted:
            return Transaction.objects.filter(user=self.request.user, is_deleted=True)
        return Transaction.objects.filter(user=self.request.user, is_deleted=False)



# Splits under transaction  -------- Splits transactions
class TransactionSplitViewSet(viewsets.ModelViewSet):
    serializer_class = TransactionSplitSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Filter splits for the logged-in user & specific transaction
        transaction_id = self.kwargs.get("transaction_pk")
        return TransactionSplit.objects.filter(
            transaction__id=transaction_id,
            transaction__user=self.request.user
        )

    def perform_create(self, serializer):
        # Get transaction from URL
        transaction_id = self.kwargs.get("transaction_pk")
        transaction = get_object_or_404(Transaction, id=transaction_id, user=self.request.user)

        # Save split linked to this transaction
        serializer.save(transaction=transaction)

# Attachments  --------  Upload attachments to transactions
class AttachmentViewSet(viewsets.ModelViewSet):
    queryset = Attachment.objects.all()
    serializer_class = AttachmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # User-ku kaliya arki karo attachments-ka transactions-kiisa
        return Attachment.objects.filter(transaction__user=self.request.user)
    
    def perform_create(self, serializer):
        transaction = serializer.validated_data["transaction"]
        if transaction.user != self.request.user:
            raise PermissionError("You cannot add attachments to someone else's transaction.")
        serializer.save()


# -------- Manually trigger recurring task (for testing) --------
@api_view(["POST"])
def run_recurring_task(request):
    generate_due_recurring_transactions_task()
    return Response({"detail": "Recurring task executed manually."})


# -------- Recurring Bills --------  CRUD + generate transaction from bill
class RecurringBillViewSet(viewsets.ModelViewSet):
    serializer_class = RecurringBillSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return RecurringBill.objects.filter(user=self.request.user)

    def get_serializer_context(self):
        return {"request": self.request}  # <--


    # Optional: Haddii aad rabto, perform_create waa redundancy halkan
    # def perform_create(self, serializer):
    #     serializer.save(user=self.request.user)

    # ---- Custom Endpoints ----
    @action(detail=True, methods=["post"])
    def pay_bill(self, request, pk=None):
        bill = self.get_object()

        if bill.is_paid:
            return Response({"detail": "Bill already paid"}, status=status.HTTP_400_BAD_REQUEST)

        # 1️⃣ Check if account is empty first
        if bill.account.balance <= 0:
            return Response(
                {"detail": "Account-kaagu waa faaruq yahay. Fadlan lacag ku shubo si aad biilka u bixiso."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2️⃣ Check if balance is enough for the bill
        if bill.account.balance < bill.amount:
            return Response(
                {"detail": "Lacagta account-ka kuma filna bixinta biilka."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with db_transaction.atomic():
                # Deduct from account
                bill.account.balance -= Decimal(bill.amount)
                bill.account.save(update_fields=["balance"])

                # Mark bill as paid
                bill.is_paid = True
                bill.last_generated_date = now().date()
                bill.save(update_fields=["is_paid", "last_generated_date"])

                # Create transaction record
                Transaction.objects.create(
                    user=request.user,
                    account=bill.account,
                    category=bill.category,
                    type="Expense",
                    amount=bill.amount,
                    currency=bill.currency,
                    transaction_date=now().date(),
                    is_recurring_instance=True,
                    recurring_bill=bill,
                    description=f"Payment for {bill.name}"
                )

            return Response({"detail": f"{bill.name} has been paid!"}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


    @action(detail=False, methods=["get"])
    def total_monthly(self, request):
        today = now().date()
        qs = self.get_queryset().filter(
            next_due_date__month=today.month,
            next_due_date__year=today.year,
            is_active=True,
        )
        total = qs.aggregate(total=Sum("amount"))["total"] or 0
        return Response({"month": today.strftime("%B %Y"), "total_bills": total})

    @action(detail=False, methods=["get"])
    def overdue(self, request):
        today = now().date()
        qs = self.get_queryset().filter(next_due_date__lt=today, is_active=True, is_paid=False)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def upcoming(self, request):
        today = now().date()
        qs = self.get_queryset().filter(next_due_date__gte=today, is_active=True, is_paid=False)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

#------ budgets------CRUD +-----
class BudgetViewSet(viewsets.ModelViewSet):
    serializer_class = BudgetSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["category__name", "month", "year"]
    ordering_fields = ["month", "year", "amount", "category__name"]
    ordering = ["-year", "-month"]

    def get_queryset(self):
        return Budget.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    # -------- Rollover logic --------
    @action(detail=False, methods=["post"])
    def rollover(self, request):
        """
        Automatically rollover budgets with rollover_enabled = True
        to next month if remaining amount > 0.
        """
        user = request.user
        today = date.today()
        budgets = Budget.objects.filter(
            user=user,
            month=today.month,
            year=today.year,
            rollover_enabled=True
        )
        rolled_over = []
        for budget in budgets:
            spent = Transaction.objects.filter(
                user=user,
                category=budget.category,
                transaction_date__year=budget.year,
                transaction_date__month=budget.month,
                type="Expense"
            ).aggregate(total=Sum("amount"))["total"] or 0

            remaining = budget.amount - spent
            if remaining > 0:
                # Create budget for next month
                next_month = budget.month + 1
                next_year = budget.year
                if next_month > 12:
                    next_month = 1
                    next_year += 1

                new_budget, created = Budget.objects.get_or_create(
                    user=user,
                    category=budget.category,
                    month=next_month,
                    year=next_year,
                    defaults={"amount": remaining, "currency": budget.currency, "rollover_enabled": True}
                )
                rolled_over.append({"category": budget.category.name, "remaining": remaining})
        return Response({"rolled_over": rolled_over})

    # -------- Budget summary --------
    
    @action(detail=False, methods=["get"])
    def summary(self, request):
        """
        Return budget summary for selected month/year:
        total_spent, total_remaining, complete_budgets
        """
        user = request.user

        # Haddii frontend uu soo diro filter month/year
        month = int(request.query_params.get("month") or date.today().month)
        year = int(request.query_params.get("year") or date.today().year)

        budgets = Budget.objects.filter(user=user, month=month, year=year)
        summary = []

        for budget in budgets:
            spent = (
                Transaction.objects.filter(
                    user=user,
                    category=budget.category,
                    transaction_date__year=budget.year,
                    transaction_date__month=budget.month,
                    type="Expense"  # ama TransactionType.EXPENSE haddii Enum la isticmaalayo
                )
                .aggregate(total=Sum("amount"))["total"] or 0
            )
            remaining = budget.amount - spent
            summary.append({
                "id": str(budget.id),
                "category_id": budget.category.id,
                "category_name": budget.category.name,
                "budget_amount": float(budget.amount),
                "total_spent": float(spent),
                "total_remaining": float(remaining),
                "currency": budget.currency.code,
                "rollover_enabled": budget.rollover_enabled,
                "is_complete": remaining <= 0,
                "month": budget.month,
                "year": budget.year,
            })

        return Response({
            "month": month,
            "year": year,
            "budgets": summary
        })

# -------- Notifications --------  Read-only notifications + mark as read.
class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # Users can only see their own notifications
        return Notification.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
            return NotificationUpdateSerializer
        return NotificationSerializer
    
    @action(detail=False, methods=['get'])
    def unread(self, request):
        """Get all unread notifications for the current user"""
        unread_notifications = self.get_queryset().filter(is_read=False)
        page = self.paginate_queryset(unread_notifications)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(unread_notifications, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def count_unread(self, request):
        """Count unread notifications for the current user"""
        count = self.get_queryset().filter(is_read=False).count()
        return Response({'unread_count': count})
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all notifications as read for the current user"""
        updated = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({'status': f'{updated} notifications marked as read'})
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark a specific notification as read"""
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response({'status': 'Notification marked as read'})
    
    @action(detail=True, methods=['post'])
    def mark_unread(self, request, pk=None):
        """Mark a specific notification as unread"""
        notification = self.get_object()
        notification.is_read = False
        notification.save()
        return Response({'status': 'Notification marked as unread'})
    @action(detail=False, methods=['get'], url_path='unread_count')
    
    def unread_count(self, request):
        count = self.get_queryset().filter(is_read=False).count()
        return Response({'unread_count': count})

    
    @action(detail=False, methods=['get'])
    def by_type(self, request):
        """Get notifications filtered by type"""
        notification_type = request.query_params.get('type', None)
        if notification_type:
            notifications = self.get_queryset().filter(type=notification_type)
        else:
            notifications = self.get_queryset()
            
        page = self.paginate_queryset(notifications)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(notifications, many=True)
        return Response(serializer.data)
    
# -------- Exchange Rates --------  aqris-only + get rate for given date.

class ExchangeRateViewSet(viewsets.ModelViewSet):
    queryset = ExchangeRate.objects.all()
    serializer_class = ExchangeRateSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by base currency
        base_currency = self.request.query_params.get('base_currency')
        if base_currency:
            queryset = queryset.filter(base_currency__code=base_currency)
        
        # Filter by target currency
        target_currency = self.request.query_params.get('target_currency')
        if target_currency:
            queryset = queryset.filter(target_currency__code=target_currency)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)
        
        return queryset
    
    @action(detail=False, methods=['post'])
    def fetch_latest(self, request):
        """Trigger manual fetch of latest exchange rates"""
        base_currency = request.data.get('base_currency', 'USD')
        target_currencies = request.data.get('target_currencies', ['SOS'])
        
        # Trigger async task
        fetch_exchange_rates.delay(base_currency, target_currencies)
        
        return Response({
            "status": "success",
            "message": "Exchange rate fetch initiated"
        }, status=status.HTTP_202_ACCEPTED)
    
    @action(detail=False, methods=['get'])
    def convert(self, request):
        """Convert amount from one currency to another"""
        amount = float(request.query_params.get('amount', 1))
        from_currency = request.query_params.get('from_currency')
        to_currency = request.query_params.get('to_currency')
        date = request.query_params.get('date')
        
        if not from_currency or not to_currency:
            return Response(
                {"error": "from_currency and to_currency are required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            if from_currency == to_currency:
                converted_amount = amount
            else:
                # Try to find direct rate
                rate_obj = ExchangeRate.objects.filter(
                    base_currency__code=from_currency,
                    target_currency__code=to_currency,
                    date=date if date else timezone.now().date()
                ).latest('date')
                
                converted_amount = amount * float(rate_obj.rate)
            
            return Response({
                "amount": amount,
                "from_currency": from_currency,
                "to_currency": to_currency,
                "converted_amount": converted_amount,
                "rate": float(rate_obj.rate) if from_currency != to_currency else 1.0,
                "date": rate_obj.date if from_currency != to_currency else timezone.now().date()
            })
            
        except ExchangeRate.DoesNotExist:
            return Response(
                {"error": f"No exchange rate found for {from_currency} to {to_currency}"},
                status=status.HTTP_404_NOT_FOUND
            )
# -------- Audit Logs --------  Read-only audit logs for the user
class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing audit logs.
    """
    queryset = AuditLog.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['table_name', 'record_id', 'action', 'user']
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return AuditLogDetailSerializer
        return AuditLogSerializer
    
    def get_queryset(self):
        # Users can only see their own audit logs
        return AuditLog.objects.filter(user=self.request.user)

