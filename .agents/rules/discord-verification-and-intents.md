---
description: Reglas y directrices para la gestion de Privileged Intents y procesos de verificacion en Discord Developer Portal.
globs: ["main.py", "docs/**", "legal/**"]
---

# Discord Bot Verification & Privileged Intents Protocol

1. **Message Content Intent Justification:**
   - La justificacion SIEMPRE debe enfocarse en la naturaleza del Starboard: la API de Discord devuelve `message.content = ""` al recibir reacciones (`on_raw_reaction_add`) si no se cuenta con el intent.
   - Demostrar que el 100% de los comandos de usuario son Slash Commands nativos.
   - Aclarar el procesamiento transitorio en memoria RAM y que NUNCA se almacena texto de mensajes en bases de datos.

2. **Aislamiento Estricto de Pruebas Multimedia:**
   - NUNCA incluir capturas o videos que contengan comandos de prefijo (ej. `sk!`, `ww!`) o elementos de otros bots/proyectos (ej. Werewolf).
   - Todo video de verificacion debe mostrar la ejecucion de un Slash Command con autocompletado y el renderizado del Starboard en vivo.

3. **Minimizacion de Intents:**
   - No solicitar `Server Members` o `Presences` a menos que sea estrictamente indispensable y justificado para evitar la regla de "rechazo global" de Discord.
