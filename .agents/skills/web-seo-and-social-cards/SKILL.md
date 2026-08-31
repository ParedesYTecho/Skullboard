---
name: web-seo-and-social-cards
description: >-
  Best practices for Web SEO, Dynamic OpenGraph social previews (Discord/Twitter/iMessage),
  structured schema markup (JSON-LD), PWA manifests, and sitemap synchronization.
  Use when optimizing landing pages for search engine ranking and rich link previews in Discord.
---

# Web SEO & Dynamic Social Cards Architecture

This skill guides the implementation of high-converting social preview cards, OpenGraph tags, and search engine optimization.

## 1. Discord & Twitter Social Preview Tags
- **OpenGraph Standards:**
  - `<meta property="og:title" content="SkullBoard — El Bot de Starboard Definitivo">`
  - `<meta property="og:description" content="...">`
  - `<meta property="og:image" content="https://skullboard.vercel.app/og-image.png">`
  - `<meta property="og:image:width" content="1200">`
  - `<meta property="og:image:height" content="630">`
  - `<meta name="theme-color" content="#d6d6de">` (Creates a custom colored embed sidebar in Discord chat!)
- **Twitter Card Specs:**
  - `<meta name="twitter:card" content="summary_large_image">`

## 2. PWA Manifest & App Icons
- Include `manifest.json` with `theme_color`, `background_color`, `display: standalone`, and high-res icon assets (`192x192`, `512x512`) for mobile home-screen installation.

## 3. Structured Data (JSON-LD)
- Add `<script type="application/ld+json">` describing the SoftwareApplication / WebApplication schema to appear with rich snippets in Google search results.
