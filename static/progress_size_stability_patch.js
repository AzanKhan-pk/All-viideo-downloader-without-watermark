(() => {
  if (window.__AVD_PROGRESS_SIZE_STABILITY__) return;
  window.__AVD_PROGRESS_SIZE_STABILITY__ = true;

  const normalize = value => String(value ?? '').replace(/\s+/g, ' ').trim();
  const isPlaceholder = value => {
    const text = normalize(value).toLowerCase();
    return !text || text === 'unknown' || text === 'size unavailable' || text === '—' || text === '-' || /^0(?:\.0+)?\s*b$/.test(text);
  };

  function findSizeValue(card) {
    const stats = card.querySelectorAll('.job-stats .stat');
    for (const stat of stats) {
      const label = normalize(stat.querySelector('.stat-label')?.textContent).toLowerCase();
      if (label === 'file size' || label === 'filesize') return stat.querySelector('.stat-value');
    }
    return null;
  }

  function completed(card) {
    const status = normalize(card.querySelector('[data-field="status"], .job-status')?.textContent).toLowerCase();
    return status === 'completed' || status.includes('completed');
  }

  function stabilize(card) {
    if (!card || card.classList.contains('avd-history-card')) return;
    const node = findSizeValue(card);
    if (!node) return;

    const current = normalize(node.textContent);
    if (completed(card)) {
      delete card.dataset.avdFixedFileSize;
      delete card.dataset.avdFinalSize;
      return;
    }

    const locked = normalize(card.dataset.avdFixedFileSize);
    if (locked && !isPlaceholder(locked)) {
      if (current !== locked) node.textContent = locked;
      return;
    }

    if (!isPlaceholder(current)) {
      card.dataset.avdFixedFileSize = current;
    }
  }

  function scan(root = document) {
    root.querySelectorAll?.('.job').forEach(stabilize);
  }

  const boot = () => {
    scan();
    const jobs = document.getElementById('jobs');
    if (jobs && window.MutationObserver) {
      const observer = new MutationObserver(() => scan(jobs));
      observer.observe(jobs, {childList: true, subtree: true, characterData: true});
    }
    setInterval(() => scan(jobs || document), 500);
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
