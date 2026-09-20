(() => {
  if (window.__AVD_MOUSE_CLICK_FINAL_FIX__) return;
  window.__AVD_MOUSE_CLICK_FINAL_FIX__ = true;

  const interactive = (node) => {
    if (!(node instanceof Element)) return null;
    return node.closest(
      'button,a,input,select,textarea,[role="button"],[role="link"],[contenteditable="true"],summary,label'
    );
  };

  const isNonInteractiveContainer = (node) => {
    if (!(node instanceof Element)) return true;
    return !interactive(node);
  };

  document.addEventListener('click', (event) => {
    if (event.defaultPrevented) return;

    const direct = interactive(event.target);
    if (direct) return;

    const x = event.clientX;
    const y = event.clientY;
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;

    let original = event.target instanceof Element ? event.target : null;
    let oldPointerEvents = '';
    if (original && isNonInteractiveContainer(original)) {
      oldPointerEvents = original.style.pointerEvents;
      original.style.pointerEvents = 'none';
    }

    let underlying = document.elementFromPoint(x, y);
    if (original) original.style.pointerEvents = oldPointerEvents;

    underlying = interactive(underlying);
    if (!underlying || underlying === direct) return;

    event.preventDefault();
    event.stopImmediatePropagation();

    try {
      underlying.focus({preventScroll: true});
    } catch (_) {}

    underlying.click();
  }, true);

  // Do not let decorative/fixed overlays steal pointer input.
  const style = document.createElement('style');
  style.textContent = `
    html, body { pointer-events: auto !important; }
    button, a, input, select, textarea, [role="button"], [role="link"], summary {
      pointer-events: auto !important;
    }
  `;
  document.head.appendChild(style);
})();