from django.core.mail import EmailMultiAlternatives
import random
from django.utils import timezone
from .models import OTP
from django.conf import settings

def send_verification_email(user):
    # Generate 6-digit OTP
      # Generate 6-digit OTP
    code = f"{random.randint(100000, 999999)}"
    OTP.objects.create(user=user, code=code)

    subject = "Your verification code"
    html_content = f"""
        <p>Hello {user.username},</p>
        <p>Your verification code is:</p>
        <h2>{code}</h2>
        <p>This code will expire in 30 minutes.</p>
    """
    text_content = f"Hello {user.username},\nYour verification code is: {code}\nThis code will expire in 30 minutes."

    try:
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,  # ✅ Halkan waa muhiim
            to=[user.email],
        )
        email.attach_alternative(html_content, "text/html")
        email.send()
        print(f"OTP email sent to {user.email}")
        return True
    except Exception as e:
        print(f"Failed to send OTP email via SMTP: {e}")
        raise

