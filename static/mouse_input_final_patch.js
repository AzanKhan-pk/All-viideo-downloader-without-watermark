(() => {
  if (window.__AVD_MOUSE_INPUT_FINAL__) return;
  window.__AVD_MOUSE_INPUT_FINAL__ = true;

  const interactive = 'button,a,input,textarea,select,option,label,summary,[role="button"],[role="option"]';

  function repair() {
    document.querySelectorAll(interactive).forEach(el => {
      el.style.pointerEvents = 'auto';
      if (el.tagName === 'BUTTON' || el.tagName === 'A' || el.tagName === 'LABEL') el.style.cursor = 'pointer';
    });
    document.querySelectorAll('input,textarea').forEach(el => {
      el.style.userSelect = 'text';
      el.style.webkitUserSelect = 'text';
    });
  }

  // A transparent fixed/absolute layer can steal every click in WebView2.
  // On pointer-down, disable only a large non-interactive blocker under the cursor.
  document.addEventListener('pointerdown', event => {
    if (event.button !== 0 && event.button !== 2) return;
    const target = event.target;
    if (target && target.closest(interactive)) return;
    let node = target;
    while (node && node !== document.body) {
      const style = getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      const large = rect.width >= innerWidth * 0.70 && rect.height >= innerHeight * 0.70;
      const positioned = style.position === 'fixed' || style.position === 'absolute';
      const namedOverlay = /overlay|backdrop|modal|drawer|sheet|drag-region/i.test(String(node.id) + ' ' + String(node.className));
      if (large && positioned && !namedOverlay && !node.closest(interactive)) {
        node.style.pointerEvents = 'none';
        break;
      }
      if (namedOverlay && !node.classList.contains('open') && !node.classList.contains('show')) {
        node.style.pointerEvents = 'none';
        break;
      }
      node = node.parentElement;
    }
  }, true);

  document.addEventListener('mousemove', event => {
    const el = document.elementFromPoint(event.clientX, event.clientY);
    if (el && el.closest(interactive)) el.style.cursor = (el.matches('input,textarea') ? 'text' : 'pointer');
  }, {passive:true});

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', repair, {once:true}); else repair();
  setTimeout(repair, 100); setTimeout(repair, 500); setTimeout(repair, 1500); setInterval(repair, 3000);
})();
