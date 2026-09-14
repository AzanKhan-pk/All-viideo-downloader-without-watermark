(() => {
  if (window.__AVD_FOLDER_ACTION_POSITION__) return;
  window.__AVD_FOLDER_ACTION_POSITION__ = true;

  const style = document.createElement('style');
  style.textContent = `
    .avd-history-actions { justify-content: flex-end !important; align-items: center !important; }
    .avd-history-actions .avd-open-folder { min-width: auto !important; padding: 0 12px !important; }
  `;
  document.head.appendChild(style);

  function apply(root = document) {
    root.querySelectorAll?.('.avd-history-actions').forEach(actions => {
      actions.style.justifyContent = 'flex-end';
      const button = actions.querySelector('.avd-open-folder');
      if (button) {
        button.textContent = '📂 Open in folder';
        button.title = 'Open in folder';
        button.setAttribute('aria-label', 'Open in folder');
      }
    });
  }

  const boot = () => {
    apply();
    const jobs = document.getElementById('jobs');
    if (jobs && window.MutationObserver) {
      new MutationObserver(() => apply(jobs)).observe(jobs, {childList: true, subtree: true});
    }
    setInterval(() => apply(jobs || document), 700);
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
