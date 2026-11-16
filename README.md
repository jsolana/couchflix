<p align="center"><img src="docs/logo.svg" alt="COUCHFLIX logo" width="192"></p>

<h1 align="center">COUCHFLIX</h1>
<p align="center"><strong>Less scrolling. More chilling.</strong></p>

Intelligent entertainment discovery: an agent that knows your taste, your streaming platforms and your history, and always has something good ready. Runs locally with **a single command**.

![Home screen](docs/screenshots/home.png)

> The interface and the built-in rules agent are in Spanish.

## Features

- **Perfiles de sesión (family profiles)**: a Netflix-style "¿Quién está viendo?" screen is always the entry point; each family member has their own name, avatar and fully private data (taste profile, history, searches, suggestions). See [Session profiles](#session-profiles-family).
- **Sugerencias (Suggestions)**: a personalized carousel ("Para ti") and, kept separate, *Random Couch Sessions* (seasonal picks, hidden gems, outside your comfort zone, your last search).
- **Buscar (Search)**: ask the agent anything in natural language and refine with one tap ("more recent", "other options"…).
- **Perfil (Profile)**: a 6-dimension audiovisual radar that builds up from the centre, with top genres, evolution and an activity history.
- **Detail view** with icon actions: watched, like, love, dislike, comment and refresh; metadata and availability update dates are shown separately.
- Everything is stored in **SQLite**; switching sections never triggers new searches.
- Swappable catalog providers (`ICatalogProvider`) with normalization, de-duplication and per-attribute provenance.
- Skeletons that match the real cards exactly, subtle micro-interactions, collapsible sidebar, keyboard/touch support, `prefers-reduced-motion`.

| First-load placeholders | Carousel |
|---|---|
| ![Placeholders](docs/screenshots/initial-placeholders.png) | ![Carousel](docs/screenshots/carousel.png) |

| Detail | Profile |
|---|---|
| ![Detail](docs/screenshots/detail.png) | ![Profile](docs/screenshots/profile.png) |

| Search | Agent results |
|---|---|
| ![Search](docs/screenshots/search.png) | ![Results](docs/screenshots/agent-results.png) |

| Who's watching? | Manage a profile |
|---|---|
| ![Profile picker](docs/screenshots/profile-picker.png) | ![Edit profile](docs/screenshots/profile-manage.png) |

> Screenshots are generated with Playwright against a **fictional test catalog** (fixtures) so they can be produced offline and without API keys. In real use you get posters and data from TMDB.

## Requirements

- Python 3.11+ (`uv` is optional: if installed it is used to create the environment).
- A free [TMDB](https://www.themoviedb.org/settings/api) API key for real data.

## Getting started

```bash
cp .env.example .env     # then add your keys (or run `make env`)
./couchflix              # or: make run
```

The launcher checks Python, creates `.venv`, installs dependencies, creates/migrates the database and starts the server at <http://127.0.0.1:8765>.

Run `make` to list every helper command (`run`, `test`, `unit`, `e2e`, `screenshots`, `build`, `rebuild`, `clean`, `clean-db`, `reset`…).

### Standalone binary (optional)

```bash
make build      # produces dist/couchflix (PyInstaller); dist/ and build/ are git-ignored
```

Run it from a folder that contains your `.env`; the database is created in `./data`. The binary is built for the OS/architecture you build it on.

## Running it at home 24/7 (Docker / Raspberry Pi)

A laptop suspends or hibernates and the service stops with it. For an always-on home deployment, a **Raspberry Pi 4/5** (3–10 W, no sleep mode) or any small always-on machine running Docker is a good fit. The repo ships a `Dockerfile` (multi-arch: `linux/arm64` for the Pi, `linux/amd64`) and a `docker-compose.yml`.

### What you need

- Raspberry Pi 4 or 5 (2 GB RAM is enough), **Raspberry Pi OS 64-bit** (Lite is fine), wired Ethernet if possible.
- A good microSD card, or better a USB SSD: SQLite writes often and cheap SD cards wear out.
- A [TMDB](https://www.themoviedb.org/settings/api) API key.

### 1. Prepare the Pi

Flash Raspberry Pi OS with [Raspberry Pi Imager](https://www.raspberrypi.com/software/) and, in its advanced options, set a hostname (e.g. `couchflix`), your user, Wi-Fi if needed, and enable SSH. Then:

```bash
ssh <user>@couchflix.local
sudo apt update && sudo apt full-upgrade -y
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER      # log out and back in afterwards
```

Give the Pi a **fixed IP** (a DHCP reservation in your router is the easiest way) so the address never changes.

### 2. Deploy

```bash
git clone <your-repo-url> couchflix && cd couchflix
cp .env.example .env && nano .env     # set TMDB_API_KEY (and the LLM keys if you use them)
docker compose up -d --build
```

The first build takes a couple of minutes on a Pi. When it finishes, open `http://<pi-ip>:8765` from any device on your Wi-Fi (or `http://couchflix.local:8765`).

- `restart: unless-stopped` makes Docker start the app on boot and restart it if it crashes. Docker itself starts at boot (`sudo systemctl enable docker`, already the default).
- The SQLite database lives in the named volume `couchflix-data` (mounted at `/data`), so it survives rebuilds and updates.
- The image runs as a non-root user and has a healthcheck (`docker ps` shows `healthy`).

### 3. Day-to-day

```bash
docker compose logs -f              # follow logs
docker compose restart              # restart
docker compose down                 # stop (data is kept)
git pull && docker compose up -d --build     # update to a new version
```

**Backup** the database (the volume is called `<folder>_couchflix-data`, normally `couchflix_couchflix-data`):

```bash
docker run --rm -v couchflix_couchflix-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/couchflix-backup-$(date +%F).tgz -C /data .
```

You can also download your data as JSON from the app's settings (*export*).

### 4. Build the image on another machine (optional)

To avoid compiling on the Pi, build the arm64 image from your computer and ship it:

```bash
docker buildx build --platform linux/arm64 -t couchflix:latest --load .
docker save couchflix:latest | gzip | ssh <user>@couchflix.local 'gunzip | docker load'
```

Then, on the Pi, use `docker compose up -d` (without `--build`).

### 5. Reaching it away from home

Do **not** forward port 8765 on your router: the app has no login, and anyone who reaches it can pick any profile. Instead use a private network such as [Tailscale](https://tailscale.com/download): install it on the Pi (`curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up`) and on your phones, and open `http://<tailscale-name-or-ip>:8765`.

### Tips for maximum uptime

- Use Ethernet and a decent power supply (undervoltage is the most common cause of Pi instability).
- Optionally add a small UPS and keep the SD/SSD healthy; avoid pulling the plug while it writes.
- If you keep using a laptop instead, disable sleep: macOS `sudo pmset -a sleep 0 disablesleep 1` (or run `caffeinate -s`), Linux `sudo systemctl mask sleep.target suspend.target hibernate.target`, Windows *Power options → Never sleep* and *lid close → do nothing*.

## Configuration

Through environment variables, a `.env` file in the working directory (see `.env.example`), or from the UI (settings icon at the bottom of the sidebar):

| Variable | Description |
|---|---|
| `TMDB_API_KEY` | TMDB key (v3) or token (v4). Without it the app still starts and asks you to configure a provider. |
| `COUCHFLIX_PROVIDERS` | Registered providers, `tmdb` by default. |
| `COUCHFLIX_DB` | SQLite path. Defaults to **`data/couchflix.db`**. |
| `COUCHFLIX_PORT` / `COUCHFLIX_HOST` | `8765` / `0.0.0.0` (accesible desde la red local; usa `127.0.0.1` para restringir a este equipo). |
| `COUCHFLIX_LLM`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENAI_BASE_URL` | Optional LLM agent (see [Agent](#agent)). |

Initial values: country **Spain**, platform **Netflix** (only until you configure your own), empty history, and a neutral profile with every dimension at **50**. If you turn off all platforms, Netflix is not assumed: you are told, and searches run without a subscription filter. Settings also let you change the country, platforms, the Random Couch Sessions refresh interval, active providers, credentials, the LLM, recalculate the profile and export your data.

### Session profiles (family)

The first screen is always a Netflix-style **"who's watching?"** picker. Each profile (name + one of 12 built-in avatars, or a picture from your device) has its own private data space: taste profile, history, ratings, searches and suggestions are never shared between profiles, and deleting a profile erases all of it. Up to 8 profiles; the pre-existing one is named **Javi**. Settings, platforms and the catalog cache are global. Use **Administrar perfiles** on the picker to rename a profile, change its avatar (or upload your own image) or delete it, and *Cambiar perfil* in the menu to go back to the picker. There is no PIN: anyone on your network can pick any profile.

### Profile learning

Each dimension starts at 50. **Love** and **like** push it up, **dislike** pulls it down (the strongest signal), watching without rating is neutral, and searches *you* type add a weak, capped nudge. Suggestions generated automatically by the app, and refinement buttons, never affect your profile or appear in your activity history. The profile can be recalculated from the stored history at any time.

## Providers

All providers implement `ICatalogProvider` (`search`, `get_details`, `get_availability`, `get_provider_name`, `is_available`). Recommendations only read the normalized catalog through `CatalogService`, never a provider directly.

- **TMDB** (active): metadata, posters, genres, TMDB rating and per-country availability. TMDB's availability data is provided by JustWatch, so that attribution must be shown.
- **JustWatch** (`justwatch.py`, **disabled**): research outcome → [its partner API requires a contract and a partner token](https://apis.justwatch.com/docs/api), its [terms](https://partners.justwatch.com/legal/termsofuse) restrict public/commercial use of the content and require branded links, and unofficial libraries have neither support nor permission. COUCHFLIX therefore **does not scrape it**. If you obtain partner access, implement the adapter's three methods and add `justwatch` to `COUCHFLIX_PROVIDERS`.
- **OMDb / others**: write a class implementing the interface and register it in `web/app.py:build_providers`. Per-attribute priority is configurable through `provider_priority`.
- `fake` / `fake_down`: **tests only**, never enabled by default and excluded from the binary.

The app keeps working from persisted data if a provider goes down.

Cache policy: metadata 30 days, availability 24 h (independent); the refresh icon in the detail view forces a query.

## Agent

By default a **rules engine** (Spanish) interprets the request (genre, duration, rating, platform, recency, "similar to…", surprise, etc.). The UI always shows whether the answer came from **Reglas** (rules) or **IA** (LLM). To use an LLM (it only interprets the request; if it fails, the rules engine takes over):

- Anthropic: `COUCHFLIX_LLM=anthropic` and `ANTHROPIC_API_KEY`.
- OpenAI-compatible (OpenAI, OpenRouter, Ollama…): `COUCHFLIX_LLM=openai`, `OPENAI_API_KEY`, and `OPENAI_BASE_URL` if you are not using api.openai.com. The model is chosen in Settings (default `gpt-4o-mini`).

## Tests

```bash
make test                             # unit + Playwright acceptance (no Internet needed)
./couchflix test tests/unit           # unit only
./couchflix test -m screenshots       # regenerate docs/screenshots
```

Acceptance tests start the real app with the fictional provider and a temporary database.

## Project layout

```
couchflix_app/
  domain/          entities, criteria, profile
  application/     use cases (Couchflix facade)
  services/        catalog, recommender, profile, agent
  infrastructure/  SQLite + migrations, repositories, providers
  web/             FastAPI + UI (HTML/CSS/JS, no build step)
tests/             unit/ and e2e/
```
