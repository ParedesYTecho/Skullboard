# Caso técnico: SkullBoard

[Volver al README](../README.md) · [English](technical-case-study.md)

SkullBoard parece un bot pequeño: cuenta calaveras y copia mensajes. Pero además del bot hay una API, un dashboard con inicio de sesión de Discord y una base de datos con datos de terceros, y cada una de esas piezas plantea problemas propios. Este documento recoge las decisiones que más me enseñaron. El código es privado, así que describo el diseño sin enseñar listados.

## Piezas y responsabilidades

<img src="../assets/arquitectura.svg" alt="Arquitectura de SkullBoard" width="100%">

El bot y la API viven en un único proceso Python desplegado en Render. El bot usa `discord.py` con `AutoShardedBot` sobre el bucle de `asyncio`. La API es una aplicación Flask que corre en un hilo aparte y sirve el dashboard: OAuth, configuración por servidor, rankings y estado del sistema. La web es estática y la sirve Vercel, que reescribe `/api` hacia el backend, de modo que el navegador solo habla con un origen. Los datos están en PostgreSQL gestionado por Supabase.

Un solo proceso simplifica el despliegue y deja que bot y API compartan cachés: cuando se guarda un ajuste desde el dashboard, la API invalida la caché del bot. El precio es que ambos comparten recursos y un fallo grave del proceso afecta a los dos.

## 1. Veinte reacciones al mismo mensaje

<img src="../assets/flujo.svg" alt="Flujo de una reacción" width="100%">

El primer diseño ingenuo es obvio: en cada reacción, contar y actualizar. Con una ráfaga de reacciones eso significa decenas de peticiones a la API de Discord y a la base de datos para llegar al mismo número.

La solución tiene tres capas. Los eventos de reacción se escuchan en su forma *raw*, de modo que llegan aunque el mensaje no esté en la caché de `discord.py`. Un debouncer agrupa las reacciones de cada mensaje: espera dos segundos y reinicia la espera con cada reacción nueva. El temporizador guarda un número de generación para que un temporizador antiguo no dispare una comprobación que ya no corresponde. Después, un lock por mensaje garantiza que dos comprobaciones del mismo mensaje nunca se solapen.

El lock fue la parte delicada. Un lock por clave que no se limpia deja memoria ocupada para siempre, y uno que se limpia mal puede liberarse mientras otra tarea lo espera. La implementación cuenta las referencias y retira el lock al quedarse sin usuarios, incluso si la tarea que esperaba se cancela. Esa condición es fácil de pasar por alto.

La misma idea se aplica al borrado. Cuando se borran mensajes en bloque, el bot agrupa las consultas en lotes de hasta cien identificadores y limita a ocho las tareas de borrado simultáneas, para no saturar las conexiones con la base de datos.

La configuración de cada servidor, el prefijo, los canales ignorados y el récord se guardan en cachés con caducidad de entre dos y cinco minutos. Se invalidan de forma explícita al escribir, de modo que un cambio desde el dashboard se nota de inmediato.

## 2. Cuando el tablón y la realidad no coinciden

Un tablón que copia mensajes acumula inconsistencias: duplicados por reintentos, copias de mensajes que ya no existen y recuentos desfasados. Para repararlo, `/resync` recorre el canal de destacados y extrae de cada copia el enlace al mensaje original. Agrupa las copias por original, conserva la más reciente y borra el resto. Después consulta el mensaje original: si ya no existe, elimina sus copias y su registro, y si existe, corrige el recuento.

Esa operación hace muchas llamadas a Discord, y varios servidores pueden lanzarla a la vez. Por eso comparten un limitador global de 8 peticiones por segundo, bastante por debajo del límite global de la API. El lock por servidor evita además que dos reconciliaciones del mismo canal compitan entre sí.

Los fallos parciales se tratan por separado. Si la base no responde al preguntar si un mensaje ya está destacado, el bot no publica nada y lo reintenta, porque suponer que no existe habría creado un duplicado. Si Discord publica la copia y la base no guarda el registro, el bot retira la copia recién publicada en lugar de dejarla huérfana. Los reintentos son tres, a los 5, 20 y 60 segundos, y solo ante fallos pasajeros (base de datos o errores 5xx de Discord).

## 3. Un dashboard con inicio de sesión de Discord

El dashboard permite consultar rankings y, a los administradores, cambiar la configuración. Eso exige OAuth2, y la autenticación es donde más fácil resulta equivocarse. Estas son las decisiones principales.

### Los tokens de Discord no llegan al navegador

Tras el login, el cliente recibe una cookie opaca (`__Host-` en producción, con `HttpOnly`, `Secure` y `SameSite=Lax`). El servidor guarda los tokens cifrados con Fernet, indexados por un HMAC del identificador de sesión. La versión inicial guardaba las sesiones en memoria del proceso, lo que se perdía en cada reinicio y no escalaba a más de un worker. Pasarlas a la base de datos obligó a resolver la renovación de tokens: dos peticiones simultáneas podían renovar la misma sesión. Una reserva condicional en la propia fila actúa como lock distribuido y evita esa carrera. Un logout posterior nunca recrea la sesión.

### El `state` de OAuth es de un solo uso

Se genera aleatorio y se guarda como HMAC con caducidad de diez minutos. Al volver de Discord, el backend lo consume, y repetir la petición falla. Llegué a diseñar un segundo identificador ligado al navegador mediante una cookie propia del flujo. Lo descarté porque el requisito es que el navegador reciba una sola cookie, y el `state` persistente, aleatorio y de un solo uso ya cubría el caso. La decisión anterior quedó registrada como sustituida.

### Discord devuelve más permisos de los que pides

Si el usuario ya había autorizado la aplicación con otros permisos, la respuesta los incluye. La primera versión comparaba los permisos con una igualdad exacta y rechazaba a esos usuarios con un error confuso. Ahora se exige que estén los necesarios y se normalizan las mayúsculas.

### El backend no se fía del cliente al escribir

Los cambios de configuración exigen cabecera CSRF, origen permitido y permisos de administrador comprobados contra Discord. El canal elegido tiene que ser visible para el bot antes de guardarse, porque aceptar cualquier identificador numérico permitiría apuntar el tablón a un sitio donde no puede escribir.

## 4. Un error que las pruebas no veían

Un cambio que endurecía las cabeceras y la comprobación de orígenes eliminó la excepción de `GET /api/auth/start`, la única ruta que no exigía cabecera `Origin`. Todas las pruebas pasaban. Pero los navegadores no envían `Origin` en peticiones GET del mismo origen, y el dashboard llama a esa ruta precisamente así, a través del proxy de Vercel. En producción, el login habría devuelto 403 a todo el mundo.

Las pruebas no lo detectaban porque enviaban la cabecera a mano. Lo detectó una revisión antes de llegar a producción, y lo confirmé después construyendo un entorno que reproduce el recorrido completo: el backend real, Discord y la base de datos simulados en memoria, un proxy local que reenvía las cabeceras como lo hace Vercel y un navegador Chrome real. La corrección acepta un GET sin `Origin` solo en esa ruta y solo si `Sec-Fetch-Site` no indica una petición entre sitios. Las pruebas ahora comprueban los dos lados: que el login same-origin funciona y que las peticiones cross-site se rechazan.

Ese entorno se ha quedado como parte del conjunto de pruebas. Cubre el login, la persistencia de la sesión, la reutilización de un `state`, el cierre de sesión y el guardado de ajustes.

## Datos, seguridad y honestidad del estado

Las tablas tienen seguridad a nivel de fila activada sin políticas para clientes públicos. Solo el rol de servicio del backend accede. No añadí políticas para el cliente mientras no existiera una correspondencia fiable entre usuarios de Supabase y propietarios de servidores de Discord, y una política supuesta es peor que ninguna. La base guarda identificadores, contadores y configuración, no el texto de los mensajes.

La página de estado no muestra cifras que no pueda respaldar. Cuando el proveedor del bot no está registrado, responde `unknown`, y se retiraron un uptime y un SLA que se mostraban sin que nada los midiera.

## Pruebas y despliegue

Las pruebas son de tres tipos: comprobaciones estáticas de invariantes del proyecto, pruebas de la autenticación y las rutas con el cliente de pruebas de Flask, y el recorrido de extremo a extremo en un navegador real. Los despliegues salen de la rama principal, protegida, a través de pull requests. Render redespliega el backend y Vercel la web, y cada despliegue previo queda disponible para volver atrás.

## Estado actual

La web rediseñada está publicada en las rutas principales desde octubre de 2026. La API se sirve con Waitress y las dependencias del backend están fijadas. Los rankings resuelven los perfiles de Discord en paralelo cuando la caché está fría. El destacado al azar puede recuperar el texto desde la copia publicada en el canal de destacados si no puede leer el original.

El panel distingue los fallos de consulta de la ausencia real de mensajes. Cada ranking muestra 25 resultados y «Cargar más» añade otros 25, hasta 100. La base devuelve siempre un prefijo ordenado con desempate estable, de modo que ampliar la lista no repite ni se salta filas.
