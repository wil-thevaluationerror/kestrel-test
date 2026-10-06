"""Loading and hashing of configuration.

Config is loaded once per run into a frozen bundle. The bundle also carries the hash of
every config file, which goes into the run manifest: a report is only reproducible if you
know which mappings and tolerances produced it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .contract import (
    FundConfig,
    MappingConfig,
    MetricDictionary,
    PresentationConfig,
    Resolution,
    RulesConfig,
)
from .hashing import sha256_text
from .paths import Layout, display_path


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"missing config file: {path}")
    return yaml.safe_load(path.read_text()) or {}


@dataclass(frozen=True)
class ConfigBundle:
    fund: FundConfig
    rules: RulesConfig
    dictionary: MetricDictionary
    presentation: PresentationConfig
    mappings: dict[str, MappingConfig]  # keyed by template name
    resolutions: tuple[Resolution, ...]
    config_hashes: dict[str, str]
    resolutions_file: str
    resolutions_sha256: str

    def mapping_for(self, template: str) -> MappingConfig:
        if template not in self.mappings:
            raise KeyError(f"no mapping config for template {template!r}")
        return self.mappings[template]


def load_config(layout: Layout, resolutions_path: Path | None = None) -> ConfigBundle:
    """Read every config file, validate it against the contract, and hash it."""
    hashes: dict[str, str] = {}

    def read(path: Path) -> dict:
        raw = path.read_text()
        hashes[display_path(path, layout.root)] = sha256_text(raw)
        return yaml.safe_load(raw) or {}

    fund = FundConfig.model_validate(read(layout.config / "fund.yaml"))
    rules = RulesConfig.model_validate(read(layout.config / "rules.yaml"))
    dictionary = MetricDictionary.model_validate(read(layout.config / "metric_dictionary.yaml"))
    presentation = PresentationConfig.model_validate(read(layout.config / "presentation.yaml"))
    _reject_unknown_presentation_metrics(presentation, dictionary)
    _require_a_tab_for_every_asset_class(fund, presentation)

    mappings: dict[str, MappingConfig] = {}
    for mapping_path in sorted(layout.mappings.glob("*.yaml")):
        mapping = MappingConfig.model_validate(read(mapping_path))
        mappings[mapping.template] = mapping

    res_path = resolutions_path or (layout.config / "resolutions.yaml")
    res_rel = display_path(res_path, layout.root)
    resolutions: tuple[Resolution, ...] = ()
    if res_path.exists():
        payload = read(res_path)
        entries = payload.get("resolutions") or []
        resolutions = tuple(Resolution.model_validate(e) for e in entries)
        _reject_duplicate_resolutions(resolutions)

    return ConfigBundle(
        fund=fund,
        rules=rules,
        dictionary=dictionary,
        presentation=presentation,
        mappings=mappings,
        resolutions=resolutions,
        config_hashes=hashes,
        resolutions_file=res_rel,
        resolutions_sha256=hashes.get(res_rel, ""),
    )


def _reject_unknown_presentation_metrics(
    presentation: PresentationConfig, dictionary: MetricDictionary
) -> None:
    """A headline metric that does not exist would render as an empty lead figure.

    Caught at load so the failure names the config line, not a blank space on the page.
    """
    for asset_class, settings in presentation.asset_classes.items():
        known = dictionary.metrics.get(asset_class)
        if known is None:
            raise ValueError(
                f"config/presentation.yaml describes asset class {asset_class!r}, which has no "
                "entry in config/metric_dictionary.yaml"
            )
        wanted = [
            settings.headline_metric,
            *settings.aggregate_metrics,
            *settings.lower_is_better,
            *settings.neutral_metrics,
        ]
        unknown = sorted({m for m in wanted if m not in known})
        if unknown:
            raise ValueError(
                f"config/presentation.yaml references metrics {unknown} that are not defined "
                f"for asset class {asset_class!r} in config/metric_dictionary.yaml"
            )


def _require_a_tab_for_every_asset_class(
    fund: FundConfig, presentation: PresentationConfig
) -> None:
    """A holding whose asset class has no tab would disappear from the summary.

    The page is built by iterating the tabs, so this is the one place that mismatch can be
    caught before it becomes a silently missing holding.
    """
    missing = sorted(
        {
            holding.asset_class
            for holding in fund.holdings
            if holding.asset_class not in presentation.asset_classes
        }
    )
    if missing:
        raise ValueError(
            f"config/fund.yaml has holdings in asset classes {missing} with no entry in "
            "config/presentation.yaml; they would not appear on the summary"
        )


def _reject_duplicate_resolutions(resolutions: tuple[Resolution, ...]) -> None:
    """Two decisions on one exception means nobody knows which one was applied."""
    seen: set[str] = set()
    for res in resolutions:
        if res.exception_id in seen:
            raise ValueError(
                f"duplicate resolution for {res.exception_id}: one decision per exception"
            )
        seen.add(res.exception_id)
