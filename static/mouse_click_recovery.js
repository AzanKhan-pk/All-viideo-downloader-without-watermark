(() => {
  if (window.__AVD_MOUSE_CLICK_RECOVERY__) return;
  window.__AVD_MOUSE_CLICK_RECOVERY__ = true;

  const isControl = el => !!el && !!el.closest('button,a,input,textarea,select,summary,[role="button"]');
  const repairControls = root => {
    (root || document).querySelectorAll?.('button,a,input,textarea,select,summary,[role="button"]').forEach(el => {
      el.style.pointerEvents = 'auto';
      if (el.disabled && el.tagName === 'BUTTON') return;
    });
  };

  const repairOverlays = () => {
    const vw = Math.max(document.documentElement.clientWidth, window.innerWidth || 0);
    const vh = Math.max(document.documentElement.clientHeight, window.innerHeight || 0);
    document.querySelectorAll('body *').forEach(el => {
      if (!el || el === document.body || el === document.documentElement) return;
      const s = getComputedStyle(el);
      if (s.display === 'none' || s.visibility === 'hidden') return;
      if (s.pointerEvents === 'none') return;
      if (!(s.position === 'fixed' || s.position === 'absolute')) return;
      const r = el.getBoundingClientRect();
      if (r.width < vw * 0.72 || r.height < vh * 0.72) return;
      if (isControl(el)) return;
      if (el.classList.contains('toast') || el.classList.contains('avd-context-menu')) {
        if (!el.classList.contains('open') && !el.classList.contains('show')) el.style.pointerEvents = 'none';
        return;
      }
      el.style.pointerEvents = 'none';
    });
    repairControls(document);
  };

  const boot = () => {
    repairOverlays();
    setTimeout(repairOverlays, 100);
    setTimeout(repairOverlays, 500);
    setTimeout(repairOverlays, 1200);
    if (window.MutationObserver) {
      new MutationObserver(() => repairOverlays()).observe(document.body, {childList:true, subtree:true});
    }
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true});
  else boot();
})();
