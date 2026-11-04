# Decisiones técnicas

Cada decisión indica qué se eligió, por qué y qué se acepta a cambio.

## 1. La cola vive en PostgreSQL

- **Elegido:** la tabla `notifications` es también la cola; el worker reclama con
  `FOR UPDATE SKIP LOCKED`.
- **Por qué:** una pieza menos que operar (sin Redis ni RabbitMQ) en una VM de 8 GB con US$100 de
  presupuesto. El cambio de estado y el trabajo son una sola transacción, así que no hay mensajes
  perdidos ni duplicados entre la cola y la base.
- **Se acepta:** el rendimiento está limitado por PostgreSQL y el worker consulta por intervalo
  (1 s). Es suficiente para el volumen del proyecto.

## 2. Recuperación por plazo de bloqueo (`locked_until`)

- **Elegido:** un trabajo `processing` cuyo plazo venció se vuelve a tomar.
- **Por qué:** si el worker muere a medias, los estados no se pierden y el trabajo continúa sin
  intervención.
- **Se acepta:** semántica "al menos una vez". Un envío de correo que se completó justo antes de la
  caída podría repetirse. El plazo (`lock_seconds`, 60 s) debe ser mayor que un intento normal.

## 3. Idempotencia sin ventana de expiración

- **Elegido:** índice único parcial por (cliente, canal, clave), sin caducidad.
- **Por qué:** la garantía dura mientras exista el registro, que cumple de sobra el mínimo de 24 horas
  y se resuelve en la base, sin tareas de limpieza.
- **Se acepta:** una clave no se puede reutilizar nunca para el mismo cliente y canal.

## 4. Claves de API con hash

- **Elegido:** se guarda `SHA-256` de la clave; la clave se muestra una sola vez al crear el cliente.
- **Por qué:** las claves son aleatorias de 256 bits, así que un hash rápido es suficiente y permite
  buscar por hash en cada solicitud. Una fuga de la base no revela credenciales utilizables.

## 5. Una sola imagen para API, worker y migraciones

- **Elegido:** el comando cambia (`uvicorn`, `notifier.worker.main`, `notifier.migrate`).
- **Por qué:** una imagen que se construye una vez y se promueve de dev a prod sin reconstruirla.
- **Migraciones:** corren en un `initContainer` de la API con bloqueo consultivo, seguras con varias
  réplicas.

## 6. K3s en una sola VM

- **Elegido:** un nodo con K3s, dev y prod separados por namespaces.
- **Por qué:** lo pide el enunciado y es lo que cabe en el presupuesto. K3s consume mucho menos que
  un Kubernetes completo.
- **Se acepta:** sin alta disponibilidad; si la VM cae, caen ambos ambientes. Dev y prod comparten
  CPU y memoria, por eso los Pods declaran requests y límites.

## 7. Tamaño y región de la VM

- **Elegido:** `Standard_B2as_v2` (2 vCPU, 8 GB) en `northcentralus`.
- **Por qué:** la suscripción solo permite cinco regiones y el tamaño disponible sin restricciones
  allí es este. 8 GB alcanzan para dos ambientes y el stack de métricas.
- **Se confirma con:** los requests reales medidos ([DEV-14-costos.md](../DEV/DEV-14-costos.md)).

## 8. Sin llaves ni contraseñas: OIDC y mínimo privilegio

- **Elegido:** GitHub se autentica en Azure por OIDC con tres identidades separadas (`infra`, `plan`,
  `deploy`); el estado remoto usa Entra ID, sin llaves de la cuenta de almacenamiento.
- **Por qué:** no hay secreto que se pueda filtrar o rotar. `plan` es solo lectura porque un pull
  request puede modificar el workflow que corre con su identidad.
- **Detalle:** GitHub emite el subject con IDs inmutables de repo y propietario. El bootstrap lo lee del
  repositorio real; si se escribe a mano, el inicio de sesión falla.
- **Datos personales:** la IP autorizada y los correos de alerta son *secrets*, no variables, porque los
  logs de Actions son públicos.

## 9. Superficie de red mínima

- **Elegido:** solo 80/443 abiertos a Internet y SSH desde una IP; la API de Kubernetes (6443) cerrada.
- **Por qué:** lo exige el enunciado (5.3). Se administra por SSH o `az vm run-command`.
- **Se acepta:** si cambia la IP de quien administra, hay que actualizar `TF_ADMIN_CIDR` y aplicar. La
  variable rechaza `0.0.0.0/0`.

## 10. Costos: apagado manual y automático, alertas solo informativas

- **Elegido:** apagar la VM al terminar cada sesión (workflow `Infra ops`), apagado automático a las
  23:00 y alertas de presupuesto al 50, 80 y 100 %.
- **Por qué:** las alertas de Azure solo envían correo y no detienen recursos. El apagado automático
  es una red de seguridad, no sustituye al manual.
- **Se acepta:** desasignada, la VM no cobra cómputo, pero el disco y la IP pública siguen cobrando.

## 11. Intervenciones manuales mínimas y declaradas

- **Elegido:** solo el bootstrap (una vez) y la configuración de GitHub. Todo lo demás es código y
  pipeline, incluida la destrucción y la reconstrucción.
- **Por qué:** el bootstrap crea las identidades y el almacenamiento que el pipeline necesita para
  existir; no puede crearlos él mismo. Es idempotente y está en [DEV-13-reconstruccion.md](../DEV/DEV-13-reconstruccion.md).

## 12. Cifrado de Secrets en K3s

- **Elegido:** `--secrets-encryption` al instalar K3s.
- **Por qué:** los Secrets de Kubernetes son base64, no cifrado; así quedan cifrados en el almacén.
- **Se acepta:** protege el almacén en disco, no a quien tenga acceso de administrador al clúster.

## 13. HTTPS con Let's Encrypt y rutas por ambiente

- **Elegido:** certificado de Let's Encrypt (HTTP-01) emitido por el Traefik de K3s, con el nombre DNS
  de Azure de la IP pública y rutas `/dev` y `/prod`.
- **Por qué:** es gratis, se renueva solo y el nombre no cambia al reconstruir la VM. Cumple el
  transporte cifrado que pide el enunciado (5.3) sin comprar un dominio.
- **Se acepta:** un solo nombre para los dos ambientes (se separan por ruta) y que Traefik guarde el
  certificado en un volumen del nodo; si se pierde, se vuelve a emitir.

## Alternativas descartadas

| Tema | Alternativa | Por qué no |
|---|---|---|
| Cola | Redis, RabbitMQ o Azure Service Bus | Otra pieza que operar, vigilar y pagar; la cola en PostgreSQL ya da transaccionalidad con el estado y basta para el volumen del proyecto. Cambiarla queda aislado en `repository.py` y el worker |
| Base de datos | Azure Database for PostgreSQL | Costo fijo mensual que consume una parte relevante de los US$100. Se despliega PostgreSQL en el clúster con un volumen persistente |
| Orquestación | AKS (Kubernetes administrado) | El enunciado exige K3s en VM de Azure; AKS además cobra los nodos y el plano de control |
| Orquestación | Dos nodos o dos VM (una por ambiente) | Duplica el costo de cómputo; el enunciado admite namespaces y no exige alta disponibilidad |
| Reintentos | Reintento inmediato, sin espera | Aumenta la carga sobre un proveedor que ya falla. Se usa espera exponencial (5 s, 10 s) |
| Idempotencia | Caché o ventana de 24 h con limpieza | Más piezas y un caso límite al expirar. El índice único es atómico y también cubre la repetición concurrente |
| Autenticación | JWT o OAuth2 | El enunciado solo pide identificar a la aplicación y rechazar a las no autorizadas; una clave por cliente lo resuelve con menos superficie |
| Autenticación de Azure | Service principal con secreto de cliente | Hay que guardarlo y rotarlo. Con OIDC no existe secreto que filtrar |
| Estado de Terraform | Local, o llave de la cuenta de almacenamiento | El estado local se pierde con la laptop. La llave de la cuenta da acceso total; se usa Entra ID con rol acotado |
| Exposición del clúster | Abrir 6443 con una lista de IP | El enunciado pide no exponer la API de Kubernetes. Se administra por SSH, restringido a una IP |
| Costos | Automatizar el apagado desde la alerta de presupuesto | Las alertas solo notifican. Se usa apagado programado (23:00) más apagado manual |
| Imagen | Una imagen por componente | Tres imágenes que mantener y publicar para el mismo código. Una sola, con comando distinto, se construye una vez y se promueve |
| Certificado | Autofirmado, o cert-manager | El autofirmado no es de confianza y obliga a usar `-k`. cert-manager añade componentes que el resolver ACME de Traefik ya cubre |
| Nombre DNS | Dominio propio, o `sslip.io` | Un dominio cuesta; `sslip.io` depende de la IP y se rompería al reconstruir |
