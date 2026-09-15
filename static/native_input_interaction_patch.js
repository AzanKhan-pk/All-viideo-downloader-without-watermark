(() => {
  if (window.__AVD_NATIVE_INPUT_INTERACTION__) return;
  window.__AVD_NATIVE_INPUT_INTERACTION__ = true;

  const isEditable = target => {
    const el = target && target.closest ? target.closest('input, textarea, [contenteditable="true"]') : null;
    return !!el && !el.disabled && !el.readOnly;
  };

  // Keep the browser's native context menu on editable controls so URL
  // copy/cut/paste/select and normal text selection work.
  window.addEventListener('contextmenu', event => {
    if (isEditable(event.target)) event.stopPropagation();
  }, true);

  // Make the normal HTML controls fully mouse-interactive.  This is limited
  // to controls and does not interfere with the downloader's own handlers.
  const style = document.createElement('style');
  style.textContent = `
    button, a, input, textarea, select, [role="button"], [contenteditable="true"] {
      pointer-events: auto !important;
    }
    #url, input[type="text"], input[type="url"], textarea, [contenteditable="true"] {
      user-select: text !important;
      -webkit-user-select: text !important;
      -webkit-touch-callout: default !important;
      cursor: text !important;
    }
    button, a, select, [role="button"] { cursor: pointer !important; }
  `;
  (document.head || document.documentElement).appendChild(style);

  // If an old transparent/fixed UI layer is sitting above a real control,
  // pass mouse activation through to the control underneath it.  This only
  // handles genuine interactive targets found at the pointer position.
  const underlyingControl = event => {
    if (!event || !document.elementsFromPoint) return null;
    const list = document.elementsFromPoint(event.clientX, event.clientY) || [];
    for (const el of list) {
      if (el === event.target) continue;
      const control = el.closest?.('button, a, input, textarea, select, [role="button"], [contenteditable="true"]');
      if (control && !control.disabled) return control;
    }
    return null;
  };

  window.addEventListener('mousedown', event => {
    if (event.button !== 0 || isEditable(event.target)) return;
    const control = underlyingControl(event);
    if (!control) return;
    if (control.matches('input, textarea, select, [contenteditable="true"]')) {
      try { control.focus(); } catch (_) {}
    }
  }, true);

  window.addEventListener('mouseup', event => {
    if (event.button !== 0 || isEditable(event.target)) return;
    const control = underlyingControl(event);
    if (!control || !control.matches('button, a, [role="button"]')) return;
    try { control.click(); } catch (_) {}
  }, true);
})();
