import tensorflow as tf
from tensorflow.keras import layers, models
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau, ModelCheckpoint


# Definimos la extensión .keras obligatoria en las versiones nuevas
MODEL_PATH = "/content/modelo_tpi.keras"
EPOCHS = 50

def build_model(input_shape=(96, 96, 3), num_classes=NUM_CLASSES):
    model = models.Sequential([
        # Capa de entrada obligatoria
        layers.Input(shape=input_shape),

        # Bloque Convolucional 1
        layers.Conv2D(32, (3, 3), padding="same"),
        layers.BatchNormalization(),
        layers.Activation("relu"),
        layers.MaxPooling2D((2, 2)),

        # Bloque Convolucional 2
        layers.Conv2D(64, (3, 3), padding="same"),
        layers.BatchNormalization(),
        layers.Activation("relu"),
        layers.MaxPooling2D((2, 2)),

        layers.Conv2D(128, (3, 3), padding="same"),
        layers.BatchNormalization(),
        layers.Activation("relu"),
        layers.MaxPooling2D((2, 2)),

        # Elimina memorización masiva
        layers.GlobalAveragePooling2D(),
        layers.Dropout(0.5),

        # Capa intermedia (necesaria para 3+ clases)
        layers.Dense(128, activation="relu"),
        layers.Dropout(0.3),

        # Salida multiclase
        layers.Dense(num_classes, activation="softmax")
    ])

    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.0001),
        loss="categorical_crossentropy",
        metrics=["accuracy"]
    )
    return model

model_tpi = build_model()
model_tpi.summary()

# Callbacks ajustados para Keras 3
callbacks = [
    EarlyStopping(
        monitor="val_accuracy",
        patience=15,
        restore_best_weights=True,
        verbose=1
    ),
    ReduceLROnPlateau(
        monitor="val_loss",
        factor=0.5,
        patience=5,
        min_lr=1e-6,
        verbose=1
    ),
    ModelCheckpoint(
        MODEL_PATH, # Ahora apunta a la ruta con extensión .keras
        monitor="val_accuracy",
        save_best_only=True,
        verbose=1
    )
]

print("\n🚀 Iniciando entrenamiento...\n")
history = model_tpi.fit(
    train_generator,
    validation_data=val_generator,
    epochs=EPOCHS,
    callbacks=callbacks,
    verbose=1
)

print(f"\n✅ Modelo guardado exitosamente en: {MODEL_PATH}")
print("📦 Iniciando descarga del archivo .keras...\n")