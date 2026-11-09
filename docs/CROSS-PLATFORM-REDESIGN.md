# Cross-platform product refresh

## Product direction
Build an original, responsive media-downloader experience for Windows desktop and Android, using the existing Flask + yt-dlp engine. Keep the public GitHub Pages site as a download/marketing page; do not expose a public unauthenticated downloader endpoint.

## UX principles
- Clear hierarchy, restrained motion, accessible contrast, keyboard focus, reduced-motion support.
- Original visual identity: deep ink surfaces, electric cyan and violet accents, warm amber for active states; avoid copying another app's branding.
- Responsive layouts: desktop sidebar + main workspace; mobile bottom navigation and compact stacked cards.
- Motion is purposeful: subtle page transitions, progress shimmer, state-change feedback, skeleton loading, and success confirmation. Respect the prefers-reduced-motion media query.
- Do not animate continuously when idle; avoid distracting decorative motion.

## Main workflow
1. Paste or share a public media URL.
2. Analyze with yt-dlp and display detected site, title, thumbnail, duration, uploader, and available formats.
3. Show only real source formats. Offer common heights 240p, 360p, 480p, 720p, 1080p, 1440p, 2160p only when a compatible source stream exists. Never upscale or label an unavailable format as native quality.
4. Let the user choose video, audio-only, or image/gallery mode where supported.
5. Start, pause/resume when technically supported, cancel, and retry downloads.
6. Show per-job progress percentage, downloaded/total bytes, instantaneous speed, ETA, elapsed time, selected resolution, and final file path. Unknown values must display as unknown rather than fabricated values.
7. Persist completed history and user download-location settings across restarts.

## Download engine requirements
- Keep yt-dlp as the extractor layer and FFmpeg for merging separate audio/video streams.
- Treat each extractor as variable: show site-specific capabilities and clear errors rather than promising every site.
- Do not bypass DRM, paywalls, private access controls, or login restrictions. Users must have permission to download media.
- Use a real format selector based on yt-dlp format metadata. Prefer a requested height or the best available format at/below it; clearly explain fallback.
- Determine final file size from the completed file on disk.
- Protect against path traversal, unsafe filenames, duplicate job IDs, and concurrent state corruption.
- Add a bounded job queue and safe cleanup for temporary files.

## Cross-platform implementation
- Desktop: retain the native Windows packaging path already in the repository; improve responsive desktop UI and keyboard/mouse interactions.
- Android: retain the current Android build path; support share-intent/paste URL, storage permissions through supported Android APIs, notifications, and background-work constraints.
- Share the same design tokens, user-facing terminology, and API contracts across platforms.
- Do not remove or silently replace existing features until parity tests pass.

## 21st.dev MCP setup
The requested remote MCP endpoint is:
- URL: https://21st.dev/api/mcp
- Header: x-api-key: value from environment variable API_KEY_21ST

Never commit a real API key. Configure it in the developer's local MCP client as an environment variable/secret. Example configuration:

```json
{
  "mcpServers": {
    "21st": {
      "url": "https://21st.dev/api/mcp",
      "headers": {
        "x-api-key": "${API_KEY_21ST}"
      }
    }
  }
}
```

The MCP connection is not active until the developer supplies a valid key in their own environment and the MCP client supports remote HTTP MCP servers. Do not put the key in app source, Git history, Android assets, or public CI logs.

## Acceptance checks
- A URL that yt-dlp supports can be analyzed and formats are rendered from actual extractor metadata.
- Unavailable qualities are not shown as selectable native formats.
- Progress values update from actual yt-dlp hooks and final file stats.
- A download failure shows a useful site/extractor error and does not leave a false completed state.
- Windows and Android builds use the same naming, icons, terminology, and core interaction model.
- Layout works at 360px mobile width and 1280px desktop width.
- Motion respects reduced-motion preferences.
- Existing history, location, image/gallery, and audio features remain covered by regression tests.
