# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the terms described in the LICENSE file in
# the root directory of this source tree.
"""Persist F5 guardrail URL + API token to a small JSON file (local path or in-cluster mount)."""

from __future__ import annotations

import json
import os
from pathlib import Path


def state_path() -> Path:
    override = os.environ.get("F5_GUARDRAILS_STATE_FILE", "").strip()
    if override:
        return Path(override)
    xdg = os.environ.get("XDG_STATE_HOME", "").strip()
    if xdg:
        return Path(xdg) / "f5-guardrails" / "guardrails_state.json"
    return Path.home() / ".config" / "f5-guardrails" / "guardrails_state.json"


def read_state() -> dict[str, str]:
    p = state_path()
    if not p.is_file():
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return {
            "guardrail_url": str(data.get("guardrail_url", "") or ""),
            "api_token": str(data.get("api_token", "") or ""),
        }
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def write_state(guardrail_url: str, api_token: str) -> None:
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(
            {"guardrail_url": guardrail_url, "api_token": api_token},
            f,
            indent=2,
        )
