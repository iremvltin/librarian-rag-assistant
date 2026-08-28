"""
foundry_utils.py
A small helper layer that communicates directly with the `foundry` CLI 
instead of FoundryLocalManager (the old SDK). It parses the CLI's text output 
to avoid SDK/CLI version incompatibility issues.
"""

import re
import subprocess
import sys

from openai import OpenAI

URL_PATTERN = re.compile(r"http://127\.0\.0\.1:\d+")


def _run_foundry(*args: str, timeout: int = 60) -> str:
    """`foundry <args>` calistirir, stdout+stderr'i tek string olarak dondurur."""
    try:
        result = subprocess.run(
            ["foundry", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError:
        print(
            "HATA: 'foundry' komutu bulunamadi. Foundry Local CLI PATH'te "
            "olmali. 'foundry --help' terminalde calisiyor mu kontrol et.",
            file=sys.stderr,
        )
        raise
    return (result.stdout or "") + (result.stderr or "")


def get_foundry_base_url() -> str:
    """Sunucuyu (gerekirse) baslatir ve http://127.0.0.1:PORT adresini dondurur."""
    output = _run_foundry("server", "start")
    match = URL_PATTERN.search(output)
    if not match:
        # start ciktisinda bulunamadiysa status'a bak
        output = _run_foundry("server", "status")
        match = URL_PATTERN.search(output)
    if not match:
        raise RuntimeError(
            "Foundry Local sunucu adresi bulunamadi.\n"
            f"Komut ciktisi:\n{output}\n"
            "Terminalde 'foundry server status' calistirip URL'yi kontrol et."
        )
    return match.group(0)


def ensure_model_loaded(alias: str) -> None:
    """Model cache'de yoksa indirir, sonra daemon hafizasina yukler."""
    download_output = _run_foundry("model", "download", alias, timeout=1800)
    if "error" in download_output.lower() and "already" not in download_output.lower():
        print(f"[UYARI] '{alias}' indirilirken beklenmedik cikti:\n{download_output}")

    load_output = _run_foundry("model", "load", alias, timeout=300)
    if "error" in load_output.lower() and "already" not in load_output.lower():
        print(f"[UYARI] '{alias}' yuklenirken beklenmedik cikti:\n{load_output}")


def get_client() -> OpenAI:
    """Foundry Local'a bagli, OpenAI-uyumlu bir client dondurur."""
    base_url = get_foundry_base_url()
    return OpenAI(base_url=f"{base_url}/v1", api_key="not-needed")


def resolve_model_id(client: OpenAI, alias: str) -> str:
    """
    /v1/models listesinden alias'a en cok benzeyen gercek model id'sini bulur.
    Bulamazsa alias'i oldugu gibi dondurur (bircok durumda Foundry Local
    alias'i direkt kabul eder).
    """
    try:
        models = client.models.list()
        for m in models.data:
            if alias.lower() in m.id.lower():
                return m.id
    except Exception as exc:
        print(f"[UYARI] Model listesi alinamadi, alias oldugu gibi kullanilacak: {exc}")
    return alias