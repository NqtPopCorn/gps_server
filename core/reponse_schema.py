from rest_framework import serializers as drf_serializers
from rest_framework.response import Response
from drf_spectacular.utils import inline_serializer


def api_response(data=None, message="Success", http_status=200):
    return Response({"status": http_status, "message": message, "data": data}, status=http_status)

def api_pagination_response_schema(name: str, data_serializer: drf_serializers.Serializer):
    return inline_serializer(
        name=name,
        fields={
            "status": drf_serializers.IntegerField(),
            "message": drf_serializers.CharField(),
            "data": inline_serializer(
                name=f"{name}Data",
                fields={
                    "results": data_serializer if isinstance(data_serializer, drf_serializers.ListSerializer) else data_serializer(),
                    "total": drf_serializers.IntegerField(),
                    "totalPage": drf_serializers.IntegerField()
                }
            )
        }
    )

def api_response_schema(name: str, data_serializer: drf_serializers.Serializer):
    return inline_serializer(
        name=name,
        fields={
            "status": drf_serializers.IntegerField(),
            "message": drf_serializers.CharField(),
            "data": data_serializer if isinstance(data_serializer, drf_serializers.ListSerializer) else data_serializer()
        }
    )

def build_url(request, file_path):
    return request.build_absolute_uri("/media/" + str(file_path))
