# Blog 3 HTML conversion report

## Files
- `articles/html/03-backpressure-is-not-an-overload-policy-preview.html`: complete standalone document with title and viewport.
- `articles/html/03-backpressure-is-not-an-overload-policy-wordpress.html`: scoped HTML fragment with a local `<style>` block and semantic `<article>`; WordPress supplies the post title.

## Publishing conventions
Local Blog 1 and Blog 2 exports were inspected. Blog 1 uses semantic HTML and native figure/caption elements without CSS. Blog 2 uses semantic sections and tables with extensive inline styles, including a fixed light-background executive summary that is potentially low-contrast in dark themes. The new export retains the semantic approach but uses a **single scoped root class** `.gup3-article`, accessible overflow containers and light/dark-aware CSS. It introduces no external framework or JavaScript. No Blog 1/2 HTML exports were located in the GitHub repository search; the local exports were available as publishing references.

## Source and content parity
- Approved source: `articles/03-backpressure-is-not-an-overload-policy.md` at commit `62647db51e48b81f07128456b9b60d660715b904`.
- Markdown section headings: **7**. Generated section headings: **7**.
- Approved main figures: **4**. Generated figures: **4** with image, alt text and associated `figcaption`.
- Tables generated: **2**.
- Conversion is structural: no research claims, numbers, source text, conclusions or appendix entries were intentionally changed. Inline formatting and Markdown table syntax were translated to HTML.
- Figure 2 was unavailable at the older figure URL commit `25771cda...`; its exact approved file exists at reviewed manuscript commit `62647db51e48b81f07128456b9b60d660715b904`. Its image source was repinned to that commit without changing the image or caption.
- Other three images remain pinned to `25771cda...`, where GitHub file fetch confirmed their existence.

## Figure and rendering QA
- GitHub connector confirmed that all four PNGs exist at their final pinned paths. **HTTP image delivery to the WordPress frontend and actual pixel-level chart readability were not tested.**
- Figure 4 retains the **full approved figure**, not a speculative crop, because faithful visual cropping and inspection were unavailable. Its original caption explicitly warns that the zoomed right goodput axis may exaggerate the approximately 0.208 pp difference; the left collision panel supports the claim.
- Images use intrinsic aspect ratio (`width:100%;height:auto;object-fit:contain`), link to full-resolution source and retain informative manuscript alt text.
- No browser-based desktop/mobile screenshots were inspected; therefore **visual QA is incomplete**. Check charts at 700–800 CSS px and narrow phones, especially Figure 4's axes and labels.

## Responsive and theme QA
- Scoped CSS includes 800 px maximum article width, fluid heading sizes, mobile type adjustments, horizontal overflow for tables and code, keyboard focus outlines, and prefers-color-scheme dark palette.
- These are **implementation checks**, not verified browser render results. The WordPress theme may impose its own text colors or editor filtering. The article supports explicit `data-gup3-theme="light"` or `"dark"` overrides on the root if necessary.
- **Outstanding WordPress checks:** confirm the Custom HTML block retains `<style>`, `<article>`, `<figure>`, `<figcaption>`, `role` and `tabindex`; inspect actual light/dark theme contrast, figure aspect ratios, table scroll behavior, links and keyboard focus; verify lazy-loaded PNGs resolve in the published preview. If the editor strips styles, enqueue the same scoped CSS via theme Custom CSS rather than inlining unscoped rules.

## Gate
**BLOCKED — VISUAL QA INCOMPLETE.** The artifacts are ready for a rendering pass, not for a final ready-to-publish claim.
