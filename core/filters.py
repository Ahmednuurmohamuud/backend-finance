# core/filters.py
import django_filters as df
import django_filters
from .models import Transaction, Budget, AuditLog, RecurringBill

class TransactionFilter(df.FilterSet):
    min_date = df.DateFilter(field_name="transaction_date", lookup_expr="gte")
    max_date = df.DateFilter(field_name="transaction_date", lookup_expr="lte")
    type = df.CharFilter(field_name="type")
    account = df.UUIDFilter(field_name="account_id")
    category = df.UUIDFilter(field_name="category_id")

    class Meta:
        model = Transaction
        fields = ["type","account","category","min_date","max_date"]

class BudgetFilter(df.FilterSet):
    class Meta:
        model = Budget
        fields = ["month","year","category"]

class AuditLogFilter(django_filters.FilterSet):
    table_name = django_filters.CharFilter(field_name="table_name", lookup_expr="iexact")  # exact match ignore case

    class Meta:
        model = AuditLog
        fields = ["table_name", "action"]
class RecurringBillFilter(df.FilterSet):
    class Meta:
        model = RecurringBill
        fields = ["is_active"]