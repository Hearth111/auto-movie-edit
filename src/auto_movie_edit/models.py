"""Data models representing spreadsheet concepts."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from .utils import Timecode

@dataclass(slots=True)
class TelopPattern:
    """Represents a telop (caption) pattern definition."""
    pattern_id: str
    source: Optional[str] = None
    overrides: Dict[str, Any] = field(default_factory=dict)
    base_width: Optional[int] = None
    base_height: Optional[int] = None
    fps: Optional[float] = None
    description: Optional[str] = None
    notes: Optional[str] = None

@dataclass(slots=True)
class Asset:
    """Represents a single asset (image, audio, part, etc.)."""
    asset_id: str
    kind: Optional[str] = None
    path: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    default_layer: Optional[int] = None
    default_x: Optional[float] = None
    default_y: Optional[float] = None
    default_zoom: Optional[float] = None
    notes: Optional[str] = None

@dataclass(slots=True)
class Pack:
    """Represents a multi-object pack definition."""
    pack_id: str
    source: Optional[str] = None
    overrides: Dict[str, Any] = field(default_factory=dict)
    base_width: Optional[int] = None
    base_height: Optional[int] = None
    fps: Optional[float] = None
    notes: Optional[str] = None

@dataclass(slots=True)
class FxPreset:
    """Represents an FX preset definition referenced from the timeline."""
    fx_id: str
    fx_type: Optional[str] = None
    source: Optional[str] = None
    asset: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class Character:
    """Represents a character with its part definitions."""
    name: str
    parts: Dict[str, str] = field(default_factory=dict)  # part_name -> base_path


@dataclass(slots=True)
class ExpressionPreset:
    """Represents a reusable combination of expression parts."""

    preset_id: str
    character: Optional[str] = None
    tones: List[str] = field(default_factory=list)
    parts: Dict[str, str] = field(default_factory=dict)
    notes: Optional[str] = None

@dataclass(slots=True)
class LayerBand:
    """Represents mapping from a role to a layer band."""
    role: str
    layer: int

@dataclass(slots=True)
class TimelineObject:
    """Represents a non-character object entry on the timeline."""
    role: str
    identifier: str
    layer: Optional[int]
    resolved: Optional[Asset] = None
    source_column: Optional[str] = None

@dataclass(slots=True)
class TimelineFx:
    """Represents FX applied to a timeline row."""
    fx_id: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    source_column: Optional[str] = None
    source_key: Optional[str] = None
    column_index: Optional[int] = None
    resolved: Optional[FxPreset] = None
    applied_parameters: Dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class TimelineRow:
    """Represents a single TIMELINE row from the spreadsheet."""
    index: int
    start: Optional[Timecode]
    end: Optional[Timecode]
    subtitle: Optional[str]
    telop: Optional[str]
    character: Optional[str] = None
    expressions: Dict[str, str] = field(default_factory=dict)
    objects: List[TimelineObject] = field(default_factory=list)
    fxs: List[TimelineFx] = field(default_factory=list)
    packs: List[str] = field(default_factory=list)
    notes: Dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class WorkbookData:
    """Container for all information extracted from the workbook."""

    telop_patterns: Dict[str, TelopPattern] = field(default_factory=dict)
    assets: Dict[str, Asset] = field(default_factory=dict)
    packs: Dict[str, Pack] = field(default_factory=dict)
    fx_presets: Dict[str, FxPreset] = field(default_factory=dict)
    characters: Dict[str, Character] = field(default_factory=dict)
    expression_presets: Dict[str, ExpressionPreset] = field(default_factory=dict)
    layers: Dict[str, LayerBand] = field(default_factory=dict)
    timeline: List[TimelineRow] = field(default_factory=list)
    schema_map: Dict[str, Dict[str, List[str]]] = field(default_factory=dict)

