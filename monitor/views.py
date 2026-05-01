from accounts.permissions import HasDeviceId
import h3
import json
from collections import Counter
from django_redis import get_redis_connection
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.throttling import ScopedRateThrottle


# ==============================
# Configuration
# ==============================

# Time (seconds) before a user is considered offline if no heartbeat is received
HEARTBEAT_TTL = 45

# H3 resolution level:
# 10 ≈ hexagon edge ~66m → suitable for pedestrian-level heatmaps / POI tracking, r ~ 70m
H3_RESOLUTION = 10


# ==============================
# Heartbeat API
# ==============================

class HeartbeatView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'heartbeat_limit'
    permission_classes = [HasDeviceId]

    """
    POST /api/monitor/heartbeat

    Purpose:
    - Track active users/guests in near real-time
    - Optionally store their location as an H3 index for heatmap aggregation
    """

    def post(self, request):
        visitor_id = request.headers.get("X-Device-Id")
        user_id = request.data.get("user_id")
        lang_code = request.data.get("lang_code")

        # GPS coordinates from client (optional)
        lat = request.data.get("lat")
        lng = request.data.get("lng")

        # At least one identifier must be provided
        if not visitor_id and not user_id:
            return Response(
                {"detail": "visitor_id hoặc user_id là bắt buộc."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Normalize identifier format for Redis key
        identifier = f"user:{user_id}" if user_id else f"guest:{visitor_id}"

        # Build payload — always include lang_code if provided
        payload = {}

        if lang_code:
            payload["lang_code"] = lang_code

        # Convert GPS → H3 index (hex cell)
        if lat and lng:
            try:
                payload["h3index"] = h3.latlng_to_cell(
                    float(lat),
                    float(lng),
                    H3_RESOLUTION
                )
            except (ValueError, TypeError):
                # Ignore invalid coordinates, still save the rest
                pass

        # Serialize to JSON for reliable Redis storage/retrieval
        value = json.dumps(payload) if payload else "active"

        # Store status in Redis with TTL
        redis_conn = get_redis_connection("default")
        redis_conn.set(
            f"online_status:{identifier}",
            value,
            ex=HEARTBEAT_TTL
        )

        return Response(status=status.HTTP_204_NO_CONTENT)


# ==============================
# Monitoring Stats API
# ==============================

class MonitorStatsView(APIView):
    """
    GET /api/monitor/stats

    Purpose:
    - Provide real-time monitoring stats for admin dashboard
    - Includes:
        + total online users
        + user vs guest breakdown
        + heatmap aggregation (H3 index → count)
        + language breakdown global (lang_code → count)
        + language breakdown per H3 cell (h3index → {lang_code → count})
    """

    permission_classes = [IsAdminUser]

    def get(self, request):
        redis_conn = get_redis_connection("default")

        # ------------------------------
        # Step 1: Fetch all active keys using SCAN (non-blocking)
        # ------------------------------
        cursor = 0
        all_keys = []

        while True:
            cursor, keys = redis_conn.scan(
                cursor=cursor,
                match="online_status:*",
                count=1000
            )
            all_keys.extend(keys)

            if cursor == 0:
                break

        # Early return if no active users
        if not all_keys:
            return Response({
                "status": "success",
                "data": {
                    "total_online": 0,
                    "users": 0,
                    "guests": 0,
                    "heatmap": {},
                    "heatmap_languages": {},
                    "languages": {},
                }
            })

        # ------------------------------
        # Step 2: Count users vs guests
        # ------------------------------
        active_users = sum(1 for k in all_keys if b":user:" in k)
        active_guests = len(all_keys) - active_users

        # ------------------------------
        # Step 3: Parse values & build aggregations
        # ------------------------------

        # Fetch all values in a single Redis call (efficient)
        values = redis_conn.mget(all_keys)

        h3_indices = []
        lang_codes = []
        # h3index → {lang_code → count}
        hex_lang_map: dict[str, list[str]] = {}

        for v in values:
            if not v:
                continue

            decoded = v.decode("utf-8")

            # Skip bare "active" markers (no location/lang data)
            if decoded == "active":
                continue

            try:
                data = json.loads(decoded)
            except (ValueError, TypeError):
                continue

            h3index = data.get("h3index")
            lang = data.get("lang_code")

            if h3index:
                h3_indices.append(h3index)

                if lang:
                    hex_lang_map.setdefault(h3index, []).append(lang)

            if lang:
                lang_codes.append(lang)

        # Aggregate language counts per H3 cell
        heatmap_languages = {
            h3index: dict(Counter(langs))
            for h3index, langs in hex_lang_map.items()
        }

        # ------------------------------
        # Response
        # ------------------------------
        return Response({
            "status": "success",
            "data": {
                "total_online": active_users + active_guests,
                "users": active_users,
                "guests": active_guests,
                "heatmap": dict(Counter(h3_indices)),        # H3 cell → count
                "heatmap_languages": heatmap_languages,      # H3 cell → {lang → count}
                "languages": dict(Counter(lang_codes)),      # global lang → count
            },
        })