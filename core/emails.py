import resend
from django.conf import settings
from django.core.signing import TimestampSigner
from django.utils import timezone

signer = TimestampSigner()



def send_verification_email(user):
    token = signer.sign(user.id)
    verification_link = f"{settings.FRONTEND_URL}/verify_email?token={token}"

    try:
        response = resend.Emails.send({
            "from": "Finance <info@personalfinanace.site>",
            "to": [user.email],
            "subject": "Verify your email",
            "html": f"""
                <p>Hello {user.username},</p>
                <p>Click this link to verify your email:</p>
                <a href="{verification_link}">{verification_link}</a>
                <p>This link will expire in 24 hours.</p>
            """,
        })
        print("Email sent:", response)
        return response
    except Exception as e:
        print("Failed to send verification email:", e)
        raise
