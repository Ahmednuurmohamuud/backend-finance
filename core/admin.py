# core/admin.py
from django.contrib import admin
from .models import *
admin.site.register([Currency, User, Category, Account, Transaction, TransactionSplit,
Attachment, Budget, RecurringBill, Notification, ExchangeRate, AuditLog])