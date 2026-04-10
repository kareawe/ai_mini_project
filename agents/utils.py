"""Shared helpers for agent modules."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import requests
from openai import OpenAI


REQUEST_TIMEOUT = 20
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

DATE_PATTERNS = [
    re.compile(r'article:published_time"\s+content="([^"]+)"', re.IGNORECASE),
    re.compile(r'article:modified_time"\s+content="([^"]+)"', re.IGNORECASE),
    re.compile(r'citation_publication_date"\s+content="([^"]+)"', re.IGNORECASE),
    re.compile(r'name="dc\.date"\s+content="([^"]+)"', re.IGNORECASE),
    re.compile(r'itemprop="datePublished"\s+content="([^"]+)"', re.IGNORECASE),
    re.compile(r'itemprop="dateModified"\s+content="([^"]+)"', re.IGNORECASE),
    re.compile(r'<time[^>]+datetime="([^"]+)"', re.IGNORECASE),
    re.compile(r'"datePublished"\s*:\s*"([^"]+)"', re.IGNORECASE),
    re.compile(r'"dateModified"\s*:\s*"([^"]+)"', re.IGNORECASE),
]

KNOWN_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %B %Y",
    "%d %b %Y",
]

COMPANY_ALIASES = {
    "samsung": "Samsung Electronics",
    "samsung electronics": "Samsung Electronics",
    "sk hynix": "SK hynix",
    "hynix": "SK hynix",
    "micron": "Micron",
    "micron technology": "Micron",
    "intel": "Intel",
    "intel corporation": "Intel",
    "advanced micro devices": "AMD",
    "amd": "AMD",
    "nvidia": "NVIDIA",
    "nvidia corporation": "NVIDIA",
    "broadcom": "Broadcom",
    "broadcom inc": "Broadcom",
    "tsmc": "TSMC",
    "taiwan semiconductor manufacturing company": "TSMC",
}


def get_api_key() -> str:
    load_dotenv_file()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required to run the workflow.")
    return api_key


def get_client() -> OpenAI:
    return OpenAI(api_key=get_api_key())


def load_dotenv_file(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def normalize_company_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name.strip())
    lowered = cleaned.lower()
    return COMPANY_ALIASES.get(lowered, cleaned)


def dedupe_keep_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = normalize_company_name(value)
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        ordered.append(normalized)
    return ordered


def normalize_date(raw_value: str) -> str:
    text = raw_value.strip()
    if not text:
        return ""

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    for fmt in KNOWN_DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue

    match = re.search(r"(\d{4})[-/.](\d{2})[-/.](\d{2})", text)
    if match:
        year, month, day = match.groups()
        return f"{year}-{month}-{day}"

    return ""


def parse_date_value(raw_value: str):
    normalized = normalize_date(raw_value)
    if not normalized:
        return None
    try:
        return datetime.strptime(normalized, "%Y-%m-%d").date()
    except ValueError:
        return None


def is_recent_date(raw_value: str, days: int = 365) -> bool:
    parsed = parse_date_value(raw_value)
    if parsed is None:
        return False
    delta = datetime.utcnow().date() - parsed
    return delta.days <= days


def fetch_page_date(url: str) -> str:
    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
    except requests.RequestException:
        return ""

    html = response.text
    for pattern in DATE_PATTERNS:
        match = pattern.search(html)
        if not match:
            continue
        normalized = normalize_date(match.group(1))
        if normalized:
            return normalized

    return ""


def extract_domain(url: str) -> str:
    return urlparse(url).netloc.lower()


def infer_source_type(url: str, company: str) -> str:
    domain = extract_domain(url)

    if "patent" in domain or "uspto" in domain or "espacenet" in domain:
        return "patent"

    if any(key in domain for key in ("jedec.org", "cxlconsortium.org")):
        return "standard"

    if any(
        key in domain
        for key in (
            "arxiv.org",
            "ieeexplore.ieee.org",
            "acm.org",
            "springer.com",
            "nature.com",
            "sciencedirect.com",
            "semanticscholar.org",
            "mdpi.com",
            "doi.org",
        )
    ):
        return "paper"

    company_key = re.sub(r"[^a-z0-9]", "", company.lower())
    domain_key = re.sub(r"[^a-z0-9]", "", domain)
    if company_key and company_key in domain_key:
        return "official"

    if any(
        key in domain
        for key in (
            "samsung.com",
            "skhynix.com",
            "micron.com",
            "intel.com",
            "amd.com",
            "nvidia.com",
            "broadcom.com",
            "tsmc.com",
        )
    ):
        return "official"

    return "news"


def json_dumps(data: object) -> str:
    return json.dumps(data, ensure_ascii=True, indent=2)
