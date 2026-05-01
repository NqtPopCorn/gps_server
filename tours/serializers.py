from django.utils import timezone
from payments.models import UserAvailableTour
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field, extend_schema_serializer
from drf_spectacular.types import OpenApiTypes
from tours.models import Tour, TourPoint
from pois.serializers import POISerializer
from rest_framework.serializers import ListSerializer

class TourPointDetailInlineSerializer(serializers.Serializer):
    id = serializers.CharField()
    position = serializers.IntegerField()
    poi = POISerializer()

class TourSerializer(serializers.ModelSerializer):
    point_count = serializers.SerializerMethodField()

    class Meta:
        model = Tour
        fields = ['id', 'name', 'description', 'point_count', 'image', 'created_at', 'updated_at', 'status']

    @extend_schema_field(OpenApiTypes.INT)
    def get_point_count(self, obj):
        return obj.tour_points.count()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for field in ('created_at', 'updated_at'):
            if field not in data:
                data[field] = None
        return data


class TourPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = TourPoint
        fields = ['id', 'tour_id', 'poi_id', 'position', 'image']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        return data

class TourDetailSerializer(TourSerializer):
    pois = serializers.SerializerMethodField()
    can_start = serializers.SerializerMethodField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    currency = serializers.CharField(max_length=3, read_only=True)

    class Meta(TourSerializer.Meta):
        fields = TourSerializer.Meta.fields + ['pois', 'can_start', 'price', 'currency']

    @extend_schema_field(TourPointDetailInlineSerializer(many=True))
    def get_pois(self, obj):
        lang = self.context.get('lang', 'en')
        result = []
        for tp in obj.tour_points.select_related('poi').prefetch_related('poi__localized_data'):
            poi_data = POISerializer(tp.poi, context={**self.context, 'lang': lang}).data
            result.append({'position': tp.position, 'poi': poi_data})
        return result

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_can_start(self, obj):
        user = self.context.get('user')
        if not user:
            return False    
        return UserAvailableTour.objects.filter(user=user, tour=obj, expired_at__gt=timezone.now()).exists()

class AddTourPointSerializer(serializers.Serializer):
    poi_id = serializers.CharField()
    position = serializers.IntegerField(min_value=1)

class UpdateTourPointSerializer(serializers.Serializer):
    poi_id = serializers.CharField()
    position = serializers.IntegerField(min_value=1)

class CreateTourSerializer(serializers.ModelSerializer):
    image = serializers.FileField(required=False)

    class Meta:
        model = Tour
        fields = ['name', 'description', 'image', 'status']

class UpdateTourSerializer(serializers.ModelSerializer):
    image = serializers.FileField(required=False)

    class Meta:
        model = Tour
        fields = ['name', 'description', 'image', 'status']
        read_only_fields = ['id', 'created_at', 'updated_at']

class TourActivationCodeSerializer(serializers.Serializer):
    tour_id = serializers.CharField(help_text="ID của Tour")
    code = serializers.CharField(help_text="Mã QR (Activation Code)")
    expires_in = serializers.IntegerField(help_text="Số giây còn lại")
    expired_at = serializers.DateTimeField(help_text="Thời điểm hết hạn")
