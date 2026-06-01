# Documentación — RAPIRO TPI 2026

La documentación técnica del proyecto se mantiene en Google Docs:

**[Abrir documentación](https://docs.google.com/document/d/1vbTp3xJYdJGE47qV9Rcr60ATsrLZ3OObodSBHoKp2o8/edit?usp=sharing)**

## Contenido actual

- Estructura y configuración del entorno de desarrollo
- Gestión de dependencias
- Configuración del entorno virtual
- Variables de entorno y configuración sensible
- Verificación de la instalación
- Módulo de captura de video (`src/capture/stream_capture.py`)
  - Compatibilidad con múltiples fuentes de video (webcam local / IP Webcam)
  - Autodetección de cámara local (índices 0–4, múltiples backends Windows)
  - Inicialización y warmup de conexión (descarte de primeros frames)
  - Preprocesamiento de frames (BGR→RGB, normalización [0,1])
  - Corrección de orientación (rotación 90°) y volteo horizontal configurable
  - Preview en tiempo real con overlay de fuente y resolución
- Módulo de generación de dataset (`src/capture/dataset_generator.py`)
  - Captura de rostros por persona hacia `data/own_dataset/<persona>/`
  - Detección con Haar Cascade (96×96 px por recorte)
  - Numeración incremental (`<persona>_0000.jpg`, `<persona>_0001.jpg`, …)
  - Controles en vivo: Espacio/P para pausar, Q para salir
  - Parámetros configurables: `--max-fotos`, `--intervalo-ms`, `--source`, `--salida`
- Módulo de carga de modelos (`src/capture/model_loader.py`)
  - Arquitectura del clasificador binario CNN (entrada 96×96×3)
  - Compatibilidad Keras 2 / Keras 3 al cargar pesos `.h5`
  - Función `load_modelo_binario(ruta)` para uso desde otros módulos
- Reconocimiento en vivo (`src/capture/reconocimiento_vivo.py`)
  - Clasificación binaria en tiempo real (Luciano / Paola)
  - Mismo pipeline de preprocesamiento que el generador de dataset
  - Overlay con nombre, confianza y valor sigmoid por rostro detectado
  - Parámetros: `--pesos`, `--umbral`, `--source`
