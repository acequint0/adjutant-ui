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
  const subtitle = $("subtitle");
  const btnLlama = $("btn-llamafile");
  const llamaWrap = $("llama-wrap");
  const llamaFrame = $("llama-frame");
  const llamaOffTitle = $("llama-off-title");
  const llamaOffBody = $("llama-off-body");
  const llamaOffHint = $("llama-off-hint");

  const SUBTITLE_AGENT = "COMMAND CONSOLE // GROK BUILD";
  const SUBTITLE_LLAMA = "LOCAL LLM // 127.0.0.1:8080";
  const LLAMAFILE_FALLBACK = "http://127.0.0.1:8080/";

  metaHost.textContent = location.hostname || "127.0.0.1";
  let llamaOn = false;
  let llamaBusy = false;
  let llamaLoaded = false;
  let grokLink = "";
  let modeBeforeLlama = metaMode.textContent || "PTY";

  const setLink = (mode, origin) => {
    if (origin !== "llama") grokLink = mode;
    if (llamaOn && origin !== "llama") return;
    led.className = "led" + (mode === "ok" ? " ok" : mode === "bad" ? " bad" : "");
    if (origin === "llama") {
      linkState.textContent = mode === "ok" ? "LLAMAFILE" : "NO LLAMAFILE";
      return;
    }
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
    { at: 60, text: "UED COMMAND INTERFACE  //  REV 0.2.1" },
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

    document.addEventListener("click", (ev) => {
      if (llamaOn) return;
      if (ev.target.closest("a, button, nav, input, textarea, iframe")) return;
      term.focus();
    });
  };

  const openPortal = (url, name) => {
    const width = Math.min(1440, Math.max(900, Math.round(screen.availWidth * 0.68)));
    const height = Math.min(960, Math.max(700, Math.round(screen.availHeight * 0.86)));
    const left = Math.max(24, Math.round(screen.availWidth - width - 28));
    const top = Math.max(24, Math.round((screen.availHeight - height) / 2));
    const features = [
      "popup=yes",
      `width=${width}`,
      `height=${height}`,
      `left=${left}`,
      `top=${top}`,
      "resizable=yes",
      "scrollbars=yes",
      "menubar=no",
      "toolbar=no",
      "location=yes",
      "status=no",
    ].join(",");
    const win = window.open(url, name, features);
    if (win) {
      try {
        win.opener = null;
      } catch {
        /* ignore */
      }
      try {
        win.focus();
      } catch {
        /* ignore */
      }
    }
  };

  $("btn-imagine").addEventListener("click", (ev) => {
    ev.preventDefault();
    openPortal("https://grok.com/imagine", "adjutantImagine");
  });
  $("btn-grok").addEventListener("click", (ev) => {
    ev.preventDefault();
    openPortal("https://grok.com", "adjutantGrok");
  });

  const llamaUrl = (base) => {
    const raw = (base || LLAMAFILE_FALLBACK).trim();
    return raw.endsWith("/") ? raw : raw + "/";
  };

  const probeLlama = async () => {
    try {
      const resp = await fetch("/api/llamafile", { cache: "no-store" });
      const meta = await resp.json();
      return {
        ok: Boolean(meta && meta.ok),
        url: llamaUrl(meta && meta.url),
        error: meta && meta.error,
      };
    } catch {
      return { ok: false, url: llamaUrl(LLAMAFILE_FALLBACK) };
    }
  };

  const ensureLlama = async () => {
    const already = await probeLlama();
    if (already.ok) return already;
    const resp = await fetch("/api/llamafile", {
      method: "POST",
      cache: "no-store",
    });
    const meta = await resp.json();
    return {
      ok: Boolean(meta && meta.ok),
      url: llamaUrl(meta && meta.url),
      error: (meta && (meta.error || meta.status)) || "start failed",
    };
  };

  const showLlamaOverlay = (kind, title, body, hint) => {
    llamaWrap.classList.remove("offline", "starting");
    llamaWrap.classList.add(kind);
    llamaOffTitle.textContent = title;
    llamaOffBody.textContent = body;
    llamaOffHint.textContent = hint;
  };

  const setLlama = async (on) => {
    llamaOn = on;
    document.documentElement.classList.toggle("llama", on);
    btnLlama.setAttribute("aria-pressed", on ? "true" : "false");
    subtitle.textContent = on ? SUBTITLE_LLAMA : SUBTITLE_AGENT;
    if (!on) {
      llamaWrap.hidden = true;
      llamaWrap.classList.remove("offline", "starting");
      metaMode.textContent = modeBeforeLlama;
      setLink(grokLink || "");
      term.focus();
      return;
    }

    modeBeforeLlama = metaMode.textContent || modeBeforeLlama;
    metaMode.textContent = "LLAMA";
    llamaWrap.hidden = false;

    const frameSrc = llamaFrame.getAttribute("src") || "";
    if (llamaLoaded && frameSrc && frameSrc !== "about:blank") {
      const probe = await probeLlama();
      if (probe.ok) {
        llamaWrap.classList.remove("offline", "starting");
        setLink("ok", "llama");
        try {
          llamaFrame.contentWindow && llamaFrame.contentWindow.focus();
        } catch {
          /* ignore */
        }
        return;
      }
      llamaLoaded = false;
    }

    showLlamaOverlay(
      "starting",
      "BRINGING UP LLAMAFILE",
      "STARTING LOCAL MODEL",
      "127.0.0.1:8080"
    );
    setLink("ok", "llama");
    linkState.textContent = "STARTING";
    llamaBusy = true;
    btnLlama.disabled = true;
    try {
      const probe = await ensureLlama();
      if (!llamaOn) {
        llamaLoaded = Boolean(probe.ok);
        if (probe.ok && (llamaFrame.getAttribute("src") || "") === "about:blank") {
          llamaFrame.src = probe.url;
        }
        return;
      }
      if (probe.ok) {
        llamaWrap.classList.remove("offline", "starting");
        if (llamaFrame.getAttribute("src") !== probe.url) llamaFrame.src = probe.url;
        llamaLoaded = true;
        setLink("ok", "llama");
        try {
          llamaFrame.contentWindow && llamaFrame.contentWindow.focus();
        } catch {
          /* ignore */
        }
      } else {
        llamaLoaded = false;
        showLlamaOverlay(
          "offline",
          "LLAMAFILE FAILED",
          "LOCAL MODEL DID NOT COME UP",
          String(probe.error || "see llamafile log").slice(0, 140)
        );
        setLink("bad", "llama");
      }
    } catch (err) {
      if (!llamaOn) return;
      llamaLoaded = false;
      showLlamaOverlay(
        "offline",
        "LLAMAFILE FAILED",
        "LOCAL MODEL DID NOT COME UP",
        String(err && err.message ? err.message : err).slice(0, 140)
      );
      setLink("bad", "llama");
    } finally {
      llamaBusy = false;
      btnLlama.disabled = false;
    }
  };

  btnLlama.addEventListener("click", (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    if (llamaBusy) return;
    setLlama(!llamaOn);
  });

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
