# Despliegue — publicar InsurAgent en una URL

**Autor:** Diego Carrillo Mondragón

Objetivo: que alguien abra un enlace, ingrese con las credenciales del reporte
PDF y use la aplicación **sin instalar nada**.

> **Despliegue activo:** https://dieguetecm-ui-insuragent-streamlit-app-f0ocjz.streamlit.app

## Hacer la aplicación accesible sin cuenta

Streamlit Community Cloud crea las aplicaciones con acceso restringido: quien
abra el enlace recibe un `303` hacia la pantalla de acceso de Streamlit. Para
que cualquiera pueda usarla:

1. Abrir la app en [share.streamlit.io](https://share.streamlit.io).
2. **⋮ → Settings → Sharing**.
3. En *Who can view this app*, elegir **«This app is public and searchable»**
   (o *anyone with the link*) y guardar.

Comprobación desde fuera —debe responder `200`, no `303`:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://dieguetecm-ui-insuragent-streamlit-app-f0ocjz.streamlit.app/
```

El proyecto ya está preparado para eso. Lo que sigue son los pasos que sólo
puedes dar tú, porque requieren tus cuentas.

---

## Lo que ya está listo

| Pieza | Para qué |
|---|---|
| `streamlit_app.py` | Punto de entrada que Streamlit Cloud ejecuta. Vuelca los secretos de la plataforma al entorno y prepara el disco. |
| `insuragent.bootstrap` | Siembra la base sintética (cartera + historial) y construye el índice FAISS en el primer arranque. Idempotente. |
| `requirements.txt` | Manifiesto **sin PyTorch**: 214 MB de RSS en vez de 2 158 MB, que es lo que hace viable el plan gratuito. |
| `.streamlit/config.toml` | Tema y límite de carga de 10 MB, alineado con lo que valida el agente FNOL. |
| `.streamlit/secrets.toml.example` | Plantilla de los secretos a pegar en el panel de la plataforma. |

### Por qué el despliegue no usa embeddings densos

El modelo `paraphrase-multilingual-MiniLM-L12-v2` pesa 458 MB y, con PyTorch,
lleva el proceso a **2 158 MB de RSS**. Streamlit Community Cloud da ~1 GB: no
cabe.

La alternativa es el embedder léxico con el diccionario del dominio
(`insuragent.rag.lexicon`), que traduce el habla del asegurado a la redacción
contractual — «choqué» y «colisión» comparten término canónico. Medido sobre el
mismo set dorado:

| Backend | Precisión RAG | RSS | Arranque |
|---|---|---|---|
| `sentence-transformers` | 15/15 · 100 % | 2 158 MB | ~6 s |
| `hash` (léxico del dominio) | **15/15 · 100 %** | **214 MB** | **0.3 s** |

A esta escala —19 cláusulas, vocabulario acotado— el modelo denso no aporta
precisión medible. Su ventaja real es generalizar a términos que el diccionario
no prevé; con un corpus de miles de cláusulas y consultas más variadas, esa
ventaja reaparecería y habría que volver al modelo denso sobre un plan con más
memoria.

---

## Streamlit Community Cloud

### 1. Subir el repositorio a GitHub

El plan gratuito despliega desde un repositorio **público**. Antes de subirlo,
confirma que nada sensible viaja:

```bash
git init
git add -A
git status --short          # revisar la lista
python -m pytest tests/test_gitignore.py    # 37 comprobaciones de seguridad
git commit -m "InsurAgent: PoC de asistente agéntico para el ramo de autos"
git branch -M main
git remote add origin https://github.com/<usuario>/insuragent.git
git push -u origin main
```

`.env` y `.streamlit/secrets.toml` están excluidos: la API key nunca sale de tu
máquina.

### 2. Crear la aplicación

1. Entrar a [share.streamlit.io](https://share.streamlit.io) con la cuenta de GitHub.
2. **New app** → seleccionar el repositorio y la rama `main`.
3. **Main file path**: `streamlit_app.py`.
4. **Advanced settings** → Python 3.12.

### 3. Configurar los secretos

En **Advanced settings → Secrets**, pegar el contenido de
`.streamlit/secrets.toml.example` con los valores reales:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
ANTHROPIC_WORKSPACE_ID = "wrkspc_..."
INSURAGENT_LLM_PROVIDER = "anthropic"
INSURAGENT_ANTHROPIC_MODEL = "claude-opus-5"
INSURAGENT_EFFORT = "low"
INSURAGENT_EMBEDDING_BACKEND = "hash"
```

Se guardan cifrados en la plataforma y se inyectan en tiempo de ejecución. No
tocan el repositorio.

### 4. Poner la URL en el reporte

El primer despliegue tarda unos minutos. Cuando responda, añade la URL a tu
`.env` local y regenera el PDF:

```bash
echo 'INSURAGENT_PUBLIC_URL=https://<tu-app>.streamlit.app' >> .env
make report
```

El capítulo «Acceso al servicio» pasa a encabezarse con el enlace en grande,
seguido de las credenciales sintéticas. Quien reciba el PDF ya no necesita
instalar nada.

---

## Qué esperar de la aplicación publicada

* **Arranque en frío.** Streamlit Cloud duerme las apps sin tráfico. La primera
  visita tras un rato tarda unos segundos mientras se siembra el disco efímero.
* **Disco efímero.** Cada reinicio parte de cero: la base se vuelve a sembrar
  igual —la generación es determinista, así que las credenciales del PDF siguen
  siendo válidas— pero los siniestros que registren los visitantes se pierden.
  Para una demo es lo deseable: cada visitante encuentra el sistema limpio.
* **Degradación visible.** Si la API key caduca o se queda sin saldo, la app
  sigue funcionando con el componente determinista y muestra un aviso rojo en
  pantalla diciendo que las respuestas **no** provienen del modelo. Sin ese
  aviso, una demo caducada parecería funcionar bien y engañaría al visitante.

### Sobre la API key en una URL pública

Con una llave de vigencia corta el riesgo queda acotado, pero conviene tener
presente:

1. **Mientras la llave viva, el límite es tu saldo, no la fecha.** Cualquiera con
   el enlace puede consumir créditos; no hay límite de peticiones por visitante.
   Si el enlace circula más de lo previsto, el gasto es real.
2. **Al caducar, la demo no se cae: se degrada.** Sigue respondiendo con el
   componente determinista. El aviso en pantalla lo hace evidente, pero si vas a
   compartir el enlace más allá de esos días conviene rotar la llave y no dejar
   que el visitante juzgue al sistema por el modo degradado.
3. **Las credenciales del PDF son sintéticas y pueden publicarse.** El riesgo
   está en la llave, no en los datos.

---

## Alternativas

| Opción | URL permanente | Costo | Requiere |
|---|---|---|---|
| **Streamlit Community Cloud** | sí | gratis | repo público en GitHub |
| **Hugging Face Spaces** | sí | gratis | cuenta HF; usa el `Dockerfile` |
| **GCP Cloud Run** | sí | centavos, escala a cero | `gcloud` + facturación; `infra/terraform/` ya validado |
| **Túnel (cloudflared)** | no | gratis | nada, pero exige tu máquina encendida |

Para Cloud Run, el camino está escrito y validado:

```bash
cd infra/terraform
export TF_VAR_anthropic_api_key="sk-ant-..."
terraform init && terraform apply
terraform output service_url
```
