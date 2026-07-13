"""Tests for file upload policy indexing and helpers."""

from __future__ import annotations

from pathlib import Path

from PIL import Image as PILImage

from pixfabrica_core.file_upload_policy import (
    ContentThumbFactorPolicy,
    DisplayWidthFactorPolicy,
    JobBoundsFactorPolicy,
    UploadPolicyContext,
    VinylCoverFactorPolicy,
    build_file_upload_policy_index,
    collect_file_upload_policies,
    manifest_covers_max_px,
)
from pixfabrica_core.image_optimize import optimize_image_file
from pixfabrica_core.upload_manifest import write_upload_manifest
from pixfabrica_std.image.background_image import BackgroundImage
from pixfabrica_std.image.image import Image
from pixfabrica_std.image.vinyl_record import VinylRecord
from pixfabrica_std.player.mini_track_card import MiniTrackCard
from pixfabrica_std.player.track_card import TrackCard


def test_background_image_declares_source_upload_policy():
    policy = BackgroundImage.source_upload_policy()
    assert isinstance(policy, JobBoundsFactorPolicy)
    assert policy.factor == 1.5


def test_job_bounds_factor_policy_uses_project_dimensions():
    policy = JobBoundsFactorPolicy(factor=2.0)
    ctx = UploadPolicyContext(
        clip_type="std-background-image",
        plugin_id="pixfabrica-std",
        field="source",
        kind="image",
        target_width=1920,
        target_height=1080,
    )
    assert policy.max_px(ctx) == 3840
    assert policy.max_px_from_bounds(1080, 1080) == 2160


def test_collect_file_upload_policies_from_background_image():
    policies = collect_file_upload_policies(BackgroundImage)
    assert "source" in policies
    assert isinstance(policies["source"], JobBoundsFactorPolicy)


def test_build_file_upload_policy_index_includes_background_image():
    class _Plugin:
        clip_types = [BackgroundImage]

    index = build_file_upload_policy_index([_Plugin()])
    assert ("std-background-image", "source") in index


def test_optimize_image_file_preserves_aspect_ratio(tmp_path: Path):
    src = tmp_path / "wide.png"
    PILImage.new("RGB", (4000, 1200), color=(255, 0, 0)).save(src)

    result = optimize_image_file(src, max_px=3840)

    assert result.resized is True
    assert result.optimized_for.width == 3840
    assert result.optimized_for.height == 1152
    with PILImage.open(src) as saved:
        assert saved.size == (3840, 1152)


def test_manifest_covers_max_px(tmp_path: Path):
    media = tmp_path / "bg.png"
    media.write_bytes(b"png")
    write_upload_manifest(
        media,
        clip_type="std-background-image",
        plugin_id="pixfabrica-std",
        kind="image",
        size=3,
        content_sha256="abc",
        optimized_for={"width": 3840, "height": 1152, "fps": 0.0},
    )
    assert manifest_covers_max_px(media, 3840) is True
    assert manifest_covers_max_px(media, 3000) is False


def test_vinyl_record_declares_source_upload_policy():
    policy = VinylRecord.source_upload_policy()
    assert isinstance(policy, VinylCoverFactorPolicy)
    assert policy.factor == 1.2
    assert policy.disc_bake_max_px == 768.0


def test_vinyl_record_cover_cap_uses_node_factor():
    policy = VinylRecord.source_upload_policy()
    # 1920×1080 → disc capped at 768 → 1.2×768 = 921.6 → 921
    assert policy.cover_max_px(1920, 1080) == 921


def test_vinyl_cover_factor_policy_caps_at_disc_bake_max():
    policy = VinylCoverFactorPolicy(factor=2.0, disc_bake_max_px=768.0)
    # 1920×1080 job → min inner edge 1080 → disc capped at 768 → cover cap 1536
    assert policy.cover_max_px(1920, 1080) == 1536
    # 640×640 job → disc 640 → cover cap 1280
    assert policy.cover_max_px(640, 640) == 1280


def test_vinyl_cover_respects_width():
    policy = VinylCoverFactorPolicy(factor=2.0, disc_bake_max_px=768.0)
    # 1920×1080, width 50% → layout min(960, 1080) = 960 → disc capped at 768 → 1536
    assert policy.cover_max_px(1920, 1080, width_frac=0.5) == 1536


def test_track_card_declares_source_upload_policy():
    policy = TrackCard.source_upload_policy()
    assert isinstance(policy, ContentThumbFactorPolicy)
    assert policy.factor == 2.0
    assert policy.thumb_max_px == 512.0


def test_content_thumb_factor_policy_uses_layout_defaults():
    policy = ContentThumbFactorPolicy(factor=2.0, thumb_max_px=512.0)
    # 1920×1080, band 10% → side ≈ 84.6 → 169
    assert policy.max_px_from_bounds(1920, 1080) == 169


def test_content_thumb_factor_policy_reads_clip_params():
    policy = ContentThumbFactorPolicy(factor=2.0, thumb_max_px=512.0)
    ctx = UploadPolicyContext(
        clip_type="std-track-card",
        plugin_id="pixfabrica-std",
        field="source",
        kind="image",
        target_width=800,
        target_height=600,
        clip_params={
            "padding_y": 0.0,
            "cover_scale": 0.5,
            "progress_height": 0.0,
            "band_height": 1.0,
        },
    )
    assert policy.max_px(ctx) == 600


def test_collect_file_upload_policies_from_track_card():
    policies = collect_file_upload_policies(TrackCard)
    assert "source" in policies
    assert isinstance(policies["source"], ContentThumbFactorPolicy)


def test_collect_file_upload_policies_from_mini_track_card():
    policies = collect_file_upload_policies(MiniTrackCard)
    assert "source" in policies
    assert isinstance(policies["source"], ContentThumbFactorPolicy)


def test_image_declares_display_width_upload_policy():
    policy = Image.source_upload_policy()
    assert isinstance(policy, DisplayWidthFactorPolicy)
    assert policy.factor == 2.0
    assert policy.min_px == 64


def test_collect_file_upload_policies_from_image():
    policies = collect_file_upload_policies(Image)
    assert "source" in policies
    assert isinstance(policies["source"], DisplayWidthFactorPolicy)


def test_build_file_upload_policy_index_includes_image():
    class _Plugin:
        clip_types = [Image]

    index = build_file_upload_policy_index([_Plugin()])
    assert ("std-image", "source") in index
