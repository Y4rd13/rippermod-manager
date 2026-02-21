const SAFE_URL_RE = /^https?:\/\//i;

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function sanitizeUrl(url: string): string {
  const trimmed = url.trim();
  return SAFE_URL_RE.test(trimmed) ? trimmed : "#";
}

/**
 * Convert Nexus Mods BBCode to safe HTML.
 *
 * Nexus descriptions are a mix of BBCode and HTML — HTML `<br />` tags
 * are normalised to newlines before escaping so they survive the pipeline.
 *
 * Handles the BBCode subset used by Nexus:
 * [b], [i], [u], [s], [url], [img], [quote], [code],
 * [list]+[*], [size], [color], [center], [line]/[hr], [heading]
 */
export function bbcodeToHtml(bbcode: string): string {
  // Nexus mixes HTML <br> / <br /> with BBCode — normalise to newlines first
  let s = bbcode.replace(/<br\s*\/?>/gi, "\n");

  s = escapeHtml(s);

  // Simple inline tags
  s = s.replace(/\[b\]([\s\S]*?)\[\/b\]/gi, "<strong>$1</strong>");
  s = s.replace(/\[i\]([\s\S]*?)\[\/i\]/gi, "<em>$1</em>");
  s = s.replace(/\[u\]([\s\S]*?)\[\/u\]/gi, "<u>$1</u>");
  s = s.replace(/\[s\]([\s\S]*?)\[\/s\]/gi, "<del>$1</del>");

  // [url=...]...[/url]
  s = s.replace(
    /\[url=(&quot;|")?(.+?)\1?\]([\s\S]*?)\[\/url\]/gi,
    (_, _q, href, text) =>
      `<a href="${sanitizeUrl(href)}" target="_blank" rel="noopener noreferrer">${text}</a>`,
  );
  // [url]...[/url]
  s = s.replace(
    /\[url\]([\s\S]*?)\[\/url\]/gi,
    (_, href) =>
      `<a href="${sanitizeUrl(href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(href)}</a>`,
  );

  // [img]...[/img]
  s = s.replace(
    /\[img\]([\s\S]*?)\[\/img\]/gi,
    (_, src) => `<img src="${sanitizeUrl(src)}" alt="" loading="lazy" />`,
  );

  // [quote]...[/quote]  (may include author attribute)
  s = s.replace(
    /\[quote(?:=[^\]]+)?\]([\s\S]*?)\[\/quote\]/gi,
    "<blockquote>$1</blockquote>",
  );

  // [code]...[/code]
  s = s.replace(/\[code\]([\s\S]*?)\[\/code\]/gi, "<pre><code>$1</code></pre>");

  // [heading]...[/heading]
  s = s.replace(/\[heading\]([\s\S]*?)\[\/heading\]/gi, "<h3>$1</h3>");

  // [size=N]...[/size]  — clamp to 8-36px
  s = s.replace(/\[size=(\d+)\]([\s\S]*?)\[\/size\]/gi, (_, n, text) => {
    const px = Math.min(36, Math.max(8, Number(n)));
    return `<span style="font-size:${px}px">${text}</span>`;
  });

  // [color=X]...[/color]  — only allow hex/named colours
  s = s.replace(/\[color=([#\w]+)\]([\s\S]*?)\[\/color\]/gi, (_, color, text) => {
    const safe = /^#?[\w]+$/.test(color) ? color : "inherit";
    return `<span style="color:${safe}">${text}</span>`;
  });

  // [center]...[/center]
  s = s.replace(
    /\[center\]([\s\S]*?)\[\/center\]/gi,
    '<div style="text-align:center">$1</div>',
  );

  // [list] + [*] items
  s = s.replace(/\[list\]([\s\S]*?)\[\/list\]/gi, (_, inner: string) => {
    const items = inner
      .split(/\[\*\]/)
      .map((t) => t.trim())
      .filter(Boolean);
    if (items.length === 0) return "";
    return "<ul>" + items.map((item) => `<li>${item}</li>`).join("") + "</ul>";
  });

  // Standalone [*] not inside [list] — treat as bullet
  s = s.replace(/\[\*\]\s*/g, "&bull; ");

  // [line] / [hr]
  s = s.replace(/\[(?:line|hr)\]/gi, "<hr>");

  // Strip any remaining unknown BBCode tags
  s = s.replace(/\[\/?\w+(?:=[^\]]+)?\]/g, "");

  // Newlines → <br> (skip inside <pre> blocks)
  s = s
    .split(/(<pre[\s\S]*?<\/pre>)/i)
    .map((chunk, i) => (i % 2 === 0 ? chunk.replace(/\n/g, "<br>") : chunk))
    .join("");

  return s;
}
