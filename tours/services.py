from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from tours.models import UserAvailableTour
from tours.models import TourActivationCode, TourActivationLog
from django.core.exceptions import ValidationError

def syncUserAvailbleTour(user, device_id):
    available_tours = UserAvailableTour.objects.filter(user=None, device_id=device_id)
    available_tours.update(user=user)


@transaction.atomic
def activate_code(user, device_id, raw_code: str, tour):    

    # device Id khong the thieu
    if not device_id:
        raise ValidationError(
            "device_id là bắt buộc"
        )
    
    # Kiểm tra 1 thiết bị đã activate code này trước đó chưa
    # => mỗi device chỉ được activate 1 lần / 1 code
    already_activated = (
        TourActivationLog.objects
        .filter(
            device_id=device_id,
            raw_code=raw_code
        )
        .exists()
    )

    if already_activated:
        raise ValidationError(
            "Thiết bị này đã kích hoạt tour trước đó"
        )


    now = timezone.now()

    try:
        code = (
            TourActivationCode.objects
            .select_for_update()
            .get(code=raw_code, tour=tour)
        )
    except TourActivationCode.DoesNotExist:
        raise ValidationError("Code không hợp lệ")

    code.validate_redeemable(now)

    query = {"tour": code.tour}

    if user:
        query["user"] = user
    else:
        query["device_id"] = device_id

    access, created = (
        UserAvailableTour.objects
        .select_for_update()
        .get_or_create(
            **query,
            defaults={"expired_at": now},
        )
    )

    base_time = max(now, access.expired_at)

    access.expired_at = (
        base_time +
        timedelta(days=code.days_credit)
    )

    access.save(update_fields=["expired_at"])

    code.used_count += 1
    code.save(update_fields=["used_count"])

    # Ghi log activate
    TourActivationLog.objects.create(
        device_id=device_id,
        raw_code=code.code,
        granted_until=access.expired_at,
    )

    return access
