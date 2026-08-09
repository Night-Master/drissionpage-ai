# -*- coding:utf-8 -*-
"""Minimal .env loader for the demos (no third-party dependency).

Reads KEY=VALUE pairs from a .env file next to this script and sets them
with environ.setdefault(), so real environment variables always win.
"""
from os import environ
from pathlib import Path


def load_dotenv():
    env_path = Path(__file__).parent / '.env'
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        environ.setdefault(key.strip(), value.strip().strip('"\''))
