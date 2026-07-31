# CVSender

**CVSender** es una herramienta local en Python para automatizar el envío individual de currículums a partir de un archivo CSV generado por un asistente de búsqueda laboral.

La aplicación reutiliza plantillas guardadas en Thunderbird, conserva su asunto, cuerpo, firma y archivos adjuntos, selecciona automáticamente la plantilla correcta mediante el campo `idioma_recomendado` y envía un mensaje independiente a cada destinatario por SMTP.

Repositorio:

<https://github.com/JFCrypT/CVSender>

---

## Objetivo

CVSender automatiza la etapa de envío dentro de este flujo:

```text
Asistente de búsqueda laboral
            ↓
        resultados.csv
            ↓
         CVSender
            ↓
Selección de plantilla Thunderbird
            ↓
 Envío individual mediante SMTP
            ↓
 Registro histórico y archivo EML
```

CVSender no busca empleos, no modifica el currículum y no redacta el contenido del correo. Su responsabilidad es recibir un CSV ya validado, seleccionar la plantilla correspondiente y efectuar los envíos.

---

## Características

- Lee archivos CSV UTF-8.
- Valida íntegramente el CSV antes del primer envío.
- Procesa todas las filas válidas.
- Selecciona automáticamente una de tres plantillas de Thunderbird.
- Conserva asunto, cuerpo, firma y archivos adjuntos.
- Envía un correo independiente a cada dirección.
- Genera una copia `.eml` de cada mensaje.
- Incluye un modo `dry-run` que no conecta al servidor SMTP.
- Mantiene un historial acumulativo en `envios.csv`.
- Registra envíos correctos y errores.
- Detecta direcciones duplicadas dentro del mismo CSV.
- Permite configurar la pausa entre mensajes.
- No requiere paquetes externos de Python.
- No requiere un entorno virtual.
- No almacena la contraseña SMTP.

---

## Plantillas de Thunderbird

Thunderbird debe contener exactamente estas tres plantillas:

| `idioma_recomendado` | Asunto de la plantilla |
|---|---|
| `ingles` | `CV Submission` |
| `español-industrial` | `Enviar CV` |
| `español-académico` | `Enviar CV: docencia` |

Cada plantilla debe contener:

- El asunto definitivo.
- El cuerpo definitivo.
- La firma.
- El currículum correspondiente como archivo adjunto.

CVSender toma el mensaje completo de Thunderbird y reemplaza únicamente los datos necesarios para el nuevo envío, como el destinatario, la fecha y el identificador del mensaje.

Cuando se modifica el texto, la firma o los adjuntos de una plantilla en Thunderbird, debe repetirse:

```bash
python3 cvsender.py --preparar
```

---

## Formato del CSV

El archivo de entrada debe usar codificación UTF-8 y contener exactamente este encabezado:

```csv
organizacion_o_reparticion,puesto_o_area_recomendada,idioma_recomendado,correo,recomendacion
```

Ejemplo:

```csv
organizacion_o_reparticion,puesto_o_area_recomendada,idioma_recomendado,correo,recomendacion
"Empresa internacional","Applied Cryptography Engineer","ingles","careers@example.com","Enviar CV directamente."
"Empresa argentina","Desarrollo Python y ciberseguridad","español-industrial","rrhh@example.com.ar","Enviar CV directamente."
"Universidad","Criptografía y Seguridad Informática","español-académico","docencia@example.edu.ar","Enviar CV directamente."
```

CVSender utiliza principalmente:

- `correo`: dirección destinataria.
- `idioma_recomendado`: selección de la plantilla.

Las demás columnas se conservan en el registro histórico para archivar el contexto completo de cada postulación.

Todas las filas válidas se procesan. No existe una columna de autorización.

---

## Generación del CSV con el Prompt Maestro Genérico

El repositorio incluye un prompt reutilizable para generar resultados compatibles con CVSender:

[Prompt Maestro Genérico](docs/Prompt%20Maestro%20Gen%C3%A9rico.md)

El prompt está diseñado para utilizarse en un asistente con capacidad de búsqueda web. Cuando se selecciona la modalidad **CORREOS**, produce:

1. Una tabla visible con los destinos encontrados.
2. Un bloque CSV UTF-8 que refleja exactamente esa tabla.
3. Los valores normalizados de `idioma_recomendado` que CVSender utiliza para seleccionar la plantilla de Thunderbird.

El archivo generado debe guardarse en la raíz del proyecto, por ejemplo:

```text
/ruta/a/CVSender/resultados.csv
```

Después puede validarse y procesarse con:

```bash
python3 cvsender.py resultados.csv --dry-run
python3 cvsender.py resultados.csv
```

El prompt es un recurso complementario. CVSender no lo ejecuta, no realiza búsquedas laborales y no genera por sí mismo el archivo CSV.

---

## Requisitos

- Linux.
- Python 3.11 o posterior.
- Thunderbird configurado.
- Las tres plantillas guardadas en Thunderbird.
- Acceso SMTP a la cuenta remitente.
- Contraseña SMTP o contraseña de aplicación compatible.

No se requieren dependencias instaladas mediante `pip`.

Verificación:

```bash
python3 --version
```

No hace falta crear un entorno virtual porque CVSender utiliza únicamente la biblioteca estándar de Python.

---

## Estructura del repositorio

```text
CVSender/
├── cvsender.py
├── resultados_ejemplo.csv
├── README.md
├── .gitignore
└── docs/
    └── Prompt Maestro Genérico.md
```

CVSender guarda su estado operativo dentro de la carpeta del proyecto:

```text
CVSender/
└── CVSender_state/
    ├── plantillas/
    │   ├── ingles.eml
    │   ├── espanol-industrial.eml
    │   └── espanol-academico.eml
    ├── smtp.json
    ├── archivo_eml/
    │   ├── dry-run/
    │   ├── pendientes/
    │   ├── enviados/
    │   └── errores/
    └── envios.csv
```

El archivo `.gitignore` debe excluir:

- `CVSender_state/`.
- La configuración local.
- Las copias de las plantillas.
- Los mensajes `.eml`.
- El historial de envíos.
- Los CSV reales generados.
- `.vscode/`.
- Los archivos `*.code-workspace`.
- Los archivos `.env`.

Se conserva únicamente `resultados_ejemplo.csv`.

> `CVSender_state/smtp.json` puede contener datos locales del perfil y del servidor SMTP. Debe permanecer excluido del repositorio.

---

## Ubicación local del proyecto

Clone o copie el repositorio en cualquier ubicación local, por ejemplo:

```text
/ruta/a/CVSender/
```

Entre en la raíz del proyecto:

```bash
cd "/ruta/a/CVSender"
```

Todos los archivos generados por la aplicación permanecen dentro de esa carpeta, bajo `CVSender_state/`.

---

## Preparación inicial

Thunderbird puede permanecer abierto.

```bash
cd "/ruta/a/CVSender"

python3 cvsender.py --preparar
```

Durante la preparación, CVSender:

1. Detecta el perfil activo de Thunderbird.
2. Localiza la carpeta `Templates` o `Plantillas`.
3. Crea una instantánea temporal de solo lectura.
4. Reintenta si Thunderbird modifica el almacén mientras se copia.
5. Localiza las tres plantillas por su asunto exacto.
6. Verifica que cada plantilla tenga al menos un PDF adjunto.
7. Copia las plantillas definitivas a `CVSender_state/plantillas/`.
8. Lee la configuración SMTP del perfil.
9. Guarda la configuración SMTP sin almacenar contraseñas.
10. Elimina la instantánea temporal.

CVSender no bloquea, modifica ni cierra Thunderbird.

La preparación debe repetirse cuando:

- Se modifica una plantilla.
- Se reemplaza un archivo adjunto.
- Cambia la cuenta remitente.
- Cambia la configuración SMTP.

### Perfil o carpeta de plantillas manual

```bash
cd "/ruta/a/CVSender"

python3 cvsender.py --preparar \
  --profile "/ruta/al/perfil" \
  --templates-path "/ruta/al/archivo/Templates"
```

---

## Prueba sin enviar

Antes de realizar envíos reales:

```bash
cd "/ruta/a/CVSender"

python3 cvsender.py resultados.csv --dry-run
```

Este modo:

- Valida el CSV completo.
- Selecciona la plantilla de cada fila.
- Genera los mensajes `.eml`.
- Registra el estado `GENERADO`.
- No abre una conexión SMTP.
- No envía correos.
- No crea borradores en Thunderbird.
- No modifica las plantillas originales.

Los mensajes generados quedan en:

```text
CVSender_state/archivo_eml/dry-run/
```

El estado `GENERADO` significa que el mensaje fue construido y archivado correctamente, pero no enviado.

---

## Envío real

```bash
cd "/ruta/a/CVSender"

python3 cvsender.py resultados.csv
```

CVSender solicita la contraseña SMTP de forma oculta y envía todas las filas válidas, una por una.

La pausa predeterminada entre mensajes es de **10 segundos**.

### Contraseña de aplicación

Cuando Thunderbird utiliza OAuth2, CVSender no puede reutilizar el token almacenado por Thunderbird. En ese caso, debe utilizarse una contraseña de aplicación proporcionada por el proveedor de correo.

Una contraseña de aplicación:

- No es un OTP.
- Puede reutilizarse en ejecuciones posteriores.
- Permanece válida hasta que sea revocada o invalidada por el proveedor.
- No debe guardarse en el repositorio.

La opción recomendada es introducirla cuando CVSender la solicite, porque el ingreso es oculto y no queda escrito en el código, el CSV ni el historial.

### Contraseña mediante variable de entorno

También puede proporcionarse temporalmente mediante una variable de entorno sin escribirla directamente en la línea de comandos:

```bash
cd "/ruta/a/CVSender"

read -rsp "Contraseña SMTP o de aplicación: " CVSENDER_SMTP_PASSWORD
echo
export CVSENDER_SMTP_PASSWORD

python3 cvsender.py resultados.csv

unset CVSENDER_SMTP_PASSWORD
```

La contraseña no se almacena en:

- El código.
- El CSV de entrada.
- Las plantillas.
- Los archivos `.eml`.
- `smtp.json`.
- El registro histórico.

> Evite escribir la contraseña directamente en un comando `export`, porque podría quedar registrada en el historial de la shell.

---

## Pausa entre envíos

La pausa predeterminada es de diez segundos.

Puede modificarse para una ejecución concreta:

```bash
python3 cvsender.py resultados.csv --delay 20
```

Sin pausa:

```bash
python3 cvsender.py resultados.csv --delay 0
```

Una pausa mayor puede reducir rechazos temporales cuando se envían numerosos mensajes semejantes o varios destinatarios pertenecen al mismo dominio.

---

## Registro de resultados

Cada ejecución agrega información a:

```text
CVSender_state/envios.csv
```

`envios.csv` funciona como historial acumulativo: no se reemplaza en cada ejecución. Las nuevas filas se agregan al final.

El registro conserva:

- Fecha y hora.
- Organización.
- Puesto o área.
- Idioma recomendado.
- Correo.
- Recomendación.
- Plantilla utilizada.
- Estado.
- Detalle.
- Ruta del mensaje `.eml`.

Estados posibles:

- `GENERADO`: creado mediante `--dry-run`, sin envío SMTP.
- `ENVIADO`: aceptado por el servidor SMTP.
- `ERROR`: no pudo generarse o enviarse.

`envios.csv` contiene toda la información de `resultados.csv` y agrega los datos operativos del procesamiento. Por ello, puede utilizarse como histórico principal.

El archivo `resultados.csv` puede tratarse como entrada temporal, pero conviene conservarlo hasta confirmar que todas las filas fueron enviadas o registradas correctamente.

---

## Archivo de mensajes EML

CVSender conserva una copia exacta de cada mensaje generado:

```text
CVSender_state/archivo_eml/
```

Subcarpetas:

- `dry-run/`: mensajes creados sin envío.
- `pendientes/`: mensajes preparados antes del intento SMTP.
- `enviados/`: mensajes aceptados por SMTP.
- `errores/`: mensajes cuyo envío falló.

CVSender no escribe directamente en los archivos internos de Thunderbird.

El proveedor de correo puede guardar automáticamente los mensajes enviados por SMTP en la carpeta `Sent` o `Enviados` del servidor. Cuando eso ocurre, Thunderbird los muestra al sincronizar. Este comportamiento depende del proveedor.

---

## Validaciones

Antes del primer envío, CVSender comprueba:

- Que el archivo exista.
- Que el CSV tenga el encabezado exacto.
- Que no existan campos vacíos.
- Que cada fila tenga una única dirección de correo válida.
- Que `idioma_recomendado` use uno de los tres valores admitidos.
- Que las tres plantillas estén disponibles.
- Que cada plantilla incluya un PDF adjunto.
- Que el remitente coincida con la configuración SMTP.
- Que no existan direcciones duplicadas dentro del mismo CSV.

Si alguna fila no supera la validación, la ejecución se cancela antes de enviar el primer correo.

---

## Direcciones duplicadas

De forma predeterminada, una dirección repetida dentro del mismo CSV produce un error.

Para permitir duplicados deliberadamente:

```bash
cd "/ruta/a/CVSender"

python3 cvsender.py resultados.csv --permitir-duplicados
```

La detección de duplicados se aplica al CSV de la ejecución actual. No impide volver a enviar una dirección que ya aparece en `envios.csv`.

---

## Reintento de errores

Un error individual no detiene las filas restantes.

El procedimiento recomendado es:

1. Revisar `CVSender_state/envios.csv`.
2. Identificar las filas con estado `ERROR`.
3. Crear manualmente un CSV nuevo que contenga únicamente esas filas.
4. Esperar un intervalo razonable.
5. Reenviar solo el CSV reducido.

Ejemplo:

```bash
python3 cvsender.py resultados_reintento.csv
```

No debe repetirse el CSV completo si parte de sus destinatarios ya fue enviada correctamente, porque esos mensajes se enviarían nuevamente.

El historial conservará ambos eventos:

```text
primer intento  → ERROR
segundo intento → ENVIADO
```

---

## Opciones disponibles

```bash
cd "/ruta/a/CVSender"

python3 cvsender.py --help
```

### Sobrescribir la configuración SMTP

```bash
python3 cvsender.py resultados.csv \
  --smtp-host smtp.example.com \
  --smtp-port 587 \
  --smtp-security starttls \
  --smtp-user usuario@example.com
```

Valores admitidos para `--smtp-security`:

```text
plain
starttls
ssl
```

### Diagnóstico SMTP

```bash
python3 cvsender.py resultados.csv --debug-smtp
```

Este modo puede mostrar metadatos de la conversación SMTP, pero no muestra la contraseña.

> El modo de diagnóstico puede exponer direcciones, dominios y respuestas del servidor en la terminal. No publique su salida sin revisarla.

---

## Comportamiento ante errores

- Un CSV inválido cancela la ejecución antes del primer envío.
- Cada mensaje se archiva antes del intento SMTP.
- Un error individual no detiene las filas restantes.
- Los mensajes aceptados por SMTP se mueven a `enviados`.
- Los mensajes rechazados se mueven a `errores`.
- El proceso devuelve un código distinto de cero cuando existe al menos un error.
- CVSender no reintenta automáticamente los mensajes rechazados.

---

## Seguridad

CVSender:

- No controla gráficamente Thunderbird.
- No exige cerrar Thunderbird.
- Lee el perfil mediante instantáneas temporales de solo lectura.
- No extrae contraseñas guardadas en Thunderbird.
- No extrae tokens OAuth2.
- No almacena credenciales.
- No modifica las plantillas originales.
- No envía mensajes en copia masiva.
- No agrega destinatarios adicionales.
- No depende de APIs laborales externas.
- Utiliza únicamente la biblioteca estándar de Python.

Los archivos sensibles y operativos se encuentran bajo `CVSender_state/`, que debe permanecer excluido mediante `.gitignore`.

Antes de publicar cambios, verifique:

```bash
git status --ignored
```

No deben quedar preparados para commit:

- `CVSender_state/`.
- `resultados.csv` u otros CSV reales.
- Archivos `.env`.
- Archivos `.eml`.
- Configuración de Visual Studio Code.
- Salidas de diagnóstico con datos personales.

---

## Limitaciones actuales

- Funciona únicamente con las tres plantillas configuradas.
- El encabezado del CSV es estricto.
- No modifica el cuerpo del mensaje para cada organización.
- No personaliza el asunto por destinatario.
- No reemplaza automáticamente los archivos adjuntos definidos en la plantilla.
- No guarda por sí mismo los mensajes en la carpeta `Sent` de Thunderbird.
- No reutiliza los tokens OAuth2 de Thunderbird.
- No reintenta automáticamente los errores.
- No evita duplicados comparando contra el historial completo.
- El envío depende de que el proveedor admita autenticación SMTP compatible.

---

## Autor

**José Federico Castro Tramontina**

GitHub: [JFCrypT](https://github.com/JFCrypT)
