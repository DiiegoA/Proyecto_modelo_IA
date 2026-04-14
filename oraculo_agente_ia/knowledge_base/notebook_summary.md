# Resumen curado del notebook de Adult Income

El proyecto usa el dataset Adult Census Income para predecir si una persona cae en una clase de ingreso alrededor del umbral `>50K` o `<=50K`.

## Artefacto de producción

- El notebook prepara y exporta un pipeline serializado para inferencia.
- La API `oraculo_api` carga ese artefacto para atender peticiones autenticadas de predicción.
- El servicio registra auditoría de cada predicción, incluyendo payload original, payload normalizado, latencia, request id y versión del modelo.

## Contrato operativo

- El backend no debe aceptar texto libre como sustituto del contrato estructurado de predicción.
- La integración correcta es convertir la entrada del usuario a los campos del esquema y solo entonces llamar a la API.
