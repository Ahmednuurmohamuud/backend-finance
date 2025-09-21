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
            "from": settings.DEFAULT_FROM_EMAIL,
            "to": [user.email],
            "subject": "Verify Your Email for Finance App",
            "html": f"""
            <div style="font-family: Arial, sans-serif; background-color: #f4f4f7; padding: 20px;">
                <div style="max-width: 600px; margin: auto; background-color: #ffffff; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    
                    <!-- Header / Logo -->
                    <div style="background-color: #4f46e5; padding: 20px; text-align: center;">
                        <img src="https://pr-finance.up.railway.app/logo.png" alt="Finance Logo" style="width: 120px; height: auto;">
                    </div>
                    
                    <!-- Body -->
                    <div style="padding: 30px; color: #333333; line-height: 1.5;">
                        <h2 style="color: #4f46e5;">Hello {user.username},</h2>
                        <p>Welcome to Finance App! Please verify your email to get started.</p>
                        
                        <!-- Button -->
                        <p style="text-align: center; margin: 30px 0;">
                            <a href="{verification_link}" style="background-color: #4f46e5; color: #ffffff; padding: 12px 25px; text-decoration: none; border-radius: 6px; font-weight: bold;">
                                Verify Email
                            </a>
                        </p>
                        
                        <p>This link will expire in 24 hours. If you did not create an account, you can safely ignore this email.</p>
                        
                        <p>Thank you,<br>The Finance Team</p>
                    </div>
                    
                    <!-- Footer -->
                    <div style="background-color: #f4f4f7; text-align: center; padding: 15px; font-size: 12px; color: #888888;">
                        © 2025 Finance App. All rights reserved.
                    </div>
                </div>
            </div>
            """
        })
        print("Email sent:", response)
        return response
    except Exception as e:
        print("Failed to send verification email:", e)
        raise
