from django.db.models import OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from pois.models import Poi, LocalizedData
import math
from django.db.models import Q, F
from django.db.models import FilteredRelation

# def get_poi_queryset(lang, q=None):
#     localized_qs = LocalizedData.objects.filter(
#         poi=OuterRef("pk"),
#         lang_code=lang
#     )

#     fallback_qs = LocalizedData.objects.filter(
#         poi=OuterRef("pk"),
#         lang_code=OuterRef("default_lang")
#     )

#     qs = Poi.objects.filter(status="active")

#     # annotate fields
#     qs = qs.annotate(
#         name=Coalesce(
#             Subquery(localized_qs.values("name")[:1]),
#             Subquery(fallback_qs.values("name")[:1])
#         ),
#         description=Coalesce(
#             Subquery(localized_qs.values("description")[:1]),
#             Subquery(fallback_qs.values("description")[:1])
#         ),
#         audio=Coalesce(
#             Subquery(localized_qs.values("audio")[:1]),
#             Subquery(fallback_qs.values("audio")[:1])
#         )
#     )

#     if q:
#         qs = qs.filter(name__icontains=q)

#     return qs

def get_poi_queryset(lang, q=None):
    qs = (
        Poi.objects
        .filter(status="active")
        .annotate(
            localized=FilteredRelation(
                "localized_data",
                condition=Q(localized_data__lang_code=lang)
            ),
            fallback=FilteredRelation(
                "localized_data",
                condition=Q(localized_data__lang_code=F("default_lang"))
            )
        )
        .annotate(
            name=Coalesce("localized__name", "fallback__name"),
            description=Coalesce("localized__description", "fallback__description"),
            audio=Coalesce("localized__audio", "fallback__audio"),
        )
    )

    if q:
        qs = qs.filter(
            Q(localized__name__icontains=q) |
            Q(fallback__name__icontains=q)
        )

    return qs

def paginate_queryset(qs, page, page_size):
    page = max(page, 1)
    page_size = min(page_size, 100)  # tránh abuse

    total = qs.count()  # chậm nếu data lớn
    total_page = math.ceil(total / page_size)

    offset = (page - 1) * page_size

    return qs[offset:offset + page_size], total, total_page