"""Tests for Pexels settings parsing."""

from __future__ import annotations

from pixfabrica_api import pexels_settings


def test_default_queries_without_env(monkeypatch):
    monkeypatch.delenv("PIXFABRICA_PEXELS_DEFAULT_QUERIES", raising=False)
    assert pexels_settings.pexels_default_queries() == ("inspirational", "music")


def test_default_queries_from_env(monkeypatch):
    monkeypatch.setenv("PIXFABRICA_PEXELS_DEFAULT_QUERIES", " neon , city, neon ")
    assert pexels_settings.pexels_default_queries() == ("neon", "city")


def test_default_queries_falls_back_when_empty(monkeypatch):
    monkeypatch.setenv("PIXFABRICA_PEXELS_DEFAULT_QUERIES", " , , ")
    assert pexels_settings.pexels_default_queries() == ("inspirational", "music")


def test_default_video_queries_without_env(monkeypatch):
    monkeypatch.delenv("PIXFABRICA_PEXELS_DEFAULT_VIDEO_QUERIES", raising=False)
    assert pexels_settings.pexels_default_video_queries() == ("cinematic", "abstract", "motion")


def test_default_video_queries_from_env(monkeypatch):
    monkeypatch.setenv("PIXFABRICA_PEXELS_DEFAULT_VIDEO_QUERIES", " city , neon, city ")
    assert pexels_settings.pexels_default_video_queries() == ("city", "neon")
