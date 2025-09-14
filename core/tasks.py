# core/tasks.py - Automation and background jobs
from celery import shared_task
from django.utils import timezone
from datetime import timedelta, date
from django.conf import settings
from django.db import transaction as dbtx
import requests
from django.contrib.auth import get_user_model

# Import models at the top to avoid circular imports
from .models import (
    RecurringBill, ExchangeRate, Currency, 
    Budget, Notification, NotificationType,
    Transaction
)

# Import utility functions
from core.utils.notifications import (
    check_budget_notifications, 
    create_sample_notification, 
    create_budget_notification
)

# Import email service
from core.services.email_service import send_notification_email

User = get_user_model()

# Helper function for next due date calculation (moved to top)
def _next_due(freq: str, d: date) -> date:
    """Calculate next due date based on frequency"""
    from dateutil.relativedelta import relativedelta
    
    frequency_map = {
        "Daily": d + timedelta(days=1),
        "Weekly": d + timedelta(weeks=1),
        "Bi-Weekly": d + timedelta(weeks=2),
        "Monthly": d + relativedelta(months=1),
        "Quarterly": d + relativedelta(months=3),
        "Annually": d + relativedelta(years=1),
    }
    
    return frequency_map.get(freq, d)


@shared_task
def run_daily_budget_warnings():
    """Daily budget warning task - runs only once per day"""
    today = date.today()
    print(f"📊 Running daily budget warnings for {today}...")
    
    for budget in Budget.objects.all():
        # Check if notification was already sent today
        notification_exists = Notification.objects.filter(
            user=budget.user,
            type=NotificationType.BUDGET,
            related_id=budget.id,
            sent_at__date=today
        ).exists()
        
        if not notification_exists:
            # Let the budget model handle the alert logic
            budget.check_budget_alerts()


@shared_task
def send_email_notification_task(user_id, subject, message, notification_id=None, email_type="general", extra_data=None):
    """Task: Send email notification with improved parameters"""
    try:
        user = User.objects.get(id=user_id)
        
        result = send_notification_email(
            user=user,
            subject=subject,
            message=message,
            notification_id=notification_id,
            email_type=email_type,
            extra_data=extra_data
        )
        
        return f"Email sent: {result}"
        
    except Exception as e:
        print(f"❌ Error sending email: {str(e)}")
        return f"Error sending email: {str(e)}"


@shared_task
def test_notification_task():
    """Task: Test notification system"""
    print("✅ Testing notification task...")
    return "Notification task working correctly"


@shared_task
def generate_due_recurring_transactions_task():
    """Generate all due recurring transactions efficiently"""
    print(f"🔍 Checking for due recurring bills on {timezone.now().date()}...")
    
    # Get only bills that are due today or earlier
    bills = RecurringBill.objects.filter(
        is_active=True, 
        is_deleted=False, 
        next_due_date__lte=timezone.now().date()
    ).select_related('user', 'account', 'category', 'currency')
    
    if not bills.exists():
        print("✅ No due recurring bills found")
        return "No due bills"
    
    print(f"📋 Found {bills.count()} due recurring bill(s)")
    
    successful_generations = 0
    failed_generations = 0
    
    for bill in bills:
        try:
            result = generate_single_recurring_tx(bill.id)
            if result:
                successful_generations += 1
                print(f"✅ Generated transaction for bill: {bill.name}")
            else:
                failed_generations += 1
                print(f"❌ Failed to generate transaction for bill: {bill.name}")
        except Exception as e:
            failed_generations += 1
            print(f"💥 Error processing bill {bill.name}: {str(e)}")
    
    return f"Generated {successful_generations} transactions, {failed_generations} failed"


def generate_single_recurring_tx(bill_id):
    """Generate a single recurring transaction with improved error handling"""
    try:
        with dbtx.atomic():
            # Lock the bill for processing
            bill = RecurringBill.objects.select_for_update().get(pk=bill_id)
            
            # Double-check conditions
            if not bill.is_active or bill.is_deleted:
                print(f"⏭️ Bill {bill.name} is inactive or deleted, skipping")
                return None
            
            # Verify the bill is still due (in case of concurrent processing)
            if bill.next_due_date > timezone.now().date():
                print(f"⏭️ Bill {bill.name} is no longer due, skipping")
                return None
            
            # Create the transaction
            tx = Transaction.objects.create(
                user=bill.user, 
                account=bill.account, 
                category=bill.category, 
                type=bill.type,
                amount=bill.amount, 
                currency=bill.currency, 
                description=f"[Auto] {bill.name}",
                transaction_date=bill.next_due_date, 
                is_recurring_instance=True, 
                recurring_bill=bill
            )
            
            # Update bill dates
            original_due_date = bill.next_due_date
            bill.last_generated_date = bill.next_due_date
            bill.next_due_date = _next_due(bill.frequency, bill.next_due_date)
            bill.updated_at = timezone.now()
            bill.save(update_fields=["last_generated_date", "next_due_date", "updated_at"])
            
            # Notify user with more detailed message
            notification_message = (
                f"Lacag socda ayaa otomaatig loo abuuray: {bill.name}. "
                f"Qadarta: ${bill.amount} {bill.currency.code}. "
                f"Taariikhda: {original_due_date}"
            )
            
            notification = Notification.objects.create(
                user=bill.user,
                type=NotificationType.BILL_DUE,
                message=notification_message,
                related_id=tx.id
            )
            
            # Send email notification as a separate task
            send_email_notification_task.delay(
                user_id=bill.user.id,
                subject=f"Lacag socda oo la abuuray: {bill.name}",
                message=notification_message,
                notification_id=notification.id,
                email_type="recurring"
            )
            
            print(f"💰 Generated transaction {tx.id} for bill {bill.name}")
            return str(tx.id)
            
    except RecurringBill.DoesNotExist:
        print(f"❌ Bill with ID {bill_id} does not exist")
        return None
    except Exception as e:
        print(f"💥 Unexpected error processing bill {bill_id}: {str(e)}")
        return None



# --- USD/SOS Exchange Rate from Fixer.io ---
@shared_task
def fetch_usd_sos_fixer_rate():
    """Fetch USD to SOS exchange rate from Fixer.io and update ExchangeRate table."""
    FIXER_API_KEY = getattr(settings, "FIXER_API_KEY", None)
    if not FIXER_API_KEY:
        return "No FIXER_API_KEY in settings"
    url = f"http://data.fixer.io/api/latest?access_key={FIXER_API_KEY}&base=USD&symbols=SOS"
    try:
        response = requests.get(url)
        data = response.json()
        if data.get("success") and "rates" in data and "SOS" in data["rates"]:
            rate_value = data["rates"]["SOS"]
            date_val = data.get("date")
            # Get or create currency objects
            base_currency_obj, _ = Currency.objects.get_or_create(
                code="USD", defaults={"name": "US Dollar", "symbol": "$"}
            )
            target_currency_obj, _ = Currency.objects.get_or_create(
                code="SOS", defaults={"name": "Somali Shilling", "symbol": "S"}
            )
            # Create or update exchange rate
            ExchangeRate.objects.update_or_create(
                base_currency=base_currency_obj,
                target_currency=target_currency_obj,
                date=date_val,
                defaults={
                    "rate": rate_value,
                    "last_fetched_at": timezone.now(),
                    "source": "Fixer.io"
                }
            )
            return f"USD/SOS rate updated: {rate_value}"
        else:
            return f"Failed to fetch rate: {data}"
    except Exception as e:
        return f"Error fetching USD/SOS from Fixer.io: {str(e)}"

# ---------- FETCH USD/SOS ----------
@shared_task
def fetch_exchange_rates(base_currency='USD', target_currencies=None):
    if target_currencies is None:
        target_currencies = ['SOS']
    
    try:
        # Using ExchangeRate.host API
        url = f"https://api.exchangerate.host/latest?base={base_currency}"
        response = requests.get(url)
        data = response.json()
        
        if data.get('success', False):
            rates = data['rates']
            date = data['date']
            
            for target_currency in target_currencies:
                if target_currency in rates:
                    rate_value = rates[target_currency]
                    
                    # Get or create currency objects
                    base_currency_obj, _ = Currency.objects.get_or_create(
                        code=base_currency,
                        defaults={'name': base_currency, 'symbol': base_currency}
                    )
                    
                    target_currency_obj, _ = Currency.objects.get_or_create(
                        code=target_currency,
                        defaults={'name': target_currency, 'symbol': target_currency}
                    )
                    
                    # Create or update exchange rate
                    exchange_rate, created = ExchangeRate.objects.update_or_create(
                        base_currency=base_currency_obj,
                        target_currency=target_currency_obj,
                        date=date,
                        defaults={
                            'rate': rate_value,
                            'last_fetched_at': timezone.now()
                        }
                    )
            
            return f"Successfully fetched rates for {base_currency} to {target_currencies}"
        
    except Exception as e:
        return f"Error fetching exchange rates: {str(e)}"