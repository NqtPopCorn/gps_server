from history.services import syncHistory
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import AccessToken

from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample, inline_serializer
from rest_framework import serializers as drf_serializers

from accounts.serializers import RegisterSerializer, LoginSerializer, UserResponseSerializer
from core.reponse_schema import api_response, api_response_schema
from django.db import transaction

from tours.services import syncUserAvailbleTour

class RegisterView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        summary="Register new user",
        description="Create a new user account with email and password (minimum 8 characters).",
        request=RegisterSerializer,
        responses={
            201: OpenApiResponse(
                response=api_response_schema("RegisterResponse", UserResponseSerializer),
                description="User registered successfully",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "status": 201,
                            "message": "User registered successfully",
                            "data": {
                                "id": "550e8400-e29b-41d4-a716-446655440000",
                                "email": "user@example.com",
                                "role": "tourist",
                                "created_at": "2024-01-01T00:00:00Z",
                                "is_active": True,
                            },
                        },
                    )
                ],
            ),
            400: OpenApiResponse(description="Invalid request parameters"),
            409: OpenApiResponse(description="Email already exists"),
        },
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            errors = serializer.errors
            if 'email' in errors and any('already registered' in str(e) for e in errors['email']):
                return Response({"error": "Email already registered"}, status=status.HTTP_409_CONFLICT)
            return Response({"error": "Invalid request parameters", "details": errors},
                            status=status.HTTP_400_BAD_REQUEST)
                            
        user = serializer.save()
        user_data = UserResponseSerializer(user).data
        return api_response(data=user_data, message="User registered successfully", http_status=201)


class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        summary="User login",
        description="Authenticate user and receive a JWT Bearer token.",
        request=LoginSerializer,
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    name="LoginResponse",
                    fields={
                        "status": drf_serializers.IntegerField(),
                        "message": drf_serializers.CharField(),
                        "data": inline_serializer(
                            name="LoginData",
                            fields={
                                "access_token": drf_serializers.CharField(),
                                "token_type": drf_serializers.CharField(),
                                "user": UserResponseSerializer(),
                            },
                        ),
                    },
                ),
                description="Login successful",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "status": 200,
                            "message": "Login successful",
                            "data": {
                                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                                "token_type": "Bearer",
                                "user": {
                                    "id": "550e8400-e29b-41d4-a716-446655440000",
                                    "email": "user@example.com",
                                    "role": "tourist",
                                    "created_at": "2024-01-01T00:00:00Z",
                                    "is_active": True,
                                },
                            },
                        },
                    )
                ],
            ),
            400: OpenApiResponse(description="Invalid request parameters"),
            401: OpenApiResponse(description="Invalid credentials"),
        },
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"error": "Invalid request parameters", "details": serializer.errors},
                            status=status.HTTP_400_BAD_REQUEST)
        user = serializer.validated_data['user']

        # get device or fingerprint to sync history if exists
        device_id = request.headers.get('X-Device-Id', None)
        if(device_id):
            with transaction.atomic():
                # sync user travel history
                syncHistory(user, device_id)

                # sync user avalable tour
                syncUserAvailbleTour(user, device_id)

        token = AccessToken.for_user(user)
        user_data = UserResponseSerializer(user).data
        data = {
            "access_token": str(token),
            "token_type": "Bearer",
            "user": user_data,
        }


        return api_response(data=data, message="Login successful", http_status=200)

class ProfileView(APIView):
    @extend_schema(
        tags=["Auth"],
        summary="User profile",
        description="Get user profile.",
        responses={
            200: OpenApiResponse(
                response=api_response_schema("ProfileResponse", UserResponseSerializer),
                description="User profile retrieved successfully",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "status": 200,
                            "message": "User profile retrieved successfully",
                            "data": {
                                "id": "550e8400-e29b-41d4-a716-446655440000",
                                "email": "user@example.com",
                                "role": "tourist",
                                "created_at": "2024-01-01T00:00:00Z",
                                "is_active": True,
                            },
                        },
                    )
                ],
            ),
            401: OpenApiResponse(description="Unauthorized"),
        },
    )
    def get(self, request):
        user = request.user
        user_data = UserResponseSerializer(user).data
        
        return api_response(data=user_data, message="User profile retrieved successfully", http_status=200)