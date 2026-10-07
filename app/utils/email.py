import os
from email.message import EmailMessage
from urllib.parse import urlsplit
from aiosmtplib import send
import httpx
from dotenv import load_dotenv
from pydantic import EmailStr, TypeAdapter, ValidationError

from app.core.config import settings

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
    BREVO_API_KEY = settings.BREVO_API_KEY
    BREVO_SENDER = settings.EMAIL_USERNAME
    url = settings.BREVO_URL    
    
    #BREVO_API_KEY = os.getenv("BREVO_API_KEY")
    #BREVO_SENDER = os.getenv("EMAIL_USERNAME")
    #url = os.getenv("BREVO_URL")

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": BREVO_API_KEY,
    }

    data = {
        "sender": {"email": BREVO_SENDER, "name": "Explainit.tech"},
        "to": [{"email": to_email}],
        "subject": "Login OTP for Explainit.tech",
        "htmlContent": f"<html><head></head><body><p>Hello,</p>This is Your OTP is: {otp}</p> <p>It will expire in 5 minutes.</p><p>Thank you.</p></body></html>",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=data)
        response.raise_for_status()
        return {"status": True, "response": response}


class ContactEmailConfigurationError(Exception):
    pass


class ContactEmailProviderError(Exception):
    pass


class ContactEmailTimeoutError(Exception):
    pass


async def send_contact_email(
    *, name: str, email: str, message: str, phone: str | None = None
) -> None:
    """Send plain text, using the verified site sender and visitor Reply-To."""
    api_key = settings.BREVO_API_KEY.strip()
    url = settings.BREVO_URL.strip()
    sender = settings.EMAIL_USERNAME.strip()
    recipient = settings.CONTACT_EMAIL_TO.strip()
    if not all((api_key, url, sender, recipient)):
        raise ContactEmailConfigurationError()
    try:
        endpoint = urlsplit(url)
        if endpoint.scheme != "https" or not endpoint.netloc:
            raise ContactEmailConfigurationError()
        address = TypeAdapter(EmailStr)
        sender = str(address.validate_python(sender))
        recipient = str(address.validate_python(recipient))
    except (ValidationError, ValueError):
        raise ContactEmailConfigurationError() from None

    contact_details = f"Name: {name}\nEmail: {email}"
    if phone:
        contact_details += f"\nPhone: {phone}"
    payload = {
        "sender": {"email": sender, "name": "explainit"},
        "to": [{"email": recipient}],
        "replyTo": {"email": email, "name": name},
        "subject": "New explainit contact message",
        "textContent": f"{contact_details}\n\n{message}",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url,
                headers={
                    "accept": "application/json",
                    "content-type": "application/json",
                    "api-key": api_key,
                },
                json=payload,
            )
    except httpx.TimeoutException:
        raise ContactEmailTimeoutError() from None
    except httpx.RequestError:
        raise ContactEmailProviderError() from None

    if response.status_code != 201:
        raise ContactEmailProviderError()
    try:
        accepted = response.json()
    except ValueError:
        raise ContactEmailProviderError() from None
    if not isinstance(accepted, dict):
        raise ContactEmailProviderError()
    message_id = accepted.get("messageId")
    if not isinstance(message_id, str) or not message_id.strip():
        raise ContactEmailProviderError()
