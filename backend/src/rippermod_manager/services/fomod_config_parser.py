"""FOMOD ModuleConfig.xml parser.

Parses the FOMOD installer configuration into frozen dataclasses for
stateless processing. Handles UTF-16/UTF-8 BOM-encoded XML files
commonly found in Nexus Mods archives.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum

import defusedxml.ElementTree as DefusedET

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class GroupType(StrEnum):
    SELECT_EXACTLY_ONE = "SelectExactlyOne"
    SELECT_AT_MOST_ONE = "SelectAtMostOne"
    SELECT_AT_LEAST_ONE = "SelectAtLeastOne"
    SELECT_ALL = "SelectAll"
    SELECT_ANY = "SelectAny"


class PluginType(StrEnum):
    REQUIRED = "Required"
    RECOMMENDED = "Recommended"
    OPTIONAL = "Optional"
    NOT_USABLE = "NotUsable"
    COULD_BE_USABLE = "CouldBeUsable"


class DependencyOperator(StrEnum):
    AND = "And"
    OR = "Or"


class FileState(StrEnum):
    ACTIVE = "Active"
    INACTIVE = "Inactive"
    MISSING = "Missing"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FileMapping:
    source: str
    destination: str
    priority: int
    is_folder: bool


@dataclass(frozen=True)
class FlagSetter:
    name: str
    value: str


@dataclass(frozen=True)
class FlagCondition:
    name: str
    value: str


@dataclass(frozen=True)
class FileCondition:
    file: str
    state: FileState


@dataclass(frozen=True)
class CompositeDependency:
    operator: DependencyOperator
    flag_conditions: list[FlagCondition] = field(default_factory=list)
    file_conditions: list[FileCondition] = field(default_factory=list)
    nested: list[CompositeDependency] = field(default_factory=list)


@dataclass(frozen=True)
class TypeDescriptor:
    default_type: PluginType
    patterns: list[tuple[CompositeDependency, PluginType]] = field(default_factory=list)


@dataclass(frozen=True)
class FomodPlugin:
    name: str
    description: str
    image_path: str
    files: list[FileMapping]
    condition_flags: list[FlagSetter]
    type_descriptor: TypeDescriptor


@dataclass(frozen=True)
class FomodGroup:
    name: str
    type: GroupType
    plugins: list[FomodPlugin]


@dataclass(frozen=True)
class FomodStep:
    name: str
    groups: list[FomodGroup]
    visible: CompositeDependency | None = None


@dataclass(frozen=True)
class ConditionalInstallPattern:
    dependency: CompositeDependency
    files: list[FileMapping]


@dataclass(frozen=True)
class FomodConfig:
    module_name: str
    module_image: str
    required_install_files: list[FileMapping]
    steps: list[FomodStep]
    conditional_file_installs: list[ConditionalInstallPattern]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_path(path: str) -> str:
    """Convert backslashes to forward slashes and strip leading/trailing slashes."""
    return path.replace("\\", "/").strip("/")


def _parse_file_mapping(element, *, is_folder: bool) -> FileMapping:
    src = _normalise_path(element.get("source", ""))
    dst = _normalise_path(element.get("destination", ""))
    try:
        priority = int(element.get("priority", "0"))
    except (ValueError, TypeError):
        priority = 0
    return FileMapping(source=src, destination=dst, priority=priority, is_folder=is_folder)


def _parse_files_element(parent) -> list[FileMapping]:
    files_el = parent.find("files")
    if files_el is None:
        return []
    mappings: list[FileMapping] = []
    for child in files_el:
        tag = child.tag.lower() if child.tag else ""
        if tag == "file":
            mappings.append(_parse_file_mapping(child, is_folder=False))
        elif tag == "folder":
            mappings.append(_parse_file_mapping(child, is_folder=True))
    return mappings


def _parse_flag_conditions(parent) -> list[FlagSetter]:
    flags_el = parent.find("conditionFlags")
    if flags_el is None:
        return []
    setters: list[FlagSetter] = []
    for flag in flags_el:
        name = flag.get("name", "")
        value = flag.text.strip() if flag.text else ""
        if name:
            setters.append(FlagSetter(name=name, value=value))
    return setters


def _parse_composite_dependency(element) -> CompositeDependency:
    operator = DependencyOperator(element.get("operator", "And"))
    flag_conds: list[FlagCondition] = []
    file_conds: list[FileCondition] = []
    nested: list[CompositeDependency] = []

    for child in element:
        tag = child.tag.lower() if child.tag else ""
        if tag == "flagdependency":
            flag_conds.append(
                FlagCondition(
                    name=child.get("flag", ""),
                    value=child.get("value", ""),
                )
            )
        elif tag == "filedependency":
            state_str = child.get("state", "Active")
            try:
                state = FileState(state_str)
            except ValueError:
                state = FileState.ACTIVE
            file_conds.append(
                FileCondition(file=_normalise_path(child.get("file", "")), state=state)
            )
        elif tag == "dependencies":
            nested.append(_parse_composite_dependency(child))

    return CompositeDependency(
        operator=operator,
        flag_conditions=flag_conds,
        file_conditions=file_conds,
        nested=nested,
    )


def _parse_type_descriptor(element) -> TypeDescriptor:
    # Simple <type> element
    type_el = element.find("type")
    if type_el is not None:
        type_name = type_el.get("name", "Optional")
        try:
            default_type = PluginType(type_name)
        except ValueError:
            default_type = PluginType.OPTIONAL
        return TypeDescriptor(default_type=default_type)

    # Complex <dependencyType> with patterns
    dep_type_el = element.find("dependencyType")
    if dep_type_el is not None:
        default_el = dep_type_el.find("defaultType")
        default_name = default_el.get("name", "Optional") if default_el is not None else "Optional"
        try:
            default_type = PluginType(default_name)
        except ValueError:
            default_type = PluginType.OPTIONAL

        patterns_el = dep_type_el.find("patterns")
        patterns: list[tuple[CompositeDependency, PluginType]] = []
        if patterns_el is not None:
            for pattern in patterns_el.findall("pattern"):
                dep_el = pattern.find("dependencies")
                type_el_inner = pattern.find("type")
                if dep_el is not None and type_el_inner is not None:
                    dep = _parse_composite_dependency(dep_el)
                    pat_type_name = type_el_inner.get("name", "Optional")
                    try:
                        pat_type = PluginType(pat_type_name)
                    except ValueError:
                        pat_type = PluginType.OPTIONAL
                    patterns.append((dep, pat_type))

        return TypeDescriptor(default_type=default_type, patterns=patterns)

    return TypeDescriptor(default_type=PluginType.OPTIONAL)


def _parse_plugin(element) -> FomodPlugin:
    name = element.get("name", "")

    desc_el = element.find("description")
    description = desc_el.text.strip() if desc_el is not None and desc_el.text else ""

    image_el = element.find("image")
    image_path = ""
    if image_el is not None:
        image_path = _normalise_path(image_el.get("path", ""))

    files = _parse_files_element(element)
    condition_flags = _parse_flag_conditions(element)

    type_desc_el = element.find("typeDescriptor")
    if type_desc_el is not None:
        type_descriptor = _parse_type_descriptor(type_desc_el)
    else:
        type_descriptor = TypeDescriptor(default_type=PluginType.OPTIONAL)

    return FomodPlugin(
        name=name,
        description=description,
        image_path=image_path,
        files=files,
        condition_flags=condition_flags,
        type_descriptor=type_descriptor,
    )


def _apply_order(items: list, order: str, key_attr: str = "name") -> list:
    """Apply ordering attribute: Explicit (default), Ascending, or Descending."""
    if order == "Ascending":
        return sorted(items, key=lambda x: getattr(x, key_attr, "").lower())
    if order == "Descending":
        return sorted(items, key=lambda x: getattr(x, key_attr, "").lower(), reverse=True)
    return items


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_fomod_config(xml_bytes: bytes) -> FomodConfig:
    """Parse FOMOD ModuleConfig.xml bytes into a FomodConfig dataclass.

    Handles UTF-16 LE/BE BOM and UTF-8 BOM encoded files.

    Raises:
        ValueError: If the XML cannot be parsed.
    """
    try:
        text = xml_bytes
        if text.startswith(b"\xff\xfe") or text.startswith(b"\xfe\xff"):
            text = xml_bytes.decode("utf-16").encode("utf-8")
        elif text.startswith(b"\xef\xbb\xbf"):
            text = xml_bytes[3:]

        root = DefusedET.fromstring(text)
    except Exception as exc:
        raise ValueError(f"Failed to parse FOMOD config XML: {exc}") from exc

    # Module name
    module_name_el = root.find("moduleName")
    module_name = ""
    if module_name_el is not None and module_name_el.text:
        module_name = module_name_el.text.strip()

    # Module image
    module_image_el = root.find("moduleImage")
    module_image = ""
    if module_image_el is not None:
        module_image = _normalise_path(module_image_el.get("path", ""))

    # Required install files
    required_files: list[FileMapping] = []
    req_el = root.find("requiredInstallFiles")
    if req_el is not None:
        for child in req_el:
            tag = child.tag.lower() if child.tag else ""
            if tag == "file":
                required_files.append(_parse_file_mapping(child, is_folder=False))
            elif tag == "folder":
                required_files.append(_parse_file_mapping(child, is_folder=True))

    # Install steps
    steps: list[FomodStep] = []
    steps_el = root.find("installSteps")
    if steps_el is not None:
        steps_order = steps_el.get("order", "Explicit")
        raw_steps: list[FomodStep] = []

        for step_el in steps_el.findall("installStep"):
            step_name = step_el.get("name", "")

            # Visibility condition
            visible: CompositeDependency | None = None
            visible_el = step_el.find("visible")
            if visible_el is not None:
                visible = _parse_composite_dependency(visible_el)

            groups: list[FomodGroup] = []
            groups_el = step_el.find("optionalFileGroups")
            if groups_el is not None:
                groups_order = groups_el.get("order", "Explicit")
                raw_groups: list[FomodGroup] = []

                for group_el in groups_el.findall("group"):
                    group_name = group_el.get("name", "")
                    group_type_str = group_el.get("type", "SelectAny")
                    try:
                        group_type = GroupType(group_type_str)
                    except ValueError:
                        group_type = GroupType.SELECT_ANY

                    plugins: list[FomodPlugin] = []
                    plugins_el = group_el.find("plugins")
                    if plugins_el is not None:
                        plugins_order = plugins_el.get("order", "Explicit")
                        raw_plugins = [_parse_plugin(p) for p in plugins_el.findall("plugin")]
                        plugins = _apply_order(raw_plugins, plugins_order)

                    raw_groups.append(
                        FomodGroup(name=group_name, type=group_type, plugins=plugins)
                    )

                groups = _apply_order(raw_groups, groups_order)

            raw_steps.append(FomodStep(name=step_name, groups=groups, visible=visible))

        steps = _apply_order(raw_steps, steps_order)

    # Conditional file installs
    conditional_installs: list[ConditionalInstallPattern] = []
    cfi_el = root.find("conditionalFileInstalls")
    if cfi_el is not None:
        patterns_el = cfi_el.find("patterns")
        if patterns_el is not None:
            for pattern_el in patterns_el.findall("pattern"):
                dep_el = pattern_el.find("dependencies")
                files_el = pattern_el.find("files")
                if dep_el is not None and files_el is not None:
                    dep = _parse_composite_dependency(dep_el)
                    files: list[FileMapping] = []
                    for child in files_el:
                        tag = child.tag.lower() if child.tag else ""
                        if tag == "file":
                            files.append(_parse_file_mapping(child, is_folder=False))
                        elif tag == "folder":
                            files.append(_parse_file_mapping(child, is_folder=True))
                    conditional_installs.append(
                        ConditionalInstallPattern(dependency=dep, files=files)
                    )

    return FomodConfig(
        module_name=module_name,
        module_image=module_image,
        required_install_files=required_files,
        steps=steps,
        conditional_file_installs=conditional_installs,
    )
