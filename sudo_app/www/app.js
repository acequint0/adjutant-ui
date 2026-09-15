(() => {
  const $ = (id) => document.getElementById(id);
  const btn = $("btn-sudo");
  const stateEl = $("sudo-state");
  const dock = btn.closest(".sudo-dock");
  const btnLock = $("btn-nolock");
  const lockStateEl = $("nolock-state");
  const lockDock = btnLock.closest(".sudo-dock");
  const led = $("led");
  const linkState = $("link-state");
  const hint = $("hint");
  const metaUser = $("meta-user");
  const metaHost = $("meta-host");
  const metaClock = $("meta-clock");
  const btnUninstall = $("btn-uninstall");

  metaHost.textContent = location.hostname || "127.0.0.1";
  let busy = false;
  let lockBusy = false;
  let sudoErr = "";
  let lockErr = "";

  const tick = () => {
    metaClock.textContent = new Date().toTimeString().slice(0, 8);
  };
  tick();
  setInterval(tick, 1000);

  const refreshLink = () => {
    const err = sudoErr || lockErr;
    led.className = "led" + (err ? " bad" : " ok");
    if (err) {
      linkState.textContent = "FAULT";
      return;
    }
    const sudoOn = btn.getAttribute("aria-checked") === "true";
    linkState.textContent = sudoOn ? "NOPASSWD" : "PASSWD";
  };

  const paint = (on, err, user, touchHint) => {
    btn.setAttribute("aria-checked", on ? "true" : "false");
    stateEl.textContent = on ? "ON" : "OFF";
    dock.classList.toggle("err", Boolean(err));
    sudoErr = err ? String(err) : "";
    if (user) metaUser.textContent = user;
    if (touchHint || err) {
      hint.textContent = err
        ? String(err).slice(0, 180)
        : on
          ? "SUDO WILL NOT ASK FOR A PASSWORD"
          : "TURN ON REQUIRES YOUR PASSWORD // TURN OFF DOES NOT";
    }
    btn.title = err ? String(err).slice(0, 160) : on ? "Passwordless sudo is on" : "Passwordless sudo is off";
    refreshLink();
  };

  const paintLock = (on, err, touchHint) => {
    btnLock.setAttribute("aria-checked", on ? "true" : "false");
    lockStateEl.textContent = on ? "ON" : "OFF";
    lockDock.classList.toggle("err", Boolean(err));
    lockErr = err ? String(err) : "";
    if (touchHint || err) {
      hint.textContent = err
        ? String(err).slice(0, 180)
        : on
          ? "SCREEN WILL NOT LOCK FOR THIS SESSION"
          : "IDLE LOCK RESTORED FOR THIS SESSION";
    }
    btnLock.title = err
      ? String(err).slice(0, 160)
      : on
        ? "Screen lock is inhibited for this login"
        : "Screen lock follows the desktop";
    refreshLink();
  };

  const loadSudo = async () => {
    try {
      const resp = await fetch("/api/sudo", { cache: "no-store" });
      const meta = await resp.json();
      paint(Boolean(meta && meta.enabled), meta && meta.error, meta && meta.user, false);
    } catch (err) {
      paint(false, err && err.message ? err.message : "status failed", null, false);
    }
  };

  const loadLock = async () => {
    try {
      const resp = await fetch("/api/nolock", { cache: "no-store" });
      const meta = await resp.json();
      paintLock(Boolean(meta && meta.enabled), meta && meta.error, false);
    } catch (err) {
      paintLock(false, err && err.message ? err.message : "nolock status failed", false);
    }
  };

  const load = async () => {
    await Promise.all([loadSudo(), loadLock()]);
  };

  const setSudo = async (on) => {
    if (busy) return;
    busy = true;
    btn.disabled = true;
    if (on) hint.textContent = "IDENTIFY WITH YOUR PASSWORD";
    try {
      const resp = await fetch("/api/sudo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: on }),
      });
      const meta = await resp.json();
      paint(Boolean(meta && meta.enabled), meta && meta.ok ? "" : meta && meta.error, meta && meta.user, true);
    } catch (err) {
      paint(!on, err && err.message ? err.message : "toggle failed", null, true);
    } finally {
      busy = false;
      btn.disabled = false;
    }
  };

  const setLock = async (on) => {
    if (lockBusy) return;
    lockBusy = true;
    btnLock.disabled = true;
    hint.textContent = on ? "INHIBITING SCREEN LOCK" : "RESTORING IDLE LOCK";
    try {
      const resp = await fetch("/api/nolock", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: on }),
      });
      const meta = await resp.json();
      paintLock(Boolean(meta && meta.enabled), meta && meta.ok ? "" : meta && meta.error, true);
    } catch (err) {
      paintLock(!on, err && err.message ? err.message : "nolock toggle failed", true);
    } finally {
      lockBusy = false;
      btnLock.disabled = false;
    }
  };

  btn.addEventListener("click", (ev) => {
    ev.preventDefault();
    const on = btn.getAttribute("aria-checked") === "true";
    setSudo(!on);
  });

  btnLock.addEventListener("click", (ev) => {
    ev.preventDefault();
    const on = btnLock.getAttribute("aria-checked") === "true";
    setLock(!on);
  });

  btnUninstall.addEventListener("click", async (ev) => {
    ev.preventDefault();
    if (!confirm("Remove the NOPASSWD desktop utility? Adjutant stays installed.")) return;
    btnUninstall.disabled = true;
    try {
      const resp = await fetch("/api/uninstall", { method: "POST" });
      const meta = await resp.json().catch(() => ({}));
      hint.textContent = (meta && meta.error) || "UTILITY REMOVED. YOU CAN CLOSE THIS WINDOW.";
      linkState.textContent = "REMOVED";
      led.className = "led bad";
    } catch (err) {
      hint.textContent = err && err.message ? err.message : "uninstall failed";
      btnUninstall.disabled = false;
    }
  });

  load();
  setInterval(load, 2000);
})();
