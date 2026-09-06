# Adjutant UI 0.2.1

Web command console for Grok Build. `adjutant` opens a local browser window that wraps the Grok TUI in a terminal emulator.

Requires Grok Build for the agent console (`~/.grok/bin/agent`). `adjutant --shell` works without it.

Source: https://github.com/acequint0/adjutant-ui

## Kali Linux — install from GitHub

Pick one.

### 1. Clone the GitHub repo (user install, no root)

```bash
sudo apt-get update
sudo apt-get install -y git python3
git clone https://github.com/acequint0/adjutant-ui.git
cd adjutant-ui
git checkout v0.2.1
chmod +x install.sh
./install.sh
```

Later updates from the same repo:

```bash
cd ~/adjutant-ui   # or wherever you cloned it
git pull
./install.sh
```

### 2. One-liner from GitHub

```bash
curl -fsSL https://raw.githubusercontent.com/acequint0/adjutant-ui/v0.2.1/packaging/kali-install.sh | bash
```

### 3. Add GitHub as an apt repository

This points apt at the latest GitHub Release (Packages index + `.deb`).

```bash
curl -fsSL https://raw.githubusercontent.com/acequint0/adjutant-ui/v0.2.1/packaging/add-repo.sh | sudo bash
```

Or by hand:

```bash
echo 'deb [trusted=yes] https://github.com/acequint0/adjutant-ui/releases/latest/download/ ./' \
  | sudo tee /etc/apt/sources.list.d/adjutant.list
sudo apt-get update
sudo apt-get install -y adjutant-ui
```

Update later:

```bash
sudo apt-get update
sudo apt-get install --only-upgrade adjutant-ui
```

### 4. Download the `.deb`

```bash
wget https://github.com/acequint0/adjutant-ui/releases/download/v0.2.1/adjutant-ui_0.2.1_all.deb
sudo apt-get install -y ./adjutant-ui_0.2.1_all.deb
```

## Install from this folder (any Debian-based OS)

```bash
cd adjutant-ui
chmod +x install.sh
./install.sh
```

No root needed. Files go to `~/.local`.

System-wide:

```bash
sudo ./install.sh --system
```

Build the Debian package locally:

```bash
./packaging/build-deb.sh
sudo apt-get install -y ./dist/adjutant-ui_0.2.1_all.deb
```

## Use

```bash
adjutant            # web console (Grok Build)
adjutant --imagine  # official Imagine UI on grok.com (4 versions to pick)
adjutant --grok-web # grok.com chat
adjutant --tui      # classic terminal
adjutant --shell    # web console running your shell
adjutant --stop     # shut down the background console
adjutant --status
adjutant --version
```

The console header has **IMAGINE** and **GROK** buttons. Imagine is the original web picker (four variants). Build's `image_gen` tool still writes one local file per call; for art, Adjutant is set to generate four and wait for a pick, or you can jump to grok.com/imagine.

The footer has a **LLAMAFILE** button. The first click starts `~/llamafile-pentest/run.sh` if nothing is listening on `127.0.0.1:8080`, flips the console green, and wraps that UI. Later clicks just bring that session back (llamafile stays running). Click the button again while it is showing to return to the Grok terminal. Override with `ADJUTANT_LLAMAFILE` / `ADJUTANT_LLAMAFILE_ROOT` if needed.

Extra arguments are forwarded to Grok: `adjutant -c`, `adjutant -- "fix the bug"`.

The console binds to `127.0.0.1` only.

## Versions

| Version | Notes |
|---|---|
| **0.2.1** | User install writes `export PATH="$HOME/.local/bin:$PATH"` into `~/.bashrc` so `adjutant` works in new shells. |
| 0.2.0 | Footer **LLAMAFILE** button. First click starts the local llamafile at `127.0.0.1:8080` and wraps it in a green console. Later clicks bring that session back. |
| 0.1.0 | First Kali/Debian release: web terminal, IMAGINE / GROK buttons, HUD, `--shell`, `--tui`. |

## Sound clip

Replace `~/.local/share/adjutant/adjutant-online.wav` with any 16-bit PCM WAV. The boot sequence plays it automatically.
