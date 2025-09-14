# core/audit.py
from .models import AuditLog
from ipware import get_client_ip
def create_audit(request=None, **kwargs):
    """
    Helper function to create audit log entries
    """
    ip_address = None
    if request:
        client_ip, is_routable = get_client_ip(request)
        if client_ip:
            ip_address = client_ip
    
    # Ensure we have the required fields
    required_fields = ['user', 'table_name', 'record_id', 'action']
    for field in required_fields:
        if field not in kwargs:
            raise ValueError(f"Missing required field: {field}")
    
    # Create the audit log entry
    audit_data = {
        'user': kwargs.get('user'),
        'table_name': kwargs.get('table_name'),
        'record_id': kwargs.get('record_id'),
        'action': kwargs.get('action'),
        'old_data': kwargs.get('old_data'),
        'new_data': kwargs.get('new_data'),
        'ip_address': ip_address or kwargs.get('ip_address')
    }
    
    AuditLog.objects.create(**audit_data)

# def get_budget_total_spent(budget):
#     return (
#         Transaction.objects.filter(
#             user=budget.user,
#             category=budget.category,
#             type="Expense",
#             date__year=budget.year,
#             date__month=budget.month
#         ).aggregate(total=Sum("amount"))["total"] or 0
#     )
