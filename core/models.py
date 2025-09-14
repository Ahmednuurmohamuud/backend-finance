from django.db import models
import uuid
from django.db import transaction as db_transaction
from django.db.models import Sum, F
from django.db.models import Q
from rest_framework.permissions import IsAuthenticated

from datetime import date
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, F

# ----- Choices matching your ENUMs -----
class AccountType(models.TextChoices):
    BANK = "Bank", "Bank"
    SAVINGS = "Savings", "Savings"
    CREDIT_CARD = "Credit Card", "Credit Card"
    LOAN = "Loan", "Loan"
    INVESTMENT = "Investment", "Investment"
    CASH = "Cash", "Cash"
 
class TransactionType(models.TextChoices):
    INCOME = "Income", "Income"
    EXPENSE = "Expense", "Expense"
    TRANSFER = "Transfer", "Transfer"

class RecurringFrequency(models.TextChoices):
    DAILY="Daily"; WEEKLY="Weekly"; BI_WEEKLY="Bi-Weekly"
    MONTHLY="Monthly"; QUARTERLY="Quarterly"; ANNUALLY="Annually"

# ----- Notifications -----
class NotificationType(models.TextChoices):
    BUDGET = "Budget", "Budget Alert"
    BILL_DUE = "Bill Due", "Bill Due Reminder"
    WARNING = "Warning", "Warning Alert"
    INSIGHT = "Insight", "Financial Insight"

class AuditAction(models.TextChoices):
    CREATE = "CREATE", "Create"
    UPDATE = "UPDATE", "Update"
    DELETE = "DELETE", "Delete"

# ----- Soft delete manager -----
class SoftDeleteQuerySet(models.QuerySet):
    def alive(self): return self.filter(is_deleted=False)
    def dead(self): return self.filter(is_deleted=True)

class SoftDeleteModel(models.Model):
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    objects = SoftDeleteQuerySet.as_manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        self.is_deleted = True
        self.save(update_fields=["is_deleted","updated_at"])

# ----- Currencies -----
class Currency(models.Model):
    code = models.CharField(primary_key=True, max_length=3)
    name = models.CharField(max_length=255, unique=True)
    symbol = models.CharField(max_length=10)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

def __str__(self):
    return self.code


# ----- User -----
class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    preferred_currency = models.ForeignKey(Currency, to_field="code", on_delete=models.PROTECT)
    monthly_income_est = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    savings_goal = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    is_verified = models.BooleanField(default=False)
    google_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    photo = models.ImageField(upload_to="profile_photos/", blank=True, null=True)
    two_factor_enabled = models.BooleanField(default=False)
    # models.py
    last_verification_sent = models.DateTimeField(null=True, blank=True)

    REQUIRED_FIELDS = ["email", "preferred_currency"]

    def __str__(self):
        return self.username

# ----- OTP Codes -----
class OTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_valid(self, valid_minutes=30):
        return (
            not self.is_used and
            timezone.now() - self.created_at <= timezone.timedelta(minutes=valid_minutes)
        )

# ----- Categories -----
class Category(SoftDeleteModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE)

    class Meta:
        unique_together = (("user","name","parent","is_deleted"),)

    def _str_(self): return self.name

# ----- Accounts -----
class Account(SoftDeleteModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=AccountType.choices)
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    currency = models.ForeignKey(Currency, to_field="code", on_delete=models.PROTECT)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=["user","type"])]

    def __str__(self):
      return f"{self.name} ({self.type})"
    
# ----- Recurring Bills (declared before Transaction for FK) -----
class RecurringBill(SoftDeleteModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    category = models.ForeignKey("Category", null=True, blank=True, on_delete=models.SET_NULL)
    name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.ForeignKey(Currency, to_field="code", on_delete=models.PROTECT)
    type = models.CharField(max_length=10, choices=TransactionType.choices)
    frequency = models.CharField(max_length=12, choices=RecurringFrequency.choices)
    start_date = models.DateField()
    next_due_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    last_generated_date = models.DateField(null=True, blank=True)
    is_paid = models.BooleanField(default=False)  # New field 

    class Meta:
        indexes = [
            models.Index(fields=["user", "next_due_date", "is_active"]),
            models.Index(fields=["account"]),
        ]

    def __str__(self):
        return f"{self.name} - {self.amount} {self.currency}"

# ----- Transactions -----
class Transaction(SoftDeleteModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    account = models.ForeignKey(Account, related_name="transactions", on_delete=models.PROTECT)
    target_account = models.ForeignKey(Account, related_name="incoming_transfers", null=True, blank=True, on_delete=models.PROTECT)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL)
    type = models.CharField(max_length=10, choices=TransactionType.choices)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.ForeignKey(Currency, to_field="code", on_delete=models.PROTECT)
    converted_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    converted_currency = models.ForeignKey(Currency, to_field="code", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    description = models.TextField(blank=True, default="")
    transaction_date = models.DateField()
    is_recurring_instance = models.BooleanField(default=False)
    recurring_bill = models.ForeignKey(RecurringBill, null=True, blank=True, on_delete=models.SET_NULL)
    description_tsv = SearchVectorField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user","transaction_date","type"]),
            models.Index(fields=["account","transaction_date"]),
            models.Index(fields=["category"]),
            GinIndex(fields=["description_tsv"]),
        ]
        constraints = [
            models.CheckConstraint(
                name="transfer_requires_target",
                check=(
                    Q(type=TransactionType.TRANSFER, target_account__isnull=False) |
                    Q(type__in=[TransactionType.INCOME, TransactionType.EXPENSE], target_account__isnull=True)
                )
            )
        ]

    # ---------------- Custom validation ----------------
    def clean(self):
        if self.type == TransactionType.EXPENSE and self.account.type == AccountType.SAVINGS:
            raise ValidationError("Saving account cannot be used directly for expenses. Transfer required.")

        if self.type == TransactionType.TRANSFER and self.account.type == AccountType.SAVINGS:
            if self.target_account and self.target_account.type == AccountType.SAVINGS:
                raise ValidationError("Cannot transfer from one savings account to another savings account.")

        if self.currency != self.account.currency:
            raise ValidationError("Transaction currency must match the account currency.")

    # ---------------- Save method ----------------
    def save(self, *args, **kwargs):
        # Kaliya validate oo save transaction-ka, balance update ha dhicin halkan
        self.full_clean()
        super().save(*args, **kwargs)

    # ---------------- Soft-delete rollback ----------------
    def delete(self, using=None, keep_parents=False):
        with transaction.atomic():
            # Balance rollback hadda waxaa fiican in lagu sameeyo view ama serializer
            super().delete(using=using, keep_parents=keep_parents)

# ----- Transaction Splits -----
class TransactionSplit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="splits")
    category = models.ForeignKey(Category, on_delete=models.RESTRICT)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = (("transaction","category"),)

    def clean(self):
        existing_total = (
            TransactionSplit.objects
            .filter(transaction=self.transaction)
            .exclude(pk=self.pk)
            .aggregate(total=Sum("amount"))["total"] or 0
        )

        if existing_total + self.amount > self.transaction.amount:
            raise ValidationError(
                f"Total of splits ({existing_total + self.amount}) exceeds transaction amount ({self.transaction.amount})."
            )

    def save(self, *args, **kwargs):
        self.full_clean()

        is_new = self._state.adding

        with db_transaction.atomic():
            super().save(*args, **kwargs)

            # Update account balance only for new splits
            if is_new:
                account = self.transaction.account
                if self.transaction.type == TransactionType.INCOME:
                    account.balance = F("balance") + self.amount
                elif self.transaction.type == TransactionType.EXPENSE:
                    if account.balance < self.amount:
                        raise ValidationError("Insufficient funds for expense.")
                    account.balance = F("balance") - self.amount
                account.save(update_fields=["balance"])
                account.refresh_from_db(fields=["balance"])

# ----- Attachments -----
class Attachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="attachments")
    file_url = models.URLField(max_length=512)
    file_type = models.CharField(max_length=50, blank=True, default="")
    file_size = models.IntegerField(null=True, blank=True)
    uploaded_at = models.DateTimeField(default=timezone.now)

# ----- Budgets -----
class Budget(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    spent_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)  # Cusub
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    month = models.IntegerField()
    year = models.IntegerField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.ForeignKey(Currency, to_field="code", on_delete=models.PROTECT)
    rollover_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = (("user","category","month","year"),)
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["category"]),
            models.Index(fields=["user","year","month","category"]),
        ]


    @property
    def total_spent(self):
        # Wadar kharashka ku saabsan user, category, month & year
        total = Transaction.objects.filter(
            user=self.user,
            category=self.category,
            type='Expense',
            transaction_date__year=self.year,
            transaction_date__month=self.month
        ).aggregate(total=Sum('amount'))['total'] or 0
        return total

    @property
    def total_remaining(self):
        return self.amount - self.total_spent
    
    @property
    def spent_percentage(self):
        """Return the percentage of budget spent"""
        if self.amount == 0:
            return 0
        return (self.total_spent / self.amount) * 100
    
    def check_budget_alerts(self):
        """Check if budget alerts need to be sent"""
        from .utils.notifications import create_budget_notification
        from .models import NotificationType
        
        percentage = self.spent_percentage
        
        if percentage >= 90:
            create_budget_notification(
                self.user,
                f"Your {self.category.name} budget is {percentage:.0f}% spent",
                f"You've spent ${self.total_spent:.2f} of ${self.amount:.2f}. "
                f"Only ${self.total_remaining:.2f} remaining.",
                self.id,
                NotificationType.BUDGET
            )
            return True
        elif percentage >= 75:
            create_budget_notification(
                self.user,
                f"Your {self.category.name} budget is {percentage:.0f}% spent",
                f"You've spent ${self.total_spent:.2f} of ${self.amount:.2f}. "
                f"${self.total_remaining:.2f} remaining.",
                self.id,
                NotificationType.BUDGET
            )
            return True
        elif self.total_remaining < 0:
            create_budget_notification(
                self.user,
                f"Your {self.category.name} budget has been exceeded",
                f"You've exceeded your budget by ${abs(self.total_remaining):.2f}. "
                f"Total spent: ${self.total_spent:.2f} of ${self.amount:.2f}.",
                self.id,
                NotificationType.WARNING
            )
            return True
        
        return False

# ----- Notifications -----
class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    type = models.CharField(max_length=20, choices=NotificationType.choices)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    sent_at = models.DateTimeField(default=timezone.now)
    related_id = models.UUIDField(null=True, blank=True)
    email_sent = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['user', 'sent_at']),
        ]
    
    def __str__(self):
        return f"{self.type} for {self.user}: {self.message[:50]}..."

# ----- Exchange rates -----
class ExchangeRate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    base_currency = models.ForeignKey(Currency, to_field="code", on_delete=models.PROTECT, related_name="base_rates")
    target_currency = models.ForeignKey(Currency, to_field="code", on_delete=models.PROTECT, related_name="target_rates")
    rate = models.DecimalField(max_digits=15, decimal_places=6)
    date = models.DateField()
    source = models.CharField(max_length=50, default="ExchangeRate.host")
    last_fetched_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = (("base_currency","target_currency","date"),)
        indexes = [
            models.Index(fields=["base_currency","target_currency"]),
            models.Index(fields=["date"]),
        ]

        def __str__(self):
                return f"{self.base_currency.code}/{self.target_currency.code}: {self.rate} on {self.date}"

# ----- Audit Logs -----
class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    table_name = models.CharField(max_length=100)
    record_id = models.UUIDField()
    action = models.CharField(max_length=50, choices=AuditAction.choices)
    old_data = models.JSONField(null=True, blank=True)
    new_data = models.JSONField(null=True, blank=True)
    changed_at = models.DateTimeField(default=timezone.now)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-changed_at']
        indexes = [
            models.Index(fields=['table_name', 'record_id']),
            models.Index(fields=['user', 'changed_at']),
        ]
    
    def __str__(self):
        return f"{self.action} on {self.table_name} by {self.user} at {self.changed_at}"