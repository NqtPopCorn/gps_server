from pois.models import LocalizedData
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser, AllowAny
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from django.conf import settings
from drf_spectacular.utils import OpenApiResponse
from drf_spectacular.types import OpenApiTypes
from django.shortcuts import get_object_or_404

from pois.models import Poi

from . import services
from core.reponse_schema import api_response_schema, api_response

class TranslateRequestSerializer(serializers.Serializer):
    description = serializers.CharField()
    name = serializers.CharField()
    target_language = serializers.CharField()

class TranslateResponseSerializer(serializers.Serializer):
    name = serializers.CharField()
    description = serializers.CharField()

class TranslateAPIView(APIView):
    # permission_classes = [IsAdminUser]
    permission_classes = [AllowAny]

    @extend_schema(
        request=TranslateRequestSerializer,
        responses={200: api_response_schema("TranslateResponseWrapper", TranslateResponseSerializer)},
        summary="Translate text",
        description="Admin-only endpoint to translate text using Google Gen AI."
    )
    def post(self, request):
        serializer = TranslateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        name = serializer.validated_data['name']
        description = serializer.validated_data['description']
        target_language = serializer.validated_data['target_language']
        
        try:
            res = services.translate_poi_data(name, description, target_language)
            return api_response({
                "name": res["name"],
                "description": res["description"],
                })
        except Exception as e:
            return Response({"error": str(e)}, status=500)

class TTSRequestSerializer(serializers.Serializer):
    text = serializers.CharField()
    # allow both lang_code and locale
    lang_code = serializers.CharField(default="vi")
    gender = serializers.ChoiceField(choices=["Female", "Male"], default="Female")

class TTSResponseSerializer(serializers.Serializer):
    url = serializers.CharField()

class TTSAPIView(APIView):
    # permission_classes = [IsAdminUser]
    permission_classes = [AllowAny]

    @extend_schema(
        request=TTSRequestSerializer,
        responses={200: OpenApiResponse(response=OpenApiTypes.BINARY)},
        summary="Generate text-to-speech",
        description="Admin-only endpoint to generate audio using Edge TTS. Returns attached blob audio file."
    )
    def post(self, request, *args, **kwargs):
        """
            return blob audio file
        """

        serializer = TTSRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        text = serializer.validated_data['text']
        lang_code = serializer.validated_data['lang_code']
        gender = serializer.validated_data['gender']
         
        try:
            from django.http import StreamingHttpResponse
            response = StreamingHttpResponse(services.generate_speech(text, lang_code, gender), content_type="audio/mpeg")
            response['Content-Disposition'] = 'attachment; filename="audio.mp3"'
            return response
        except Exception as e:
            return Response({"error": str(e)}, status=500)
