import os
from email.message import EmailMessage
from aiosmtplib import send
import httpx
from dotenv import load_dotenv

load_dotenv()

# Render is blocking smtp port 587 --- so we need to use a transactional email API- Brevo API
# async def send_email_otp(to_email: str, otp: str):
#     message = EmailMessage()
#     from_email = os.getenv("EMAIL_USERNAME")
#
#     message["From"] = from_email
#     message["To"] = to_email
#     message["Subject"] = "Your OTP for ExplainIt.Tech"
#     message.set_content(f"Your OTP is: {otp}\nIt will expire in 5 minutes.")
#
#     await send(
#         message,
#         hostname=os.getenv("EMAIL_HOST"),
#         port=int(os.getenv("EMAIL_PORT")),
#         username=os.getenv("EMAIL_USERNAME"),
#         password=os.getenv("EMAIL_PASSWORD"),
#         start_tls=True,   # ✅ this enables STARTTLS for Outlook
#     )


async def send_email_otp(to_email: str, otp: str):
    BREVO_API_KEY = os.getenv("BREVO_API_KEY")
    BREVO_SENDER = os.getenv("EMAIL_USERNAME")
    url = os.getenv("BREVO_URL")

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": BREVO_API_KEY,
    }

    data = {
        "sender": {"email": BREVO_SENDER, "name": "Explainit.tech"},
        "to": [{"email": to_email}],
        "subject": "Login OTP for Explainit.tech",
        "htmlContent": f"<html><head></head><body><p>Hello,</p>This is Your OTP is:{otp}</p> <p>It will expire in 5 minutes.</p><p>Thank you.</p></body></html>",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=data)
        response.raise_for_status()
        return {"status": True, "response": response}
