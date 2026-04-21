from django.contrib import admin
from .models import Space, Amenity, SpacePhoto


@admin.register(Amenity)
class AmenityAdmin(admin.ModelAdmin):
    list_display = ['name', 'icon']
    search_fields = ['name']


@admin.register(Space)
class SpaceAdmin(admin.ModelAdmin):
    list_display = ['name', 'space_type', 'capacity', 'price_per_hour', 'price_per_day', 'is_available']
    list_filter = ['space_type', 'is_available']
    search_fields = ['name', 'address']
    filter_horizontal = ['amenities']

@admin.register(SpacePhoto)
class SpacePhotoAdmin(admin.ModelAdmin):
    list_display = ['space', 'is_primary', 'uploaded_at']
    list_filter = ['is_primary']