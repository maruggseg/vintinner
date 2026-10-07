# Runner de Fly.io (Madrid)

Esto despliega un runner auto-alojado de GitHub Actions en Fly.io,
región Madrid (`mad`), para que el scraping de Vinted salga con IP
española en vez de la IP de los runners normales de GitHub.

## Pasos (desde tu PC, con flyctl instalado)

1. Instalar flyctl (PowerShell, como administrador no hace falta):
   ```
   iwr https://fly.io/install.ps1 -useb | iex
   ```
   Cierra y abre otra vez PowerShell para que reconozca el comando `fly`.

2. Iniciar sesión (abre el navegador, usa la cuenta que ya creaste):
   ```
   fly auth login
   ```

3. Crear un token de acceso personal (PAT) de GitHub solo para este repo:
   - GitHub → tu foto de perfil → **Settings** → **Developer settings** →
     **Personal access tokens** → **Fine-grained tokens** → **Generate new token**.
   - "Repository access": **Only select repositories** → `vintinner`.
   - En "Permissions" → "Repository permissions" → **Administration: Read and write**
     (es el único permiso que necesita para registrar el runner).
   - Genera el token y cópialo. **No lo pegues en el chat**, solo lo
     vas a usar en el paso 5, directamente en tu terminal.

4. Entra en esta carpeta (`runner/`) en tu terminal y ejecuta:
   ```
   fly launch --no-deploy --copy-config --name vintinner-runner
   ```
   Cuando pregunte la región, confirma Madrid (`mad`). Cuando pregunte
   si quieres una base de datos, bases de datos Redis, etc., responde que no.

5. Guarda el token como secreto (te lo pedirá de forma oculta, o puedes
   pasarlo así — tu terminal, nunca el chat):
   ```
   fly secrets set ACCESS_TOKEN=pega_aqui_tu_token
   ```

6. Despliega:
   ```
   fly deploy
   ```

7. Comprueba que el runner aparece como "Idle" en GitHub:
   `https://github.com/maruggseg/vintinner/settings/actions/runners`

Cuando el runner salga ahí como activo, hay que cambiar
`.github/workflows/vinted.yml` para que use `runs-on: [self-hosted, spain]`
en vez de `ubuntu-latest`. Eso lo hago yo en cuanto confirmes que el
runner está "Idle" en esa página.
