from rest_framework import serializers
from .models import History
from pois.serializers import POISerializer


class CreateHistorySerializer(serializers.Serializer):
    poi_id = serializers.UUIDField(required=True)

class HistorySerializer(serializers.ModelSerializer):
    poi = POISerializer()

    class Meta:
        model = History
        fields = ["poi", "created_at"]