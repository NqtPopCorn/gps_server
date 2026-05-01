"""
pois/management/commands/update_h3index.py

Cập nhật cột h3_index cho toàn bộ (hoặc một phần) POI dựa trên lat/lon.

Tương thích:
    h3-py >= 4.x  →  h3.latlng_to_cell(lat, lng, resolution)
    h3-py 3.x     →  h3.geo_to_h3(lat, lng, resolution)

Cách dùng:
    python manage.py update_h3index
    python manage.py update_h3index --resolution 8
    python manage.py update_h3index --only-missing        # chỉ row chưa có index
    python manage.py update_h3index --dry-run             # preview, không ghi DB
    python manage.py update_h3index --batch 500
"""

import h3
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from pois.models import Poi

# ── Compat shim: h3-py v3 vs v4 ─────────────────────────────────────────────
if hasattr(h3, "latlng_to_cell"):          # v4+
    def _geo_to_h3(lat: float, lng: float, resolution: int) -> str:
        return h3.latlng_to_cell(lat, lng, resolution)
else:                                       # v3
    def _geo_to_h3(lat: float, lng: float, resolution: int) -> str:
        return h3.geo_to_h3(lat, lng, resolution)
# ─────────────────────────────────────────────────────────────────────────────


class Command(BaseCommand):
    help = "Sinh / cập nhật h3_index cho các POI từ latitude & longitude."

    # ── CLI arguments ─────────────────────────────────────────────────────────

    def add_arguments(self, parser):
        parser.add_argument(
            "--resolution",
            type=int,
            default=9,
            metavar="R",
            help="H3 resolution (0–15). Mặc định: 9 (~150 m edge length).",
        )
        parser.add_argument(
            "--batch",
            type=int,
            default=200,
            metavar="N",
            help="Số row xử lý mỗi lần bulk_update. Mặc định: 200.",
        )
        parser.add_argument(
            "--only-missing",
            action="store_true",
            help="Chỉ cập nhật các POI có h3_index rỗng / null.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Tính toán nhưng không ghi vào DB.",
        )

    # ── Main ──────────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        resolution   = options["resolution"]
        batch_size   = options["batch"]
        only_missing = options["only_missing"]
        dry_run      = options["dry_run"]

        if not (0 <= resolution <= 15):
            raise CommandError("--resolution phải nằm trong khoảng 0–15.")

        qs = Poi.objects.only("id", "latitude", "longitude", "h3_index")
        if only_missing:
            qs = qs.filter(h3_index__in=["", None])

        total = qs.count()

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n{'[DRY-RUN] ' if dry_run else ''}"
            f"Cập nhật h3_index  —  resolution={resolution}  "
            f"(h3-py {h3.__version__})"
        ))
        self.stdout.write(f"  POI cần xử lý : {total}")
        self.stdout.write(f"  Batch size     : {batch_size}")
        self.stdout.write(f"  Chỉ missing    : {only_missing}")
        self.stdout.write("-" * 52)

        if total == 0:
            self.stdout.write(self.style.SUCCESS("Không có POI nào cần cập nhật."))
            return

        updated = skipped = errors = 0
        offset  = 0

        while offset < total:
            batch = list(qs[offset: offset + batch_size])
            to_update = []

            for poi in batch:
                try:
                    new_index = _geo_to_h3(poi.latitude, poi.longitude, resolution)
                except Exception as exc:
                    self.stderr.write(
                        f"  [ERROR] POI {poi.id} "
                        f"(lat={poi.latitude}, lon={poi.longitude}): {exc}"
                    )
                    errors += 1
                    continue

                if poi.h3_index == new_index:
                    skipped += 1
                    continue

                poi.h3_index = new_index
                to_update.append(poi)

            if to_update and not dry_run:
                with transaction.atomic():
                    Poi.objects.bulk_update(to_update, ["h3_index"])

            updated += len(to_update)
            offset  += batch_size

            self.stdout.write(
                f"  [{min(offset, total)}/{total}]  "
                f"updated={updated}  skipped={skipped}  errors={errors}"
            )

        self.stdout.write("-" * 52)
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"[DRY-RUN] Sẽ cập nhật {updated} POI (không có gì được ghi)."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Hoàn thành: {updated} cập nhật | "
                f"{skipped} bỏ qua (không đổi) | "
                f"{errors} lỗi."
            ))