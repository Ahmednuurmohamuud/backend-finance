# core/utils/notifications.py
from celery import shared_task
from django.utils import timezone
from django.contrib.auth import get_user_model
from ..models import Notification, NotificationType, Budget, RecurringBill, Transaction
from core.services.email_service import send_notification_email
from django.db import transaction as dbtx 
from datetime import timedelta, date
from dateutil.relativedelta import relativedelta

User = get_user_model()

def create_budget_notification(user, subject, message, related_id=None, notification_type=NotificationType.BUDGET):
    """Create in-app and email notification for budget alerts."""
    notification = Notification.objects.create(
        user=user,
        type=notification_type,
        message=message,
        related_id=related_id
    )
    print(f"✅ Budget notification created: {notification.message}")
    # Send email
    send_notification_email(
        user=user,
        subject=subject,
        message=message,
        notification_id=notification.id
    )
    return notification.id


@shared_task
def check_budget_notifications():
    """Check all budgets and send notifications if needed"""
    print("🚀 Checking budget notifications...")
    try:
        today = timezone.now().date()
        
        for budget in Budget.objects.all():
            # Check if notification was already sent today using sent_at field
            notification_exists = Notification.objects.filter(
                user=budget.user,
                type=NotificationType.BUDGET,
                related_id=budget.id,
                sent_at__date=today  # ← Use sent_at instead of created_at
            ).exists()
            
            # Use check_budget_alerts() instead of is_over_budget()
            if not notification_exists:
                budget.check_budget_alerts()  # This handles the notification logic
                    
    except Exception as e:
        print(f"❌ Error in check_budget_notifications: {e}")


@shared_task
def create_sample_notification(user_id, message, notification_type="BUDGET"):
    """Tusaale function: Abuuritaanka notification-ka"""
    try:
        user = User.objects.get(id=user_id)
        
        notification = Notification.objects.create(
            user=user,
            type=notification_type,
            message=message,
            related_id=None
        )
        
        print(f"✅ Sample notification created for {user.username}")
        return notification.id
        
    except Exception as e:
        print(f"❌ Error creating notification: {e}")
        return None


def _next_due(freq: str, d: date) -> date:
    """Return the next due date given frequency string and current date d."""
    if d is None:
        return d
    f = (freq or "").strip().lower()
    if f in ("daily", "day"):
        return d + timedelta(days=1)
    if f in ("weekly", "week"):
        return d + timedelta(weeks=1)
    if f in ("bi-weekly", "biweekly", "2-week", "2 weeks"):
        return d + timedelta(weeks=2)
    if f in ("monthly", "month"):
        return d + relativedelta(months=1)
    if f in ("quarterly", "quarter"):
        return d + relativedelta(months=3)
    if f in ("annually", "yearly", "annual", "year"):
        return d + relativedelta(years=1)
    # fallback: no change
    return d


def create_recurring_bill_notification(user, bill, transaction):
    """
    Create notification for recurring bill transactions
    """
    try:
        message = f"Recurring bill '{bill.name}' of {bill.amount} {bill.currency.code} has been processed."
        
        notification = Notification.objects.create(
            user=user,
            type=NotificationType.RECURRING_BILL,
            message=message,
            related_id=transaction.id
        )
        
        # Send email notification
        send_notification_email(
            user=user,
            subject=f"Recurring Bill Processed: {bill.name}",
            message=message,
            notification_id=notification.id
        )
        
        print(f"✅ Recurring bill notification created for {bill.name}")
        return notification.id
        
    except Exception as e:
        print(f"❌ Error creating recurring bill notification: {e}")
        return None


@shared_task
def generate_due_recurring_transactions_task():
    """Find due recurring bills and generate transactions."""
    today = timezone.now().date()
    print(f"🔍 Checking for due recurring bills on {today}...")
    bills = RecurringBill.objects.filter(
        is_active=True,
        is_deleted=False,
        next_due_date__lte=today
    ).select_related("user", "account", "category", "currency")

    if not bills.exists():
        print("✅ No due recurring bills found")
        return "No due bills"

    print(f"📋 Found {bills.count()} due recurring bill(s)")
    success = 0
    failed = 0
    for bill in bills:
        try:
            res = generate_single_recurring_tx(bill.id)
            if res:
                success += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            print(f"💥 Error processing bill {bill.id} ({bill.name}): {e}")

    return f"Generated {success} transactions, {failed} failed"


def generate_single_recurring_tx(bill_id):
    """Create a single transaction for a due recurring bill and notify the user."""
    try:
        with dbtx.atomic():
            bill = RecurringBill.objects.select_for_update().get(pk=bill_id)

            # skip if inactive/deleted or no longer due
            if not bill.is_active or bill.is_deleted:
                print(f"⏭️ Bill {bill.name} inactive/deleted, skipping")
                return None

            today = timezone.now().date()
            if bill.next_due_date is None or bill.next_due_date > today:
                print(f"⏭️ Bill {bill.name} not due (next_due_date={bill.next_due_date}), skipping")
                return None

            original_due_date = bill.next_due_date

            tx = Transaction.objects.create(
                user=bill.user,
                account=bill.account,
                category=bill.category,
                type=bill.type,
                amount=bill.amount,
                currency=bill.currency,
                description=f"[Auto] {bill.name}",
                transaction_date=original_due_date,
                is_recurring_instance=True,
                recurring_bill=bill
            )

            # update bill dates
            bill.last_generated_date = original_due_date
            bill.next_due_date = _next_due(bill.frequency, original_due_date)
            bill.updated_at = timezone.now()
            bill.save(update_fields=["last_generated_date", "next_due_date", "updated_at"])

            # create notification + email via reusable helper
            create_recurring_bill_notification(bill.user, bill, tx)

            print(f"💰 Generated transaction {tx.id} for bill {bill.name}")
            return str(tx.id)

    except RecurringBill.DoesNotExist:
        print(f"❌ Bill with ID {bill_id} does not exist")
        return None
    except Exception as e:
        print(f"💥 Unexpected error processing bill {bill_id}: {e}")
        return None