"""`python -m couchflix_app` — loads .env, creates/migrates the DB (done by Db) and serves the app."""
import os
import sys
from pathlib import Path

import uvicorn


def load_dotenv(path: Path = Path(".env")) -> None:
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _lan_ip() -> str:
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # no se envía tráfico; solo elige la interfaz
            return s.getsockname()[0]
    except OSError:
        return "<IP-de-tu-equipo>"


def main() -> None:
    load_dotenv()
    host, port = os.environ.get("COUCHFLIX_HOST", "0.0.0.0"), int(os.environ.get("COUCHFLIX_PORT", "8765"))
    from .web.app import create_app
    app = create_app()
    if not app.state.core.catalog.active_providers():
        print("⚠  Sin proveedor de catálogo activo: define TMDB_API_KEY (ver README). La app arrancará igualmente.", file=sys.stderr)
    shown = "127.0.0.1" if host in ("0.0.0.0", "") else host
    print(f"\n  COUCHFLIX  ·  Less scrolling. More chilling.\n  → http://{shown}:{port}")
    if host in ("0.0.0.0", ""):
        print(f"  → Desde tu móvil (misma wifi): http://{_lan_ip()}:{port}")
    print()
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
