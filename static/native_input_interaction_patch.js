(() => {
  if (window.__AVD_NATIVE_INPUT_INTERACTION__) return;
  window.__AVD_NATIVE_INPUT_INTERACTION__ = true;

  const isEditable = target => {
    const el = target && target.closest ? target.closest('input, textarea, [contenteditable="true"]') : null;
    return !!el && !el.disabled && !el.readOnly;
  };

  // The app has a custom context menu for normal page content. Editable
  // controls must keep the browser's native menu so URL copy/cut/paste/select
  // and normal text selection continue to work.
  window.addEventListener('contextmenu', event => {
    if (isEditable(event.target)) {
      event.stopPropagation();
    }
  }, true);

  const style = document.createElement('style');
  style.textContent = `
    #url,
    input[type="text"],
    input[type="url"],
    textarea,
    [contenteditable="true"] {
      user-select: text !important;
      -webkit-user-select: text !important;
      -webkit-touch-callout: default !important;
      cursor: text !important;
      pointer-events: auto !important;
    }
  `;
  document.head.appendChild(style);
})();
