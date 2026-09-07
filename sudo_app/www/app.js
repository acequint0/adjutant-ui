(() => {
  const $ = (id) => document.getElementById(id);
  const btn = $("btn-sudo");
  const stateEl = $("sudo-state");
  const dock = btn.closest(".sudo-dock");
  const led = $("led");
  const linkState = $("link-state");
  const hint = $("hint");
  const metaUser = $("meta-user");
  const metaHost = $("meta-host");
  const metaClock = $("meta-clock");
  const btnUninstall = $("btn-uninstall");

  metaHost.textContent = location.hostname || "127.0.0.1";
  let busy = false;

  const tick = () => {
    metaClock.textContent = new Date().toTimeString().slice(0, 8);
  };
  tick();
  setInterval(tick, 1000);

  const paint = (on, err, user) => {
    btn.setAttribute("aria-checked", on ? "true" : "false");
    stateEl.textContent = on ? "ON" : "OFF";
    dock.classList.toggle("err", Boolean(err));
    led.className = "led" + (err ? " bad" : " ok");
    linkState.textContent = err ? "FAULT" : on ? "NOPASSWD" : "PASSWD";
    if (user) metaUser.textContent = user;
    hint.textContent = err
      ? String(err).slice(0, 180)
      : on
        ? "SUDO WILL NOT ASK FOR A PASSWORD"
        : "TURN ON REQUIRES YOUR PASSWORD // TURN OFF DOES NOT";
    btn.title = err ? String(err).slice(0, 160) : on ? "Passwordless sudo is on" : "Passwordless sudo is off";
  };

  const load = async () => {
    try {
      const resp = await fetch("/api/sudo", { cache: "no-store" });
      const meta = await resp.json();
      paint(Boolean(meta && meta.enabled), meta && meta.error, meta && meta.user);
    } catch (err) {
      paint(false, err && err.message ? err.message : "status failed");
    }
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
      paint(Boolean(meta && meta.enabled), meta && meta.ok ? "" : meta && meta.error, meta && meta.user);
    } catch (err) {
      paint(!on, err && err.message ? err.message : "toggle failed");
    } finally {
      busy = false;
      btn.disabled = false;
    }
  };

  btn.addEventListener("click", (ev) => {
    ev.preventDefault();
    const on = btn.getAttribute("aria-checked") === "true";
    setSudo(!on);
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
