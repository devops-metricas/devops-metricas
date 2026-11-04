# Qué necesitamos para el proyecto (Escenario 1: Notificaciones multicanal)

## La idea

Construimos una plataforma compartida de notificaciones.
Varias aplicaciones le piden enviar mensajes a sus usuarios.
Ella los envía por correo de prueba o como notificación interna.
Reintenta si algo falla, evita enviar duplicados y permite consultar qué pasó con cada envío.
Además de programarlo, hay que montarlo en la nube, desplegarlo de forma automática y demostrar con datos que funciona. Esa parte pesa tanto como el programa.

## Las piezas

- **Aplicaciones cliente:** los sistemas que piden enviar mensajes. Cada una se registra y se identifica, como clientes de una oficina de correos con su propio carnet.
- **API:** recibe solicitudes, verifica quién las envía y responde con un número de seguimiento. Es el mostrador.
- **Worker:** hace los envíos y reintenta si fallan. Es el cartero.
- **Cola de trabajos:** la lista de envíos pendientes, como una bandeja de salida.
- **Base de datos:** guarda cada notificación, su estado y el historial de intentos. Es el libro de registro.
- **Canales:** correo de prueba y notificaciones internas que el destinatario puede consultar.
- **Estados:** aceptada, pendiente, en proceso, entregada, fallida.
- **Clave de idempotencia:** etiqueta única que evita que una solicitud repetida cree dos envíos. Es como el número de pedido que impide cobrar dos veces.

**Regla clave:** que la API responda con éxito solo significa "recibido", no "entregado". Si el worker se reinicia a medias, los estados no se pierden y el trabajo continúa.

## Qué hay que programar

- **Aplicaciones cliente:** registrar al menos dos y saber cuál origina cada solicitud. Rechazar a los clientes no autorizados.
- **Recibir solicitudes:** destinatario, canal, contenido y una clave de idempotencia opcional.
- **Dos canales:** correo de prueba y notificaciones internas que el destinatario puede consultar.
- **Estados:** guardar cada transición.
- **Reintentos:** las fallas pasajeras (un error 503 o un timeout) se reintentan, hasta 3 intentos en total y con espera entre intentos. Los errores permanentes (destinatario inválido) terminan como fallidos sin reintentar.
- **Idempotencia:**
  - Repetir la misma solicitud (misma aplicación, canal y clave durante 24 horas) no crea otro envío y devuelve la referencia original.
  - Si la clave se repite con contenido distinto, se rechaza.
- **Consultas:**
  - Estado e historial de intentos de cada notificación.
  - Reproceso de una fallida por una persona autorizada.
  - Recuentos y tasas por canal y estado.

## Qué hay que montar en Azure

- **Una máquina virtual (VM):** la computadora en la nube donde corre todo.
- **K3s:** una versión liviana de Kubernetes, el programa que arranca, vigila y reinicia nuestras aplicaciones.
- **Dos ambientes:** dev para probar y prod como el oficial, separados con namespaces dentro del mismo K3s.
- **Base de datos PostgreSQL** y un correo de prueba (simulador o servidor SMTP de pruebas) para el canal de correo.
- **Terraform:** crea la infraestructura con código en vez de clics, y se puede borrar y recrear igual.
- **State remoto:** el archivo donde Terraform recuerda lo que creó. Va en Azure, no en una laptop.
- **Costos:** hay US$100 en total. Se apaga la VM al terminar cada sesión y se ponen alertas de gasto.

## Cómo llega el código a producción

1. Se trabaja en una rama y se abre un pull request, que es un pedido de revisión.
2. GitHub Actions corre solo el lint y las pruebas. Si fallan, no se puede unir a main.
3. Otra persona revisa y aprueba.
4. Actions construye la imagen de contenedor, que es la aplicación empaquetada, y la etiqueta con el identificador del commit.
5. Se despliega a dev. Si todo va bien, se promueve la misma imagen a prod, sin reconstruirla.
6. Si algo sale mal, se hace rollback a la versión anterior. Ojo: el rollback no devuelve datos borrados.

## Reglas de oro

- Nunca subir contraseñas ni claves al repo.
- `terraform apply` lo ejecuta solo el pipeline, no una persona desde su computadora.
- GitHub entra a Azure con OIDC, que son permisos temporales sin contraseñas guardadas. Esa es la idea central del Lab 4 de DevOps.

## Cómo sabemos que funciona

El objetivo es responder con datos, no con opiniones: cuántas solicitudes aceptadas se entregan a tiempo y qué canal causa los reintentos.

- **Logs:** una línea por evento, con identificadores para seguir una notificación de punta a punta.
- **Métricas (Prometheus):** solicitudes, errores, intentos por canal, tiempo de entrega y tamaño de la fila de pendientes.
- **Trazas (OpenTelemetry):** el recorrido de una notificación por API, cola y worker, con el tiempo de cada tramo.
- **Dashboard (Grafana):** 6 o más paneles, cada uno responde una pregunta.
- **Alertas:** 2 avisos. Hay que mostrar una disparando y luego recuperándose.
- **SLI y SLO:** el SLI es lo que medimos (por ejemplo, % de notificaciones entregadas en menos de X segundos) y el SLO es la meta (por ejemplo, 99%). El presupuesto de error es el margen para fallar sin incumplir la meta.
- **Incidente controlado:** rompemos algo a propósito (por ejemplo, que el proveedor de correo responda con errores), lo detectamos con datos y lo arreglamos.

## Qué hay que demostrar y entregar

### Pruebas del escenario

1. Enviar un lote de 100 solicitudes válidas entre ambos canales y verificar que todas tienen identificador y estado.
2. Simular fallas del proveedor de correo: se reintenta, las solicitudes siguen registradas y el canal interno sigue funcionando.
3. Repetir 5 veces la misma solicitud con la misma clave, en secuencia y a la vez: debe existir un solo envío.
4. Reiniciar el worker con trabajos pendientes y comprobar que los estados no desaparecen.
5. Seguir una solicitud de extremo a extremo con logs, métricas y trazas, y justificar una alerta por más fallas o retraso.

### Documentos en el repo

- `docs/EVIDENCIAS.md`: por cada requisito, un enlace que lo pruebe.
- `docs/COM/COM-06-decisiones.md`: qué elegimos y por qué.
- `docs/COM/COM-02-arquitectura.md`, `docs/MET/MET-01-catalogo-de-indicadores.md`, `docs/DEV/DEV-13-reconstruccion.md` y `docs/DEV/DEV-14-costos.md`.

### Defensa individual

Cada integrante debe poder explicar cualquier parte del sistema sin ayuda. Nadie debe ser "el único que sabe" algo.

## Glosario

- **Contenedor / imagen:** la aplicación empaquetada con todo lo que necesita para correr igual en cualquier lado.
- **Kubernetes / K3s:** el programa que arranca, vigila y reinicia contenedores. K3s es su versión liviana.
- **Terraform:** crea infraestructura escribiendo código.
- **CI/CD:** pruebas y despliegue automáticos.
- **OIDC:** permisos temporales para que GitHub entre a Azure sin contraseñas.
- **Rollback:** volver a la versión anterior que funcionaba.
- **Namespace:** una "carpeta" dentro de K3s para separar ambientes.
- **Probe:** chequeo que K3s hace para saber si la aplicación está viva y lista.
- **Prometheus / Grafana:** una guarda los números y la otra los dibuja en paneles.
- **OpenTelemetry:** estándar para registrar el recorrido de una solicitud (trazas).
- **SLI / SLO:** lo que medimos y la meta que nos ponemos.
- **Idempotencia:** repetir la misma solicitud no produce un segundo efecto.
