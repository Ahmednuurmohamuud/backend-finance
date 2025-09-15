# core/services/email_service.py
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
FRONTEND_URL = "https://finance-frontend-production-a0b9.up.railway.app"


def send_notification_email(user, subject, message, notification_id=None, email_type="general", extra_data=None):
    """Send an email notification to a user with improved template support"""
    try:
        # Prepare base context
        context = {
            'subject': subject,
            'message': message,
            'action_url': f"https://finance-frontend-production-a0b9.up.railway.app/notifications/{notification_id}" if notification_id else f"{settings.FRONTEND_URL}/notifications",
            'unsubscribe_url': f"{FRONTEND_URL}/settings/notifications",
            'settings_url': f"{FRONTEND_URL}/settings",
            'support_url': f"{FRONTEND_URL}/support",
            'user_name': user.get_full_name() or user.username,
        }
        
        # Add extra data if provided
        if extra_data:
            context.update(extra_data)
        
        # Choose template based on email type
        template_name = 'emails/notification.html'
        if email_type == "budget":
            template_name = 'emails/budget_notification.html'
        elif email_type == "transaction":
            template_name = 'emails/transaction_notification.html'
        elif email_type == "bill":
            template_name = 'emails/recurring_notification.html'
        
        # Render email content
        html_content = render_to_string(template_name, context)
        text_content = strip_tags(html_content)
        
        # Create and send email
        email = EmailMultiAlternatives(
            subject=f"Finance App: {subject}",
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email]
        )
        email.attach_alternative(html_content, "text/html")
        
        result = email.send()
        print(f"📧 Email sent to {user.email}. Result: {result}")
        
        # Update notification if ID provided
        if notification_id:
            from ..models import Notification
            try:
                notification = Notification.objects.get(id=notification_id)
                notification.email_sent = True
                notification.sent_at = timezone.now()
                notification.save(update_fields=["email_sent", "sent_at"])
            except Notification.DoesNotExist:
                print(f"⚠️ Notification with ID {notification_id} not found")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to send email to {user.email}: {e}")
        # Log the error for debugging
        import traceback
        print(f"🔍 Error details: {traceback.format_exc()}")
        return False

# def send_test_email(user_email):
#     """Test function: Send a test email"""
#     try:
#         email = EmailMultiAlternatives(
#             subject="Test Email from Finance App",
#             body="This is a test email to verify the email service is working correctly.",
#             from_email=settings.DEFAULT_FROM_EMAIL,
#             to=[user_email]
#         )
        
#         result = email.send()
#         print(f"📧 Test email sent to {user_email}. Result: {result}")
#         return True
        
#     except Exception as e:
#         print(f"❌ Failed to send test email: {e}")
#         return False