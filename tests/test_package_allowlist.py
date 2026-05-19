"""Tests for src/ham/package_allowlist.py — Phase 1 #6."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.ham import builder_chat_scaffold
from src.ham.builder_error_codes import PREVIEW_PACKAGE_INSTALL_DENIED
from src.ham.package_allowlist import (
    AllowlistRecord,
    PackageAllowlist,
    check_install_allowed,
    is_allowed,
    list_allowed,
    load_from_yaml,
    packages_from_package_json,
    packages_from_requirements,
    set_package_allowlist_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    set_package_allowlist_for_tests(None)
    yield
    set_package_allowlist_for_tests(None)


class TestPredicate:
    def test_npm_allowed_and_denied(self) -> None:
        record = AllowlistRecord(npm=frozenset({"react", "vite"}), pip=frozenset())
        allowlist = PackageAllowlist(record)
        assert allowlist.is_allowed("react", "npm") is True
        assert allowlist.is_allowed("React", "npm") is True
        assert allowlist.is_allowed("left-pad", "npm") is False

    def test_pip_allowed_and_denied(self) -> None:
        record = AllowlistRecord(npm=frozenset(), pip=frozenset({"fastapi", "pydantic"}))
        allowlist = PackageAllowlist(record)
        assert allowlist.is_allowed("fastapi", "pip") is True
        assert allowlist.is_allowed("requests", "pip") is False

    def test_unknown_manager_raises(self) -> None:
        record = AllowlistRecord(npm=frozenset({"react"}), pip=frozenset())
        allowlist = PackageAllowlist(record)
        with pytest.raises(ValueError, match="Unknown manager"):
            allowlist.list_allowed("cargo")  # type: ignore[arg-type]

    def test_list_allowed_sorted(self) -> None:
        record = AllowlistRecord(npm=frozenset({"vite", "react"}), pip=frozenset({"uvicorn"}))
        allowlist = PackageAllowlist(record)
        assert allowlist.list_allowed("npm") == ["react", "vite"]
        assert allowlist.list_allowed("pip") == ["uvicorn"]


class TestYamlRoundTrip:
    def test_load_from_yaml(self, tmp_path: Path) -> None:
        path = tmp_path / "allowlist.yaml"
        path.write_text(
            "version: '2'\nnpm:\n  - react\npip:\n  - fastapi\n",
            encoding="utf-8",
        )
        record = load_from_yaml(path)
        assert record.version == "2"
        assert "react" in record.npm
        assert "fastapi" in record.pip

    def test_default_yaml_loads(self) -> None:
        record = load_from_yaml()
        assert "react" in record.npm
        assert "fastapi" in record.pip


class TestInstallCommandGate:
    def test_npm_install_denies_unknown_package(self) -> None:
        pkg_json = json.dumps({"dependencies": {"react": "^18", "evil-pkg": "1.0.0"}})
        denial = check_install_allowed(
            ["npm", "install"],
            source_files={"package.json": pkg_json},
        )
        assert denial is not None
        assert denial.error_code == PREVIEW_PACKAGE_INSTALL_DENIED
        assert denial.error_details == {"package": "evil-pkg", "manager": "npm"}

    def test_npm_install_allows_scaffold_packages(self) -> None:
        pkg_json = json.dumps(
            {
                "dependencies": {"react": "^18.3.1", "react-dom": "^18.3.1"},
                "devDependencies": {
                    "vite": "^5.4.11",
                    "@vitejs/plugin-react": "^4.3.4",
                    "typescript": "^5.0.0",
                },
            }
        )
        assert check_install_allowed(["npm", "install"], source_files={"package.json": pkg_json}) is None

    def test_pip_install_denies_unknown_package(self) -> None:
        denial = check_install_allowed(["pip", "install", "malicious-lib"])
        assert denial is not None
        assert denial.error_code == PREVIEW_PACKAGE_INSTALL_DENIED

    def test_pip_install_from_requirements(self) -> None:
        denial = check_install_allowed(
            ["pip", "install"],
            source_files={"requirements.txt": "fastapi\nmalware\n"},
        )
        assert denial is not None
        assert denial.error_details["package"] == "malware"


class TestScaffoldCoverage:
    def test_calculator_scaffold_packages_are_allowlisted(self) -> None:
        files, _meta = builder_chat_scaffold._build_react_scaffold_files(  # noqa: SLF001
            "build a calculator app",
        )
        body = files.get("package.json")
        assert body is not None
        for package in packages_from_package_json(body):
            assert is_allowed(package, "npm"), package


class TestParsingHelpers:
    def test_packages_from_requirements_strips_pins(self) -> None:
        assert packages_from_requirements("fastapi>=0.1\n# comment\npydantic==2") == [
            "fastapi",
            "pydantic",
        ]
