from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
launcher = ROOT / "windows" / "launcher.py"
text = launcher.read_text(encoding="utf-8")

marker = """    const refreshFolder = () => {\n"""
if marker not in text:
    raise SystemExit("Patch target not found: refreshFolder")

injection = r'''    // Job-card close control: remove the item from the visible download list
    // only. It deliberately does not delete the completed file from disk.
    const hiddenJobs = new Set(JSON.parse(localStorage.getItem('avd-hidden-jobs') || '[]'));
    const rememberHidden = key => {
      hiddenJobs.add(key);
      localStorage.setItem('avd-hidden-jobs', JSON.stringify([...hiddenJobs].slice(-200)));
    };
    const jobKey = job => {
      const title = job.querySelector('.job-title')?.textContent?.trim() || '';
      const stats = job.querySelector('.job-stats')?.textContent?.trim() || '';
      return (title + '|' + stats).slice(0, 500);
    };
    const addJobCloseButtons = () => {
      document.querySelectorAll('.job').forEach(job => {
        const key = jobKey(job);
        if (hiddenJobs.has(key)) { job.style.display = 'none'; return; }
        if (job.querySelector('.avd-job-close')) return;
        job.style.position = 'relative';
        const close = document.createElement('button');
        close.type = 'button';
        close.className = 'avd-job-close';
        close.setAttribute('aria-label', 'Remove from download list');
        close.title = 'Remove from list (keeps saved file)';
        close.textContent = '×';
        close.onclick = e => {
          e.preventDefault();
          e.stopPropagation();
          rememberHidden(jobKey(job));
          job.remove();
          const count = document.querySelectorAll('.job:not([style*="display: none"])').length;
          const badge = document.querySelector('.jobs-count');
          if (badge) badge.textContent = String(count);
        };
        job.appendChild(close);
      });
    };
    const jobStyle = document.createElement('style');
    jobStyle.textContent = `.avd-job-close{position:absolute;top:8px;right:8px;width:30px;height:30px;padding:0;border:1px solid rgba(255,255,255,.12);border-radius:9px;background:rgba(239,68,68,.12);color:#ffb8b8;font:900 22px/28px Arial,sans-serif;cursor:pointer;z-index:5}.avd-job-close:hover{background:rgba(239,68,68,.24);color:#fff}.job{position:relative!important}`;
    document.head.appendChild(jobStyle);
    const jobObserver = new MutationObserver(addJobCloseButtons);
    jobObserver.observe(document.body, {childList:true, subtree:true});
    setTimeout(addJobCloseButtons, 300);

'''
text = text.replace(marker, injection + marker, 1)
launcher.write_text(text, encoding="utf-8")

# Make TikTok extraction URL-aware and resilient: try browser impersonation for
# TikTok, but keep a non-impersonated fallback if the site changes its fingerprint
# challenge. This is intentionally limited to public URLs supported by yt-dlp.
tiktok = ROOT / "tools" / "tiktok_focus_patch.py"
t = tiktok.read_text(encoding="utf-8")
old = '''            opts.update({\n                "impersonate": "chrome",\n                "http_headers": {\n                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",\n                    "Accept-Language": "en-US,en;q=0.9",\n                    "Referer": "https://www.tiktok.com/",\n                },\n            })'''
new = '''            opts.update({\n                # curl_cffi browser impersonation is useful for TikTok's TLS/fingerprint checks.\n                # Keep it scoped to TikTok instead of forcing it on every extractor.\n                "impersonate": "chrome-131:windows-10",\n                "http_headers": {\n                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",\n                    "Accept-Language": "en-US,en;q=0.9",\n                    "Referer": "https://www.tiktok.com/",\n                },\n            })'''
if old in t:
    t = t.replace(old, new, 1)
else:
    raise SystemExit("TikTok patch target not found")
tiktok.write_text(t, encoding="utf-8")

print("UI job close control and TikTok fallback-ready settings patched.")
