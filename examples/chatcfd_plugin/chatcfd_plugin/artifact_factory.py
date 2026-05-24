"""CFDArtifactFactory — turn tool results into UI-renderable artifacts.

For loadFile: a mesh artifact (mesh blob hash + zones) so the front-end
can fetch and render it via VTK.js.
For calculate: an inline chart/table artifact.
For exportData: a downloadable-file artifact.

This stays in chatcfd. Framework only carries the dict through.
"""

from __future__ import annotations

import hashlib
from typing import Any

from agentkit.plugin.artifact_factory import ArtifactFactory


class CFDArtifactFactory(ArtifactFactory):
    def make(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any,
    ) -> dict[str, Any] | None:
        if not isinstance(result, dict) or "error" in result:
            return None

        if tool_name == "loadFile":
            mesh = result.get("data") or b""
            return {
                "kind": "mesh",
                "title": f"Mesh — {arguments.get('case')}",
                "session_id": result.get("session_id"),
                "zones": result.get("zones", []),
                "mesh_hash": hashlib.sha1(mesh).hexdigest()[:12],
                "cells": result.get("cells"),
                # real chatcfd: include URL like /api/mesh/{session}/{zone}
            }

        if tool_name == "calculate":
            return {
                "kind": "table",
                "title": f"calculate({arguments.get('method')})",
                "values": result.get("values") or result.get("rows"),
            }

        if tool_name == "exportData":
            return {
                "kind": "file",
                "title": "Download",
                "files": result.get("output_files", []),
            }

        return None
