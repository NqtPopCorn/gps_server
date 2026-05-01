
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
import math
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser, AllowAny
from django.shortcuts import get_object_or_404

from drf_spectacular.utils import (
    extend_schema, OpenApiResponse, OpenApiParameter, OpenApiExample, inline_serializer
)
from drf_spectacular.types import OpenApiTypes

from pois.models import Poi, LocalizedData
from pois.serializers import (
    POISerializer, POIDetailSerializer,
    CreatePOISerializer, UpdatePOISerializer,
    LocalizationWriteSerializer, LocalizationResponseSerializer
)

from core.cloudinary_helper import upload_image, upload_audio, delete_resources_by_prefix

from pois.services import get_poi_queryset, paginate_queryset

from accounts.models import User
from accounts.permissions import IsPartnerUser
from django.db import transaction
from django.core.cache import cache

from core.reponse_schema import api_response, api_response_schema, api_pagination_response_schema, build_url

# ─── PUBLIC ENDPOINTS ────────────────────────────────────────────────────────

# def _zoom_to_limit(zoom: int) -> int:
#     """Limit POI count theo zoom level để tránh lag."""
#     if zoom <= 11:   return 15
#     elif zoom <= 13: return 40
#     elif zoom <= 15: return 100
#     else:            return 300  # zoom sát đất, hiện gần hết

# class POINearbyView(APIView):
#     permission_classes = [AllowAny]

#     # /api/pois/nearby
#     @extend_schema(
#         tags=["POI"],
#         summary="Get nearby POIs",
#         description=(
#             "Retrieve active Points of Interest near a given GPS coordinate. "
#         ),
#         parameters=[
#             OpenApiParameter("min_lat", OpenApiTypes.FLOAT, OpenApiParameter.QUERY, required=True,
#                              description="Minimum latitude of the search area"),
#             OpenApiParameter("min_lng", OpenApiTypes.FLOAT, OpenApiParameter.QUERY, required=True,
#                              description="Minimum longitude of the search area"),
#             OpenApiParameter("max_lat", OpenApiTypes.FLOAT, OpenApiParameter.QUERY, required=True,
#                              description="Maximum latitude of the search area"),
#             OpenApiParameter("max_lng", OpenApiTypes.FLOAT, OpenApiParameter.QUERY, required=True,
#                              description="Maximum longitude of the search area"),
#             OpenApiParameter("zoom", OpenApiTypes.INT, OpenApiParameter.QUERY, required=True,
#                             description="zoom of the search area"),
#             OpenApiParameter("lang", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True,
#                              description="Language code for localized content",
#                              enum=["vi", "en", "fr", "zh", "ja"]),
#         ],
#         responses={
#             200: OpenApiResponse(response=api_response_schema("POINearbyResponse", POISerializer(many=True)), description="List of nearby POIs"),
#             400: OpenApiResponse(description="Missing or invalid query parameters"),
#         },
#     )
#     def get(self, request):
#         # 1. Parse params
#         min_lat = request.query_params.get("min_lat")
#         min_lng = request.query_params.get("min_lng")
#         max_lat = request.query_params.get("max_lat")
#         max_lng = request.query_params.get("max_lng")
#         zoom_str = request.query_params.get("zoom")
#         lang     = request.query_params.get("lang", "vi")

#         try:
#             min_lat = float(min_lat)
#             min_lng = float(min_lng)
#             max_lat = float(max_lat)
#             max_lng = float(max_lng)
#             zoom = int(zoom_str)
#         except (ValueError, TypeError) as exc:
#             return Response(
#                 {"error": f"Invalid bbox or zoom: {exc}"},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         # Limit theo zoom
#         limit = _zoom_to_limit(zoom)

#         # normalize bbox
#         def norm(v): return round(v, 3)

#         cache_key = f"poi:{norm(min_lat)}:{norm(min_lng)}:{norm(max_lat)}:{norm(max_lng)}:{zoom}:{lang}"

#         cached = cache.get(cache_key)
#         if cached:
#             return api_response(data=cached)

#         qs = (
#             Poi.objects
#             .filter(
#                 status="active",
#                 latitude__gte=min_lat,
#                 latitude__lte=max_lat,
#                 longitude__gte=min_lng,
#                 longitude__lte=max_lng,
#             )
#             .prefetch_related("localized_data")
#             .order_by("type", "slug")
#             [:limit]
#         )

#         data = POISerializer(qs, many=True, context={"lang": lang}).data

#         cache.set(cache_key, data, timeout=60*60)
        
#         return api_response(data=data)

import h3 as h3lib                        # pip install h3

# ---------------------------------------------------------------------------
# Resolution → H3 child-expansion resolution cap
#
# The FE sends cells at whatever zoom resolution is currently visible.
# POIs are stored on the model with h3_index at RESOLUTION 9.
#
# Rule:
#   query_res <= POI_STORAGE_RES  →  expand to children at POI_STORAGE_RES
#   query_res >  POI_STORAGE_RES  →  climb to parent at POI_STORAGE_RES
#
# The RESOLUTION_ROW_LIMIT table gives a DB-row guard per resolution so that
# a single coarse cell cannot return an unbounded result set.
# ---------------------------------------------------------------------------

POI_STORAGE_RESOLUTION: int = 8         # resolution used when h3_index was written

RESOLUTION_ROW_LIMIT: dict[int, int] = {
    1: 5000,
    2: 3000,
    3: 2000,
    4: 1000,
    5: 500,
    6: 200,
    7: 100,
    8: 50,
    9: 20,
    10: 10,
    11: 10,
    12: 10,
    13: 10,
    14: 10,
    15: 10,
}

H3_CACHE_TTL: int = 5 * 60              # seconds – tune to your cache backend


def _get_pois_for_cell(cell: str, lang: str):
    """
    Return a serialized list of active POIs that fall inside *cell*.

    Strategy
    --------
    1. Resolve the cell to resolution POI_STORAGE_RESOLUTION so we can match
       against the stored h3_index column directly.
       - coarser cell  (res < 9) → expand to children at res-9
       - same or finer (res ≥ 9) → climb to the parent at res-9
    2. Filter Poi by h3_index__in (children) or h3_index == parent.
    3. Apply a row cap derived from the cell's resolution to avoid huge payloads.
    """
    try:
        resolution: int = h3lib.get_resolution(cell)
    except Exception:
        return []                          # invalid cell index → return empty

    row_limit: int = RESOLUTION_ROW_LIMIT.get(resolution, 50)
    

    if resolution < POI_STORAGE_RESOLUTION:
        # Expand: get all res-9 children that belong to this coarser cell.
        # h3.h3_to_children returns a SET; cast to list for the ORM.
        storage_cells = list(h3lib.cell_to_children(cell, POI_STORAGE_RESOLUTION))
        qs = (
            Poi.objects
            .filter(h3_index__in=storage_cells, status="active")
            .prefetch_related("localized_data")
            [:row_limit]
        )
    elif resolution == POI_STORAGE_RESOLUTION:
        qs = (
            Poi.objects
            .filter(h3_index=cell, status="active")
            .prefetch_related("localized_data")
            [:row_limit]
        )
    else:
        # Query cell is finer than storage resolution → climb up to res-9 parent.
        parent_cell = h3lib.cell_to_parent(cell, POI_STORAGE_RESOLUTION)
        qs = (
            Poi.objects
            .filter(h3_index=parent_cell, status="active")
            .prefetch_related("localized_data")
            [:row_limit]
        )

    return list(POISerializer(qs, many=True, context={"lang": lang}).data)


class POIByH3CellsView(APIView):
    """
    POST /api/pois/h3-batch/

    Body
    ----
    {
        "cells": ["8928308280fffff", "8928308281fffff", ...],
        "lang":  "vi"
    }

    Response
    --------
    {
        "8928308280fffff": [ ...pois... ],
        "8928308281fffff": [],            # or omitted – both are valid
        ...
    }

    Algorithm (mirrors FE pseudo-code)
    -----------------------------------
    for cell in cells:
        if cache.has(cell, lang):
            result[cell] = cache.get(cell, lang)
        else:
            res   = h3.h3_get_resolution(cell)
            limit = RESOLUTION_ROW_LIMIT[res]
            pois  = findPOIInsideHex(cell, limit, lang)
            cache.set(cell, lang, pois)
            result[cell] = pois
    return result
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["POI"],
        summary="Batch-fetch POIs by H3 cell indexes",
        description=(
            "Accept a list of H3 cell indexes and return all active POIs grouped "
            "by cell index.  Results are cached per cell+language for 5 minutes."
        ),
        request=inline_serializer(
            name="H3BatchRequest",
            fields={
                "cells": serializers.ListSerializer(child=serializers.CharField()),
                "lang": serializers.ChoiceField(choices=["vi", "en", "fr", "zh", "ja"]),
            },
        ),
        responses={
            200: OpenApiResponse(description="Map of { h3_index: POI[] }"),
            400: OpenApiResponse(description="Missing or invalid request body"),
        },
    )
    def post(self, request):
        cells = request.data.get("cells")
        lang  = request.data.get("lang", "vi")

        if not cells or not isinstance(cells, list):
            return Response(
                {"error": "cells must be a non-empty list of H3 index strings"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result: dict = {}

        for cell in cells:
            if not isinstance(cell, str):
                result[cell] = []
                continue

            cache_key = f"h3_pois__{cell}__{lang}"
            cached    = cache.get(cache_key)

            if cached is not None:
                result[cell] = cached
                continue

            # ── core lookup ──────────────────────────────────────────────────
            pois_data = _get_pois_for_cell(cell, lang)
            # ─────────────────────────────────────────────────────────────────

            cache.set(cache_key, pois_data, timeout=H3_CACHE_TTL)
            result[cell] = pois_data

        return api_response(data=result)

class POISearchView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["POI"],
        summary="Search POI",
        description="Search POI by name in the specified language.",
        parameters=[
            OpenApiParameter("lang", OpenApiTypes.STR, OpenApiParameter.QUERY,
                             description="Language code for localized content",
                             enum=["vi", "en", "fr", "zh", "ja"]),
            OpenApiParameter("name", OpenApiTypes.STR, OpenApiParameter.QUERY,
                             description="Name of the POI to search for"),
        ],
        responses={
            200: OpenApiResponse(response=api_response_schema("POISearchResponse", POISerializer(many=True)), description="List of POIs matching the search query"),
            400: OpenApiResponse(description="Missing or invalid query parameters"),
        },
    )
    def get(self, request):
        lang = request.query_params.get('lang', 'vi')
        name = request.query_params.get('name', '')

        qs = get_poi_queryset(lang, name)
        data = POISerializer(
            qs,
            many=True,
            context={'lang': lang},
        ).data
        return api_response(data=data)
        

class POIDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["POI"],
        summary="Get POI detail",
        description="Retrieve detailed information about a single active POI in the specified language.",
        parameters=[
            OpenApiParameter("lang", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False,
                             description="Language code for localized content",
                             enum=["vi", "en", "fr", "zh", "ja"]),
        ],
        responses={
            200: OpenApiResponse(response=api_response_schema("POIDetailResponse", POISerializer), description="POI detail"),
            400: OpenApiResponse(description="Missing lang parameter"),
            404: OpenApiResponse(description="POI not found"),
        },
    )
    def get(self, request, slug):
        lang = request.query_params.get('lang', 'vi')
        poi = get_object_or_404(Poi.objects.prefetch_related('localized_data'), slug=slug, status='active')
        data = POISerializer(poi, context={'lang': lang}).data
        return api_response(data=data)


# ─── ADMIN POI ENDPOINTS ─────────────────────────────────────────────────────

class AdminPOIListCreateView(APIView):
    # test
    # permission_classes = [AllowAny] 
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="admin_pois_list",
        tags=["Admin-POI"],
        summary="List all POIs (admin)",
        description="Retrieve all POIs with optional type/status filtering and pagination. Requires admin token.",
        parameters=[
            OpenApiParameter("page", OpenApiTypes.INT, OpenApiParameter.QUERY, description="Page number (default: 1)"),
            OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY,
                             description="Items per page (default: 20, max: 100)"),
            OpenApiParameter("type", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False,
                             description="Filter by POI type",
                             enum=["food", "drink", "museum", "park", "historical", "other"]),
            OpenApiParameter("status", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False,
                             description="Filter by status", enum=["active", "inactive"]),
        ],
        responses={
            200: OpenApiResponse(response=api_pagination_response_schema("AdminPOIListResponse", POIDetailSerializer(many=True)), description="Paginated list of POIs"),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden – admin only"),
        },
    )
    def get(self, request):
        page = int(request.query_params.get('page', 1))
        limit = min(int(request.query_params.get('limit', 20)), 100)
        poi_type = request.query_params.get('type')
        poi_status = request.query_params.get('status')

        qs = Poi.objects.prefetch_related('localized_data')
        if poi_type:
            qs = qs.filter(type=poi_type)
        if poi_status:
            qs = qs.filter(status=poi_status)
        if request.user.role == 'partner':
            qs = qs.filter(owner=request.user)

        total = qs.count()
        offset = (page - 1) * limit
        pois = qs[offset: offset + limit]

        serializer = POIDetailSerializer(pois, many=True)
        data = {
            "total": total, "results": serializer.data, "totalPage": math.ceil(total / limit)
        }
        return api_response(data=data)

    @extend_schema(
        tags=["Admin-POI"],
        summary="Create POI",
        description=(
            "Create a new Point of Interest with default language content. "
            "Accepts multipart/form-data (supports image + audio file upload). Requires admin token."
        ),
        request={
            "multipart/form-data": CreatePOISerializer,
        },
        responses={
            201: OpenApiResponse(response=api_response_schema("AdminPOICreateResponse", POIDetailSerializer), description="POI created successfully"),
            400: OpenApiResponse(description="Invalid request parameters"),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden – admin only"),
            409: OpenApiResponse(description="Slug already exists"),
        },
    )
    def post(self, request):
        serializer = CreatePOISerializer(data=request.data)
        if not serializer.is_valid():
            errors = serializer.errors
            if 'slug' in errors and any('already exists' in str(e) for e in errors['slug']):
                return Response({"error": "Slug already exists"}, status=status.HTTP_409_CONFLICT)
            return Response({"error": "Invalid request parameters", "details": errors},
                            status=status.HTTP_400_BAD_REQUEST)

        # Lấy data ra trước để code gọn gàng
        vd = serializer.validated_data
        image_file = vd.pop('image', None)
        audio_file = vd.pop('default_audio', None)
        default_name = vd.pop('default_name')
        default_description = vd.pop('default_description', '')
        default_lang = vd.get('default_lang', 'vi')

        # --- BẮT ĐẦU TRANSACTION ---
        try:
            with transaction.atomic():
                # 1. Partner credit check (Lock row an toàn)
                if request.user.role == 'partner':
                    user = User.objects.select_for_update().get(pk=request.user.pk)
                    if user.poi_credits <= 0:
                        # Return trong block atomic không sao cả, DB chưa bị thay đổi
                        return Response(
                            {'error': 'Bạn không có lượt tạo POI. Vui lòng mua thêm tại /api/payments/buy-poi-credit/'},
                            status=status.HTTP_402_PAYMENT_REQUIRED,
                        )
                    user.poi_credits -= 1
                    user.save(update_fields=['poi_credits'])

                # 2. Tạo POI
                poi = Poi.objects.create(**{k: v for k, v in vd.items()})
                if(request.user.role == 'partner'):
                    poi.owner = request.user
                    poi.save(update_fields=['owner'])

                # 3. Xử lý lưu ảnh
                if image_file:
                    poi.image = upload_image(image_file, folder=f"gps_server/pois/{poi.id}")
                    poi.save(update_fields=['image'])

                # 4. Xử lý lưu audio
                audio_url = None
                if audio_file:
                    audio_url = upload_audio(audio_file, folder=f"gps_server/pois/{poi.id}")

                # 5. Tạo LocalizedData
                LocalizedData.objects.create(
                    poi=poi,
                    lang_code=default_lang,
                    name=default_name,
                    description=default_description,
                    audio=audio_url,
                )
                
        except Exception as e:
            # Nếu xảy ra bất kỳ lỗi gì (lỗi lưu file, lỗi DB), toàn bộ dữ liệu (bao gồm cả việc trừ credit)
            # sẽ được Rollback tự động.
            return Response(
                {"error": "Đã xảy ra lỗi trong quá trình tạo hệ thống POI.", "details": str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        # --- KẾT THÚC TRANSACTION ---

        poi.refresh_from_db()
        data = POIDetailSerializer(poi, context={'lang': default_lang}).data
        return api_response(data=data, message="POI created successfully", http_status=201)

class AdminPOIDetailView(APIView):
    # test
    permission_classes = [AllowAny]
    # permission_classes = [IsAdminUser]

    @extend_schema(
        operation_id="admin_pois_retrieve",
        tags=["Admin-POI"],
        summary="Get POI detail (admin)",
        description="Retrieve full POI details including all admin fields. Requires admin token.",
        responses={
            200: OpenApiResponse(response=api_response_schema("AdminPOIDetailResponse", POIDetailSerializer), description="POI detail"),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden – admin only"),
            404: OpenApiResponse(description="POI not found"),
        },
    )
    def get(self, request, id):
        poi = get_object_or_404(Poi.objects.prefetch_related('localized_data'), pk=id)
        data = POIDetailSerializer(poi, context={'lang': poi.default_lang}).data
        return api_response(data=data)

    @extend_schema(
        tags=["Admin-POI"],
        summary="Update POI",
        description=(
            "Partially update POI fields. Accepts multipart/form-data (supports image upload). "
            "Only provided fields are updated. Requires admin token."
        ),
        request={
            "multipart/form-data": UpdatePOISerializer,
        },
        responses={
            200: OpenApiResponse(response=api_response_schema("AdminPOIListCreateResponse", POIDetailSerializer), description="POI updated successfully"),
            400: OpenApiResponse(description="Invalid request parameters"),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden – admin only"),
            404: OpenApiResponse(description="POI not found"),
        },
    )
    def patch(self, request, id):
        poi = get_object_or_404(Poi, pk=id)
        serializer = UpdatePOISerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"error": "Invalid request parameters", "details": serializer.errors},
                            status=status.HTTP_400_BAD_REQUEST)

        vd = serializer.validated_data
        image_file = vd.pop('image', None)
        if image_file:
            vd['image'] = upload_image(image_file, folder=f"gps_server/pois/{poi.id}")

        for attr, value in vd.items():
            setattr(poi, attr, value)
        poi.save()

        poi.refresh_from_db()
        data = POIDetailSerializer(
            Poi.objects.prefetch_related('localized_data').get(pk=poi.pk),
            context={'lang': poi.default_lang},
        ).data
        return api_response(data=data, message="POI updated successfully")

    @extend_schema(
        tags=["Admin-POI"],
        summary="Delete POI",
        description="Permanently delete a POI and all its localizations. Requires admin token.",
        responses={
            204: OpenApiResponse(description="POI deleted successfully"),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden – admin only"),
            404: OpenApiResponse(description="POI not found"),
        },
    )
    def delete(self, request, id):
        poi = get_object_or_404(Poi, pk=id)
        poi.delete()
        # Xoá toàn bộ media của POI này trên Cloudinary
        delete_resources_by_prefix(f"gps_server/pois/{id}")
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── ADMIN POI LOCALIZATION ENDPOINTS ────────────────────────────────────────

class AdminPOILocalizationView(APIView):
    # test
    permission_classes = [AllowAny]
    # permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin-POI"],
        summary="Create or update translated content",
        description=(
            "Add or update POI content (name, description, audio) for a specific language. "
            "If a localization for that language already exists it will be overwritten. "
            "Accepts multipart/form-data (supports audio file upload)."
        ),
        request={
            "multipart/form-data": LocalizationWriteSerializer,
        },
        responses={
            200: OpenApiResponse(response=api_response_schema("AdminPOILocalizationResponse", LocalizationResponseSerializer), description="Localization updated"),
            400: OpenApiResponse(description="Invalid request parameters"),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden – admin only"),
            404: OpenApiResponse(description="POI not found"),
        },
    )
    def post(self, request, poi_id):
        poi = get_object_or_404(Poi, pk=poi_id)
        serializer = LocalizationWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"error": "Invalid request parameters", "details": serializer.errors},
                            status=status.HTTP_400_BAD_REQUEST)

        vd = serializer.validated_data
        audio_file = vd.pop('audio', None)
        lang_code = vd['lang_code']
        
        audio_url = None
        if audio_file:
            audio_url = upload_audio(audio_file, folder=f"gps_server/pois/{poi.id}")

        loc, _ = LocalizedData.objects.update_or_create(
            poi=poi,
            lang_code=lang_code,
            defaults={
                'name': vd['name'],
                'description': vd.get('description', ''),
                'audio': audio_url,
            },
        )
        data = LocalizationResponseSerializer(loc).data
        return api_response(data=data, message="Localization updated successfully")

    @extend_schema(
        tags=["Admin-POI"],
        summary="Get all POI localizations",
        description="Retrieve all language versions (localizations) for the given POI. Requires admin token.",
        responses={
            200: OpenApiResponse(
                response=api_response_schema("AdminPOILocalizationListResponse", LocalizationResponseSerializer(many=True)),
                description="List of localizations",
            ),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden – admin only"),
            404: OpenApiResponse(description="POI not found"),
        },
    )
    def get(self, request, poi_id):
        poi = get_object_or_404(Poi, pk=poi_id)
        locs = LocalizedData.objects.filter(poi=poi)
        data = LocalizationResponseSerializer(locs, many=True).data
        return api_response(data=data)


class AdminPOILocalizationDeleteView(APIView):
    # test
    permission_classes = [AllowAny]
    # permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin-POI"],
        summary="Delete specific localization",
        description="Remove POI content for a specific language. Requires admin token.",
        responses={
            204: OpenApiResponse(description="Localization deleted"),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden – admin only"),
            404: OpenApiResponse(description="POI or localization not found"),
        },
    )
    def delete(self, request, poi_id, lang_code):
        poi = get_object_or_404(Poi, pk=poi_id)
        loc = get_object_or_404(LocalizedData, poi=poi, lang_code=lang_code)
        loc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

# from accounts.permissions import IsPartnerUser
# # -----PARTNER POI ENDPOINTS -----
# class PartnerPOIListCreateView(APIView):
#     # test
#     permission_classes = [IsPartnerUser] 
#     # permission_classes = [IsAdminUser]

#     @extend_schema(
#         operation_id="partner_pois_list",
#         tags=["Partner-POI"],
#         summary="List all POIs (partner)",
#         description="Retrieve all POIs with optional type/status filtering and pagination. Requires partner token.",
#         parameters=[
#             OpenApiParameter("page", OpenApiTypes.INT, OpenApiParameter.QUERY, description="Page number (default: 1)"),
#             OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY,
#                              description="Items per page (default: 20, max: 100)"),
#             OpenApiParameter("type", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False,
#                              description="Filter by POI type",
#                              enum=["food", "drink", "museum", "park", "historical", "other"]),
#             OpenApiParameter("status", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False,
#                              description="Filter by status", enum=["active", "inactive"]),
#         ],
#         responses={
#             200: OpenApiResponse(response=api_pagination_response_schema("AdminPOIListResponse", POIDetailSerializer(many=True)), description="Paginated list of POIs"),
#             401: OpenApiResponse(description="Unauthorized"),
#             403: OpenApiResponse(description="Forbidden – admin only"),
#         },
#     )
#     def get(self, request):
#         user = request.user
#         page = int(request.query_params.get('page', 1))
#         limit = min(int(request.query_params.get('limit', 20)), 100)
#         poi_type = request.query_params.get('type')
#         poi_status = request.query_params.get('status')

#         qs = Poi.objects.prefetch_related('localized_data')
#         if poi_type:
#             qs = qs.filter(type=poi_type)
#         if poi_status:
#             qs = qs.filter(status=poi_status)
#         if user.role == 'partner':
#             qs = qs.filter(owner=user)

#         total = qs.count()
#         offset = (page - 1) * limit
#         pois = qs[offset: offset + limit]

#         serializer = POIDetailSerializer(pois, many=True)
#         data = {
#             "total": total, "results": serializer.data, "totalPage": math.ceil(total / limit)
#         }
#         return api_response(data=data)

    # @extend_schema(
    #     operation_id='partner_pois_create',
    #     tags=['Partner-POI'],
    #     summary='Tạo POI mới (yêu cầu có POI credit)',
    #     description=(
    #         'Partner tạo POI mới. Yêu cầu `poi_credits >= 1`. '
    #         'Mỗi lần tạo thành công sẽ trừ 1 credit. '
    #         'Mua credit tại: POST /api/payments/buy-poi-credit/'
    #     ),
    #     request={
    #         'multipart/form-data': CreatePOISerializer,
    #     },
    #     responses={
    #         201: OpenApiResponse(response=api_response_schema('PartnerPOICreateResponse', POIDetailSerializer), description='POI created successfully'),
    #         400: OpenApiResponse(description='Invalid request parameters'),
    #         402: OpenApiResponse(description='Không đủ POI credit – cần mua thêm lượt'),
    #         401: OpenApiResponse(description='Unauthorized'),
    #         403: OpenApiResponse(description='Forbidden – partner only'),
    #         409: OpenApiResponse(description='Slug already exists'),
    #     },
    # )
    # def post(self, request):
    #     from django.db import transaction as db_transaction
    #     from accounts.models import User

    #     # ── Kiểm tra credit trước khi xử lý form ──
    #     # Dùng select_for_update để tránh race condition khi nhiều request đồng thời
    #     with db_transaction.atomic():
    #         user = User.objects.select_for_update().get(pk=request.user.pk)
    #         if user.poi_credits <= 0:
    #             return Response(
    #                 {'error': 'Bạn không có lượt tạo POI. Vui lòng mua thêm tại /api/payments/buy-poi-credit/'},
    #                 status=status.HTTP_402_PAYMENT_REQUIRED,
    #             )

    #         serializer = CreatePOISerializer(data=request.data)
    #         if not serializer.is_valid():
    #             errors = serializer.errors
    #             if 'slug' in errors and any('already exists' in str(e) for e in errors['slug']):
    #                 return Response({'error': 'Slug already exists'}, status=status.HTTP_409_CONFLICT)
    #             return Response({'error': 'Invalid request parameters', 'details': errors},
    #                             status=status.HTTP_400_BAD_REQUEST)

    #         vd = serializer.validated_data
    #         image_file = vd.pop('image', None)
    #         audio_file = vd.pop('default_audio', None)
    #         default_name = vd.pop('default_name')
    #         default_description = vd.pop('default_description', '')
    #         default_lang = vd.get('default_lang', 'vi')

    #         poi = Poi.objects.create(**{k: v for k, v in vd.items()}, owner=user)

    #         if image_file:
    #             image_path = f"pois/{poi.id}/image{os.path.splitext(image_file.name)[1]}"
    #             saved_path = default_storage.save(image_path, ContentFile(image_file.read()))
    #             poi.image = build_url(request, saved_path)
    #             poi.save(update_fields=['image'])

    #         audio_url = None
    #         if audio_file:
    #             audio_path = f"pois/{poi.id}/audio_{default_lang}{os.path.splitext(audio_file.name)[1]}"
    #             saved_path = default_storage.save(audio_path, ContentFile(audio_file.read()))
    #             audio_url = build_url(request, saved_path)

    #         LocalizedData.objects.create(
    #             poi=poi,
    #             lang_code=default_lang,
    #             name=default_name,
    #             description=default_description,
    #             audio=audio_url,
    #         )

    #         # ── Trừ 1 credit sau khi tạo POI thành công ──
    #         user.poi_credits -= 1
    #         user.save(update_fields=['poi_credits'])

    #     poi.refresh_from_db()
    #     data = POIDetailSerializer(poi, context={'lang': default_lang}).data
    #     return api_response(
    #         data=data,
    #         message=f'POI created successfully. Số lượt còn lại: {user.poi_credits}',
    #         http_status=201,
    #     )

