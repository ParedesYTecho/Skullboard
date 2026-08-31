---
name: playwright-visual-testing
description: >-
  Visual regression, responsiveness auditing, and end-to-end frontend testing
  using browser automation tools (Playwright / Chrome DevTools / Puppeteer).
  Use when validating HTML/CSS changes across mobile (360px, 390px, 414px),
  tablet (768px), and desktop (1280px+) viewports, checking contrast in Dark/Light themes,
  and testing interactive frontend components.
---

# Playwright & Responsive UI Visual Testing

This skill provides step-by-step procedures for auditing web pages for responsive layout integrity, theme contrast compliance, and interaction robustness.

## Viewport Matrix to Test

| Viewport Category | Resolution | Key Areas to Verify |
| :--- | :--- | :--- |
| **Small Mobile** | 360x640 / 375x667 | Touch targets >= 44px, zero horizontal overflow, nav collapsed cleanly |
| **Standard Mobile (iPhone/Android)** | 390x844 / 414x896 | Input font-size >= 16px (no iOS auto-zoom), sliding filter chips |
| **Tablet** | 768x1024 | 6-column bento re-stacking, 3-column stats band |
| **Desktop** | 1280x800 / 1440x900 | 12-column grid layout, hover microinteractions, max-width constraints |

## Testing Checklist

1. **Horizontal Overflow Bug:**
   - Execute `document.documentElement.scrollWidth > window.innerWidth`. Must always evaluate to `false`.
2. **Theme Toggle Verification:**
   - Switch `data-theme="light"` and `data-theme="dark"`. Verify WCAG AA contrast (>4.5:1 for body text, >7:1 for headers).
3. **Interactive Components:**
   - Test command search filter and clear button.
   - Test accordion toggle on `.cmd.has-params` with both mouse click and keyboard (`Enter` / `Space`).
   - Test clipboard copy button feedback (`✓ Copiado!`).
   - Test contact form validation and honeypot field.
