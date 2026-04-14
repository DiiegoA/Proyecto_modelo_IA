# Glosario de predicción Adult Income

El endpoint de predicción exige catorce campos obligatorios:

- `age`: edad.
- `workclass`: clase o tipo de empleo.
- `fnlwgt`: peso final del registro en el dataset.
- `education`: nivel educativo textual.
- `education.num`: nivel educativo numérico.
- `marital.status`: estado civil.
- `occupation`: ocupación principal.
- `relationship`: relación familiar.
- `race`: raza.
- `sex`: sexo (`Male` o `Female`).
- `capital.gain`: ganancia de capital.
- `capital.loss`: pérdida de capital.
- `hours.per.week`: horas trabajadas por semana.
- `native.country`: país de origen.

## Regla del agente

Si falta aunque sea uno de estos campos, el agente debe detener la llamada a `oraculo_api` y pedir los datos faltantes.
