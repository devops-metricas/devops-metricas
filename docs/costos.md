# Costos

Tope del proyecto: **US$100** acumulados en la suscripción Azure for Students (DEV-14, 5.9).

## 1. Estimación

Precios de lista de la API pública de precios de Azure (`prices.azure.com`), región `northcentralus`,
consultados en noviembre de 2026. Los créditos o descuentos de la suscripción no se descuentan, por lo
que la estimación es conservadora.

| Recurso | Precio | Cuándo cobra |
|---|---|---|
| VM `Standard_B2as_v2` (Linux) | US$0.0752 por hora | Solo encendida. **Desasignada no cobra cómputo** |
| Disco SSD estándar de 64 GB (E6, LRS) | US$4.80 al mes | Siempre, incluso con la VM apagada |
| IP pública estándar estática | US$0.005 por hora (≈ US$3.60 al mes) | Siempre, incluso con la VM apagada |
| Cuenta de almacenamiento del estado de Terraform | Centavos (un archivo pequeño) | Siempre; no medido, se confirma en Cost Management |
| Red virtual, NSG, presupuesto, apagado programado | Sin costo | — |

**Costo fijo con la VM apagada:** US$4.80 + US$3.60 ≈ **US$8.40 al mes**.

### Escenarios de un mes

| Uso de la VM | Horas | Cómputo | Fijo | Total |
|---|---|---|---|---|
| 24 horas, todo el mes (lo que **no** haremos) | 720 | US$54.14 | US$8.40 | **US$62.54** |
| 8 horas al día | 240 | US$18.05 | US$8.40 | **US$26.45** |
| 4 horas al día | 120 | US$9.02 | US$8.40 | **US$17.42** |

Incluso encendida las 24 horas, un mes completo queda en US$62.54, por debajo de los US$100. El plan
es mucho menor (entre US$17 y US$27 al mes), lo que deja margen para sesiones largas de pruebas de
carga y para las demostraciones.

No hay otros servicios de pago: PostgreSQL, Mailpit y la futura pila de observabilidad corren dentro de
la misma VM. Si el equipo agrega un servicio administrado (por ejemplo Log Analytics), debe
sumarse aquí antes de activarlo.

## 2. Medidas para reducir el gasto

1. **Apagar la VM al terminar cada sesión:** *Actions → Infra ops → `deallocate`* (ver
   [reconstruccion.md](reconstruccion.md)).
2. **Apagado automático** todos los días a las 23:00 (hora de América Central), por si alguien olvida
   el paso anterior. No lo sustituye.
3. **Alertas de presupuesto** al 50, 80 y 100 % de US$100, por correo. Solo notifican: no detienen
   nada.
4. **Destrucción total** al terminar el proyecto (`destroy` y luego la limpieza del bootstrap), para
   dejar la suscripción sin cargos fijos.

## 3. Cargos observados

*Pendiente: se completa con los datos reales de Azure Cost Management → Cost analysis, agrupados por
recurso, después de la primera semana de uso. Incluir captura.*

| Fecha de consulta | Costo acumulado | Cómputo | Disco | IP pública | Estado | Observación |
|---|---|---|---|---|---|---|
| | | | | | | |

Comparar contra la estimación de la sección 1: si el gasto real se desvía, anotar por qué (VM
encendida de más, cargos no previstos).

## 4. Dimensionamiento de la VM

*Pendiente: justificar `Standard_B2as_v2` (2 vCPU, 8 GB) con los requests definidos en los manifiestos
y el consumo observado con la aplicación y la pila de métricas desplegadas.*

K3s exige como mínimo 2 vCPU y 2 GB para un nodo servidor. Se eligieron 8 GB porque en el mismo nodo
deben convivir dev, prod, PostgreSQL, Mailpit y la observabilidad. Se confirma o se ajusta con los
consumos reales.
