"""Tests for TweakXL .yaml and .tweak file parsers."""

from rippermod_manager.schemas.tweakxl import TweakOperation
from rippermod_manager.services.tweakxl_parser import (
    parse_tweak_bytes,
    parse_tweak_file,
    parse_yaml_tweaks,
)


class TestParseYamlTweaks:
    def test_flat_scalar_set(self):
        content = b"Items.GenericJunkItem.quality: Quality.Legendary"
        entries = parse_yaml_tweaks(content, "r6/tweaks/test.yaml", "mod-a")
        assert len(entries) == 1
        assert entries[0].key == "Items.GenericJunkItem.quality"
        assert entries[0].operation == TweakOperation.SET
        assert entries[0].value == "Quality.Legendary"

    def test_nested_record_with_type(self):
        content = b"""
Items.MyItem:
  $type: gamedataItem_Record
  displayName: My Custom Item
  quality: Quality.Legendary
"""
        entries = parse_yaml_tweaks(content, "r6/tweaks/test.yaml", "mod-a")
        keys = {e.key for e in entries}
        assert "Items.MyItem.$type" in keys
        assert "Items.MyItem.displayName" in keys
        assert "Items.MyItem.quality" in keys
        assert all(e.operation == TweakOperation.SET for e in entries)

    def test_append_tag(self):
        content = b"""
Items.SomeRecord.someArray:
  - !append SomeValue
"""
        entries = parse_yaml_tweaks(content, "r6/tweaks/test.yaml", "mod-a")
        assert len(entries) == 1
        assert entries[0].operation == TweakOperation.APPEND
        assert entries[0].value == "SomeValue"

    def test_remove_tag(self):
        content = b"""
Items.SomeRecord.someArray:
  - !remove OldValue
"""
        entries = parse_yaml_tweaks(content, "r6/tweaks/test.yaml", "mod-a")
        assert len(entries) == 1
        assert entries[0].operation == TweakOperation.REMOVE
        assert entries[0].value == "OldValue"

    def test_mixed_append_and_remove(self):
        content = b"""
Items.SomeRecord.tags:
  - !append NewTag
  - !remove OldTag
"""
        entries = parse_yaml_tweaks(content, "r6/tweaks/test.yaml", "mod-a")
        assert len(entries) == 2
        ops = {(e.operation, e.value) for e in entries}
        assert (TweakOperation.APPEND, "NewTag") in ops
        assert (TweakOperation.REMOVE, "OldTag") in ops

    def test_plain_list_defaults_to_append(self):
        content = b"""
Items.SomeRecord.someArray:
  - ValueA
  - ValueB
"""
        entries = parse_yaml_tweaks(content, "r6/tweaks/test.yaml", "mod-a")
        assert len(entries) == 2
        assert all(e.operation == TweakOperation.APPEND for e in entries)

    def test_invalid_yaml_returns_empty(self):
        content = b"{{{{ invalid yaml"
        entries = parse_yaml_tweaks(content, "bad.yaml", "mod-a")
        assert entries == []

    def test_source_file_and_mod_id_propagated(self):
        content = b"Foo.bar: 42"
        entries = parse_yaml_tweaks(content, "r6/tweaks/mymod.yaml", "my-mod")
        assert entries[0].source_file == "r6/tweaks/mymod.yaml"
        assert entries[0].mod_id == "my-mod"

    def test_numeric_value_stringified(self):
        content = b"Items.Foo.weight: 3.14"
        entries = parse_yaml_tweaks(content, "test.yaml", "mod-a")
        assert entries[0].value == "3.14"

    def test_boolean_value_stringified(self):
        content = b"Items.Foo.isHidden: true"
        entries = parse_yaml_tweaks(content, "test.yaml", "mod-a")
        assert entries[0].value == "True"

    def test_null_value_stringified(self):
        content = b"Items.Foo.removed: null"
        entries = parse_yaml_tweaks(content, "test.yaml", "mod-a")
        assert entries[0].value == "null"

    def test_utf8_bom_handled(self):
        content = b"\xef\xbb\xbfItems.Foo.bar: Value"
        entries = parse_yaml_tweaks(content, "test.yaml", "mod-a")
        assert len(entries) == 1
        assert entries[0].value == "Value"

    def test_empty_file_returns_empty(self):
        entries = parse_yaml_tweaks(b"", "empty.yaml", "mod-a")
        assert entries == []

    def test_multi_document_yaml(self):
        content = b"""
Items.Foo.a: 1
---
Items.Bar.b: 2
"""
        entries = parse_yaml_tweaks(content, "test.yaml", "mod-a")
        keys = {e.key for e in entries}
        assert "Items.Foo.a" in keys
        assert "Items.Bar.b" in keys

    def test_append_once_tag(self):
        content = b"""
Items.SomeRecord.someArray:
  - !append-once UniqueValue
"""
        entries = parse_yaml_tweaks(content, "test.yaml", "mod-a")
        assert len(entries) == 1
        assert entries[0].operation == TweakOperation.APPEND
        assert entries[0].value == "UniqueValue"


class TestParseTweakFile:
    def test_simple_set(self):
        content = b"Items.GenericJunkItem.quality = Quality.Legendary"
        entries = parse_tweak_file(content, "r6/tweaks/test.tweak", "mod-a")
        assert len(entries) == 1
        assert entries[0].operation == TweakOperation.SET
        assert entries[0].key == "Items.GenericJunkItem.quality"
        assert entries[0].value == "Quality.Legendary"

    def test_append_operator(self):
        content = b"Items.SomeRecord.someArray += SomeValue"
        entries = parse_tweak_file(content, "test.tweak", "mod-a")
        assert entries[0].operation == TweakOperation.APPEND

    def test_remove_operator(self):
        content = b"Items.SomeRecord.someArray -= OldValue"
        entries = parse_tweak_file(content, "test.tweak", "mod-a")
        assert entries[0].operation == TweakOperation.REMOVE

    def test_comment_lines_skipped(self):
        content = b"""# This is a comment
Items.Foo.bar = Baz
// Another comment
Items.Foo.qux = Quux
"""
        entries = parse_tweak_file(content, "test.tweak", "mod-a")
        assert len(entries) == 2

    def test_blank_lines_skipped(self):
        content = b"""
Items.A.b = 1

Items.C.d = 2

"""
        entries = parse_tweak_file(content, "test.tweak", "mod-a")
        assert len(entries) == 2

    def test_whitespace_trimmed(self):
        content = b"  Items.Foo.bar  =  Value With Spaces  "
        entries = parse_tweak_file(content, "test.tweak", "mod-a")
        assert entries[0].key == "Items.Foo.bar"
        assert entries[0].value == "Value With Spaces"

    def test_empty_file(self):
        entries = parse_tweak_file(b"", "test.tweak", "mod-a")
        assert entries == []


class TestParseTweakBytesDispatch:
    def test_yaml_extension(self):
        content = b"Items.Foo.bar: Value"
        entries = parse_tweak_bytes(content, "r6/tweaks/mod.yaml", "mod-a")
        assert len(entries) == 1

    def test_yml_extension(self):
        content = b"Items.Foo.bar: Value"
        entries = parse_tweak_bytes(content, "r6/tweaks/mod.yml", "mod-a")
        assert len(entries) == 1

    def test_xl_extension_uses_yaml_parser(self):
        content = b"Items.Foo.bar: Value"
        entries = parse_tweak_bytes(content, "r6/tweaks/mod.xl", "mod-a")
        assert len(entries) == 1
        assert entries[0].operation == TweakOperation.SET

    def test_tweak_extension(self):
        content = b"Items.Foo.bar = Value"
        entries = parse_tweak_bytes(content, "r6/tweaks/mod.tweak", "mod-a")
        assert len(entries) == 1

    def test_unknown_extension_returns_empty(self):
        entries = parse_tweak_bytes(b"whatever", "readme.txt", "mod-a")
        assert entries == []
