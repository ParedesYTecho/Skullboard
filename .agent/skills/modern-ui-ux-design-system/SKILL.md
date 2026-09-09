---
name: modern-ui-ux-design-system
description: >-
  Design tokens, modern luxury dark/light styling, fluid animations, micro-interactions,
  and UX patterns inspired by Magic UI, Aceternity UI, and Shadcn.
  Use when designing or enhancing landing pages, dashboards, interactive Discord
  embed simulators, command search palettes (Cmd+K), and toast notification systems.
---

# Modern UI/UX Design System & Luxury Aesthetics

This skill provides guidelines and patterns for engineering top-tier Web UI/UX for SaaS and Discord bot platforms.

## 1. Aesthetic Foundations (Dark Platinum Luxury)

- **Surface Layering:**
  - Base: `#0a0a0c` (Obsidian Charcoal).
  - Elevated Cards: `rgba(255, 255, 255, 0.04)` with `border: 1px solid rgba(255, 255, 255, 0.09)`.
  - Hover States: `rgba(255, 255, 255, 0.07)` with `border-color: rgba(255, 255, 255, 0.35)` and `box-shadow: 0 12px 32px rgba(0, 0, 0, 0.3)`.
- **Light Theme Harmony (Ceramic Slate):**
  - Base: `#dce1e8`. Card: `#edf1f6`. Text: `#0b111e`. Zero flashbang / muted comfortable contrast.
- **Glassmorphism:**
  - `backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);`.

## 2. Micro-Interactions & Animation Curves

- **Spring Curves:** Use `cubic-bezier(0.34, 1.56, 0.64, 1)` for bouncy, physical button and icon scaling.
- **Shimmer Light Sweep:** Use angled pseudo-elements (`linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent)`) on primary CTAs.
- **Number Tickers:** Smooth numerical count-up on stats using `requestAnimationFrame` with cubic ease-out.

## 3. UX Patterns for High Conversion

1. **Interactive Sandbox / Live Simulator:** Show users the product in action before inviting (e.g. interactive Starboard preview).
2. **Command Palette (`Ctrl+K` / `Cmd+K`):** Fast modal search with keyboard navigation.
3. **Toast Notifications:** Stackable feedback notifications (like Sonner) for copy and submit actions.
4. **Touch-First Ergonomics:** 44px minimum tap targets, sliding horizontal category chips with momentum scrolling, and 16px input font size to prevent iOS auto-zoom.
