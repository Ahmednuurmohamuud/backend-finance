from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models.expressions import CombinedExpression
from django.contrib.auth import get_user_model

from .models import Transaction, Account, Category, Budget, RecurringBill
from .audit import create_audit

User = get_user_model()

# ---------------- Helper ----------------
def safe_balance(instance):
    """
    Safely get the balance from an instance (Account or Transaction.account)
    If balance is a CombinedExpression, refresh from DB before converting to float
    """
    if hasattr(instance, 'balance') and isinstance(instance.balance, CombinedExpression):
        # Get fresh instance from DB
        instance = type(instance).objects.get(pk=instance.pk)
    return float(instance.balance) if hasattr(instance, 'balance') else None

# ----------------- TRANSACTIONS -----------------
@receiver(post_save, sender=Transaction)
def audit_transaction(sender, instance, created, **kwargs):
    safe_balance(instance.account)
    action = "CREATE" if created else "UPDATE"
    create_audit(
        user=instance.user,
        table_name="transactions",
        record_id=instance.id,
        action=action,
        new_data={
            "amount": float(instance.amount),
            "type": instance.type,
            "account": str(instance.account.id),
            "target_account": str(instance.target_account.id) if instance.target_account else None,
            "category": str(instance.category.id) if instance.category else None,
            "description": instance.description,
            "transaction_date": str(instance.transaction_date),
        }
    )

@receiver(post_delete, sender=Transaction)
def audit_transaction_delete(sender, instance, **kwargs):
    safe_balance(instance.account)
    create_audit(
        user=instance.user,
        table_name="transactions",
        record_id=instance.id,
        action="DELETE",
        old_data={
            "amount": float(instance.amount),
            "type": instance.type,
            "account": str(instance.account.id),
            "target_account": str(instance.target_account.id) if instance.target_account else None,
            "category": str(instance.category.id) if instance.category else None,
            "description": instance.description,
            "transaction_date": str(instance.transaction_date),
        }
    )

# ----------------- ACCOUNTS -----------------
@receiver(post_save, sender=Account)
def audit_account(sender, instance, created, **kwargs):
    action = "CREATE" if created else "UPDATE"
    create_audit(
        user=instance.user,
        table_name="accounts",
        record_id=instance.id,
        action=action,
        new_data={
            "name": instance.name,
            "type": instance.type,
            "is_active": instance.is_active,
            "balance": float(instance.balance) if hasattr(instance, 'balance') else None,
        }
    )

@receiver(post_delete, sender=Account)
def audit_account_delete(sender, instance, **kwargs):
    create_audit(
        user=instance.user,
        table_name="accounts",
        record_id=instance.id,
        action="DELETE",
        old_data={
            "name": instance.name,
            "type": instance.type,
            "is_active": instance.is_active,
            "balance": float(instance.balance) if hasattr(instance, 'balance') else None,
        }
    )

# ----------------- CATEGORIES -----------------
@receiver(post_save, sender=Category)
def audit_category(sender, instance, created, **kwargs):
    action = "CREATE" if created else "UPDATE"
    create_audit(
        user=instance.user,
        table_name="categories",
        record_id=instance.id,
        action=action,
        new_data={
            "name": instance.name,
            "parent": str(instance.parent.id) if instance.parent else None,
        }
    )

@receiver(post_delete, sender=Category)
def audit_category_delete(sender, instance, **kwargs):
    create_audit(
        user=instance.user,
        table_name="categories",
        record_id=instance.id,
        action="DELETE",
        old_data={
            "name": instance.name,
            "parent": str(instance.parent.id) if instance.parent else None,
        }
    )

# ----------------- BUDGETS -----------------
@receiver(post_save, sender=Budget)
def audit_budget(sender, instance, created, **kwargs):
    action = "CREATE" if created else "UPDATE"
    create_audit(
        user=instance.user,
        table_name="budgets",
        record_id=instance.id,
        action=action,
        new_data={
            "category": str(instance.category.id),
            "month": instance.month,
            "year": instance.year,
            "amount": float(instance.amount),
            "rollover_enabled": instance.rollover_enabled,
        }
    )

@receiver(post_delete, sender=Budget)
def audit_budget_delete(sender, instance, **kwargs):
    create_audit(
        user=instance.user,
        table_name="budgets",
        record_id=instance.id,
        action="DELETE",
        old_data={
            "category": str(instance.category.id),
            "month": instance.month,
            "year": instance.year,
            "amount": float(instance.amount),
            "rollover_enabled": instance.rollover_enabled,
        }
    )




# ----------------- RECURRING BILLS -----------------
@receiver(post_save, sender=RecurringBill)
def audit_recurring_bill(sender, instance, created, **kwargs):
    action = "CREATE" if created else "UPDATE"
    create_audit(
        user=instance.user,
        table_name="recurring_bills",
        record_id=instance.id,
        action=action,
        new_data={
            "name": instance.name,
            "amount": float(instance.amount),
            "currency": instance.currency.code,
            "type": instance.type,
            "frequency": instance.frequency,
            "start_date": str(instance.start_date),
            "next_due_date": str(instance.next_due_date),
            "end_date": str(instance.end_date) if instance.end_date else None,
            "is_active": instance.is_active,
        }
    )

@receiver(post_delete, sender=RecurringBill)
def audit_recurring_bill_delete(sender, instance, **kwargs):
    create_audit(
        user=instance.user,
        table_name="recurring_bills",
        record_id=instance.id,
        action="DELETE",
        old_data={
            "name": instance.name,
            "amount": float(instance.amount),
            "currency": instance.currency.code,
            "type": instance.type,
            "frequency": instance.frequency,
            "start_date": str(instance.start_date),
            "next_due_date": str(instance.next_due_date),
            "end_date": str(instance.end_date) if instance.end_date else None,
            "is_active": instance.is_active,
        }
    )