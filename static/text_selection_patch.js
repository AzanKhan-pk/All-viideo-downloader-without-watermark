(() => {
  if (window.__AVD_TEXT_SELECTION_PATCH__) return;
  window.__AVD_TEXT_SELECTION_PATCH__ = true;
  const style = document.createElement('style');
  style.textContent = `
    .job, .job *:not(button):not(a):not(input):not(textarea):not(select),
    .result, .result *:not(button):not(a):not(input):not(textarea):not(select),
    #status, #status * {
      user-select: text !important;
      -webkit-user-select: text !important;
      cursor: text !important;
    }
    button, a, input, textarea, select, img { cursor: pointer; }
    input, textarea { cursor: text; }
  `;
  document.head.appendChild(style);

  // Keep the normal browser Ctrl/Cmd+C behavior. If a selected text node is
  // present, do not let custom UI handlers interfere with the native copy.
  document.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'c') {
      const selection = window.getSelection ? String(window.getSelection() || '') : '';
      if (selection.trim()) return;
      const field = document.activeElement;
      if (field && (field.tagName === 'INPUT' || field.tagName === 'TEXTAREA')) return;
    }
  }, true);
})();
