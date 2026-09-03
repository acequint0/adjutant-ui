(() => {
  const $ = (id) => document.getElementById(id);

  const params = new URLSearchParams(location.search);
  const sessionId = params.get("s") || "";

  const boot = $("boot");
  const bootLog = $("boot-log");
  const bootHint = $("boot-hint");
  const termEl = $("term");
  const led = $("led");
  const linkState = $("link-state");
  const metaSize = $("meta-size");
  const metaCwd = $("meta-cwd");
  const metaClock = $("meta-clock");
  const metaMode = $("meta-mode");
  const metaHost = $("meta-host");

  metaHost.textContent = location.hostname || "127.0.0.1";

  const setLink = (mode) => {
    led.className = "led" + (mode === "ok" ? " ok" : mode === "bad" ? " bad" : "");
    linkState.textContent =
      mode === "ok" ? "ONLINE" : mode === "bad" ? "OFFLINE" : "STANDBY";
  };

  const tick = () => {
    const d = new Date();
    metaClock.textContent = d.toTimeString().slice(0, 8);
  };
  tick();
  setInterval(tick, 1000);

  const lines = [
    { at: 60, text: "UED COMMAND INTERFACE  //  REV 12.4" },
    { at: 220, text: "COMMS ARRAY ............... READY" },
    { at: 380, text: "AUTH TOKEN ................ LOCAL-ONLY" },
    { at: 540, text: "PTY ALLOCATOR ............. OK" },
    { at: 720, text: "COMM-LINK ESTABLISHED" },
    { at: 980, text: "ADJUTANT ONLINE." },
  ];

  const playClip = async () => {
    try {
      const audio = new Audio("/sound/online.wav?ts=" + Date.now());
      audio.volume = 0.9;
      await audio.play();
    } catch {
      /* autoplay blocked — continue without audio */
    }
  };

  const typeLines = () =>
    new Promise((resolve) => {
      let i = 0;
      const shown = [];
      const start = performance.now();
      const step = (now) => {
        while (i < lines.length && now - start >= lines[i].at) {
          shown.push(lines[i].text);
          if (lines[i].text === "ADJUTANT ONLINE.") playClip();
          i += 1;
        }
        bootLog.textContent = shown.map((l) => "> " + l).join("\n");
        if (i < lines.length) requestAnimationFrame(step);
        else resolve();
      };
      requestAnimationFrame(step);
    });

  const FitAddonCtor =
    (window.FitAddon && window.FitAddon.FitAddon) || window.FitAddon;

  const term = new Terminal({
    cursorBlink: true,
    cursorStyle: "block",
    fontFamily: '"Share Tech Mono", ui-monospace, monospace',
    fontSize: 15,
    lineHeight: 1.15,
    letterSpacing: 0,
    scrollback: 8000,
    allowProposedApi: true,
    theme: {
      background: "#0a0303",
      foreground: "#f0d0d0",
      cursor: "#e22b2b",
      cursorAccent: "#0a0303",
      selectionBackground: "#5a1515",
      black: "#0a0303",
      red: "#ff5a4a",
      green: "#5dffb0",
      yellow: "#ffc14a",
      blue: "#4aa7ff",
      magenta: "#c792ea",
      cyan: "#e22b2b",
      white: "#ffe8e8",
      brightBlack: "#6e4d4d",
      brightRed: "#ff8f82",
      brightGreen: "#8affc8",
      brightYellow: "#ffd37a",
      brightBlue: "#7cc0ff",
      brightMagenta: "#e5b0ff",
      brightCyan: "#ff6a6a",
      brightWhite: "#fff4f4",
    },
  });

  const fit = new FitAddonCtor();
  term.loadAddon(fit);
  term.open(termEl);

  const fitNow = () => {
    try {
      fit.fit();
    } catch {
      return;
    }
    metaSize.textContent = term.cols + "×" + term.rows;
  };

  const connect = () => {
    if (!sessionId) {
      setLink("bad");
      boot.classList.add("error");
      bootHint.textContent = "NO SESSION  //  RUN  adjutant";
      return;
    }

    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/${sessionId}`);
    ws.binaryType = "arraybuffer";

    const sendResize = () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
      }
    };

    ws.onopen = () => {
      setLink("ok");
      bootHint.textContent = "CHANNEL OPEN";
      fitNow();
      sendResize();
      boot.classList.add("done");
      termEl.classList.add("live");
      term.focus();
    };

    ws.onmessage = (ev) => {
      if (typeof ev.data === "string") {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === "meta") {
            if (msg.cwd) {
              metaCwd.textContent = msg.cwd;
              metaCwd.title = msg.cwd;
            }
            if (msg.mode) metaMode.textContent = msg.mode;
          } else if (msg.type === "exit") {
            setLink("bad");
            linkState.textContent = "ENDED " + (msg.code ?? "");
          }
        } catch {
          term.write(ev.data);
        }
        return;
      }
      term.write(new Uint8Array(ev.data));
    };

    ws.onclose = () => {
      setLink("bad");
    };

    ws.onerror = () => {
      setLink("bad");
      boot.classList.add("error");
      bootHint.textContent = "COMM-LINK FAILED";
    };

    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(data);
    });

    window.addEventListener("resize", () => {
      fitNow();
      sendResize();
    });

    document.addEventListener("click", () => term.focus());
  };

  const start = async () => {
    await typeLines();
    await new Promise((r) => setTimeout(r, 420));
    connect();
  };

  fetch("/api/meta")
    .then((r) => r.json())
    .then((meta) => {
      if (meta.cwd) {
        metaCwd.textContent = meta.cwd;
        metaCwd.title = meta.cwd;
      }
    })
    .catch(() => {});

  start();
})();
