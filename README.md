# CVSender

**CVSender** es una herramienta local en Python para automatizar el envío individual de currículums a partir de un archivo CSV generado por el asistente de búsqueda laboral.

El proyecto reutiliza plantillas ya creadas en Thunderbird, conserva su asunto, cuerpo, firma y archivos adjuntos, selecciona automáticamente la plantilla correcta según el campo `idioma_recomendado` y envía un mensaje separado a cada destinatario mediante SMTP.

Repositorio previsto:

```text
https://github.com/JFCrypT/CVSender
```

---

## Objetivo

Automatizar esta etapa del flujo de búsqueda laboral:

```text
Asistente de búsqueda laboral
            ↓
        resultados.csv
            ↓
         CVSender
            ↓
Plantilla Thunderbird correspondiente
            ↓
 Envío individual por correo electrónico
            ↓
 Registro y archivo de cada mensaje
```

CVSender no busca empleos, no modifica el currículum y no genera el contenido del correo. Su responsabilidad es tomar el CSV ya validado, seleccionar la plantilla correspondiente y realizar los envíos.

---

## Características

- Lee el CSV UTF-8 generado por el asistente.
- Valida el encabezado y todos los campos antes del primer envío.
- Procesa todas las filas válidas del archivo.
- Selecciona automáticamente una de tres plantillas de Thunderbird.
- Conserva asunto, cuerpo, firma y adjuntos de la plantilla.
- Envía un correo independiente a cada dirección.
- Genera mensajes `.eml` antes de enviarlos.
- Incluye un modo `dry-run` que no conecta al servidor SMTP.
- Registra envíos correctos y errores en un CSV histórico.
- Detecta direcciones duplicadas dentro del mismo archivo.
- No requiere paquetes externos de Python.
- No almacena la contraseña SMTP en el código ni en el CSV.

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

CVSender toma el mensaje completo de Thunderbird y solo reemplaza el destinatario, la fecha y el identificador del mensaje.

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

El script utiliza principalmente:

- `correo`: destinatario.
- `idioma_recomendado`: selección de la plantilla.

Las demás columnas se conservan en el registro histórico para archivar el contexto completo de cada postulación.

Todas las filas válidas se procesan. No existe una columna de autorización.

---

## Requisitos

- Linux.
- Python 3.11 o posterior.
- Thunderbird configurado.
- Las tres plantillas guardadas en Thunderbird.
- Thunderbird puede permanecer abierto durante la preparación y los envíos.
- Acceso SMTP a la cuenta remitente.
- Contraseña SMTP o contraseña de aplicación compatible.

No se requieren dependencias instaladas mediante `pip`.

---

## Estructura del repositorio

```text
CVSender/
├── cvsender.py
├── resultados_ejemplo.csv
├── README.md
└── .gitignore
```

CVSender guarda todo su estado operativo dentro de la carpeta del proyecto:

```text
/home/jfcrypt/Documents/Proyectos/CVSender/CVSender_state/
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

El archivo `.gitignore` excluye `CVSender_state/`, la configuración local, los espacios de trabajo de Visual Studio Code y todos los CSV generados, excepto `resultados_ejemplo.csv`. Por lo tanto, la configuración SMTP, las copias locales de las plantillas, los mensajes `.eml`, el historial de envíos y los resultados reales no se publican en GitHub.

---

## Ubicación local del proyecto

La ubicación prevista es:

```text
/home/jfcrypt/Documents/Proyectos/CVSender/
```

Todos los comandos de este README parten de esa carpeta:

```bash
cd "/home/jfcrypt/Documents/Proyectos/CVSender"
```

Todos los archivos generados por la aplicación permanecen dentro de esa carpeta, bajo `CVSender_state/`. CVSender no utiliza `~/.local/share/` ni otra ubicación externa al proyecto.

---

## Preparación inicial

Thunderbird puede permanecer abierto. Ejecute:

```bash
cd "/home/jfcrypt/Documents/Proyectos/CVSender"

python3 cvsender.py --preparar
```

Durante esta preparación, CVSender:

1. Detecta el perfil activo de Thunderbird.
2. Localiza la carpeta `Templates` o `Plantillas`.
3. Crea dentro de `CVSender_state/` una instantánea temporal de solo lectura.
4. Si Thunderbird modifica el almacén mientras se copia, descarta la copia y vuelve a intentarlo.
5. Localiza las tres plantillas por su asunto exacto.
6. Verifica que cada plantilla tenga al menos un PDF adjunto.
7. Copia las plantillas definitivas a `CVSender_state/plantillas/`.
8. Lee la configuración SMTP del perfil mediante una lectura estable.
9. Guarda la configuración SMTP sin almacenar contraseñas.
10. Elimina la instantánea temporal.

CVSender no bloquea, modifica ni cierra Thunderbird. La preparación debe repetirse cuando se modifique una plantilla o cambie la configuración SMTP.

### Perfil o carpeta de plantillas manual

```bash
cd "/home/jfcrypt/Documents/Proyectos/CVSender"

python3 cvsender.py --preparar \
  --profile "/ruta/al/perfil" \
  --templates-path "/ruta/al/archivo/Templates"
```

Thunderbird puede seguir utilizándose durante y después de la preparación.

---

## Prueba sin enviar

Antes de realizar envíos reales:

```bash
cd "/home/jfcrypt/Documents/Proyectos/CVSender"

python3 cvsender.py resultados.csv --dry-run
```

Este modo:

- Valida el CSV completo.
- Selecciona la plantilla de cada fila.
- Genera los mensajes `.eml`.
- No abre una conexión SMTP.
- No envía correos.

Los mensajes generados quedan en:

```text
/home/jfcrypt/Documents/Proyectos/CVSender/CVSender_state/archivo_eml/dry-run/
```

---

## Envío real

```bash
cd "/home/jfcrypt/Documents/Proyectos/CVSender"

python3 cvsender.py resultados.csv
```

CVSender solicitará la contraseña SMTP de forma oculta y enviará todas las filas válidas, una por una.

### Contraseña mediante variable de entorno

```bash
cd "/home/jfcrypt/Documents/Proyectos/CVSender"

export CVSENDER_SMTP_PASSWORD='CONTRASEÑA_O_CONTRASEÑA_DE_APLICACIÓN'
python3 cvsender.py resultados.csv
unset CVSENDER_SMTP_PASSWORD
```

La contraseña no se guarda en:

- El código.
- El CSV de entrada.
- Las plantillas.
- Los archivos `.eml`.
- El registro histórico.

---

## Registro de resultados

Cada ejecución agrega información a:

```text
/home/jfcrypt/Documents/Proyectos/CVSender/CVSender_state/envios.csv
```

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

- `GENERADO`: creado mediante `--dry-run`.
- `ENVIADO`: aceptado por el servidor SMTP.
- `ERROR`: no pudo generarse o enviarse.

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
- Que el remitente de las plantillas coincida con la configuración SMTP.
- Que no existan direcciones duplicadas en el mismo CSV.

Si alguna fila no supera la validación, se cancela toda la ejecución antes de enviar el primer correo.

---

## Direcciones duplicadas

De forma predeterminada, una dirección repetida dentro del mismo CSV produce un error.

Para permitir duplicados deliberadamente:

```bash
cd "/home/jfcrypt/Documents/Proyectos/CVSender"

python3 cvsender.py resultados.csv --permitir-duplicados
```

---

## Opciones disponibles

```bash
cd "/home/jfcrypt/Documents/Proyectos/CVSender"

python3 cvsender.py --help
```

### Modificar la pausa entre envíos

La pausa predeterminada es de 10 segundos.

```bash
python3 cvsender.py resultados.csv --delay 5
```

Sin pausa:

```bash
python3 cvsender.py resultados.csv --delay 0
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

Este modo puede mostrar metadatos de la conversación SMTP. No muestra la contraseña.

---

## Comportamiento ante errores

- Un CSV inválido cancela la ejecución antes del primer envío.
- Cada mensaje se archiva antes de conectarse al destinatario.
- Un error individual no detiene las filas restantes.
- Los mensajes aceptados por SMTP se mueven a `enviados`.
- Los mensajes rechazados se mueven a `errores`.
- El proceso devuelve un código distinto de cero cuando existe al menos un error.

---

## Seguridad

CVSender:

- No intenta controlar gráficamente Thunderbird.
- No exige cerrar Thunderbird.
- Lee el perfil mediante instantáneas temporales de solo lectura.
- No extrae contraseñas guardadas en Thunderbird.
- No guarda credenciales.
- No modifica las plantillas originales.
- No envía mensajes en copia masiva.
- No agrega destinatarios adicionales.
- No utiliza servicios externos.
- No depende de APIs de terceros.

Si Thunderbird utiliza OAuth2, CVSender no reutiliza ni extrae sus tokens. La cuenta debe admitir una contraseña SMTP, una contraseña de aplicación u otro método compatible con el servidor.

---

## Limitaciones actuales

- Funciona únicamente con las tres plantillas configuradas.
- El encabezado del CSV es estricto.
- No modifica el cuerpo del mensaje para cada organización.
- No personaliza el asunto por destinatario.
- No reemplaza los archivos adjuntos definidos en la plantilla.
- No sincroniza automáticamente los mensajes con la carpeta `Enviados` de Thunderbird.
- El envío depende de que el proveedor permita autenticación SMTP compatible.

---

## Autor

**José Federico Castro Tramontina**

GitHub: [JFCrypT](https://github.com/JFCrypT)
