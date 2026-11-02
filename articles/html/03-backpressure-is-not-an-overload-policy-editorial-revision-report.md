# Blog 3 — final editorial revision and HTML parity report

## Deliverables
- `articles/03-backpressure-is-not-an-overload-policy.md` — revised seven-section article and evidence appendix.
- `articles/html/03-backpressure-is-not-an-overload-policy-wordpress.html` — regenerated scoped WordPress Custom HTML fragment.
- `articles/html/03-backpressure-is-not-an-overload-policy-preview.html` — regenerated standalone preview.
- This report. Frozen experiment files, Stage 5/6/7 reports, claims, and raw results were not edited.

## Structural change
**Before:** (1) decision; (2) model; (3) four-policy outcomes; (4) RETRY; (5) deadline; (6) jitter; (7) choose policy, followed by a methods appendix.

**After:** (1) full-queue dilemma; (2) four policies and cost transfer; (3) compact experiment; (4) RETRY gain and bill; (5) deadlines; (6) production decision framework; (7) promise-centered conclusion. Detailed outcomes, original measured charts, full retry accounting, full deadline/anomaly study, jitter/collision study and methods are retained in appendix A–E.

## Narrative and content decisions
- Opening uses the 32-occupied-slot boundary and the question **where did the cost go?**, before introducing experimental outcomes.
- Added a semantic policy-decision table: what happens at full admission, where waiting/refusal/retry/loss is paid. RETRY remains client behavior following server refusal.
- Primary RETRY section leads with **+40.6 useful originals/run** and **+91.2 total initiated attempts/run**, and labels **+1.410 pp** plus the worse **completed-recovery-cohort p95** with unequal cohorts. These are separate measurements, not a causal efficiency ratio.
- Moved full `F/A/S/R` arithmetic, block counts and bootstrap explanation into appendix B.
- Kept deadline implications in the narrative while moving the valid, unexplained 500 ms WAIT outlier breakdown to appendix C.
- Moved full eight-client jitter experiment and Figure 4 to appendix D. Preserved **−15.873%**, staggered original arrivals, no injected herd, different expected backoff durations, bin checks and pre-traffic B2 seed correction.
- Added an eight-step production framework emphasizing original identity, immutable deadline, explicit terminal outcomes, client/server bounds and offered-demand denominators.
- Kept the final sentence distinguishing backpressure from overload policy. Removed internal manuscript-status prose from publishable body.

## Evidence and claim gate
- All four approved measured figures remain present: main tradeoff Figure 1, appendix primary outcomes Figure 2, deadline Figure 3, collision Figure 4.
- Main article retains five matched blocks, 2,880 original denominator, primary/secondary separation, recovery completed-cohort limits and explicit lack of a universal winner.
- The primary Stage 7-reviewed Figure 1 image is pinned to the reviewed manuscript commit `62647db51e48b81f07128456b9b60d660715b904`; the other three remain pinned to `25771cda76abfbcee32f994841a67e900efe5833`.
- The figures were fetched as source PNGs and visually inspected in the review environment. The eight-client Figure 4 still has a zoomed right goodput panel: it remains **in the appendix** with explicit caption warning. No unverified crop or redraw was made.
- Stage 7 SUPPORTED findings preserved; QUALIFIED comparisons retain denominators/cohorts; INCONCLUSIVE rankings remain unresolved; UNSUPPORTED causal/general claims are not asserted.

## HTML conversion QA
- Generated from the revised Markdown, not independently rewritten.
- Structural checks at generation: **7 numbered sections**, **4 figures with figcaptions**, **3 semantic tables**, no Markdown image tokens.
- WordPress export has one scoped `.gup3-article` root and scoped style rules, no `html/head/body` wrapper, no JavaScript.
- Standalone preview includes a document wrapper, viewport and title.
- Semantic table overflow containers, responsive images, keyboard focus rules, `prefers-color-scheme` dark styling, and fluid type remain in the established export.
- Figure PNG content was inspected at native resolution; **700–800 CSS px browser render and phone-size screenshots were not independently tested**. Figure 2/3/4 axes and legends may need full-resolution click access on mobile.
- No WordPress editor preview was available; confirm the theme preserves `style`, `article`, `figure`, `figcaption`, and focus/overflow CSS. If WordPress strips the style block, enqueue the same scoped CSS in theme Custom CSS.

## Review gates and outstanding work
- **Principal engineer:** production guidance is actionable; no capacity creation or universal winner asserted.
- **Senior editor:** research mechanics moved behind the practical question, with RETRY as centerpiece.
- **Senior backend reader:** four cost locations, original-demand denominator, and deadline implications appear before appendix.
- **Engineering-blog coach:** three memories are bound ownership, follow transferred cost, and optimize useful originals under deadlines.
- **Outstanding:** real browser rendering at desktop/mobile and WordPress theme light/dark visual QA; verify 700–800 CSS px chart labels and scrollable tables. This is not a claim that WordPress visual QA passed.

**Editorial verdict: READY FOR FINAL EDITORIAL REVIEW**, with visual QA remaining an explicit prepublication gate. No live WordPress publication.
