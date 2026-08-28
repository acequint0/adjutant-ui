# Adjutant UI

Web command console for Grok Build. `adjutant` opens a local browser window that wraps the Grok TUI in a terminal emulator.

Requires Grok Build already installed (`~/.grok/bin/agent`).

## Install (any Debian-based OS)

Copy this folder to the machine, then:

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

Debian package:

```bash
./packaging/build-deb.sh
sudo apt-get install -y ./dist/adjutant-ui_1.0.0_all.deb
```

## Use

```bash
adjutant            # web console (Grok)
adjutant --tui      # classic terminal
adjutant --shell    # web console running your shell
adjutant --stop     # shut down the background console
adjutant --status
```

Extra arguments are forwarded to Grok: `adjutant -c`, `adjutant -- "fix the bug"`.

The console binds to `127.0.0.1` only.

## Sound clip

Replace `~/.local/share/adjutant/adjutant-online.wav` with any 16-bit PCM WAV. The boot sequence plays it automatically.
