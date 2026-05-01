from accounts.permissions import HasDeviceId
from django.contrib.auth.models import AnonymousUser
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter

from .serializers import CreateHistorySerializer, HistorySerializer
from .models import History
from core.reponse_schema import api_response, api_response_schema
from django.utils import timezone
from django.db.models import Q



class HistoryView(APIView):
    permission_classes = [HasDeviceId]

    @extend_schema(
        tags=["History"],
        summary="Create history",
        description="Create history",
        request=CreateHistorySerializer,
        responses={
            200: OpenApiResponse(
                response=api_response_schema(
                    "CreateHistoryResponse",
                    CreateHistorySerializer
                ),
                description="History created"
            ),
            400: OpenApiResponse(description="Missing or invalid query parameters"),
        },
    )
    def post(self, request):
        serializer = CreateHistorySerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(serializer.errors, "Invalid data", 400)

        device_id = request.device_id

        user = request.user
        if(isinstance(user, AnonymousUser)):
            user = None
        History.objects.update_or_create(
            user=user,
            poi_id=serializer.validated_data["poi_id"],
            device_id=device_id,
            defaults={
                "created_at": timezone.now()
            }
        )

        return api_response(message="Recorded")

    @extend_schema(
        tags=["History"],
        summary="List history",
        description="List history",
        parameters=[
            OpenApiParameter(
                name="lang_code",
                description="Language code",
                required=False,
                type=str,
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=api_response_schema(
                    "ListHistoryResponse",
                    HistorySerializer(many=True)
                ),
                description="List of histories"
            ),
            400: OpenApiResponse(description="Missing or invalid query parameters"),
        },
    )
    def get(self, request):
        lang_code = request.query_params.get("lang_code", "vi")

        device_id = request.device_id
        user = request.user if not isinstance(request.user, AnonymousUser) else None

        histories = (
            History.objects
            .filter(device_id=device_id)
            .order_by("-created_at")[:20]
        ) if user is None else (
            History.objects
            .filter(user=user)
            .order_by("-created_at")[:20]
        )

        serializer = HistorySerializer(histories, many=True, context={"lang_code": lang_code})
        return api_response(serializer.data)