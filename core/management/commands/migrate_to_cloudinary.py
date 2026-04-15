"""
Management command: migrate_to_cloudinary

Scan Poi (image), LocalizedData (audio) and Tour (image) records that still hold
local /media/... URLs, upload the physical files to Cloudinary and update the DB
with the returned secure_url.

Usage:
    python manage.py migrate_to_cloudinary
    python manage.py migrate_to_cloudinary --delete-local   # also remove local files
"""
import os
import re

from django.core.management.base import BaseCommand
from django.conf import settings

import cloudinary.uploader

from pois.models import Poi, LocalizedData
from tours.models import Tour


# Any URL that starts with /media/ or http(s)://host/media/ is considered local
_LOCAL_RE = re.compile(r"(/media/|\\media\\)")


def _is_local(url: str) -> bool:
    return url and bool(_LOCAL_RE.search(url))


def _physical_path(url: str) -> str:
    """Convert an absolute or relative /media/... URL to a filesystem path."""
    # strip everything before /media/
    match = re.search(r"/media/(.+)", url.replace("\\", "/"))
    if not match:
        return None
    relative = match.group(1)
    return os.path.join(settings.MEDIA_ROOT, relative)


class Command(BaseCommand):
    help = "Migrate local media files (images & audio) to Cloudinary"

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete-local",
            action="store_true",
            default=False,
            help="Delete the local file after a successful upload to Cloudinary",
        )

    def handle(self, *args, **options):
        delete_local: bool = options["delete_local"]

        self.stdout.write(self.style.MIGRATE_HEADING("=== Migrating POI images ==="))
        self._migrate_poi_images(delete_local)

        self.stdout.write(self.style.MIGRATE_HEADING("=== Migrating LocalizedData audio ==="))
        self._migrate_audio(delete_local)

        self.stdout.write(self.style.MIGRATE_HEADING("=== Migrating Tour images ==="))
        self._migrate_tour_images(delete_local)

        self.stdout.write(self.style.SUCCESS("Migration complete!"))

    # ── POI images ───────────────────────────────────────────────────────────

    def _migrate_poi_images(self, delete_local: bool):
        pois = Poi.objects.exclude(image__isnull=True).exclude(image="")
        total = pois.count()
        self.stdout.write(f"Found {total} POIs with image.")

        for poi in pois:
            if not _is_local(poi.image):
                self.stdout.write(f"  [SKIP] POI {poi.id} – already on Cloudinary")
                continue

            path = _physical_path(poi.image)
            if not path or not os.path.exists(path):
                self.stdout.write(
                    self.style.WARNING(f"  [WARN] POI {poi.id} – file not found: {path}")
                )
                continue

            try:
                result = cloudinary.uploader.upload(
                    path,
                    folder=f"gps_server/pois/{poi.id}",
                    overwrite=True,
                    resource_type="image",
                )
                poi.image = result["secure_url"]
                poi.save(update_fields=["image"])
                self.stdout.write(self.style.SUCCESS(f"  [OK] POI {poi.id} -> {poi.image}"))

                if delete_local and os.path.exists(path):
                    os.remove(path)
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  [ERR] POI {poi.id}: {exc}"))

    # ── LocalizedData audio ───────────────────────────────────────────────────

    def _migrate_audio(self, delete_local: bool):
        locs = LocalizedData.objects.exclude(audio__isnull=True).exclude(audio="")
        total = locs.count()
        self.stdout.write(f"Found {total} LocalizedData records with audio.")

        for loc in locs:
            if not _is_local(loc.audio):
                self.stdout.write(f"  [SKIP] LocalizedData {loc.id} – already on Cloudinary")
                continue

            path = _physical_path(loc.audio)
            if not path or not os.path.exists(path):
                self.stdout.write(
                    self.style.WARNING(f"  [WARN] LocalizedData {loc.id} – file not found: {path}")
                )
                continue

            try:
                result = cloudinary.uploader.upload(
                    path,
                    folder=f"gps_server/pois/{loc.poi_id}",
                    overwrite=True,
                    resource_type="auto",
                )
                loc.audio = result["secure_url"]
                loc.save(update_fields=["audio"])
                self.stdout.write(
                    self.style.SUCCESS(f"  [OK] LocalizedData {loc.id} ({loc.lang_code}) -> {loc.audio}")
                )

                if delete_local and os.path.exists(path):
                    os.remove(path)
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  [ERR] LocalizedData {loc.id}: {exc}"))

    # ── Tour images ───────────────────────────────────────────────────────────

    def _migrate_tour_images(self, delete_local: bool):
        tours = Tour.objects.exclude(image__isnull=True).exclude(image="")
        total = tours.count()
        self.stdout.write(f"Found {total} Tours with image.")

        for tour in tours:
            if not _is_local(tour.image):
                self.stdout.write(f"  [SKIP] Tour {tour.id} – already on Cloudinary")
                continue

            path = _physical_path(tour.image)
            if not path or not os.path.exists(path):
                self.stdout.write(
                    self.style.WARNING(f"  [WARN] Tour {tour.id} – file not found: {path}")
                )
                continue

            try:
                result = cloudinary.uploader.upload(
                    path,
                    folder=f"gps_server/tours/{tour.id}",
                    overwrite=True,
                    resource_type="image",
                )
                tour.image = result["secure_url"]
                tour.save(update_fields=["image"])
                self.stdout.write(self.style.SUCCESS(f"  [OK] Tour {tour.id} -> {tour.image}"))

                if delete_local and os.path.exists(path):
                    os.remove(path)
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  [ERR] Tour {tour.id}: {exc}"))
