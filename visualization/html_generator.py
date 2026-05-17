from __future__ import annotations

from typing import Any, Dict

from .htmlgen.generator import build_html_from_saved_result
from .htmlgen.parameter_charts import build_parameter_charts_html

__all__ = ["build_html_from_saved_result", "build_parameter_charts_html"]
