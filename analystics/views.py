from datetime import date, datetime, time

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils.timezone import make_aware, is_naive

from rest_framework.views import APIView

from drf_spectacular.utils import (
    extend_schema, OpenApiParameter, OpenApiResponse, inline_serializer
)
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers as drf_serializers

from accounts.models import User
from accounts.permissions import IsPartnerUser, IsAdminUser
from history.models import History
from payments.models import Invoice
from pois.models import Poi, LocalizedData
from tours.models import TourPoint
from batch.models import DailyVisitStat, DailyRevenueStat

from core.reponse_schema import api_response


# ─── HELPERS ────────────────────────────────────────────────────────────────

def _parse_date_range(request):
    from_str = request.query_params.get("from")
    to_str = request.query_params.get("to")

    try:
        from_date = date.fromisoformat(from_str) if from_str else None
        to_date = date.fromisoformat(to_str) if to_str else None
    except ValueError:
        return None, None

    return from_date, to_date


def _to_aware(dt):
    if dt and is_naive(dt):
        return make_aware(dt)
    return dt


def _apply_date_filter(qs, field, from_date, to_date):
    if from_date:
        start = datetime.combine(from_date, time.min)
        qs = qs.filter(**{f"{field}__gte": _to_aware(start)})

    if to_date:
        end = datetime.combine(to_date, time.max)
        qs = qs.filter(**{f"{field}__lte": _to_aware(end)})

    return qs


def _format_date(d):
    return d.isoformat() if d else None

def _apply_pure_date_filter(qs, field, from_date, to_date):
    """Dùng riêng cho các model có trường là DateField thuần (như bảng Batch)"""
    if from_date:
        qs = qs.filter(**{f"{field}__gte": from_date})
    if to_date:
        qs = qs.filter(**{f"{field}__lte": to_date})
    return qs


# ─── ADMIN ─────────────────────────────────────────────────────────────────

class AdminOverviewView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        total_users = User.objects.count()
        total_pois = Poi.objects.count()
        
        # Lấy tổng từ bảng Batch (cực nhanh)
        total_visits = DailyVisitStat.objects.aggregate(total=Sum("visits"))["total"] or 0
        revenue = DailyRevenueStat.objects.aggregate(total=Sum("revenue"))["total"] or 0

        return api_response(data={
            "totalUsers": total_users,
            "totalPois": total_pois,
            "totalVisits": total_visits,
            "totalRevenue": revenue,
        })


class AdminVisitsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        from_date, to_date = _parse_date_range(request)

        qs = DailyVisitStat.objects.all()
        qs = _apply_pure_date_filter(qs, "date", from_date, to_date)

        # Gom nhóm theo ngày và cộng dồn visits của tất cả POI
        rows = (
            qs.values("date")
            .annotate(total_visits=Sum("visits"))
            .order_by("date")
        )

        data = [
            {"date": _format_date(r["date"]), "visits": r["total_visits"]}
            for r in rows
        ]

        return api_response(data=data)


class AdminRevenueView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        from_date, to_date = _parse_date_range(request)

        qs = DailyRevenueStat.objects.all()
        qs = _apply_pure_date_filter(qs, "date", from_date, to_date)

        # Bảng này đã gom sẵn theo ngày rồi, chỉ việc lấy ra
        rows = qs.values("date", "revenue").order_by("date")

        data = [
            {
                "date": _format_date(r["date"]),
                "revenue": r["revenue"] or 0,
            }
            for r in rows
        ]

        return api_response(data=data)


class AdminTopPoisView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        limit = int(request.query_params.get("limit", 5))
        lang = request.query_params.get("lang", "vi")
        from_date, to_date = _parse_date_range(request)

        qs = DailyVisitStat.objects.all()
        qs = _apply_pure_date_filter(qs, "date", from_date, to_date)

        # Gom nhóm theo poi_id và lấy tổng visits
        rows = (
            qs.values("poi_id")
            .annotate(total_visits=Sum("visits"))
            .order_by("-total_visits")[:limit]
        )

        poi_ids = [r["poi_id"] for r in rows]

        # Logic lấy tên POI (LocalizedData) giữ nguyên không đổi
        locs = LocalizedData.objects.filter(poi_id__in=poi_ids, lang_code=lang).values("poi_id", "name")
        name_map = {l["poi_id"]: l["name"] for l in locs}

        missing = [pid for pid in poi_ids if pid not in name_map]
        if missing:
            fallback = LocalizedData.objects.filter(poi_id__in=missing).values("poi_id", "name")
            for l in fallback:
                if l["poi_id"] not in name_map:
                    name_map[l["poi_id"]] = l["name"]

        data = [
            {
                "poiId": r["poi_id"],
                "name": name_map.get(r["poi_id"], ""),
                "visits": r["total_visits"],
            }
            for r in rows
        ]

        return api_response(data=data)

# Chua toi uu
class AdminTopToursView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        limit = int(request.query_params.get("limit", 5))
        from_date, to_date = _parse_date_range(request)

        entry_points = (
            TourPoint.objects
            .filter(position=1)
            .values("poi_id", "tour_id", "tour__name")
        )

        poi_to_tour = {
            ep["poi_id"]: (ep["tour_id"], ep["tour__name"])
            for ep in entry_points
        }

        if not poi_to_tour:
            return api_response(data=[])

        qs = History.objects.filter(poi_id__in=poi_to_tour.keys())
        qs = _apply_date_filter(qs, "created_at", from_date, to_date)

        rows = (
            qs.values("poi_id")
            .annotate(starts=Count("id"))
        )

        tour_starts = {}
        for r in rows:
            tour_id, tour_name = poi_to_tour[r["poi_id"]]
            if tour_id not in tour_starts:
                tour_starts[tour_id] = {
                    "tourId": tour_id,
                    "name": tour_name,
                    "starts": 0,
                }
            tour_starts[tour_id]["starts"] += r["starts"]

        result = sorted(
            tour_starts.values(),
            key=lambda x: x["starts"],
            reverse=True
        )[:limit]

        return api_response(data=result)


class AdminActiveUsersView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        from_date, to_date = _parse_date_range(request)

        qs = History.objects.all()
        qs = _apply_date_filter(qs, "created_at", from_date, to_date)

        rows = (
            qs.annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(users=Count("user_id", distinct=True))
            .order_by("date")
        )

        data = [
            {"date": _format_date(r["date"]), "users": r["users"]}
            for r in rows
        ]

        return api_response(data=data)


# ─── PARTNER ───────────────────────────────────────────────────────────────

class PartnerOverviewView(APIView):
    permission_classes = [IsPartnerUser]

    def get(self, request):
        poi_ids = Poi.objects.filter(owner=request.user).values_list("id", flat=True)

        # Lấy tổng visits từ batch. (Lưu ý: uniqueUsers vẫn phải quét History vì Batch chưa lưu unique user)
        total_visits = DailyVisitStat.objects.filter(poi_id__in=poi_ids).aggregate(total=Sum("visits"))["total"] or 0
        
        unique_users = History.objects.filter(poi_id__in=poi_ids).aggregate(
            users=Count("user_id", distinct=True)
        )["users"] or 0

        return api_response(data={
            "totalVisits": total_visits,
            "uniqueUsers": unique_users,
        })


class PartnerVisitsView(APIView):
    permission_classes = [IsPartnerUser]

    def get(self, request):
        from_date, to_date = _parse_date_range(request)
        poi_ids = Poi.objects.filter(owner=request.user).values_list("id", flat=True)

        qs = DailyVisitStat.objects.filter(poi_id__in=poi_ids)
        qs = _apply_pure_date_filter(qs, "date", from_date, to_date)

        rows = (
            qs.values("date")
            .annotate(total_visits=Sum("visits"))
            .order_by("date")
        )

        data = [
            {"date": _format_date(r["date"]), "visits": r["total_visits"]}
            for r in rows
        ]

        return api_response(data=data)


class PartnerPoisPerformanceView(APIView):
    permission_classes = [IsPartnerUser]

    def get(self, request):
        lang = request.query_params.get("lang", "vi")
        from_date, to_date = _parse_date_range(request)

        poi_ids = list(Poi.objects.filter(owner=request.user).values_list("id", flat=True))

        qs = DailyVisitStat.objects.filter(poi_id__in=poi_ids)
        qs = _apply_pure_date_filter(qs, "date", from_date, to_date)

        rows = (
            qs.values("poi_id")
            .annotate(total_visits=Sum("visits"))
        )

        visits_map = {r["poi_id"]: r["total_visits"] for r in rows}

        # Logic query name_map giữ nguyên
        locs = LocalizedData.objects.filter(poi_id__in=poi_ids, lang_code=lang).values("poi_id", "name")
        name_map = {l["poi_id"]: l["name"] for l in locs}

        data = [
            {
                "poiId": pid,
                "name": name_map.get(pid, ""),
                "visits": visits_map.get(pid, 0),
            }
            for pid in poi_ids
        ]

        data.sort(key=lambda x: x["visits"], reverse=True)

        return api_response(data=data)
    permission_classes = [IsPartnerUser]

    def get(self, request):
        lang = request.query_params.get("lang", "vi")
        from_date, to_date = _parse_date_range(request)

        poi_ids = list(
            Poi.objects.filter(owner=request.user).values_list("id", flat=True)
        )

        qs = History.objects.filter(poi_id__in=poi_ids)
        qs = _apply_date_filter(qs, "created_at", from_date, to_date)

        rows = (
            qs.values("poi_id")
            .annotate(visits=Count("id"))
        )

        visits_map = {r["poi_id"]: r["visits"] for r in rows}

        locs = (
            LocalizedData.objects
            .filter(poi_id__in=poi_ids, lang_code=lang)
            .values("poi_id", "name")
        )
        name_map = {l["poi_id"]: l["name"] for l in locs}

        data = [
            {
                "poiId": pid,
                "name": name_map.get(pid, ""),
                "visits": visits_map.get(pid, 0),
            }
            for pid in poi_ids
        ]

        data.sort(key=lambda x: x["visits"], reverse=True)

        return api_response(data=data)