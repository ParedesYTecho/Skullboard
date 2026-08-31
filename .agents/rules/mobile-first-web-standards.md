---
description: Estandares de diseno web Mobile-First, accesibilidad tactil y prevencion de bugs en iOS Safari.
globs: ["legal/**", "*.html", "*.css"]
---

# Mobile-First Web Standards

1. **Prevencion de Auto-Zoom en iOS Safari:**
   - Todos los inputs, selectores y textareas deben tener `font-size: 16px` como minimo en resoluciones moviles (`<= 680px`).

2. **Ergonomia Tactil:**
   - Botones y enlaces interactivos deben tener un area de pulsacion minima de `36x36px` o `padding: 8px 14px`.
   - Filtros de categorias deben usar desplazamiento horizontal tactil (`overflow-x: auto; -webkit-overflow-scrolling: touch; scrollbar-width: none;`).

3. **Anti-Overflow:**
   - Las tablas deben tener `display: block; width: 100%; overflow-x: auto;` para evitar romper el layout en pantallas estrechas.
   - La tipografia de titulos debe usar `clamp()` fluido.
