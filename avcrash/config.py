"""Read config/paper.yaml into a plain object."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "paper.yaml"


@dataclass(frozen=True)
class Window:
    name: str
    years: List[int]
    selection_years: List[int]
    train_years: List[int]
    test_year: int


@dataclass(frozen=True)
class Setup:
    name: str
    window: Window
    train_region: Optional[str]  # None = citywide temporal holdout

    @property
    def test_region(self) -> Optional[str]:
        if self.train_region is None:
            return None
        return "east" if self.train_region == "west" else "west"


class Config:
    def __init__(self, raw: dict, root: Path = ROOT):
        self.raw = raw
        self.root = root
        d = raw["data"]
        self.data_dir = (root / d["dir"]).resolve()
        self.files = {k: self.data_dir / v for k, v in d.items() if k.endswith(("_csv", "_shapefile"))}
        self.city = d["city"]
        self.av_mode = d["av_mode"]
        self.crs = raw["crs"]
        self.zones = raw["zones"]
        self.exposure: Dict[int, Dict[str, float]] = {int(k): v for k, v in raw["exposure"].items()}
        self.windows = {
            k: Window(k, list(v["years"]), list(v["selection_years"]), list(v["train_years"]), int(v["test_year"]))
            for k, v in raw["windows"].items()
        }
        self.geosplit = raw["geosplit"]
        self.screening = raw["screening"]
        self.selection = raw["selection"]
        self.fit = raw["fit"]
        self.uncertainty = raw["uncertainty"]
        self.setups = {k: self._setup(k, v) for k, v in raw["setups"].items()}
        self.extra_setups = {k: self._setup(k, v) for k, v in raw.get("extra_setups", {}).items()}

    def _setup(self, name: str, v: dict) -> Setup:
        return Setup(name, self.windows[v["window"]], v.get("train_region"))

    def setup(self, name: str) -> Setup:
        return {**self.setups, **self.extra_setups}[name]


def load_config(path: Optional[Path] = None) -> Config:
    path = Path(path) if path is not None else DEFAULT_CONFIG
    with open(path) as fh:
        return Config(yaml.safe_load(fh))
