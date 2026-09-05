# Visual Regression

> Purpose: keep intentional UI appearance changes reviewable and regressions detectable.
> Status: select a screenshot harness after the application stack is chosen.
> Update when pages, baseline policy, viewport matrix, or screenshot commands change.
> Owner persona: UX/accessibility reviewer.
> Related: testing, test catalog, agent review.
> Search terms: visual, screenshot, baseline, viewport, diff, accessibility.
> UI changes require both interactive app exercise and visual evidence for affected states.

## Policy

Use deterministic data, fonts, viewport, color scheme, and animation settings. Capture important empty/loading/error/success states, compare diffs mechanically, and have an agent review meaningful diffs visually. Store baselines in the repository or attach them to the review artifact; use Git LFS when image history becomes large.
