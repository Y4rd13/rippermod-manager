"""Tests for FOMOD ModuleConfig.xml parser."""

import pytest

from rippermod_manager.services.fomod_config_parser import (
    GroupType,
    PluginType,
    parse_fomod_config,
)


def _minimal_config_xml(
    module_name: str = "Test Mod",
    group_type: str = "SelectExactlyOne",
    plugin_type: str = "Optional",
) -> bytes:
    return f"""\
<?xml version="1.0" encoding="utf-8"?>
<config xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <moduleName>{module_name}</moduleName>
  <installSteps>
    <installStep name="Step 1">
      <optionalFileGroups>
        <group name="Options" type="{group_type}">
          <plugins>
            <plugin name="Option A">
              <description>Desc A</description>
              <files>
                <file source="a.txt" destination="mods/a.txt" priority="0" />
              </files>
              <typeDescriptor>
                <type name="{plugin_type}" />
              </typeDescriptor>
            </plugin>
          </plugins>
        </group>
      </optionalFileGroups>
    </installStep>
  </installSteps>
</config>
""".encode()


class TestParseMinimalConfig:
    def test_parses_module_name(self):
        config = parse_fomod_config(_minimal_config_xml())
        assert config.module_name == "Test Mod"

    def test_parses_one_step(self):
        config = parse_fomod_config(_minimal_config_xml())
        assert len(config.steps) == 1
        assert config.steps[0].name == "Step 1"

    def test_parses_one_group(self):
        config = parse_fomod_config(_minimal_config_xml())
        assert len(config.steps[0].groups) == 1
        assert config.steps[0].groups[0].name == "Options"

    def test_parses_one_plugin(self):
        config = parse_fomod_config(_minimal_config_xml())
        plugin = config.steps[0].groups[0].plugins[0]
        assert plugin.name == "Option A"
        assert plugin.description == "Desc A"

    def test_parses_file_mapping(self):
        config = parse_fomod_config(_minimal_config_xml())
        plugin = config.steps[0].groups[0].plugins[0]
        assert len(plugin.files) == 1
        assert plugin.files[0].source == "a.txt"
        assert plugin.files[0].destination == "mods/a.txt"
        assert plugin.files[0].priority == 0
        assert plugin.files[0].is_folder is False


class TestRequiredInstallFiles:
    def test_parses_required_files(self):
        xml = b"""\
<?xml version="1.0" encoding="utf-8"?>
<config>
  <moduleName>M</moduleName>
  <requiredInstallFiles>
    <file source="core.dll" destination="bin/core.dll" />
    <folder source="data" destination="data" />
  </requiredInstallFiles>
  <installSteps />
</config>
"""
        config = parse_fomod_config(xml)
        assert len(config.required_install_files) == 2
        assert config.required_install_files[0].source == "core.dll"
        assert config.required_install_files[0].is_folder is False
        assert config.required_install_files[1].source == "data"
        assert config.required_install_files[1].is_folder is True


class TestBOMHandling:
    def test_utf16_le_bom(self):
        xml_text = (
            '<?xml version="1.0"?><config><moduleName>UTF16</moduleName><installSteps /></config>'
        )
        xml_bytes = b"\xff\xfe" + xml_text.encode("utf-16-le")
        config = parse_fomod_config(xml_bytes)
        assert config.module_name == "UTF16"

    def test_utf16_be_bom(self):
        xml_text = (
            '<?xml version="1.0"?><config><moduleName>UTF16BE</moduleName><installSteps /></config>'
        )
        xml_bytes = b"\xfe\xff" + xml_text.encode("utf-16-be")
        config = parse_fomod_config(xml_bytes)
        assert config.module_name == "UTF16BE"

    def test_utf8_bom(self):
        xml_text = (
            '<?xml version="1.0"?><config><moduleName>UTF8BOM</moduleName><installSteps /></config>'
        )
        xml_bytes = b"\xef\xbb\xbf" + xml_text.encode("utf-8")
        config = parse_fomod_config(xml_bytes)
        assert config.module_name == "UTF8BOM"


class TestOrderAttribute:
    def test_descending_steps(self):
        xml = b"""\
<?xml version="1.0"?>
<config>
  <moduleName>M</moduleName>
  <installSteps order="Descending">
    <installStep name="First">
      <optionalFileGroups>
        <group name="G" type="SelectAny"><plugins /></group>
      </optionalFileGroups>
    </installStep>
    <installStep name="Second">
      <optionalFileGroups>
        <group name="G" type="SelectAny"><plugins /></group>
      </optionalFileGroups>
    </installStep>
  </installSteps>
</config>
"""
        config = parse_fomod_config(xml)
        assert config.steps[0].name == "Second"
        assert config.steps[1].name == "First"

    def test_explicit_order_preserves_document_order(self):
        xml = b"""\
<?xml version="1.0"?>
<config>
  <moduleName>M</moduleName>
  <installSteps order="Explicit">
    <installStep name="A">
      <optionalFileGroups>
        <group name="G" type="SelectAny"><plugins /></group>
      </optionalFileGroups>
    </installStep>
    <installStep name="B">
      <optionalFileGroups>
        <group name="G" type="SelectAny"><plugins /></group>
      </optionalFileGroups>
    </installStep>
  </installSteps>
</config>
"""
        config = parse_fomod_config(xml)
        assert config.steps[0].name == "A"
        assert config.steps[1].name == "B"


class TestGroupTypes:
    @pytest.mark.parametrize(
        "type_str,expected",
        [
            ("SelectExactlyOne", GroupType.SELECT_EXACTLY_ONE),
            ("SelectAtMostOne", GroupType.SELECT_AT_MOST_ONE),
            ("SelectAtLeastOne", GroupType.SELECT_AT_LEAST_ONE),
            ("SelectAll", GroupType.SELECT_ALL),
            ("SelectAny", GroupType.SELECT_ANY),
        ],
    )
    def test_parses_group_type(self, type_str, expected):
        config = parse_fomod_config(_minimal_config_xml(group_type=type_str))
        assert config.steps[0].groups[0].type == expected


class TestPluginTypes:
    @pytest.mark.parametrize(
        "type_str,expected",
        [
            ("Required", PluginType.REQUIRED),
            ("Recommended", PluginType.RECOMMENDED),
            ("Optional", PluginType.OPTIONAL),
            ("NotUsable", PluginType.NOT_USABLE),
            ("CouldBeUsable", PluginType.COULD_BE_USABLE),
        ],
    )
    def test_parses_plugin_type(self, type_str, expected):
        config = parse_fomod_config(_minimal_config_xml(plugin_type=type_str))
        plugin = config.steps[0].groups[0].plugins[0]
        assert plugin.type_descriptor.default_type == expected


class TestConditionFlags:
    def test_parses_condition_flags(self):
        xml = b"""\
<?xml version="1.0"?>
<config>
  <moduleName>M</moduleName>
  <installSteps>
    <installStep name="S">
      <optionalFileGroups>
        <group name="G" type="SelectAny">
          <plugins>
            <plugin name="P">
              <files />
              <conditionFlags>
                <flag name="option">selected</flag>
              </conditionFlags>
              <typeDescriptor><type name="Optional" /></typeDescriptor>
            </plugin>
          </plugins>
        </group>
      </optionalFileGroups>
    </installStep>
  </installSteps>
</config>
"""
        config = parse_fomod_config(xml)
        flags = config.steps[0].groups[0].plugins[0].condition_flags
        assert len(flags) == 1
        assert flags[0].name == "option"
        assert flags[0].value == "selected"


class TestDependencyType:
    def test_parses_dependency_type(self):
        xml = b"""\
<?xml version="1.0"?>
<config>
  <moduleName>M</moduleName>
  <installSteps>
    <installStep name="S">
      <optionalFileGroups>
        <group name="G" type="SelectAny">
          <plugins>
            <plugin name="P">
              <files />
              <typeDescriptor>
                <dependencyType>
                  <defaultType name="Optional" />
                  <patterns>
                    <pattern>
                      <dependencies operator="And">
                        <flagDependency flag="f1" value="on" />
                      </dependencies>
                      <type name="Recommended" />
                    </pattern>
                  </patterns>
                </dependencyType>
              </typeDescriptor>
            </plugin>
          </plugins>
        </group>
      </optionalFileGroups>
    </installStep>
  </installSteps>
</config>
"""
        config = parse_fomod_config(xml)
        td = config.steps[0].groups[0].plugins[0].type_descriptor
        assert td.default_type == PluginType.OPTIONAL
        assert len(td.patterns) == 1
        dep, ptype = td.patterns[0]
        assert ptype == PluginType.RECOMMENDED
        assert len(dep.flag_conditions) == 1
        assert dep.flag_conditions[0].name == "f1"


class TestVisibleConditions:
    def test_parses_step_visible(self):
        xml = b"""\
<?xml version="1.0"?>
<config>
  <moduleName>M</moduleName>
  <installSteps>
    <installStep name="S">
      <visible>
        <flagDependency flag="show" value="yes" />
      </visible>
      <optionalFileGroups>
        <group name="G" type="SelectAny"><plugins /></group>
      </optionalFileGroups>
    </installStep>
  </installSteps>
</config>
"""
        config = parse_fomod_config(xml)
        step = config.steps[0]
        assert step.visible is not None
        assert len(step.visible.flag_conditions) == 1
        assert step.visible.flag_conditions[0].name == "show"


class TestConditionalFileInstalls:
    def test_parses_conditional_file_installs(self):
        xml = b"""\
<?xml version="1.0"?>
<config>
  <moduleName>M</moduleName>
  <installSteps />
  <conditionalFileInstalls>
    <patterns>
      <pattern>
        <dependencies operator="And">
          <flagDependency flag="variant" value="A" />
        </dependencies>
        <files>
          <file source="a.dll" destination="bin/a.dll" priority="5" />
        </files>
      </pattern>
    </patterns>
  </conditionalFileInstalls>
</config>
"""
        config = parse_fomod_config(xml)
        assert len(config.conditional_file_installs) == 1
        pattern = config.conditional_file_installs[0]
        assert len(pattern.dependency.flag_conditions) == 1
        assert pattern.dependency.flag_conditions[0].value == "A"
        assert len(pattern.files) == 1
        assert pattern.files[0].priority == 5


class TestBackslashNormalization:
    def test_backslashes_converted(self):
        xml = b"""\
<?xml version="1.0"?>
<config>
  <moduleName>M</moduleName>
  <installSteps>
    <installStep name="S">
      <optionalFileGroups>
        <group name="G" type="SelectAny">
          <plugins>
            <plugin name="P">
              <files>
                <file source="sub\\dir\\file.txt" destination="mods\\out\\file.txt" />
              </files>
              <typeDescriptor><type name="Optional" /></typeDescriptor>
            </plugin>
          </plugins>
        </group>
      </optionalFileGroups>
    </installStep>
  </installSteps>
</config>
"""
        config = parse_fomod_config(xml)
        f = config.steps[0].groups[0].plugins[0].files[0]
        assert "\\" not in f.source
        assert "\\" not in f.destination
        assert f.source == "sub/dir/file.txt"
        assert f.destination == "mods/out/file.txt"


class TestPluginNoFiles:
    def test_plugin_with_no_files_element(self):
        xml = b"""\
<?xml version="1.0"?>
<config>
  <moduleName>M</moduleName>
  <installSteps>
    <installStep name="S">
      <optionalFileGroups>
        <group name="G" type="SelectAny">
          <plugins>
            <plugin name="NoFiles">
              <description>Nothing to install</description>
              <typeDescriptor><type name="Optional" /></typeDescriptor>
            </plugin>
          </plugins>
        </group>
      </optionalFileGroups>
    </installStep>
  </installSteps>
</config>
"""
        config = parse_fomod_config(xml)
        plugin = config.steps[0].groups[0].plugins[0]
        assert plugin.files == []


class TestInvalidXml:
    def test_invalid_xml_raises(self):
        with pytest.raises(ValueError, match="Failed to parse"):
            parse_fomod_config(b"not xml at all")

    def test_empty_bytes_raises(self):
        with pytest.raises(ValueError):
            parse_fomod_config(b"")


class TestMissingOptionalElements:
    def test_empty_config(self):
        xml = b'<?xml version="1.0"?><config />'
        config = parse_fomod_config(xml)
        assert config.module_name == ""
        assert config.module_image == ""
        assert config.required_install_files == []
        assert config.steps == []
        assert config.conditional_file_installs == []
