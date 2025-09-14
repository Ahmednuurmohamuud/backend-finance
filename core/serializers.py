# core/serializers.py
from rest_framework import serializers
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from .models import *
from decimal import Decimal

# ---- User & Auth ----
class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "password",
            "preferred_currency",
            "monthly_income_est",
            "savings_goal",
        )

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate_email(self, value):
        # hubi haddii email horay u jiray
        user_qs = User.objects.filter(email=value)
        if user_qs.exists():
            user = user_qs.first()
            if user.is_verified:
                raise serializers.ValidationError("Email already exists")
            else:
                raise serializers.ValidationError(
                    "Email already registered but not verified. Please check your inbox."
                )
        return value

    def create(self, validated_data):
        pwd = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(pwd)
        user.is_verified = False   # 🚨 account cusub waligiis waa unverified
        user.save()

        # 🚀 halkan ku dir email verification
        # tusaale: send_verification_email(user)
        return user

# ---- User Serializer ----
class UserSerializer(serializers.ModelSerializer):
    photo = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "first_name", "last_name", "phone",
            "preferred_currency", "monthly_income_est", "savings_goal",
            "photo", "is_active", "is_verified", "date_joined", "two_factor_enabled","last_verification_sent"
        )
        read_only_fields = ("is_active", "is_verified", "date_joined")

    def get_photo(self, obj):
        if obj.photo:
            request = self.context.get('request')
            if request:
                # Returns full URL e.g., http://localhost:8000/media/profile_photos/...
                return request.build_absolute_uri(obj.photo.url)
        return None


# ---- OTP ----
class OTPSerializer(serializers.ModelSerializer):
    class Meta:
        model = OTP
        fields = ["id", "user", "code", "is_used", "created_at"]


# ---- Currency ----
class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = '__all__'  

# ---- Category ----
class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id","name","parent","created_at","updated_at","is_deleted")
    def create(self, data):
        data["user"] = self.context["request"].user
        return super().create(data)

# ---- Account ----
class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ("id","name","type","balance","currency","is_active","is_deleted","created_at","updated_at")
    def create(self, data):
        data["user"] = self.context["request"].user
        return super().create(data)

# ---- Transaction Split ----
class TransactionSplitSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionSplit
        fields = "__all__"
        read_only_fields = ["id", "created_at", "transaction"]

# ---- Transaction ----
class TransactionSerializer(serializers.ModelSerializer):
    account = serializers.PrimaryKeyRelatedField(queryset=Account.objects.all())
    target_account = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.all(), required=False, allow_null=True
    )
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        required=False,
        allow_null=True
    )
    currency = serializers.SlugRelatedField(slug_field="code", read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id",
            "user",
            "account",
            "target_account",
            "category",
            "type",
            "amount",
            "currency",
            "description",
            "transaction_date",
        ]
        read_only_fields = ["id", "user", "currency"]

    def create(self, validated_data):
        user = self.context["request"].user
        validated_data["user"] = user

        account = validated_data["account"]
        target_account = validated_data.get("target_account")
        amount = Decimal(validated_data["amount"])
        tx_type = validated_data["type"]

        # ✅ currency si toos ah uga qaado account
        validated_data["currency"] = account.currency

        with transaction.atomic():
            # Haddii balance = 0 ama ka yar, kaliya INCOME waa la ogol yahay
            if account.balance <= 0 and tx_type != TransactionType.INCOME:
                raise serializers.ValidationError(
                    "Account-kaagu waa faaruq yahay. Kaliya INCOME ayaa la ogol yahay."
                )

            if tx_type == TransactionType.INCOME:
                account.balance += amount
                account.save(update_fields=["balance"])

            elif tx_type == TransactionType.EXPENSE:
                if account.balance < amount:
                    raise serializers.ValidationError("Insufficient funds for expense.")
                account.balance -= amount
                account.save(update_fields=["balance"])

            elif tx_type == TransactionType.TRANSFER:
                if not target_account:
                    raise serializers.ValidationError("Target account waa in la doortaa.")
                if account.balance < amount:
                    raise serializers.ValidationError("Insufficient funds for transfer.")
                account.balance -= amount
                account.save(update_fields=["balance"])
                target_account.balance += amount
                target_account.save(update_fields=["balance"])

            transaction_obj = Transaction.objects.create(**validated_data)

        return transaction_obj

# ---- Attachment ----
class AttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attachment
        fields = "__all__"
        read_only_fields = ["id", "uploaded_at"]

# ---- RecurringBill ----
class RecurringBillSerializer(serializers.ModelSerializer):
    account_name = serializers.SerializerMethodField()
    category_name = serializers.SerializerMethodField()
    account = serializers.PrimaryKeyRelatedField(queryset=Account.objects.all())
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all(), required=False, allow_null=True)

    class Meta:
        model = RecurringBill
        fields = "__all__"
        extra_kwargs = {"user": {"read_only": True}}

    def get_account_name(self, obj):
        return obj.account.name if obj.account else None

    def get_category_name(self, obj):
        return obj.category.name if obj.category else None

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().update(instance, validated_data)

# ---- Budget ----
class BudgetSerializer(serializers.ModelSerializer):
    total_spent = serializers.SerializerMethodField()
    total_remaining = serializers.SerializerMethodField()

    class Meta:
        model = Budget
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "user", "total_spent", "total_remaining"]

    def get_total_spent(self, obj):
        # Total spent in this category for the month
        transactions = Transaction.objects.filter(
            user=obj.user,
            category=obj.category,
            transaction_date__year=obj.year,
            transaction_date__month=obj.month,
            type="Expense"
        )
        return transactions.aggregate(total=Sum("amount"))["total"] or 0

    def get_total_remaining(self, obj):
        spent = self.get_total_spent(obj)
        remaining = obj.amount - spent
        if remaining < 0:
            remaining = 0
        return remaining

    def validate(self, data):
        user = self.context["request"].user
        category = data.get("category")
        month = data.get("month")
        year = data.get("year")

        budget_id = self.instance.id if self.instance else None

        if Budget.objects.filter(
            user=user,
            category=category,
            month=month,
            year=year
        ).exclude(id=budget_id).exists():
            raise serializers.ValidationError(
                "Budget for this category and month already exists."
            )
        return data

# ---- Notification ----
class NotificationSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source='get_type_display', read_only=True)
    formatted_date = serializers.SerializerMethodField()
    
    class Meta:
        model = Notification
        fields = ['id', 'type', 'type_display', 'message', 'is_read', 
                 'sent_at', 'formatted_date', 'related_id', 'email_sent']
        read_only_fields = ['id', 'sent_at', 'email_sent']

    def get_formatted_date(self, obj):
        from django.utils.timesince import timesince
        return timesince(obj.sent_at) + " ago"

class NotificationUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['is_read']

# ---- ExchangeRate ----
class ExchangeRateSerializer(serializers.ModelSerializer):
    base_currency_code = serializers.CharField(source='base_currency.code', read_only=True)
    target_currency_code = serializers.CharField(source='target_currency.code', read_only=True)
    base_currency_name = serializers.CharField(source='base_currency.name', read_only=True)
    target_currency_name = serializers.CharField(source='target_currency.name', read_only=True)
    
    class Meta:
        model = ExchangeRate
        fields = "__all__"


# ---- AuditLog ----
class AuditLogSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField()
    
    class Meta:
        model = AuditLog
        fields = ["id", "user", "table_name", "record_id", "old_data", "new_data", "action", "changed_at"]

class AuditLogDetailSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField()
    
    class Meta:
        model = AuditLog
        fields = ["id", "user", "table_name", "record_id", "old_data", "new_data", "action", "changed_at", "ip_address"]

        
