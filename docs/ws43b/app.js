const PINNED_INFO = {
  version: "v4.1.0",
  display_version: "v4.1.0",
  board_variant: "ws_lcd_43b",
  chip_family: "ESP32-S3",
  source_commit: "d6795d671be862ffae71de69a0d810b901453412",
  factory_file: "factory.bin",
  factory_bytes: 2956144,
  factory_sha256: "be4445792801b12d104070f7e26739eb5e57be49f4369babee8b0ad0a6614726",
  release_url: "https://github.com/honzo90/BambuHelper/releases/tag/v4.1.0",
};

const EXPECTED_MANIFEST = {
  name: "BambuHelper WS43B",
  version: "v4.1.0",
  new_install_prompt_erase: false,
  new_install_improv_wait_time: 0,
};

const STRINGS = {
  pl: {
    lead: "Monitor druku i suszenia AMS dla panelu Waveshare ESP32-S3-Touch-LCD-4.3B (800x480, 16MB flash).",
    steps: "Kroki",
    s1: "Użyj Chrome/Edge na komputerze i połączenia USB danych.",
    s2: "Potwierdź dokładny model: Waveshare ESP32-S3-Touch-LCD-4.3B.",
    s3: "Przygotuj instalację, następnie zainstaluj.",
    s4: "Po instalacji skonfiguruj Wi-Fi przez sieć panelu; dane tej sieci pojawią się na LCD.",
    s5: "Późniejsze aktualizacje wykonaj w WebUI panelu: Stable → Sprawdź aktualizacje.",
    notice: "Pierwsza instalacja USUWA ustawienia Wi-Fi, drukarki i poprzedni firmware. Dla już działającego panelu zalecane OTA w jego WebUI.",
    warning: "Instalator USB wymaga Chrome lub Edge na komputerze. Na iPhonie możesz przeczytać instrukcję, ale instalację wykonaj na komputerze. Po wgraniu sprawdź obraz, dotyk i połączenie Wi-Fi.",
    confirm: "Potwierdzam dokładny model 4.3B i zgodę na usunięcie ustawień",
    confirmHelp: "Inne modele płytek nie są obsługiwane przez ten instalator.",
    prepare: "Przygotuj instalację",
    source: "Kod źródłowy",
    notes: "v4.1.0 — opis wydania",
    issue: "Znany problem ekranu",
    fork: "Fork projektu",
    forkBy: "BambuHelper autorstwa Keralots",
    stConfirm: "Potwierdź model płytki i usunięcie ustawień, aby przygotować instalację.",
    stUnsupported: "Instalacja USB wymaga Chrome lub Edge na komputerze oraz połączenia HTTPS. Na iPhonie ta funkcja jest niedostępna.",
    stTick: "Zaznacz potwierdzenie modelu 4.3B.",
    stPreparing: "Przygotowanie instalacji…",
    connect: "Połącz i zainstaluj",
    stReady: "Plik sprawdzony. Instalator przygotowany. Kliknij Połącz i zainstaluj.",
    stError: "Błąd przygotowania: {msg}. Można ponowić ręcznie.",
  },
  en: {
    lead: "Print and AMS drying monitor for the Waveshare ESP32-S3-Touch-LCD-4.3B panel (800x480, 16MB flash).",
    steps: "Steps",
    s1: "Use Chrome/Edge on a computer and a USB data cable.",
    s2: "Confirm the exact model: Waveshare ESP32-S3-Touch-LCD-4.3B.",
    s3: "Prepare the installation, then install.",
    s4: "After installing, set up Wi-Fi through the panel's own network; its details appear on the LCD.",
    s5: "Later updates: panel WebUI → Stable → Check for updates.",
    notice: "The first installation ERASES Wi-Fi and printer settings and the previous firmware. For a panel that already runs, use OTA in its WebUI.",
    warning: "The USB installer needs Chrome or Edge on a computer. On an iPhone you can read the steps, but install from a computer. After flashing, check the picture, touch and Wi-Fi.",
    confirm: "I confirm the exact 4.3B model and agree to erase the settings",
    confirmHelp: "Other boards are not supported by this installer.",
    prepare: "Prepare installation",
    source: "Source code",
    notes: "v4.1.0 — release notes",
    issue: "Known display issue",
    fork: "Fork of",
    forkBy: "BambuHelper by Keralots",
    stConfirm: "Confirm the board model and erasing the settings to prepare the installation.",
    stUnsupported: "USB installation needs Chrome or Edge on a computer and an HTTPS connection. It is not available on an iPhone.",
    stTick: "Tick the 4.3B model confirmation.",
    stPreparing: "Preparing the installation…",
    connect: "Connect and install",
    stReady: "Image verified. Installer ready. Click Connect and install.",
    stError: "Preparation failed: {msg}. You can try again.",
  },
  de: {
    lead: "Druck- und AMS-Trocknungsmonitor für das Panel Waveshare ESP32-S3-Touch-LCD-4.3B (800x480, 16MB Flash).",
    steps: "Schritte",
    s1: "Verwende Chrome/Edge auf einem Computer und ein USB-Datenkabel.",
    s2: "Bestätige das genaue Modell: Waveshare ESP32-S3-Touch-LCD-4.3B.",
    s3: "Installation vorbereiten, dann installieren.",
    s4: "Richte danach das WLAN über das Netzwerk des Panels ein; seine Daten erscheinen auf dem Display.",
    s5: "Spätere Updates: im WebUI des Panels Stable → Nach Updates suchen.",
    notice: "Die Erstinstallation LÖSCHT WLAN- und Druckereinstellungen sowie die bisherige Firmware. Für ein laufendes Panel das OTA-Update im WebUI verwenden.",
    warning: "Der USB-Installer benötigt Chrome oder Edge auf einem Computer. Auf dem iPhone kannst du die Anleitung lesen, installiere aber am Computer. Prüfe danach Bild, Touch und WLAN.",
    confirm: "Ich bestätige das genaue Modell 4.3B und das Löschen der Einstellungen",
    confirmHelp: "Andere Platinen werden von diesem Installer nicht unterstützt.",
    prepare: "Installation vorbereiten",
    source: "Quellcode",
    notes: "v4.1.0 — Versionshinweise",
    issue: "Bekanntes Display-Problem",
    fork: "Fork von",
    forkBy: "BambuHelper von Keralots",
    stConfirm: "Bestätige Platinenmodell und Löschen der Einstellungen, um die Installation vorzubereiten.",
    stUnsupported: "Die USB-Installation benötigt Chrome oder Edge auf einem Computer und eine HTTPS-Verbindung. Auf dem iPhone nicht verfügbar.",
    stTick: "Setze das Häkchen zur Bestätigung des Modells 4.3B.",
    stPreparing: "Installation wird vorbereitet…",
    connect: "Verbinden und installieren",
    stReady: "Abbild geprüft. Installer bereit. Klicke auf Verbinden und installieren.",
    stError: "Vorbereitung fehlgeschlagen: {msg}. Du kannst es erneut versuchen.",
  },
};
const LANGS = ["pl", "en", "de"];
export function pickLanguage(search, stored, browserLangs) {
  const q = new URLSearchParams(search || "").get("lang");
  if (LANGS.includes(q)) return q;
  if (LANGS.includes(stored)) return stored;
  for (const l of browserLangs || []) {
    const base = String(l).slice(0, 2).toLowerCase();
    if (LANGS.includes(base)) return base;
  }
  return "en";
}
let lang = "en";
function t(key, vars = {}) {
  const s = (STRINGS[lang] && STRINGS[lang][key]) || STRINGS.en[key] || key;
  return s.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ""));
}

function fail(message) {
  throw new Error(message);
}

function assertExact(actual, expected, label) {
  if (actual !== expected) {
    fail(`${label}: oczekiwano ${String(expected)}, otrzymano ${String(actual)}`);
  }
}

export function validateRelease(info, manifest) {
  if (!info || typeof info !== "object") {
    fail("build-info.json nie jest obiektem");
  }

  if (!manifest || typeof manifest !== "object") {
    fail("manifest.json nie jest obiektem");
  }

  assertExact(info.version, PINNED_INFO.version, "info.version");
  assertExact(info.display_version, PINNED_INFO.display_version, "info.display_version");
  assertExact(info.board_variant, PINNED_INFO.board_variant, "info.board_variant");
  assertExact(info.chip_family, PINNED_INFO.chip_family, "info.chip_family");
  assertExact(info.source_commit, PINNED_INFO.source_commit, "info.source_commit");
  assertExact(info.factory_file, PINNED_INFO.factory_file, "info.factory_file");
  assertExact(info.factory_bytes, PINNED_INFO.factory_bytes, "info.factory_bytes");
  assertExact(info.factory_sha256, PINNED_INFO.factory_sha256, "info.factory_sha256");
  assertExact(info.release_url, PINNED_INFO.release_url, "info.release_url");

  assertExact(manifest.name, EXPECTED_MANIFEST.name, "manifest.name");
  assertExact(manifest.version, EXPECTED_MANIFEST.version, "manifest.version");
  assertExact(manifest.new_install_prompt_erase, EXPECTED_MANIFEST.new_install_prompt_erase, "manifest.new_install_prompt_erase");
  assertExact(manifest.new_install_improv_wait_time, EXPECTED_MANIFEST.new_install_improv_wait_time, "manifest.new_install_improv_wait_time");

  if (!Array.isArray(manifest.builds) || manifest.builds.length !== 1) {
    fail("manifest.builds musi zawiera dokładnie 1 build");
  }

  const build = manifest.builds[0];
  if (!build || typeof build !== "object") {
    fail("manifest.builds[0] nie jest obiektem");
  }

  assertExact(build.chipFamily, PINNED_INFO.chip_family, "manifest.builds[0].chipFamily");

  if (!Array.isArray(build.parts) || build.parts.length !== 1) {
    fail("manifest.builds[0].parts musi zawiera dokładnie 1 part");
  }

  const part = build.parts[0];
  if (!part || typeof part !== "object") {
    fail("manifest.builds[0].parts[0] nie jest obiektem");
  }

  assertExact(part.path, PINNED_INFO.factory_file, "manifest.builds[0].parts[0].path");
  assertExact(part.offset, 0, "manifest.builds[0].parts[0].offset");

  return true;
}

function toBytes(buffer) {
  if (buffer instanceof ArrayBuffer) {
    return new Uint8Array(buffer);
  }

  if (buffer instanceof Uint8Array) {
    return buffer;
  }

  fail("verifyFactory wymaga ArrayBuffer lub Uint8Array");
}

function bytesToHex(bytes) {
  let out = "";
  for (const byte of bytes) {
    out += byte.toString(16).padStart(2, "0");
  }
  return out;
}

export async function verifyFactory(buffer, info) {
  if (!info || typeof info !== "object") {
    fail("verifyFactory wymaga info");
  }

  const bytes = toBytes(buffer);

  if (bytes.length !== info.factory_bytes) {
    fail(`verifyFactory: długość ${bytes.length}, oczekiwano ${info.factory_bytes}`);
  }

  if (bytes[0] !== 0xe9) {
    fail("verifyFactory: magic 0xe9 nie potwierdzony");
  }

  const chipId = bytes[12] | (bytes[13] << 8);

  if (chipId !== 9) {
    fail(`verifyFactory: chipID ${chipId}, oczekiwano 9`);
  }

  if (!globalThis.crypto || !globalThis.crypto.subtle) {
    fail("verifyFactory: crypto.subtle unavailable");
  }

  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  const sha = bytesToHex(new Uint8Array(digest));

  if (sha !== info.factory_sha256) {
    fail("verifyFactory: SHA-256 mismatch");
  }

  return true;
}

function initDOM() {
  const checkbox = document.getElementById("confirm-model");
  const prepareButton = document.getElementById("prepare-button");
  const status = document.getElementById("status");
  const installerContainer = document.getElementById("installer-container");

  if (!checkbox || !prepareButton || !status || !installerContainer) {
    return;
  }

  let operationCounter = 0;
  let blobUrls = [];

  let statusState = null;
  function setStatus(key, className = "", vars = {}) {
    statusState = { key, className, vars };
    status.textContent = t(key, vars);
    status.className = `status ${className}`.trim();
  }

  function applyLanguage(next) {
    lang = next;
    try { localStorage.setItem("ws43b_installer_lang", lang); } catch { /* ignore */ }
    document.documentElement.lang = lang;
    for (const el of document.querySelectorAll("[data-i18n]")) el.textContent = t(el.dataset.i18n);
    for (const el of document.querySelectorAll("[data-lang]")) el.setAttribute("aria-current", el.dataset.lang === lang ? "true" : "false");
    for (const el of installerContainer.querySelectorAll('button[slot="activate"]')) el.textContent = t("connect");
    if (statusState) setStatus(statusState.key, statusState.className, statusState.vars);
  }

  let stored = null;
  try { stored = localStorage.getItem("ws43b_installer_lang"); } catch { /* ignore */ }
  for (const el of document.querySelectorAll("[data-lang]")) {
    el.addEventListener("click", (event) => {
      event.preventDefault();
      applyLanguage(el.dataset.lang);
      const url = new URL(location.href); url.searchParams.set("lang", lang); history.replaceState(null, "", url);
    });
  }
  applyLanguage(pickLanguage(location.search, stored, navigator.languages || [navigator.language]));
  setStatus("stConfirm");

  function revokeBlobUrls() {
    for (const url of blobUrls) {
      try {
        URL.revokeObjectURL(url);
      } catch {
        // ignore
      }
    }
    blobUrls = [];
  }

  function removeInstaller() {
    installerContainer.textContent = "";
    revokeBlobUrls();
  }

  function supportsInstall() {
    return Boolean(
      globalThis.isSecureContext &&
      navigator &&
      navigator.serial &&
      globalThis.crypto &&
      globalThis.crypto.subtle
    );
  }

  async function fetchJson(url) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);

    try {
      const response = await fetch(url, {
        credentials: "omit",
        cache: "no-store",
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status} ${response.statusText}`);
      }

      return await response.json();
    } finally {
      clearTimeout(timeout);
    }
  }

  async function fetchBinary(url) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);

    try {
      const response = await fetch(url, {
        credentials: "omit",
        cache: "no-store",
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status} ${response.statusText}`);
      }

      return await response.arrayBuffer();
    } finally {
      clearTimeout(timeout);
    }
  }

  if (!supportsInstall()) {
    checkbox.disabled = true;
    setStatus("stUnsupported", "error");
  }

  checkbox.addEventListener("change", () => {
    prepareButton.disabled = !checkbox.checked || !supportsInstall();

    if (!checkbox.checked) {
      operationCounter += 1;
      removeInstaller();
      setStatus("stConfirm");
    }
  });

  prepareButton.addEventListener("click", async () => {
    if (!checkbox.checked) {
      setStatus("stTick", "error");
      return;
    }

    if (!supportsInstall()) {
      setStatus(
        "stUnsupported",
        "error"
      );
      return;
    }

    const operationId = operationCounter + 1;
    operationCounter = operationId;

    prepareButton.disabled = true;
    removeInstaller();
    setStatus("stPreparing");

    try {
      const info = await fetchJson("./build-info.json");
      if (operationCounter !== operationId || !checkbox.checked) {
        return;
      }

      const manifest = await fetchJson("./manifest.json");
      if (operationCounter !== operationId || !checkbox.checked) {
        return;
      }

      validateRelease(info, manifest);

      const factoryBuffer = await fetchBinary("./factory.bin");
      if (operationCounter !== operationId || !checkbox.checked) {
        return;
      }

      await verifyFactory(factoryBuffer, info);
      if (operationCounter !== operationId || !checkbox.checked) {
        return;
      }

      const factoryBlob = new Blob([factoryBuffer], { type: "application/octet-stream" });
      const factoryUrl = URL.createObjectURL(factoryBlob);
      blobUrls.push(factoryUrl);

      const generatedManifest = {
        name: EXPECTED_MANIFEST.name,
        version: EXPECTED_MANIFEST.version,
        new_install_prompt_erase: EXPECTED_MANIFEST.new_install_prompt_erase,
        new_install_improv_wait_time: EXPECTED_MANIFEST.new_install_improv_wait_time,
        builds: [
          {
            chipFamily: PINNED_INFO.chip_family,
            parts: [
              {
                path: factoryUrl,
                offset: 0,
              },
            ],
          },
        ],
      };

      const manifestBlob = new Blob([JSON.stringify(generatedManifest)], {
        type: "application/json",
      });
      const manifestUrl = URL.createObjectURL(manifestBlob);
      blobUrls.push(manifestUrl);

      await import("https://unpkg.com/esp-web-tools@10.4.0/dist/web/install-button.js?module");
      if (operationCounter !== operationId || !checkbox.checked) {
        return;
      }

      await customElements.whenDefined("esp-web-install-button");
      if (operationCounter !== operationId || !checkbox.checked) {
        return;
      }

      const button = document.createElement("esp-web-install-button");
      button.setAttribute("manifest", manifestUrl);

      const activateSlot = document.createElement("button");
      activateSlot.slot = "activate";
      activateSlot.type = "button";
      activateSlot.textContent = t("connect");
      button.appendChild(activateSlot);

      installerContainer.appendChild(button);
      setStatus("stReady", "ok");
    } catch (error) {
      if (operationCounter === operationId && checkbox.checked) {
        removeInstaller();
        setStatus("stError", "error", { msg: error.message });
      }
    } finally {
      if (operationCounter === operationId) {
        prepareButton.disabled = !checkbox.checked || !supportsInstall();
      }
    }
  });
}

if (typeof document !== "undefined") {
  initDOM();
}
