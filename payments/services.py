from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from payments.models import UserAvailableTour
from tours.models import TourActivationCode, TourActivationRedemption

@transaction.atomic
def activate_code(user, raw_code):

    code = (
        TourActivationCode.objects
        .select_for_update()
        .get(code=raw_code)
    )

    if code.expired_at and code.expired_at < timezone.now():
        raise Exception("Code expired")

    if code.used_count >= code.usage_limit:
        raise Exception("Usage exceeded")

    access, created = UserAvailableTour.objects.get_or_create(
        user=user,
        tour=code.tour,
        defaults={
            "expired_at": timezone.now()
        }
    )

    base_time = max(
        timezone.now(),
        access.expired_at
    )

    access.expired_at = (
        base_time + timedelta(days=code.days_credit)
    )

    access.save(update_fields=["expired_at"])

    code.used_count += 1
    code.save(update_fields=["used_count"])

    TourActivationRedemption.objects.create(
        user=user,
        activation_code=code,
        granted_until=access.expired_at
    )