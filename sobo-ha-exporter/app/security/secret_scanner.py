"""Static secret scanner for inspecting generated export content before git commit."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar


@dataclass
class SecretFindingDetail:
    relative_path: str
    extension: str
    size_bytes: int
    rule_name: str
    line_number: int | None = None


@dataclass
class SecretScanResult:
    has_secrets: bool
    findings: list[str] = field(default_factory=list)
    detailed_findings: list[SecretFindingDetail] = field(default_factory=list)


KNOWN_UI_LABELS = {
    "password",
    "enter password",
    "passwort",
    "mot de passe",
    "contraseña",
    "senha",
    "wachtwoord",
    "lösenord",
    "adgangskode",
    "api key",
    "secret",
    "client secret",
    "user password",
    "optional password",
    "token",
    "access token",
    "api_key",
    "bearer_token",
    "password field",
    "your password",
    "account password",
}


def is_ui_translation_label(val: str) -> bool:
    """Check if matched string is an obvious UI translation label rather than a secret."""
    if not val:
        return True

    val_strip = val.strip()
    val_lower = val_strip.lower()

    if "redacted" in val_lower or "example" in val_lower or "sanitized" in val_lower:
        return True

    if val_lower in KNOWN_UI_LABELS or val_lower.replace("_", " ") in KNOWN_UI_LABELS:
        return True

    # Title-cased simple natural language label phrase (e.g. "Password", "Enter Password")
    if val_lower in KNOWN_UI_LABELS and re.match(r"^[A-Z][a-zA-Z\s]+$", val_strip):
        return True

    return False


class SecretScanner:
    """Scans files for potential high-confidence secrets before commit."""

    PATTERNS: ClassVar[list[tuple[str, re.Pattern[str]]]] = [
        ("SSH Private Key", re.compile(r"-----BEGIN (?:RSA|OPENSSH|EC|DSA) PRIVATE KEY-----")),
        ("Generic Private Key", re.compile(r"-----BEGIN PRIVATE KEY-----")),
        ("GitHub Personal Access Token", re.compile(r"ghp_[a-zA-Z0-9]{36}")),
        ("GitHub OAuth Access Token", re.compile(r"gho_[a-zA-Z0-9]{36}")),
        ("GitHub Fine-Grained Token", re.compile(r"github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59}")),
        (
            "AWS Access Key ID",
            re.compile(r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}"),
        ),
        (
            "AWS Secret Access Key",
            re.compile(r"(?i)aws_secret_access_key\s*=\s*[A-Za-z0-9/\+=]{40}"),
        ),
        ("Slack Token", re.compile(r"xox[baprs]-[0-9]{10,13}-[a-zA-Z0-9]{24}")),
        (
            "JWT / Bearer Token",
            re.compile(r"eyJ[a-zA-Z0-9_\-]{20,}\.eyJ[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]{20,}"),
        ),
        (
            "Hardcoded Password Field",
            re.compile(
                r"""(?i)["']?(?:password|passwd|api_key|secret)["']?\s*[:=]\s*["']([^"'\s]{6,})["']"""
            ),
        ),
    ]

    def scan_directory(self, target_dir: Path | str) -> SecretScanResult:
        """Scan all text files in a directory for secrets.

        Args:
            target_dir: Directory containing generated export files.

        Returns:
            SecretScanResult summarizing any detected secrets.
        """
        directory = Path(target_dir)
        findings: list[str] = []
        detailed: list[SecretFindingDetail] = []

        if not directory.exists():
            return SecretScanResult(has_secrets=False)

        for path in sorted(directory.rglob("*")):
            if path.is_file() and not path.name.startswith("."):
                file_summary, file_details = self.scan_file_detailed(path, base_dir=directory)
                findings.extend(file_summary)
                detailed.extend(file_details)

        return SecretScanResult(
            has_secrets=len(detailed) > 0,
            findings=findings,
            detailed_findings=detailed,
        )

    def scan_file(self, file_path: Path) -> list[str]:
        """Scan a single file for secret patterns."""
        summary, _ = self.scan_file_detailed(file_path, base_dir=file_path.parent)
        return summary

    def scan_file_detailed(
        self, file_path: Path, base_dir: Path
    ) -> tuple[list[str], list[SecretFindingDetail]]:
        """Scan a single file and return structured finding details without secret values."""
        summary: list[str] = []
        details: list[SecretFindingDetail] = []

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()
        except Exception:
            return summary, details

        rel_path = (
            str(file_path.relative_to(base_dir)).replace("\\", "/")
            if file_path.is_relative_to(base_dir)
            else file_path.name
        )
        ext = file_path.suffix.lower()
        size = file_path.stat().st_size if file_path.exists() else 0

        for rule_name, pattern in self.PATTERNS:
            for line_idx, line in enumerate(lines, start=1):
                matches = pattern.findall(line)
                if not matches:
                    continue

                for match in matches:
                    matched_str = match if isinstance(match, str) else str(match)
                    if rule_name == "Hardcoded Password Field" and is_ui_translation_label(
                        matched_str
                    ):
                        continue

                    if "REDACTED" in matched_str or "EXAMPLE" in matched_str:
                        continue

                    msg = (
                        f"High-confidence secret pattern '{rule_name}' "
                        f"detected in {rel_path}:L{line_idx}"
                    )
                    summary.append(msg)
                    details.append(
                        SecretFindingDetail(
                            relative_path=rel_path,
                            extension=ext,
                            size_bytes=size,
                            rule_name=rule_name,
                            line_number=line_idx,
                        )
                    )

        return summary, details
