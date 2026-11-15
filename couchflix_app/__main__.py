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


def main() -> None:
    load_dotenv()
    host, port = os.environ.get("COUCHFLIX_HOST", "127.0.0.1"), int(os.environ.get("COUCHFLIX_PORT", "8765"))
    from .web.app import create_app
    app = create_app()
    if not app.state.core.catalog.active_providers():
        print("⚠  Sin proveedor de catálogo activo: define TMDB_API_KEY (ver README). La app arrancará igualmente.", file=sys.stderr)
    print(f"\n  COUCHFLIX  ·  Less scrolling. More chilling.\n  → http://{host}:{port}\n")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
