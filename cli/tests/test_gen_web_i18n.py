"""Tests for web i18n TS object parsing."""

from __future__ import annotations

from pixfabrica_cli.commands.gen_web_i18n import (
    _legacy_extract_messages,
    _parse_ts_kv_object_body,
)


def test_parse_ts_kv_multiline_and_escape():
    body = """
  foo: 'a\\'b',
  bar: 'x',
  // comment
  a: 'b', c: 'd',
"""
    d = _parse_ts_kv_object_body(body)
    assert d["foo"] == "a'b"
    assert d["bar"] == "x"
    assert d["a"] == "b"
    assert d["c"] == "d"


def test_legacy_extract_from_fixture_snippet():
    ts = """
const en = {
  left_project: 'Project',
  left_fps: 'FPS',
} satisfies Record<string, string>

export type TranslationKey = keyof typeof en

const es: Partial<Record<TranslationKey, string>> = {
  left_project: 'Proyecto',
}

const zhCN: Partial<Record<TranslationKey, string>> = {
  left_fps: '帧率',
}

const TABLE = {}
"""
    out = _legacy_extract_messages(ts)
    assert out["en"] == {"left_project": "Project", "left_fps": "FPS"}
    assert out["es"] == {"left_project": "Proyecto"}
    assert out["zh-CN"] == {"left_fps": "帧率"}
