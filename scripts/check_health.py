#!/usr/bin/env python3
"""Ayudante de verificación de salud para el stack multiagente de OpenClaw."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import requests


def build_candidate_urls(primary: str | None) -> list[str]:
    urls: list[str] = []
    if primary:
        urls.append(primary)

    env_url = os.getenv("OPENCLAW_HEALTH_URL")
    if env_url and env_url not in urls:
        urls.append(env_url)

    for fallback in ("http://127.0.0.1:8000/health", "http://127.0.0.1:8080/health", "http://127.0.0.1:8001/health"):
        if fallback not in urls:
            urls.append(fallback)
    return urls


def check_url(url: str, timeout: float = 5.0) -> dict[str, Any]:
    response = requests.get(url, timeout=timeout)
    payload = response.json()
    payload.setdefault("http_status", response.status_code)
    payload.setdefault("url", url)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verifica la salud del dashboard y del orquestador.")
    parser.add_argument("--url", help="URL del endpoint de salud a consultar primero")
    parser.add_argument("--timeout", type=float, default=5.0, help="Tiempo máximo HTTP en segundos")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    last_error: str | None = None

    for url in build_candidate_urls(args.url):
        try:
            payload = check_url(url, timeout=args.timeout)
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            if payload.get("ok"):
                return 0
            last_error = payload.get("issues") or payload.get("status") or "falló la verificación de salud"
        except Exception as exc:
            last_error = str(exc)

    print(last_error or "Falló la verificación de salud", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
