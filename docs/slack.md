# App de Slack

`src/prelo/slack.py` (Slack Bolt, Socket Mode).

## Configuración

1. Crear la app una vez en <https://api.slack.com/apps> con "From manifest" y pegar `slack-manifest.yml`.
2. Instalarla en el workspace e invitarla al canal de aprobación.
3. Variables de entorno: `SLACK_BOT_TOKEN` (`xoxb-`), `SLACK_APP_TOKEN` (`xapp-`, scope `connections:write`), `SLACK_CANAL`.

## Uso

- `/prelo <tema>`: inicia un post. Responde con el tema recibido o con el motivo del fallo.
- Cada pieza pendiente se publica en `SLACK_CANAL` con el texto, las fuentes, las violaciones y el costo (por agente y total).
- Botones: **Aprobar**, **Editar** (abre un modal con el campo `comentario`) y **Descartar**. Cada uno reanuda el flujo y actualiza el mensaje.
- Si la pieza tiene violaciones de marca, **Aprobar** no se muestra: hay que editar o descartar.
- Las piezas de Instagram (carrusel) muestran el texto de cada lámina. Llegan después de decidir la de LinkedIn del
  mismo post: Prelo pide una aprobación por vez y cada botón reanuda exactamente la pieza de su mensaje (`peca_id`).
