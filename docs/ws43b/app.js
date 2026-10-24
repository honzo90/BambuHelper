const PINNED_INFO = {
  version: "v4.0.0-beta.2",
  display_version: "v0.9",
  board_variant: "ws_lcd_43b",
  chip_family: "ESP32-S3",
  source_commit: "552375bb3e05f0f499a0add9aa9156d92679287c",
  factory_file: "factory.bin",
  factory_bytes: 2936816,
  factory_sha256: "6e49ca8a91e1ca43ec56016dd1fc6c59fed6a020a3aab9f0531891a76259174b",
  release_url: "https://github.com/honzo90/BambuHelper/releases/tag/v4.0.0-beta.2",
};

const EXPECTED_MANIFEST = {
  name: "BambuHelper WS43B",
  version: "v4.0.0-beta.2",
  new_install_prompt_erase: false,
  new_install_improv_wait_time: 0,
};

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

  function setStatus(message, className = "") {
    status.textContent = message;
    status.className = `status ${className}`.trim();
  }

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
    setStatus("Instalacja USB wymaga Chrome lub Edge na komputerze oraz połączenia HTTPS. Na iPhonie ta funkcja jest niedostępna.", "error");
  }

  checkbox.addEventListener("change", () => {
    prepareButton.disabled = !checkbox.checked || !supportsInstall();

    if (!checkbox.checked) {
      operationCounter += 1;
      removeInstaller();
      setStatus("Potwierdź model płytki i usunięcie ustawień, aby przygotować instalację.");
    }
  });

  prepareButton.addEventListener("click", async () => {
    if (!checkbox.checked) {
      setStatus("Zaznacz potwierdzenie modelu 4.3B.", "error");
      return;
    }

    if (!supportsInstall()) {
      setStatus(
        "Instalacja USB wymaga Chrome lub Edge na komputerze oraz połączenia HTTPS. Na iPhonie ta funkcja jest niedostępna.",
        "error"
      );
      return;
    }

    const operationId = operationCounter + 1;
    operationCounter = operationId;

    prepareButton.disabled = true;
    removeInstaller();
    setStatus("Przygotowanie instalacji…");

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
      activateSlot.textContent = "Połącz i zainstaluj";
      button.appendChild(activateSlot);

      installerContainer.appendChild(button);
      setStatus("Plik sprawdzony. Instalator przygotowany. Kliknij Połącz i zainstaluj.", "ok");
    } catch (error) {
      if (operationCounter === operationId && checkbox.checked) {
        removeInstaller();
        setStatus(`Błąd przygotowania: ${error.message}. Można ponowić ręcznie.`, "error");
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
