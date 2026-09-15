(() => {
  if (window.__AVD_FINAL_UI_RELIABILITY__) return;
  window.__AVD_FINAL_UI_RELIABILITY__ = true;

  const hostOf = value => {
    try { return new URL(value).hostname.toLowerCase().replace(/^www\./, ''); }
    catch (_) { return ''; }
  };
  const extraSocial = host => host === 'facebook.com' || host.endsWith('.facebook.com') || host === 'fb.watch'
    || host === 'instagram.com' || host.endsWith('.instagram.com')
    || host === 'x.com' || host.endsWith('.x.com') || host === 'twitter.com' || host.endsWith('.twitter.com')
    || host === 'reddit.com' || host.endsWith('.reddit.com');

  function installExtraSocialFetch() {
    const button = document.getElementById('fetch');
    const input = document.getElementById('url');
    const result = document.getElementById('result');
    const status = document.getElementById('status');
    if (!button || !input || !result || !status) return;

    const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
    const quality = () => Number(document.querySelector('.qualities [data-q].active')?.dataset.q || 144);
    const mode = () => document.querySelector('.modes [data-mode].active')?.dataset.mode || 'video';

    async function start(kind) {
      const response = await fetch('/api/special-download', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({url: input.value.trim(), kind, quality: quality()})
      });
      const data = await response.json();
      if (!response.ok || !data.job_id) throw new Error(data.error || 'Could not start the download.');
      if (typeof createJobCard === 'function') createJobCard(data.job_id);
      status.textContent = kind === 'images' ? 'Picture download started.' : kind === 'audio' ? 'Audio download started.' : 'Download started.';
      if (typeof showToast === 'function') showToast(status.textContent);
    }

    function render(data) {
      const images = (data.images || []).filter(item => item && item.url).slice(0, 40);
      result.hidden = false;
      result.innerHTML = `<div class="result-title">${escapeHtml(data.title || 'Public media')}</div>` +
        `<div class="result-meta">Platform: ${escapeHtml(data.extractor || hostOf(input.value))}<br>Public media detected. Choose what you want to download.</div>` +
        (images.length ? `<div class="social-gallery"><div class="social-gallery-head"><div class="social-gallery-title">🖼️ Pictures</div><div class="social-gallery-count">${images.length} image${images.length === 1 ? '' : 's'} found</div></div>` +
          `<div class="social-gallery-grid">${images.map((img, i) => `<label class="social-image-card selected"><input type="checkbox" data-final-image="${i}" checked><img src="${escapeHtml(img.url)}" alt="Image ${i+1}" loading="lazy"></label>`).join('')}</div>` +
          `<div class="social-gallery-actions"><button class="chip" id="finalSelectAll" type="button">Select all</button><button class="chip" id="finalClearAll" type="button">Clear</button><button class="chip primary" id="finalDownloadImages" type="button">⬇ Download selected</button></div></div>` : '') +
        `<div class="download-area"><button class="btn download-btn" id="finalDownloadVideo" type="button">${mode() === 'audio' ? '🎵 Start MP3 Download' : `⬇ Start ${quality()}p MP4 Download`}</button></div>`;

      const cards = [...result.querySelectorAll('.social-image-card')];
      cards.forEach(card => card.addEventListener('click', event => {
        if (event.target.matches('input')) { card.classList.toggle('selected', event.target.checked); return; }
        const cb = card.querySelector('input'); cb.checked = !cb.checked; card.classList.toggle('selected', cb.checked);
      }));
      result.querySelector('#finalSelectAll')?.addEventListener('click', () => cards.forEach(card => { const cb = card.querySelector('input'); cb.checked = true; card.classList.add('selected'); }));
      result.querySelector('#finalClearAll')?.addEventListener('click', () => cards.forEach(card => { const cb = card.querySelector('input'); cb.checked = false; card.classList.remove('selected'); }));
      result.querySelector('#finalDownloadImages')?.addEventListener('click', async event => {
        const selected = [...result.querySelectorAll('[data-final-image]:checked')].map(cb => images[Number(cb.dataset.finalImage)]);
        if (!selected.length) { status.textContent = 'Select at least one picture first.'; return; }
        event.currentTarget.disabled = true;
        try {
          const response = await fetch('/api/special-download', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url:input.value.trim(), kind:'images', images:selected})});
          const data = await response.json();
          if (!response.ok || !data.job_id) throw new Error(data.error || 'Could not start picture download.');
          if (typeof createJobCard === 'function') createJobCard(data.job_id);
          status.textContent = 'Picture download started.';
        } catch (error) { status.textContent = error.message || 'Picture download failed.'; }
        finally { event.currentTarget.disabled = false; }
      });
      result.querySelector('#finalDownloadVideo')?.addEventListener('click', async event => {
        event.currentTarget.disabled = true;
        try { await start(mode() === 'audio' ? 'audio' : 'video'); }
        catch (error) { status.textContent = error.message || 'Download failed.'; }
        finally { event.currentTarget.disabled = false; }
      });
    }

    document.addEventListener('click', async event => {
      const target = event.target.closest('#fetch');
      if (!target || !extraSocial(hostOf(input.value.trim()))) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      target.disabled = true;
      target.textContent = 'Reading…';
      result.hidden = true;
      status.textContent = 'Checking public media…';
      try {
        const response = await fetch('/api/media-preview', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url:input.value.trim()})});
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'The site did not return usable public media data.');
        render(data);
        status.textContent = 'Media detected. Ready to download.';
      } catch (error) {
        status.textContent = error.message || 'The site did not return usable public media data.';
        if (typeof showToast === 'function') showToast(status.textContent);
      } finally { target.disabled = false; target.textContent = 'Fetch Media'; }
    }, true);
  }

  // Static CSS only: no MutationObserver/setInterval. This prevents the UI
  // freeze caused by repeatedly modifying the DOM while observing that same DOM.
  function patchFolder() {
    const style = document.createElement('style');
    style.textContent = `
      [data-field="complete"]{display:flex!important;align-items:center!important;width:100%!important;gap:10px!important}
      .avd-history-actions{width:100%!important;display:flex!important;justify-content:flex-end!important;align-items:center!important;margin-left:auto!important;gap:8px!important}
      .avd-history-actions .avd-open-folder{margin-left:auto!important;min-width:auto!important;padding:7px 12px!important;white-space:nowrap!important;font-size:0!important}
      .avd-history-actions .avd-open-folder::after{content:'📂 Open in folder';font-size:14px!important}
    `;
    document.head.appendChild(style);
  }

  const boot = () => { installExtraSocialFetch(); patchFolder(); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true}); else boot();
})();
