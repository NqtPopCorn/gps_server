from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser, AllowAny
from django.shortcuts import get_object_or_404

from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from tours.models import Tour, TourPoint
from pois.models import Poi
from tours.serializers import (
    TourSerializer, TourDetailSerializer, TourPointSerializer, TourActivationCodeSerializer,
    TourPointDetailInlineSerializer,
    CreateTourSerializer, UpdateTourSerializer,
    AddTourPointSerializer, UpdateTourPointSerializer
)
import django.utils.timezone as timezone
from core.reponse_schema import api_response, api_pagination_response_schema, api_response_schema
from core.cloudinary_helper import upload_image
from django.db import transaction
from django.db.models import F
import math

# ─── PUBLIC TOUR ENDPOINTS ───────────────────────────────────────────────────

class TourListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="tours_list",
        tags=["Tour"],
        summary="Get all tours",
        description="Retrieve all available tour collections with pagination.",
        parameters=[
            OpenApiParameter("page", OpenApiTypes.INT, OpenApiParameter.QUERY,
                             description="Page number (default: 1)"),
            OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY,
                             description="Items per page (default: 20, max: 100)"),
            OpenApiParameter("lang", OpenApiTypes.STR, OpenApiParameter.QUERY,
                             description="Language code for POI content",
                             enum=["vi", "en", "fr", "zh", "ja"]),
            OpenApiParameter("name", OpenApiTypes.STR, OpenApiParameter.QUERY,
                             description="Name of the tour to search for"),
        ],
        responses={
            200: OpenApiResponse(
                response=api_pagination_response_schema("TourListResponse", TourSerializer(many=True)),
                description="Paginated list of tours"
            ),
        },
    )
    def get(self, request):
        page = int(request.query_params.get('page', 1))
        limit = min(int(request.query_params.get('limit', 20)), 100)
        lang = request.query_params.get('lang', 'vi')
        name = request.query_params.get('name', '')

        qs = Tour.objects.filter(status='published', name__icontains=name)
        total = qs.count()
        offset = (page - 1) * limit
        tours = qs[offset: offset + limit]

        data = TourSerializer(tours, many=True, context={'lang': lang}).data
        return api_response(data={"total": total, "results": data, "totalPage": math.ceil(total / limit)})


class TourDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="tours_retrieve",
        tags=["Tour"],
        summary="Get tour detail",
        description="Get a tour with its ordered list of POIs, localized to the requested language.",
        parameters=[
            OpenApiParameter("lang", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True,
                             description="Language code for POI content",
                             enum=["vi", "en", "fr", "zh", "ja"]),
        ],
        responses={
            200: OpenApiResponse(
                response=api_response_schema("TourDetailResponse", TourDetailSerializer),
                description="Tour detail with POIs"
            ),
            400: OpenApiResponse(description="Missing lang parameter"),
            404: OpenApiResponse(description="Tour not found"),
        },
    )
    def get(self, request, id):
        lang = request.query_params.get('lang')
        if not lang:
            return Response({"error": "lang is required"}, status=status.HTTP_400_BAD_REQUEST)
        tour = get_object_or_404(
            Tour.objects.prefetch_related('tour_points__poi__localized_data'), pk=id
        )
        data = TourDetailSerializer(tour, context={'lang': lang}).data
        return api_response(data=data)

from .models import Tour, TourActivationCode
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse, inline_serializer
from rest_framework import serializers

class TourActivationCodeView(APIView):
    @extend_schema(
        summary="Lấy mã QR động kích hoạt Tour",
        description="API phục vụ cơ chế Polling cho màn hình hiển thị tại POI. Tự động cấp mã mới nếu mã cũ hết hạn.",
        tags=['Tour Activation'],
        parameters=[
            OpenApiParameter(name='tour_id', description='ID của Tour', required=True, type=str, location=OpenApiParameter.PATH)
        ],
        responses={
            200: api_response_schema("TourActivationCodeResponse", TourActivationCodeSerializer),
            404: OpenApiResponse(description='Không tìm thấy Tour')
        }
    )
    @transaction.atomic
    def get(self, request, tour_id):
        tour = get_object_or_404(Tour, id=tour_id)
        if tour.status != 'published':
            return Response({"error": "Tour is not active"}, status=status.HTTP_400_BAD_REQUEST)

        activation_code, created = TourActivationCode.objects.get_or_create(tour=tour)

        if created or activation_code.is_expired():
            activation_code.refresh_code(valid_seconds=300)

        remaining_seconds = int((activation_code.expired_at - timezone.now()).total_seconds())
        remaining_seconds = max(0, remaining_seconds) 

        return api_response({
            "tour_id": tour.id,
            "code": activation_code.code,
            "expires_in": remaining_seconds,
            "expired_at": activation_code.expired_at.isoformat()
        })

    @extend_schema(
        summary="Refresh mã QR động kích hoạt Tour",
        description="API phục vụ cơ chế Polling cho màn hình hiển thị tại POI. Tự động cấp mã mới nếu mã cũ hết hạn.",
        tags=['Tour Activation'],
        parameters=[
            OpenApiParameter(name='tour_id', description='ID của Tour', required=True, type=str, location=OpenApiParameter.PATH),
            OpenApiParameter(name='ttl', description='Thời gian sống của mã QR (giây)', required=True, type=int, location=OpenApiParameter.QUERY),
        ],
        responses={
            200: api_response_schema("TourActivationCodeResponse", TourActivationCodeSerializer),
            404: OpenApiResponse(description='Không tìm thấy Tour')
        }
    )
    @transaction.atomic
    def post(self, request, tour_id):
        tour = get_object_or_404(Tour, id=tour_id)
        if tour.status != 'published':
            return Response({"error": "Tour is not active"}, status=status.HTTP_400_BAD_REQUEST)

        ttl = int(request.query_params.get('ttl', 300))
        
        activation_code, created = TourActivationCode.objects.get_or_create(tour=tour)

        activation_code.refresh_code(valid_seconds=ttl)

        remaining_seconds = int((activation_code.expired_at - timezone.now()).total_seconds())
        remaining_seconds = max(0, remaining_seconds) 

        return api_response({
            "tour_id": tour.id,
            "code": activation_code.code,
            "expires_in": remaining_seconds,
            "expired_at": activation_code.expired_at.isoformat()
        })

class TourActivateView(APIView):
    @extend_schema(
        summary="Kích hoạt Tour",
        description="API phục vụ cơ chế Polling cho màn hình hiển thị tại POI. Tự động cấp mã mới nếu mã cũ hết hạn.",
        tags=['Tour Activation'],
        parameters=[
            OpenApiParameter(name='tour_id', description='ID của Tour', required=True, type=str, location=OpenApiParameter.PATH),
            OpenApiParameter(name='code', description='Mã QR (Activation Code)', required=True, type=str, location=OpenApiParameter.QUERY),
        ],
        responses={
            200: api_response_schema("TourActivationCodeResponse", TourActivationCodeSerializer),
            404: OpenApiResponse(description='Không tìm thấy Tour')
        }
    )
    def get(self, request, tour_id):
        tour = get_object_or_404(Tour, id=tour_id)
        if tour.status != 'published':
            return Response({"error": "Tour is not active"}, status=status.HTTP_400_BAD_REQUEST)

        code = request.query_params.get('code')
        if not code:
            return Response({"error": "Code is required"}, status=status.HTTP_400_BAD_REQUEST)

        activation_code = TourActivationCode.objects.filter(code=code).first()
        if not activation_code:
            return Response({"error": "Code is not valid"}, status=status.HTTP_400_BAD_REQUEST)
        if activation_code.is_expired():
            return Response({"error": "Code is expired"}, status=status.HTTP_400_BAD_REQUEST)
        if activation_code.tour != tour:
            return Response({"error": "Code is not valid"}, status=status.HTTP_400_BAD_REQUEST)

        remaining_seconds = int((activation_code.expired_at - timezone.now()).total_seconds())
        remaining_seconds = max(0, remaining_seconds) 

        return api_response({
            "tour_id": tour.id,
            "code": activation_code.code,
            "expires_in": remaining_seconds,
            "expired_at": activation_code.expired_at.isoformat()
        })

# ─── ADMIN TOUR ENDPOINTS ────────────────────────────────────────────────────

class AdminTourListCreateView(APIView):
    # test
    permission_classes = [IsAuthenticated]
    # permission_classes = [IsAdminUser]

    @extend_schema(
        operation_id="admin_tours_list",
        tags=["Admin-Tour"],
        summary="List all tours (admin)",
        description="Retrieve all tours with pagination. Requires admin token.",
        parameters=[
            OpenApiParameter("page", OpenApiTypes.INT, OpenApiParameter.QUERY,
                             description="Page number (default: 1)"),
            OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY,
                             description="Items per page (default: 20, max: 100)"),
        ],
        responses={
            200: OpenApiResponse(
                response=api_pagination_response_schema("AdminTourListResponse", TourSerializer(many=True)),
                description="Paginated list of tours"
            ),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden – admin only"),
        },
    )
    def get(self, request):
        page = int(request.query_params.get('page', 1))
        limit = min(int(request.query_params.get('limit', 20)), 100)
        qs = Tour.objects.all()
        if request.user.role == 'partner':
            qs = qs.filter(partner=request.user)
        total = qs.count()
        offset = (page - 1) * limit
        tours = qs[offset: offset + limit]
        data = TourSerializer(tours, many=True).data
        return api_response(data={"total": total, "results": data, "totalPage": math.ceil(total / limit)})

    @extend_schema(
        tags=["Admin-Tour"],
        summary="Create tour",
        description="Create a new draft tour collection. Requires admin token.",
        request={
            "multipart/form-data": CreateTourSerializer,
        },
        responses={
            201: OpenApiResponse(
                response=api_response_schema("AdminTourCreateResponse", TourSerializer),
                description="Tour created successfully"
            ),
            400: OpenApiResponse(description="Invalid request parameters"),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden – admin only"),
        },
    )
    def post(self, request):
        serializer = CreateTourSerializer(data=request.data)    
        if not serializer.is_valid():
            return Response({"error": "Invalid request parameters", "details": serializer.errors},
                            status=status.HTTP_400_BAD_REQUEST)

        vd = serializer.validated_data
        image_file = vd.pop('image', None)
        tour = Tour.objects.create(**{k: v for k, v in vd.items()})                    

        if image_file:
            tour.image = upload_image(image_file, folder=f"gps_server/tours/{tour.id}")
            tour.save(update_fields=['image'])

        if request.user.role == 'partner':
            tour.partner = request.user
            tour.save(update_fields=['partner'])

        data = TourSerializer(tour).data
        return api_response(data=data, message="Tour created successfully", http_status=201)


class AdminTourDetailView(APIView):
    # test
    permission_classes = [AllowAny]
    # permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin-Tour"],
        summary="Update tour",
        description="Update tour name and/or description. Requires admin token.",
        request={
            "multipart/form-data": UpdateTourSerializer,
        },
        responses={
            200: OpenApiResponse(
                response=api_response_schema("AdminTourUpdateResponse", TourSerializer),
                description="Tour updated successfully"
            ),
            400: OpenApiResponse(description="Invalid request parameters"),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden – admin only"),
            404: OpenApiResponse(description="Tour not found"),
        },
    )
    def put(self, request, id):
        tour = get_object_or_404(Tour, pk=id)
        serializer = UpdateTourSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"error": "Invalid request parameters", "details": serializer.errors},
                            status=status.HTTP_400_BAD_REQUEST)

        vd = serializer.validated_data
        image_file = vd.pop('image', None)
        if image_file:
            vd['image'] = upload_image(image_file, folder=f"gps_server/tours/{tour.id}")

        for attr, value in vd.items():
            setattr(tour, attr, value)
        tour.save()
        data = TourSerializer(tour).data
        return api_response(data=data, message="Tour updated successfully")

    @extend_schema(
        tags=["Admin-Tour"],
        summary="Delete tour",
        description="Delete a tour and all its points. Requires admin token.",
        responses={
            204: OpenApiResponse(description="Tour deleted successfully"),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden – admin only"),
            404: OpenApiResponse(description="Tour not found"),
        },
    )
    def delete(self, request, id):
        tour = get_object_or_404(Tour, pk=id)
        tour.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── ADMIN TOUR POINTS ───────────────────────────────────────────────────────

class AdminTourPointListCreateView(APIView):
    # test
    permission_classes = [AllowAny]
    # permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin-Tour"],
        summary="Add POI to tour",
        description=(
            "Add an existing POI to a tour at a specific position. "
            "Positions must be unique within a tour. Requires admin token."
        ),
        request=AddTourPointSerializer,
        responses={
            201: OpenApiResponse(
                response=api_response_schema("AdminTourPointCreateResponse", TourPointDetailInlineSerializer),
                description="POI added to tour"
            ),
            400: OpenApiResponse(description="Invalid request parameters"),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden – admin only"),
            404: OpenApiResponse(description="Tour or POI not found"),
            409: OpenApiResponse(description="Position already occupied"),
        },
    )
    
    def post(self, request, tour_id):
        tour = get_object_or_404(Tour, pk=tour_id)
        serializer = AddTourPointSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"error": "Invalid request parameters", "details": serializer.errors},
                            status=status.HTTP_400_BAD_REQUEST)
        vd = serializer.validated_data
        poi = get_object_or_404(Poi, pk=vd['poi_id'])

        if TourPoint.objects.filter(tour=tour, position=vd['position']).exists():
            return Response({"error": "Position already occupied"}, status=status.HTTP_409_CONFLICT)

        tp = TourPoint.objects.create(tour=tour, poi=poi, position=vd['position'])
        data = TourPointDetailInlineSerializer(tp).data
        return api_response(data=data, message="POI added to tour", http_status=201)

    @extend_schema(
        tags=["Admin-Tour"],
        summary="Get tour points",
        description="Retrieve all POIs in a tour ordered by position. Requires admin token.",
        responses={
            200: OpenApiResponse(
                response=api_response_schema("AdminTourPointListResponse", TourPointDetailInlineSerializer(many=True)),
                description="List of tour points"
            ),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden – admin only"),
            404: OpenApiResponse(description="Tour not found"),
        },
    )
    def get(self, request, tour_id):
        tour = get_object_or_404(Tour, pk=tour_id)
        points = TourPoint.objects.filter(tour=tour).order_by('position')
        data = TourPointDetailInlineSerializer(points, many=True).data
        return api_response(data=data)


class AdminTourPointDeleteView(APIView):
    # test
    permission_classes = [AllowAny]
    # permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin-Tour"],
        summary="Remove POI from tour",
        description="Remove a specific point (POI) from a tour. Requires admin token.",
        responses={
            204: OpenApiResponse(description="Point removed from tour"),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden – admin only"),
            404: OpenApiResponse(description="Tour or point not found"),
        },
    )
    def delete(self, request, tour_id, point_id):
        tour = get_object_or_404(Tour, pk=tour_id)
        tp = get_object_or_404(TourPoint, pk=point_id, tour=tour)
        tp.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class AdminTourPointUpdateView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Admin-Tour"],
        summary="Update tour point position",
        description="Reorder a POI within a tour by updating its position. Requires admin token.",
        request=UpdateTourPointSerializer(many=True),
        responses={
            200: OpenApiResponse(
                response=api_response_schema("AdminTourPointUpdateResponse", TourPointDetailInlineSerializer(many=True)),
                description="Position updated"
            ),
            400: OpenApiResponse(description="Invalid request parameters"),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden – admin only"),
            404: OpenApiResponse(description="Tour or point not found"),
        }
    )
    # swap/ update position
    @transaction.atomic
    def put(self, request, tour_id):
        tour = get_object_or_404(Tour, pk=tour_id)
        serializer = UpdateTourPointSerializer(data=request.data, many=True)
        if not serializer.is_valid():
            return Response({"error": "Invalid request parameters", "details": serializer.errors},
                            status=status.HTTP_400_BAD_REQUEST)

        ids_to_delete = set(TourPoint.objects.filter(tour=tour).values_list('poi_id', flat=True))

        TourPoint.objects.filter(tour=tour, poi_id__in=ids_to_delete).delete()

        updated = []
        for item in serializer.validated_data:
            tp = TourPoint.objects.create(tour=tour, poi_id=item['poi_id'], position=item['position'])
            updated.append(tp)

        data = TourPointDetailInlineSerializer(updated, many=True).data
        return api_response(data=data, message="Position updated")

