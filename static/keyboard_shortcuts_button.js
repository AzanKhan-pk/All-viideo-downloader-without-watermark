(() => {
  if (document.getElementById('avdKeyboardShortcutsButton')) return;
  const nav = document.querySelector('.nav');
  if (!nav) return;
  const button = document.createElement('button');
  button.id = 'avdKeyboardShortcutsButton';
  button.type = 'button';
  button.textContent = '⌨ Keyboard Shortcuts';
  button.title = 'Keyboard Shortcuts (F1 / Ctrl+/)';
  button.style.cssText = 'color:#cfcfdc;text-decoration:none;padding:9px 13px;border-radius:10px;font-size:14px;transition:.25s ease;background:transparent;border:0;cursor:pointer;font-weight:700;';
  button.addEventListener('mouseenter', () => { button.style.color = 'white'; button.style.background = 'rgba(255,255,255,.07)'; });
  button.addEventListener('mouseleave', () => { button.style.color = '#cfcfdc'; button.style.background = 'transparent'; });
  button.addEventListener('click', () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'F1', bubbles: true, cancelable: true })));
  nav.appendChild(button);
})();
