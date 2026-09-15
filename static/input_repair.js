(() => {
  if (window.__AVD_INPUT_REPAIR__) return;
  window.__AVD_INPUT_REPAIR__ = true;
  const repair = () => {
    document.querySelectorAll('body *').forEach((el) => {
      const s = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      if (s.position === 'fixed' && s.pointerEvents !== 'none' && r.width >= innerWidth * .85 && r.height >= innerHeight * .85) {
        const interactive = el.matches('button,a,input,textarea,select,[role="button"]') || /menu|modal|dialog|picker|toast|context/i.test(String(el.className)+' '+String(el.id));
        if (!interactive) el.style.pointerEvents = 'none';
      }
    });
    document.querySelectorAll('button,a,input,textarea,select,[role="button"]').forEach(el => { el.style.pointerEvents='auto'; });
  };
  const style=document.createElement('style');
  style.textContent='body,body *{-webkit-user-select:text;user-select:text}button,a,input,textarea,select,[role="button"]{pointer-events:auto!important}';
  document.head.appendChild(style);
  setTimeout(repair,100); setTimeout(repair,1000); setInterval(repair,2000); window.addEventListener('resize',repair);
})();
