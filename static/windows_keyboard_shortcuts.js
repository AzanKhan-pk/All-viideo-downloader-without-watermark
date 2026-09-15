(() => {
  if (window.__AVD_WINDOWS_KEYBOARD_SHORTCUTS__) return;
  window.__AVD_WINDOWS_KEYBOARD_SHORTCUTS__ = true;

  const getUrlInput = () => document.getElementById('url');
  const focusUrl = (selectAll = false) => {
    const input = getUrlInput();
    if (!input) return;
    input.focus({ preventScroll: true });
    if (selectAll) input.select();
    else if (typeof input.setSelectionRange === 'function') {
      const end = input.value.length;
      input.setSelectionRange(end, end);
    }
  };

  document.addEventListener('keydown', event => {
    const key = event.key.toLowerCase();

    // Ctrl+L / Ctrl+K: jump directly to the URL box.
    if (event.ctrlKey && !event.altKey && !event.shiftKey && (key === 'l' || key === 'k')) {
      event.preventDefault();
      event.stopPropagation();
      focusUrl(true);
      return;
    }

    // Ctrl+Enter: focus the URL box and trigger Fetch Media.
    if (event.ctrlKey && !event.altKey && key === 'enter') {
      event.preventDefault();
      event.stopPropagation();
      const input = getUrlInput();
      const button = document.getElementById('fetch');
      if (input && button) {
        focusUrl(false);
        if (!button.disabled) button.click();
      }
    }
  }, true);
})();
