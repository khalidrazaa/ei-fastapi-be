import asyncio
import logging
from datetime import timedelta
from math import ceil

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.query import lead as lead_query
from app.schemas.contact import ContactRequest
from app.utils.email import send_contact_email

logger = logging.getLogger(__name__)


class ContactHostError(Exception):
    pass


class ContactPersistenceError(Exception):
    pass


class ContactRateLimitError(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__("Contact submission limit reached.")


async def send_contact_message(
    payload: ContactRequest,
    host_site: str,
    db: AsyncSession,
) -> None:
    if host_site != "explainit.tech":
        raise ContactHostError("Contact is only available for explainit.tech.")
    try:
        async with lead_query.submission_transaction(db):
            now, count, oldest, previous = await lead_query.get_submission_window(
                db, str(payload.email), 60
            )
            blocked_until = None
            if previous is not None:
                blocked_until = previous + timedelta(seconds=60)
            if count >= 20 and oldest is not None:
                global_expiry = oldest + timedelta(seconds=60)
                blocked_until = max(blocked_until or global_expiry, global_expiry)
            if blocked_until is not None:
                raise ContactRateLimitError(
                    max(1, ceil((blocked_until - now).total_seconds()))
                )
            values = payload.model_dump(exclude={"website"})
            values.update(host_site=host_site, submitted_at=now, updated_at=now)
            lead = await lead_query.add_lead(db, values)
            lead_id = lead.id
    except SQLAlchemyError:
        raise ContactPersistenceError() from None

    # The enquiry is committed before contacting the email provider.
    try:
        await asyncio.wait_for(
            send_contact_email(
                name=payload.name,
                email=str(payload.email),
                message=payload.message,
                phone=payload.phone,
                subject=payload.subject,
            ),
            timeout=10,
        )
    except Exception as exc:
        # Avoid logging enquiry content, addresses or provider response bodies.
        logger.warning(
            "Contact email failed lead=%s error=%s", lead_id, type(exc).__name__
        )
