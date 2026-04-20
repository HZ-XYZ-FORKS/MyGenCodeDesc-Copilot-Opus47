"""Packaging contract — US-packaging.

These tests pin the project's distributable shape so regressions (missing
modules, broken entry point, stale version, src-layout mistakes) surface
immediately. They build a fresh wheel + sdist from the current source
tree into a temp dir, install the wheel into an isolated venv, and
exercise the console script.

Opt-in via RUN_PACKAGING=1 because building a wheel + venv takes several
seconds and requires network for pip on first run (hatchling must be
available in the build env).
"""

from __future__ import annotations

import os
import subprocess
import sys
import venv
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_PACKAGING") != "1",
    reason="opt-in packaging tests; set RUN_PACKAGING=1 to run",
)


def _build(tmp_path: Path) -> tuple[Path, Path]:
    """Build wheel + sdist from REPO_ROOT into tmp_path/dist. Returns
    (wheel_path, sdist_path)."""
    dist = tmp_path / "dist"
    dist.mkdir()
    # python -m build is the canonical way to produce wheel + sdist.
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--sdist",
         "--outdir", str(dist), str(REPO_ROOT)],
        check=True, capture_output=True, text=True,
    )
    wheels = list(dist.glob("*.whl"))
    sdists = list(dist.glob("*.tar.gz"))
    assert len(wheels) == 1, wheels
    assert len(sdists) == 1, sdists
    return wheels[0], sdists[0]


# =============================================================================
# [Typical] Wheel builds and contains the src-layout package with __main__.
# =============================================================================
def test_wheel_contains_expected_modules(tmp_path: Path) -> None:
    wheel, _ = _build(tmp_path)
    with zipfile.ZipFile(wheel) as zf:
        names = set(zf.namelist())

    # Top-level package and key modules must be inside the wheel.
    required = {
        "aggregateGenCodeDesc/__init__.py",
        "aggregateGenCodeDesc/__main__.py",
        "aggregateGenCodeDesc/cli.py",
        "aggregateGenCodeDesc/algorithms/alg_a.py",
        "aggregateGenCodeDesc/algorithms/alg_b.py",
        "aggregateGenCodeDesc/algorithms/alg_c.py",
        "aggregateGenCodeDesc/algorithms/alg_a_svn.py",
    }
    missing = required - names
    assert not missing, f"wheel missing modules: {missing}"

    # Tests and demo artifacts must NOT leak into the wheel.
    leaks = {n for n in names if n.startswith(("tests/", ".demo_", "scripts/"))}
    assert not leaks, f"wheel contains non-distributable paths: {leaks}"


# =============================================================================
# [Typical] Installed wheel exposes the `aggregateGenCodeDesc` console script
# and `python -m aggregateGenCodeDesc` both work.
# =============================================================================
def test_installed_wheel_exposes_cli(tmp_path: Path) -> None:
    wheel, _ = _build(tmp_path)

    venv_dir = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True).create(venv_dir)
    pybin = venv_dir / ("Scripts" if os.name == "nt" else "bin") / "python"
    script = venv_dir / ("Scripts" if os.name == "nt" else "bin") / "aggregateGenCodeDesc"

    subprocess.run(
        [str(pybin), "-m", "pip", "install", "--quiet", str(wheel)],
        check=True, capture_output=True, text=True,
    )

    # Console script lands on PATH.
    assert script.exists(), f"console script not installed at {script}"

    # Console script --help exits 0 and prints usage.
    r1 = subprocess.run(
        [str(script), "--help"], capture_output=True, text=True, timeout=20,
    )
    assert r1.returncode == 0, r1.stderr
    assert "usage: aggregateGenCodeDesc" in r1.stdout

    # python -m aggregateGenCodeDesc --help also works (ensures __main__.py is valid).
    r2 = subprocess.run(
        [str(pybin), "-m", "aggregateGenCodeDesc", "--help"],
        capture_output=True, text=True, timeout=20,
    )
    assert r2.returncode == 0, r2.stderr
    assert "usage: aggregateGenCodeDesc" in r2.stdout


# =============================================================================
# [Edge] sdist contains pyproject.toml and src/ so it is re-buildable.
# =============================================================================
def test_sdist_is_rebuildable(tmp_path: Path) -> None:
    _, sdist = _build(tmp_path)
    import tarfile
    with tarfile.open(sdist) as tf:
        names = tf.getnames()
    # All paths share a top-level project-version/ prefix.
    top = names[0].split("/", 1)[0]
    required = {f"{top}/pyproject.toml",
                f"{top}/src/aggregateGenCodeDesc/__init__.py",
                f"{top}/src/aggregateGenCodeDesc/cli.py"}
    missing = required - set(names)
    assert not missing, f"sdist missing: {missing}"
