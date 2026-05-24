"""Mock parsers that match simgraph BaseParser shape.

Real plugin would `from simgraph.modules.ingest.parsers import ...`.
Mocks let the example run + be tested without simgraph installed.
"""

from __future__ import annotations

import os


class ParseResult:
    def __init__(self, solver, files, metadata=None):
        self.solver = solver
        self.files = files
        self.metadata = metadata or {}


class _Base:
    extensions: list[str] = []
    solver_name: str = ""

    def detect(self, path: str) -> bool:
        raise NotImplementedError

    def parse(self, case_dir: str) -> ParseResult:
        raise NotImplementedError


class MockCGNS(_Base):
    extensions = [".cgns"]
    solver_name = "CGNS"

    def detect(self, p: str) -> bool:
        if os.path.isfile(p):
            return p.lower().endswith(".cgns")
        if os.path.isdir(p):
            return any(f.lower().endswith(".cgns") for f in os.listdir(p))
        return False

    def parse(self, case_dir: str) -> ParseResult:
        # mock: pretend we read it
        return ParseResult(
            solver="CGNS",
            files=[case_dir],
            metadata={"cgns_file_count": 1, "mach": 6.0, "aoa": 4.0},
        )


class MockOpenFOAM(_Base):
    extensions = [".foam"]
    solver_name = "OpenFOAM"

    def detect(self, p: str) -> bool:
        if os.path.isfile(p):
            return p.lower().endswith(".foam")
        if os.path.isdir(p):
            return os.path.exists(os.path.join(p, "system", "controlDict"))
        return False

    def parse(self, case_dir: str) -> ParseResult:
        return ParseResult(
            solver="OpenFOAM",
            files=[case_dir],
            metadata={"application": "simpleFoam", "endTime": 2000.0, "deltaT": 0.005},
        )


class MockFluent(_Base):
    extensions = [".cas", ".cas.h5", ".msh"]
    solver_name = "Fluent"

    def detect(self, p: str) -> bool:
        if os.path.isfile(p):
            low = p.lower()
            return low.endswith(".cas") or low.endswith(".cas.h5") or low.endswith(".msh")
        if os.path.isdir(p):
            return any(f.lower().endswith(".cas") for f in os.listdir(p))
        return False

    def parse(self, case_dir: str) -> ParseResult:
        return ParseResult(
            solver="Fluent",
            files=[case_dir],
            metadata={"solver_type": "pressure_based", "turbulence": "k-omega-sst"},
        )


PARSERS: dict[str, _Base] = {
    "CGNS": MockCGNS(),
    "OpenFOAM": MockOpenFOAM(),
    "Fluent": MockFluent(),
}


def auto_detect(path: str) -> str | None:
    for name, p in PARSERS.items():
        if p.detect(path):
            return name
    return None
