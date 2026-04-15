from enum import unique
from rest_framework.serializers import ListSerializer
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from pois.models import Poi, LocalizedData
import math

# def _haversine(lat1, lon1, lat2, lon2):
#     """Return distance in meters between two lat/lon points."""
#     R = 6371000  # Earth radius in meters
#     phi1, phi2 = math.radians(lat1), math.radians(lat2)
#     dphi = math.radians(lat2 - lat1)
#     dlambda = math.radians(lon2 - lon1)
#     a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
#     return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

class LocalizationResponseSerializer(serializers.ModelSerializer):
    poi_id = serializers.CharField()

    class Meta:
        model = LocalizedData
        fields = ['id', 'poi_id', 'lang_code', 'name', 'description', 'audio', 'created_at', 'updated_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # LocalizedData doesn't have created_at/updated_at yet; handle gracefully
        for field in ('created_at', 'updated_at'):
            if field not in data:
                data[field] = None
        return data


class LocalizationWriteSerializer(serializers.Serializer):
    lang_code = serializers.ChoiceField(choices=['vi', 'en', 'fr', 'zh', 'ja'])
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    audio = serializers.FileField(required=False)


class POISerializer(serializers.ModelSerializer):
    """Public POI serializer – resolves localized content for a given language."""

    name = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    audio = serializers.SerializerMethodField()
    supported_languages = serializers.SerializerMethodField()

    class Meta:
        model = Poi
        fields = ['id', 'name', 'description', 'audio', 'image', 'latitude', 'longitude', 'type', 'slug', 'supported_languages', 'radius']

    def _get_localized(self, obj):
        lang = self.context.get('lang', obj.default_lang)
        locs = {loc.lang_code: loc for loc in obj.localized_data.all()}
        return locs.get(lang) or locs.get(obj.default_lang) or (list(locs.values())[0] if locs else None)

    def _get_default_localized(self, obj):
        return LocalizedData.objects.filter(poi=obj, lang_code=obj.default_lang).first()

    @extend_schema_field(OpenApiTypes.STR)
    def get_name(self, obj):
        loc = self._get_localized(obj)
        return loc.name if loc else ''

    @extend_schema_field(OpenApiTypes.STR)
    def get_description(self, obj):
        loc = self._get_localized(obj)
        return loc.description if loc else ''

    @extend_schema_field(OpenApiTypes.URI)
    def get_audio(self, obj):
        loc = self._get_localized(obj)
        return loc.audio if loc else None

    @extend_schema_field(serializers.ListSerializer(child=serializers.CharField()))
    def get_supported_languages(self, obj):
        return [loc.lang_code for loc in obj.localized_data.all()]


class POIDetailSerializer(POISerializer):
    """Admin POI serializer – adds extra admin fields."""

    class Meta(POISerializer.Meta):
        fields = POISerializer.Meta.fields + ['radius', 'status', 'default_lang', 'created_at', 'updated_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for field in ('created_at', 'updated_at'):
            if field not in data:
                data[field] = None
        return data


class CreatePOISerializer(serializers.Serializer):
    default_lang = serializers.CharField(max_length=10, default='vi')
    default_name = serializers.CharField(max_length=255, required=True)
    default_description = serializers.CharField(required=True, allow_blank=True)
    default_audio = serializers.FileField(required=True)
    latitude = serializers.FloatField(required=True)
    longitude = serializers.FloatField(required=True)
    radius = serializers.IntegerField(min_value=5)
    image = serializers.FileField(required=True)
    type = serializers.ChoiceField(choices=['food', 'drink', 'museum', 'park', 'historical', 'other'], required=True)
    slug = serializers.SlugField(max_length=150, required=True)

    def validate_slug(self, value):
        if Poi.objects.filter(slug=value).exists():
            raise serializers.ValidationError("Slug already exists")
        return value


class UpdatePOISerializer(serializers.Serializer):
    default_lang = serializers.CharField(max_length=10, required=False)
    latitude = serializers.FloatField(required=False)
    longitude = serializers.FloatField(required=False)
    radius = serializers.IntegerField(required=False, min_value=10)
    image = serializers.FileField(required=False)
    type = serializers.ChoiceField(
        choices=['food', 'drink', 'museum', 'park', 'historical', 'other'], required=False
    )
    slug = serializers.SlugField(required=False, max_length=150)
    status = serializers.ChoiceField(choices=['active', 'inactive'], required=False)
