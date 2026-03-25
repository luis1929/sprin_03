"""
PWA install UX upgrade:
- manifest name = "America's TAX OFFICE", theme = #0f3460
- Android: refined beforeinstallprompt banner
- iOS: step-by-step visual install banner
- Updates index.html only (status.html keeps Colibry Control branding)
"""
import paramiko, io, json

HOST = "178.104.58.204"
USER = "root"
PASS = "4xJ7aXCk4cNj"
REMOTE = "/root/sprin_03"

# ── Updated manifest ───────────────────────────────────────────────────────
MANIFEST = {
    "name": "America's TAX OFFICE",
    "short_name": "TAX OFFICE",
    "description": "America's TAX OFFICE - Financial & Immigration Services",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "orientation": "portrait-primary",
    "background_color": "#0f3460",
    "theme_color": "#0f3460",
    "lang": "es",
    "icons": [
        {"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/static/icons/icon-512.png",  "sizes": "512x512",  "type": "image/png"},
        {"src": "/static/icons/icon-512.png",  "sizes": "512x512",  "type": "image/png",
         "purpose": "maskable"},
    ],
    "shortcuts": [
        {"name": "Iniciar Chat", "url": "/",
         "icons": [{"src": "/static/icons/icon-192.png", "sizes": "192x192"}]},
    ],
}

# ── Icon regenerator (corporate blue #0f3460 + gold "ATO") ────────────────
ICON_SCRIPT = r"""
from PIL import Image, ImageDraw, ImageFont
import os
os.makedirs("/root/sprin_03/static/icons", exist_ok=True)

def make(size, path):
    # Background: corporate blue
    img  = Image.new("RGBA", (size, size), (15, 52, 96, 255))   # #0f3460
    draw = ImageDraw.Draw(img)
    m = size // 10
    # Gold rounded rect
    draw.rounded_rectangle([m, m, size-m, size-m],
                            radius=size//5, fill=(240,165,0,255))
    # Dark inner
    m2 = m + size//16
    draw.rounded_rectangle([m2, m2, size-m2, size-m2],
                            radius=size//6, fill=(15,52,96,255))
    # "ATO" text in gold
    fs = size // 4
    font = None
    for fp in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
               "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
        try: font = ImageFont.truetype(fp, fs); break
        except: pass
    if not font: font = ImageFont.load_default()
    bb = draw.textbbox((0,0), "ATO", font=font)
    tw, th = bb[2]-bb[0], bb[3]-bb[1]
    draw.text(((size-tw)//2, (size-th)//2 - size//22),
              "ATO", fill=(240,165,0,255), font=font)
    # Subtitle "Financial" in white small
    sf = size // 10
    for fp in ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
               "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]:
        try: sfont = ImageFont.truetype(fp, sf); break
        except: sfont = None
    if sfont:
        sb = draw.textbbox((0,0), "Financial", font=sfont)
        sw = sb[2]-sb[0]
        draw.text(((size-sw)//2, (size-th)//2 - size//22 + th + size//20),
                  "Financial", fill=(255,255,255,180), font=sfont)
    img.save(path, "PNG")
    print(f"icon {size}x{size} OK")

make(192, "/root/sprin_03/static/icons/icon-192.png")
make(512, "/root/sprin_03/static/icons/icon-512.png")
"""

# ── PWA install block to replace in index.html ────────────────────────────
# We replace the existing pwa-banner + SW script with this improved version
PWA_BLOCK = """
<!-- ═══════════════════════════════════════════════
     PWA INSTALL — Android + iOS
     ═══════════════════════════════════════════════ -->

<!-- Android install banner -->
<div id="android-banner" style="
  display:none; position:fixed; bottom:0; left:0; right:0; z-index:9999;
  background:linear-gradient(135deg,#0f3460,#1a1f35);
  border-top:2px solid #f0a500;
  padding:14px 20px 20px;
  animation:slideUp .35s ease;">
  <div style="max-width:440px;margin:0 auto;">
    <div style="display:flex;align-items:center;gap:14px;">
      <img src="/static/icons/icon-192.png"
           style="width:54px;height:54px;border-radius:12px;flex-shrink:0;">
      <div style="flex:1;">
        <div style="color:#f0a500;font-weight:700;font-size:.95rem;line-height:1.2;">
          America's TAX OFFICE
        </div>
        <div style="color:#c8d3e0;font-size:.78rem;margin-top:2px;">
          Instala la app en tu pantalla de inicio
        </div>
      </div>
      <button onclick="dismissAndroid()"
        style="background:none;border:none;color:#8b8fa8;font-size:1.3rem;
               cursor:pointer;padding:4px;flex-shrink:0;line-height:1;">✕</button>
    </div>
    <div style="display:flex;gap:8px;margin-top:12px;">
      <button onclick="installAndroid()"
        style="flex:1;background:#f0a500;color:#000;border:none;border-radius:10px;
               padding:11px;font-weight:700;font-size:.9rem;cursor:pointer;">
        📲 Instalar App
      </button>
      <button onclick="dismissAndroid()"
        style="padding:11px 18px;background:transparent;color:#8b8fa8;
               border:1px solid #2a2d3e;border-radius:10px;cursor:pointer;font-size:.85rem;">
        Ahora no
      </button>
    </div>
  </div>
</div>

<!-- iOS install banner -->
<div id="ios-banner" style="
  display:none; position:fixed; bottom:0; left:0; right:0; z-index:9999;
  background:linear-gradient(135deg,#0f3460,#1a1f35);
  border-top:2px solid #f0a500;
  padding:16px 20px 28px;
  animation:slideUp .35s ease;">
  <div style="max-width:440px;margin:0 auto;">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;">
      <div style="display:flex;align-items:center;gap:12px;">
        <img src="/static/icons/icon-192.png"
             style="width:48px;height:48px;border-radius:11px;flex-shrink:0;">
        <div>
          <div style="color:#f0a500;font-weight:700;font-size:.92rem;">America's TAX OFFICE</div>
          <div style="color:#c8d3e0;font-size:.75rem;margin-top:1px;">Agrégala a tu pantalla de inicio</div>
        </div>
      </div>
      <button onclick="dismissIOS()"
        style="background:none;border:none;color:#8b8fa8;font-size:1.3rem;cursor:pointer;padding:4px;">✕</button>
    </div>
    <!-- Step-by-step visual instructions -->
    <div style="display:flex;align-items:center;gap:0;background:rgba(255,255,255,.06);
                border-radius:12px;padding:12px 10px;justify-content:space-between;">
      <!-- Step 1 -->
      <div style="text-align:center;flex:1;">
        <div style="font-size:1.5rem;">
          <!-- Share icon SVG -->
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#f0a500"
               stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/>
            <polyline points="16 6 12 2 8 6"/>
            <line x1="12" y1="2" x2="12" y2="15"/>
          </svg>
        </div>
        <div style="color:#f0a500;font-size:.68rem;font-weight:700;margin-top:5px;">1. Compartir</div>
        <div style="color:#8b8fa8;font-size:.65rem;margin-top:2px;line-height:1.3;">
          Toca el botón<br>de abajo
        </div>
      </div>
      <!-- Arrow -->
      <div style="color:#2a2d3e;font-size:1.2rem;flex-shrink:0;padding:0 4px;">›</div>
      <!-- Step 2 -->
      <div style="text-align:center;flex:1;">
        <div>
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#f0a500"
               stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
            <line x1="12" y1="8" x2="12" y2="16"/>
            <line x1="8" y1="12" x2="16" y2="12"/>
          </svg>
        </div>
        <div style="color:#f0a500;font-size:.68rem;font-weight:700;margin-top:5px;">2. Añadir</div>
        <div style="color:#8b8fa8;font-size:.65rem;margin-top:2px;line-height:1.3;">
          "A la pantalla<br>de inicio"
        </div>
      </div>
      <!-- Arrow -->
      <div style="color:#2a2d3e;font-size:1.2rem;flex-shrink:0;padding:0 4px;">›</div>
      <!-- Step 3 -->
      <div style="text-align:center;flex:1;">
        <div>
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#f0a500"
               stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
        </div>
        <div style="color:#f0a500;font-size:.68rem;font-weight:700;margin-top:5px;">3. Listo</div>
        <div style="color:#8b8fa8;font-size:.65rem;margin-top:2px;line-height:1.3;">
          Toca "Añadir"<br>para confirmar
        </div>
      </div>
    </div>
    <!-- iOS arrow pointing to share button -->
    <div style="text-align:center;margin-top:8px;color:#f0a500;font-size:.72rem;">
      ⬇ El botón Compartir está en la barra inferior de Safari
    </div>
  </div>
</div>

<style>
@keyframes slideUp {
  from { transform:translateY(100%); opacity:0; }
  to   { transform:translateY(0);    opacity:1; }
}
</style>

<script>
// ── Device detection ─────────────────────────────────────────────────────
const IS_IOS     = /iphone|ipad|ipod/i.test(navigator.userAgent);
const IS_ANDROID = /android/i.test(navigator.userAgent);
const IS_MOBILE  = IS_IOS || IS_ANDROID || window.innerWidth <= 768;
const IN_APP     = window.navigator.standalone === true
                   || window.matchMedia('(display-mode: standalone)').matches;
const DISMISSED  = localStorage.getItem('ato_pwa_dismissed');

// ── Android ──────────────────────────────────────────────────────────────
let _prompt = null;

window.addEventListener('beforeinstallprompt', e => {
  e.preventDefault();
  _prompt = e;
  if (IS_MOBILE && !IN_APP && !DISMISSED) {
    setTimeout(() => {
      document.getElementById('android-banner').style.display = 'block';
    }, 4000);
  }
});

async function installAndroid() {
  document.getElementById('android-banner').style.display = 'none';
  if (!_prompt) return;
  _prompt.prompt();
  const { outcome } = await _prompt.userChoice;
  _prompt = null;
}

function dismissAndroid() {
  document.getElementById('android-banner').style.display = 'none';
  localStorage.setItem('ato_pwa_dismissed', '1');
}

window.addEventListener('appinstalled', () => {
  document.getElementById('android-banner').style.display = 'none';
  localStorage.removeItem('ato_pwa_dismissed');
});

// ── iOS ───────────────────────────────────────────────────────────────────
if (IS_IOS && !IN_APP && !DISMISSED) {
  setTimeout(() => {
    document.getElementById('ios-banner').style.display = 'block';
  }, 4000);
}

function dismissIOS() {
  document.getElementById('ios-banner').style.display = 'none';
  localStorage.setItem('ato_pwa_dismissed', '1');
}

// ── Service Worker ────────────────────────────────────────────────────────
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', { scope: '/' })
      .then(r => console.log('[SW] Registrado:', r.scope))
      .catch(e => console.warn('[SW]:', e));
  });
}
</script>
"""


def run(ssh, cmd, timeout=30):
    _, out, err = ssh.exec_command(cmd, timeout=timeout)
    return (out.read() + err.read()).decode("utf-8", errors="replace").strip()


def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASS, timeout=30)
    sftp = ssh.open_sftp()

    # 1) Update manifest.json
    sftp.putfo(
        io.BytesIO(json.dumps(MANIFEST, indent=2, ensure_ascii=False).encode()),
        f"{REMOTE}/static/manifest.json"
    )
    print("OK manifest.json — name='America's TAX OFFICE', theme=#0f3460")

    # 2) Regenerate icons with corporate blue
    sftp.putfo(io.BytesIO(ICON_SCRIPT.encode()), "/tmp/gen_icons3.py")
    r = run(ssh, f"{REMOTE}/venv/bin/python /tmp/gen_icons3.py 2>&1")
    print("Icons:", r)

    # 3) Update index.html
    with sftp.open(f"{REMOTE}/templates/index.html", "r") as f:
        html = f.read().decode("utf-8")

    # Remove old PWA block (from <!-- PWA Install Banner --> or <!-- PWA -->
    # to end of </script> that contains serviceWorker.register)
    import re

    # Strategy: replace everything between our markers if they exist,
    # otherwise append before </body>
    # Remove old android/pwa banner block
    old_patterns = [
        r'<!-- PWA Install Banner -->.*?</script>',
        r'<!-- PWA.*?</script>\s*\n</body>',
        r'<div id="pwa-banner".*?</script>',
    ]
    cleaned = html
    for pat in old_patterns:
        cleaned = re.sub(pat, '', cleaned, flags=re.DOTALL)

    # Remove duplicate SW registration if present
    cleaned = re.sub(
        r"// ── Service Worker.*?}\s*\}\s*\n\s*</script>", "", cleaned, flags=re.DOTALL
    )

    # Also remove old <style> slideUp if present
    cleaned = re.sub(r'<style>\s*@keyframes slideUp.*?</style>', '', cleaned, flags=re.DOTALL)

    # Inject new block before </body>
    if "android-banner" not in cleaned:
        cleaned = cleaned.replace("</body>", PWA_BLOCK + "\n</body>")
        print("OK PWA install block inyectado en index.html")
    else:
        print("-- android-banner ya existe, reemplazando...")
        cleaned = re.sub(
            r'<!-- ═+\s*PWA INSTALL.*?</script>',
            PWA_BLOCK.strip(),
            cleaned,
            flags=re.DOTALL
        )

    # Ensure meta theme-color matches new color
    cleaned = cleaned.replace(
        'name="theme-color" content="#f0a500"',
        'name="theme-color" content="#0f3460"'
    )
    cleaned = cleaned.replace(
        'name="theme-color" content="#1a1a2e"',
        'name="theme-color" content="#0f3460"'
    )

    with sftp.open(f"{REMOTE}/templates/index.html", "w") as f:
        f.write(cleaned.encode("utf-8"))
    print("OK index.html escrito")

    # 4) Syntax check (Flask doesn't parse HTML but check Python)
    r = run(ssh, f"cd {REMOTE} && venv/bin/python -m py_compile bot_server.py 2>&1 && echo OK")
    print("Python syntax:", r)

    # 5) Restart
    r = run(ssh, "systemctl restart colibry && sleep 4 && curl -s http://localhost:5000/health", timeout=20)
    print("Flask:", r)

    # 6) Verify
    for path in ["/manifest.json", "/static/icons/icon-192.png", "/static/icons/icon-512.png"]:
        code_r = run(ssh, f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:5000{path}")
        print(f"  {path}: {code_r}")

    # 7) Show manifest
    r = run(ssh, "curl -s http://localhost:5000/manifest.json | python3 -c \"import json,sys; d=json.load(sys.stdin); print('name:', d['name']); print('theme:', d['theme_color']); print('start_url:', d['start_url'])\"")
    print("Manifest verificado:\n ", r)

    sftp.close()
    ssh.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
