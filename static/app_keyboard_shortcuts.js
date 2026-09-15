(() => {
  if (window.__AVD_APP_KEYBOARD_SHORTCUTS__) return;
  window.__AVD_APP_KEYBOARD_SHORTCUTS__ = true;

  const api = () => window.pywebview && window.pywebview.api;
  const urlInput = () => document.getElementById('url');
  const fetchButton = () => document.getElementById('fetch');

  const callNative = (name) => {
    const bridge = api();
    if (bridge && typeof bridge[name] === 'function') {
      try { return bridge[name](); } catch (_) {}
    }
    return null;
  };

  const focusUrl = (selectAll = true) => {
    const input = urlInput();
    if (!input) return;
    input.focus({ preventScroll: true });
    if (selectAll) input.select();
  };

  const fetchUrl = () => {
    const button = fetchButton();
    if (!button || button.disabled) return;
    button.click();
  };

  const openAbout = () => {
    const button = document.querySelector('.about-toggle, [data-action="about"], #aboutToggle');
    if (button) {
      button.click();
      return;
    }
    document.querySelector('.about-section')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  const overlay = document.createElement('div');
  overlay.id = 'avdKeyboardShortcutsOverlay';
  overlay.innerHTML = `
    <div class="avd-shortcuts-backdrop" data-shortcuts-close="1"></div>
    <section class="avd-shortcuts-dialog" role="dialog" aria-modal="true" aria-labelledby="avdShortcutsTitle">
      <div class="avd-shortcuts-head">
        <div>
          <div class="avd-shortcuts-kicker">KEYBOARD</div>
          <h2 id="avdShortcutsTitle">Keyboard Shortcuts</h2>
          <p>Fast controls for All Video Downloader</p>
        </div>
        <button class="avd-shortcuts-close" type="button" aria-label="Close keyboard shortcuts" data-shortcuts-close="1">×</button>
      </div>
      <div class="avd-shortcuts-list">
        <div class="avd-shortcut-row"><span>Focus URL box</span><kbd>Ctrl</kbd><b>+</b><kbd>L</kbd></div>
        <div class="avd-shortcut-row"><span>Focus URL box</span><kbd>Ctrl</kbd><b>+</b><kbd>K</kbd></div>
        <div class="avd-shortcut-row"><span>Fetch URL</span><kbd>Enter</kbd></div>
        <div class="avd-shortcut-row"><span>Focus + Fetch</span><kbd>Ctrl</kbd><b>+</b><kbd>Enter</kbd></div>
        <div class="avd-shortcut-row"><span>Paste / then press Enter to fetch</span><kbd>Ctrl</kbd><b>+</b><kbd>V</kbd></div>
        <div class="avd-shortcut-row"><span>Copy selected text</span><kbd>Ctrl</kbd><b>+</b><kbd>C</kbd></div>
        <div class="avd-shortcut-row"><span>Cut selected text</span><kbd>Ctrl</kbd><b>+</b><kbd>X</kbd></div>
        <div class="avd-shortcut-row"><span>Select all</span><kbd>Ctrl</kbd><b>+</b><kbd>A</kbd></div>
        <div class="avd-shortcut-row"><span>Refresh app</span><kbd>Ctrl</kbd><b>+</b><kbd>R</kbd></div>
        <div class="avd-shortcut-row"><span>Minimize window</span><kbd>Ctrl</kbd><b>+</b><kbd>Shift</kbd><b>+</b><kbd>M</kbd></div>
        <div class="avd-shortcut-row"><span>Full screen</span><kbd>F11</kbd> <em>or</em> <kbd>Ctrl</kbd><b>+</b><kbd>Shift</kbd><b>+</b><kbd>F</kbd></div>
        <div class="avd-shortcut-row"><span>Maximize window</span><kbd>Ctrl</kbd><b>+</b><kbd>Shift</kbd><b>+</b><kbd>X</kbd></div>
        <div class="avd-shortcut-row"><span>About</span><kbd>Ctrl</kbd><b>+</b><kbd>Shift</kbd><b>+</b><kbd>A</kbd></div>
        <div class="avd-shortcut-row"><span>Open this shortcut list</span><kbd>F1</kbd> <em>or</em> <kbd>Ctrl</kbd><b>+</b><kbd>/</kbd></div>
        <div class="avd-shortcut-row"><span>Close this overlay</span><kbd>Esc</kbd></div>
        <div class="avd-shortcut-row"><span>Exit app</span><kbd>Alt</kbd><b>+</b><kbd>F4</kbd> <em>or</em> <kbd>Ctrl</kbd><b>+</b><kbd>Shift</kbd><b>+</b><kbd>W</kbd></div>
      </div>
      <div class="avd-shortcuts-note">Normal Windows/browser editing shortcuts such as Ctrl+C, Ctrl+V, Ctrl+X and Ctrl+A remain enabled.</div>
    </section>`;

  const style = document.createElement('style');
  style.textContent = `
    #avdKeyboardShortcutsOverlay{display:none;position:fixed;inset:0;z-index:2147483646}
    #avdKeyboardShortcutsOverlay.open{display:block}
    .avd-shortcuts-backdrop{position:absolute;inset:0;background:rgba(0,0,0,.68);backdrop-filter:blur(7px)}
    .avd-shortcuts-dialog{position:absolute;left:50%;top:50%;width:min(700px,calc(100vw - 30px));max-height:min(82vh,760px);overflow:auto;transform:translate(-50%,-50%);padding:22px;border:1px solid rgba(124,58,237,.35);border-radius:22px;background:linear-gradient(145deg,rgba(20,18,30,.99),rgba(12,12,19,.99));box-shadow:0 30px 100px rgba(0,0,0,.65);color:#f8f8ff}
    .avd-shortcuts-head{display:flex;align-items:flex-start;justify-content:space-between;gap:15px;margin-bottom:17px}.avd-shortcuts-kicker{font-size:10px;font-weight:900;letter-spacing:2px;color:#facc15}.avd-shortcuts-head h2{margin-top:4px;font-size:24px}.avd-shortcuts-head p{margin-top:5px;color:#90909f;font-size:12px}.avd-shortcuts-close{width:38px;height:38px;border:1px solid rgba(255,255,255,.10);border-radius:11px;background:#11111a;color:#fff;font-size:25px;line-height:1;cursor:pointer}.avd-shortcuts-close:hover{border-color:rgba(250,204,21,.45);color:#facc15}
    .avd-shortcuts-list{display:flex;flex-direction:column;gap:7px}.avd-shortcut-row{display:flex;align-items:center;justify-content:flex-end;gap:6px;min-height:43px;padding:7px 10px;border:1px solid rgba(255,255,255,.07);border-radius:11px;background:rgba(255,255,255,.025);font-size:12px}.avd-shortcut-row span{margin-right:auto;color:#d7d7e0}.avd-shortcut-row kbd{min-width:25px;padding:5px 7px;border:1px solid rgba(255,255,255,.15);border-bottom-color:rgba(255,255,255,.28);border-radius:7px;background:#0a0a10;color:#fff;font:800 11px Inter,Arial,sans-serif;text-align:center;box-shadow:0 2px 0 rgba(255,255,255,.06)}.avd-shortcut-row b{color:#696978;font-size:10px}.avd-shortcut-row em{font-style:normal;color:#666676;font-size:10px;margin:0 2px}.avd-shortcuts-note{margin-top:14px;padding:11px 12px;border-radius:10px;background:rgba(124,58,237,.08);color:#9f9faf;font-size:11px;line-height:1.55}
    @media(max-width:600px){.avd-shortcuts-dialog{padding:16px}.avd-shortcuts-head h2{font-size:20px}.avd-shortcut-row{flex-wrap:wrap;justify-content:flex-end}.avd-shortcut-row span{width:100%;margin:0 0 3px}}
  `;
  document.head.appendChild(style);
  document.body.appendChild(overlay);

  const closeOverlay = () => overlay.classList.remove('open');
  const openOverlay = () => {
    overlay.classList.add('open');
    overlay.querySelector('.avd-shortcuts-close')?.focus();
  };
  overlay.addEventListener('click', event => {
    if (event.target.closest('[data-shortcuts-close]')) closeOverlay();
  });

  document.addEventListener('keydown', event => {
    const key = event.key.toLowerCase();
    const ctrl = event.ctrlKey && !event.altKey;
    const url = urlInput();
    const target = event.target;

    // Never block normal Ctrl+C / Ctrl+V / Ctrl+X / Ctrl+A editing.
    if (ctrl && !event.shiftKey && (key === 'c' || key === 'v' || key === 'x' || key === 'a')) return;

    // URL shortcuts.
    if (ctrl && !event.shiftKey && (key === 'l' || key === 'k')) {
      event.preventDefault();
      event.stopImmediatePropagation();
      focusUrl(true);
      return;
    }

    if (key === 'enter' && target === url) {
      event.preventDefault();
      event.stopImmediatePropagation();
      fetchUrl();
      return;
    }

    if (ctrl && key === 'enter') {
      event.preventDefault();
      event.stopImmediatePropagation();
      focusUrl(false);
      fetchUrl();
      return;
    }

    // Shortcut list: F1 or Ctrl+/.
    if (key === 'f1' || (ctrl && key === '/')) {
      event.preventDefault();
      event.stopImmediatePropagation();
      overlay.classList.contains('open') ? closeOverlay() : openOverlay();
      return;
    }

    if (key === 'escape') {
      if (overlay.classList.contains('open')) {
        event.preventDefault();
        closeOverlay();
      }
      return;
    }

    if (overlay.classList.contains('open')) return;

    if (ctrl && event.shiftKey && key === 'm') {
      event.preventDefault();
      callNative('minimize_window');
      return;
    }
    if ((key === 'f11') || (ctrl && event.shiftKey && key === 'f')) {
      event.preventDefault();
      callNative('toggle_fullscreen');
      return;
    }
    if (ctrl && event.shiftKey && key === 'x') {
      event.preventDefault();
      callNative('maximize_window');
      return;
    }
    if (ctrl && event.shiftKey && key === 'a') {
      event.preventDefault();
      openAbout();
      return;
    }
    if (ctrl && event.shiftKey && key === 'w') {
      event.preventDefault();
      callNative('close_window');
      return;
    }
  }, true);
})();
