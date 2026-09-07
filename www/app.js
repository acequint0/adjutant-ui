(() => {
  const $ = (id) => document.getElementById(id);

  const params = new URLSearchParams(location.search);
  const sessionId = params.get("s") || "";

  const boot = $("boot");
  const bootLog = $("boot-log");
  const bootHint = $("boot-hint");
  const led = $("led");
  const linkState = $("link-state");
  const metaSize = $("meta-size");
  const metaCwd = $("meta-cwd");
  const metaClock = $("meta-clock");
  const metaMode = $("meta-mode");
  const metaHost = $("meta-host");
  const subtitle = $("subtitle");
  const btnSudo = $("btn-sudo");
  const sudoState = $("sudo-state");
  const sudoDock = btnSudo && btnSudo.closest(".sudo-dock");
  const sudoPrompt = $("sudo-prompt");
  const sudoUninstall = $("sudo-app-uninstall");
  const sudoUnSep = document.querySelector(".sudo-un-sep");
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
    { at: 60, text: "UED COMMAND INTERFACE  //  REV 0.2.6" },
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

  const TERM_THEME = {
    background: "#0a0202",
    foreground: "#ffd6d6",
    cursor: "#e22b2b",
    cursorAccent: "#0a0202",
    selectionBackground: "#5a1515",
    selectionForeground: "#ffd6d6",
    black: "#050000",
    red: "#e22b2b",
    green: "#5dffb0",
    yellow: "#ffb347",
    blue: "#a07070",
    magenta: "#e22b2b",
    cyan: "#ff6a4a",
    white: "#ffd6d6",
    brightBlack: "#a07070",
    brightRed: "#ff6a4a",
    brightGreen: "#8affc8",
    brightYellow: "#ffb347",
    brightBlue: "#e22b2b",
    brightMagenta: "#ff6a6a",
    brightCyan: "#ff8f82",
    brightWhite: "#fff4f4",
  };

  const TAB_NAMES = ["alpha", "beta", "omega"];
  const panes = {};
  let activeName = "alpha";
  let openCount = 0;
  let failCount = 0;

  const tabIds = {
    alpha: params.get("alpha") || sessionId,
    beta: params.get("beta") || "",
    omega: params.get("omega") || "",
  };

  const activePane = () => panes[activeName];

  const paintTabLink = (name, mode) => {
    const btn = $("tab-" + name);
    if (!btn) return;
    btn.classList.toggle("ok", mode === "ok");
    btn.classList.toggle("bad", mode === "bad");
  };

  const applyPaneMeta = (pane) => {
    if (!pane) return;
    metaSize.textContent = pane.term.cols + "×" + pane.term.rows;
    if (pane.cwd) {
      metaCwd.textContent = pane.cwd;
      metaCwd.title = pane.cwd;
    }
    if (pane.mode) metaMode.textContent = pane.mode;
  };

  const fitPane = (pane) => {
    if (!pane) return;
    try {
      pane.fit.fit();
    } catch {
      return;
    }
    if (pane === activePane()) {
      metaSize.textContent = pane.term.cols + "×" + pane.term.rows;
    }
    if (pane.ws && pane.ws.readyState === WebSocket.OPEN) {
      pane.ws.send(JSON.stringify({ type: "resize", cols: pane.term.cols, rows: pane.term.rows }));
    }
  };

  const showTab = (name) => {
    if (!TAB_NAMES.includes(name)) return;
    activeName = name;
    TAB_NAMES.forEach((n) => {
      const paneEl = $("pane-" + n);
      const tabBtn = $("tab-" + n);
      const on = n === name;
      if (paneEl) {
        paneEl.classList.toggle("active", on);
        paneEl.hidden = !on;
      }
      if (tabBtn) tabBtn.setAttribute("aria-selected", on ? "true" : "false");
    });
    const pane = panes[name];
    if (pane) {
      fitPane(pane);
      if (!llamaOn) pane.term.focus();
      applyPaneMeta(pane);
    }
  };

  const makePane = (name) => {
    const el = $("term-" + name);
    const term = new Terminal({
      cursorBlink: true,
      cursorStyle: "block",
      fontFamily: '"Share Tech Mono", ui-monospace, monospace',
      fontSize: 15,
      lineHeight: 1.15,
      letterSpacing: 0,
      scrollback: 8000,
      allowProposedApi: true,
      theme: TERM_THEME,
    });
    const fit = new FitAddonCtor();
    term.loadAddon(fit);
    term.open(el);
    const pane = { name, term, fit, ws: null, cwd: "", mode: "" };
    panes[name] = pane;
    term.onData((data) => {
      if (pane.ws && pane.ws.readyState === WebSocket.OPEN) pane.ws.send(data);
    });
    return pane;
  };

  const connectPane = (name, sid) => {
    const pane = panes[name] || makePane(name);
    if (!sid) {
      paintTabLink(name, "bad");
      return;
    }
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/${sid}`);
    ws.binaryType = "arraybuffer";
    pane.ws = ws;

    ws.onopen = () => {
      openCount += 1;
      paintTabLink(name, "ok");
      if (openCount === 1) {
        setLink("ok");
        bootHint.textContent = "CHANNEL OPEN";
        boot.classList.add("done");
      }
      fitPane(pane);
      if (name === activeName && !llamaOn) pane.term.focus();
    };

    ws.onmessage = (ev) => {
      if (typeof ev.data === "string") {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === "meta") {
            if (msg.cwd) pane.cwd = msg.cwd;
            if (msg.mode) pane.mode = msg.mode;
            if (name === activeName && !llamaOn) applyPaneMeta(pane);
          } else if (msg.type === "exit") {
            paintTabLink(name, "bad");
            if (name === activeName) {
              setLink("bad");
              linkState.textContent = "ENDED " + (msg.code ?? "");
            }
          }
        } catch {
          pane.term.write(ev.data);
        }
        return;
      }
      pane.term.write(new Uint8Array(ev.data));
    };

    ws.onclose = () => {
      paintTabLink(name, "bad");
      if (name === activeName) setLink("bad");
    };

    ws.onerror = () => {
      failCount += 1;
      paintTabLink(name, "bad");
      if (name === activeName) setLink("bad");
      if (openCount === 0 && failCount >= TAB_NAMES.length) {
        boot.classList.add("error");
        bootHint.textContent = "COMM-LINK FAILED";
      }
    };
  };

  const cloneSession = async (fromId) => {
    const resp = await fetch("/api/session/clone", {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ from: fromId }),
    });
    if (!resp.ok) throw new Error("clone failed");
    const meta = await resp.json();
    if (!meta || !meta.id) throw new Error("clone returned no id");
    return meta.id;
  };

  const ensureTabIds = async () => {
    const seed = tabIds.alpha;
    if (!seed) return;
    for (const name of ["beta", "omega"]) {
      if (tabIds[name]) continue;
      try {
        tabIds[name] = await cloneSession(seed);
      } catch {
        tabIds[name] = "";
      }
    }
    try {
      const u = new URL(location.href);
      u.searchParams.set("s", tabIds.alpha);
      u.searchParams.set("alpha", tabIds.alpha);
      if (tabIds.beta) u.searchParams.set("beta", tabIds.beta);
      if (tabIds.omega) u.searchParams.set("omega", tabIds.omega);
      history.replaceState({}, "", u);
    } catch {
      /* ignore */
    }
  };

  const connect = async () => {
    TAB_NAMES.forEach(makePane);
    if (!tabIds.alpha) {
      setLink("bad");
      boot.classList.add("error");
      bootHint.textContent = "NO SESSION  //  RUN  adjutant";
      return;
    }
    await ensureTabIds();
    TAB_NAMES.forEach((name) => connectPane(name, tabIds[name]));
    showTab("alpha");
  };

  document.querySelectorAll(".chan-tab").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      if (llamaOn) return;
      showTab(btn.getAttribute("data-tab"));
    });
  });

  window.addEventListener("resize", () => {
    fitPane(activePane());
  });

  document.addEventListener("click", (ev) => {
    if (llamaOn) return;
    if (ev.target.closest("a, button, nav, input, textarea, iframe, #sudo-prompt")) return;
    const pane = activePane();
    if (pane) pane.term.focus();
  });

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
      const pane = activePane();
      if (pane) pane.term.focus();
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

  let sudoBusy = false;
  let sudoAppInstalled = false;
  let sudoAppDeclined = false;

  const showSudoUninstall = (on) => {
    if (sudoUninstall) sudoUninstall.hidden = !on;
    if (sudoUnSep) sudoUnSep.hidden = !on;
  };

  const paintSudo = (on, err) => {
    if (!btnSudo) return;
    btnSudo.setAttribute("aria-checked", on ? "true" : "false");
    sudoState.textContent = on ? "ON" : "OFF";
    if (sudoDock) sudoDock.classList.toggle("err", Boolean(err));
    btnSudo.title = err
      ? String(err).slice(0, 160)
      : sudoAppInstalled
        ? "Open NOPASSWD utility"
        : on
          ? "Passwordless sudo is on"
          : "Passwordless sudo is off";
  };

  const loadSudo = async () => {
    if (!btnSudo) return;
    try {
      const resp = await fetch("/api/sudo", { cache: "no-store" });
      const meta = await resp.json();
      paintSudo(Boolean(meta && meta.enabled), meta && meta.error);
    } catch (err) {
      paintSudo(false, err && err.message ? err.message : "status failed");
    }
  };

  const loadSudoApp = async () => {
    try {
      const resp = await fetch("/api/sudo-app", { cache: "no-store" });
      const meta = await resp.json();
      sudoAppInstalled = Boolean(meta && meta.installed);
      sudoAppDeclined = Boolean(meta && meta.declined);
      showSudoUninstall(sudoAppInstalled);
    } catch {
      sudoAppInstalled = false;
      showSudoUninstall(false);
    }
  };

  const sudoAppAction = async (action) => {
    const resp = await fetch("/api/sudo-app", {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    });
    return resp.json();
  };

  const setSudo = async (on) => {
    if (!btnSudo || sudoBusy) return;
    sudoBusy = true;
    btnSudo.disabled = true;
    try {
      const resp = await fetch("/api/sudo", {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: on }),
      });
      const meta = await resp.json();
      paintSudo(Boolean(meta && meta.enabled), meta && meta.ok ? "" : meta && meta.error);
    } catch (err) {
      paintSudo(!on, err && err.message ? err.message : "toggle failed");
    } finally {
      sudoBusy = false;
      btnSudo.disabled = false;
    }
  };

  const openSudoPrompt = (on) => {
    if (!sudoPrompt) return;
    sudoPrompt.hidden = false;
  };

  const closeSudoPrompt = () => {
    if (sudoPrompt) sudoPrompt.hidden = true;
  };

  if (btnSudo) {
    btnSudo.addEventListener("click", async (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      if (sudoBusy) return;
      if (sudoAppInstalled) {
        try {
          await sudoAppAction("launch");
        } catch (err) {
          paintSudo(btnSudo.getAttribute("aria-checked") === "true", err && err.message);
        }
        return;
      }
      if (!sudoAppDeclined) {
        openSudoPrompt();
        return;
      }
      const on = btnSudo.getAttribute("aria-checked") === "true";
      setSudo(!on);
    });
  }

  const yesBtn = $("sudo-prompt-yes");
  const noBtn = $("sudo-prompt-no");
  if (yesBtn) {
    yesBtn.addEventListener("click", async (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      yesBtn.disabled = true;
      try {
        const meta = await sudoAppAction("install");
        sudoAppInstalled = Boolean(meta && meta.ok && meta.installed);
        sudoAppDeclined = false;
        showSudoUninstall(sudoAppInstalled);
        closeSudoPrompt();
        if (!sudoAppInstalled) {
          paintSudo(btnSudo && btnSudo.getAttribute("aria-checked") === "true", meta && meta.error);
        }
      } catch (err) {
        paintSudo(false, err && err.message ? err.message : "install failed");
      } finally {
        yesBtn.disabled = false;
      }
    });
  }
  if (noBtn) {
    noBtn.addEventListener("click", async (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      closeSudoPrompt();
      try {
        await sudoAppAction("decline");
        sudoAppDeclined = true;
      } catch {
        sudoAppDeclined = true;
      }
    });
  }
  if (sudoUninstall) {
    sudoUninstall.addEventListener("click", async (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      if (!confirm("Remove the NOPASSWD desktop utility? Adjutant stays installed.")) return;
      try {
        await sudoAppAction("uninstall");
        sudoAppInstalled = false;
        sudoAppDeclined = false;
        showSudoUninstall(false);
        await loadSudo();
      } catch (err) {
        paintSudo(btnSudo.getAttribute("aria-checked") === "true", err && err.message);
      }
    });
  }

  const start = async () => {
    await typeLines();
    await new Promise((r) => setTimeout(r, 420));
    await connect();
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
  loadSudoApp();
  loadSudo();
  setInterval(loadSudo, 2000);
  setInterval(loadSudoApp, 4000);

  start();
})();
