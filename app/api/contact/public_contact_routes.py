from fastapi import APIRouter, Depends, HTTPException, status

from app.core.public_api_security import verify_public_app_access
from app.schemas.contact import ContactRequest, ContactResponse
from app.services import contact_service

router = APIRouter()


@router.post("", response_model=ContactResponse)
async def send_public_contact_message(
    payload: ContactRequest,
    host_site: str = Depends(verify_public_app_access),
) -> ContactResponse:
    try:
        await contact_service.send_contact_message(payload, host_site)
    except contact_service.ContactHostError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Contact is only available for explainit.tech.",
        ) from None
    except contact_service.ContactRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait before sending another message.",
            headers={"Retry-After": str(exc.retry_after)},
        ) from None
    except contact_service.ContactEmailConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The contact service is temporarily unavailable.",
        ) from None
    except contact_service.ContactEmailTimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="The email service timed out. Please try again later.",
        ) from None
    except contact_service.ContactEmailProviderError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to send your message. Please try again later.",
        ) from None

    return ContactResponse(status=True, message="Your message has been submitted.")
