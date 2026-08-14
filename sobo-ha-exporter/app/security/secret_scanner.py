"""Static secret scanner for inspecting generated export content before git commit."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar


@dataclass
class SecretScanResult:
    has_secrets: bool
    findings: list[str] = field(default_factory=list)


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
                r"""(?i)["']?(?:password|passwd|api_key|secret)["']?\s*[:=]\s*["']([^"'\s]{8,})["']"""
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

        if not directory.exists():
            return SecretScanResult(has_secrets=False)

        for path in directory.rglob("*"):
            if path.is_file() and not path.name.startswith("."):
                file_findings = self.scan_file(path)
                findings.extend(file_findings)

        return SecretScanResult(has_secrets=len(findings) > 0, findings=findings)

    def scan_file(self, file_path: Path) -> list[str]:
        """Scan a single file for secret patterns.

        Args:
            file_path: Path to the file.

        Returns:
            List of warning/finding descriptions.
        """
        findings: list[str] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return findings

        for name, pattern in self.PATTERNS:
            matches = pattern.findall(content)
            if matches:
                # Filter out known safe placeholders such as [REDACTED] or [REDACTED_TOKEN]
                real_matches = [
                    m
                    for m in matches
                    if not (isinstance(m, str) and ("REDACTED" in m or "EXAMPLE" in m))
                ]
                if real_matches:
                    rel_path = file_path.name
                    findings.append(
                        f"High-confidence secret pattern '{name}' detected in {rel_path}"
                    )

        return findings
