document.addEventListener("DOMContentLoaded", () => {
  const themeButtons = [...document.querySelectorAll("[data-theme-toggle]")];
  const currentTheme = () => document.documentElement.dataset.theme || "light";
  const updateThemeButtons = () => {
    const dark = currentTheme() === "dark";
    themeButtons.forEach((button) => {
      const label = dark ? "Mode terang" : "Mode gelap";
      const labelNode = button.querySelector("[data-theme-label]");
      const iconNode = button.querySelector("[data-theme-icon]");
      if (labelNode) labelNode.textContent = label;
      if (iconNode) iconNode.textContent = dark ? "☀" : "☾";
      button.setAttribute("aria-label", `Aktifkan ${label.toLowerCase()}`);
      button.title = `Aktifkan ${label.toLowerCase()}`;
      button.setAttribute("aria-pressed", String(dark));
    });
  };
  themeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const next = currentTheme() === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem("triplee-theme", next); } catch (_) { /* no-op */ }
      updateThemeButtons();
    });
  });
  updateThemeButtons();

  const makeLogoBackgroundTransparent = (image) => {
    if (!image.naturalWidth || image.dataset.logoProcessed === "true") return;
    image.dataset.logoProcessed = "true";
    const maxDimension = 1024;
    const scale = Math.min(1, maxDimension / Math.max(image.naturalWidth, image.naturalHeight));
    const width = Math.max(1, Math.round(image.naturalWidth * scale));
    const height = Math.max(1, Math.round(image.naturalHeight * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) return;
    context.drawImage(image, 0, 0, width, height);
    let pixels;
    try { pixels = context.getImageData(0, 0, width, height); } catch (_) { return; }
    const data = pixels.data;
    const size = width * height;
    const visited = new Uint8Array(size);
    const queue = new Int32Array(size);
    let head = 0;
    let tail = 0;
    let changed = false;
    const enqueue = (index) => {
      if (index < 0 || index >= size || visited[index]) return;
      visited[index] = 1;
      queue[tail++] = index;
    };
    for (let x = 0; x < width; x += 1) {
      enqueue(x);
      enqueue((height - 1) * width + x);
    }
    for (let y = 1; y < height - 1; y += 1) {
      enqueue(y * width);
      enqueue(y * width + width - 1);
    }
    while (head < tail) {
      const index = queue[head++];
      const offset = index * 4;
      const red = data[offset];
      const green = data[offset + 1];
      const blue = data[offset + 2];
      const alpha = data[offset + 3];
      const minimum = Math.min(red, green, blue);
      const maximum = Math.max(red, green, blue);
      const isOuterBackground = alpha === 0 || (minimum >= 218 && maximum - minimum <= 28);
      if (!isOuterBackground) continue;
      if (alpha !== 0) {
        data[offset + 3] = 0;
        changed = true;
      }
      const x = index % width;
      if (x > 0) enqueue(index - 1);
      if (x < width - 1) enqueue(index + 1);
      if (index >= width) enqueue(index - width);
      if (index < size - width) enqueue(index + width);
    }
    if (!changed) return;
    context.putImageData(pixels, 0, 0);
    image.src = canvas.toDataURL("image/png");
  };
  document.querySelectorAll("img[data-transparent-logo]").forEach((image) => {
    if (image.complete) makeLogoBackgroundTransparent(image);
    else image.addEventListener("load", () => makeLogoBackgroundTransparent(image), { once: true });
  });

  const pageLoader = document.querySelector("[data-page-loader]");
  const loaderTitle = pageLoader?.querySelector("[data-loader-title]");
  const loaderDetail = pageLoader?.querySelector("[data-loader-detail]");
  const showLoader = (title = "Memuat Triple E DMS", detail = "Menyiapkan halaman...") => {
    if (!pageLoader) return;
    loaderTitle.textContent = title;
    loaderDetail.textContent = detail;
    pageLoader.classList.add("is-active");
  };
  const hideLoader = () => pageLoader?.classList.remove("is-active");

  window.setTimeout(hideLoader, 220);
  window.addEventListener("pageshow", () => window.setTimeout(hideLoader, 120));
  window.addEventListener("beforeunload", () => {
    if (!pageLoader?.classList.contains("is-active")) {
      showLoader("Memuat halaman", "Mohon tunggu sebentar...");
    }
  });

  const toggle = document.querySelector("[data-menu-toggle]");
  const sidebar = document.getElementById("sidebar");
  if (toggle && sidebar) {
    toggle.addEventListener("click", () => sidebar.classList.toggle("open"));
  }

  document.querySelectorAll("input[type=file]").forEach((input) => {
    input.addEventListener("change", () => {
      const label = input.closest("p")?.querySelector("label");
      if (label && input.files?.length) {
        label.dataset.filename = input.files.length > 1
          ? `${input.files.length} file dipilih`
          : input.files[0].name;
      }
    });
  });

  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) {
        event.preventDefault();
        return;
      }
      const uploadInput = form.matches("[data-upload-form]")
        ? form.querySelector("input[type=file]")
        : null;
      if (uploadInput) {
        const fileCount = uploadInput.files?.length || 0;
        const totalBytes = [...(uploadInput.files || [])]
          .reduce((total, file) => total + file.size, 0);
        const totalMB = (totalBytes / (1024 * 1024)).toFixed(1);
        const button = form.querySelector("[data-upload-button]");
        if (button) {
          button.disabled = true;
          button.textContent = "Sedang mengunggah...";
        }
        showLoader(
          "Mengunggah dokumen",
          `${fileCount} file · ${totalMB} MB — jangan tutup halaman`,
        );
      } else {
        showLoader("Menyimpan perubahan", "Mohon tunggu sebentar...");
      }
    });
  });

  document.querySelectorAll("a[href]").forEach((link) => {
    link.addEventListener("click", (event) => {
      if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      if (link.target === "_blank" || link.hasAttribute("download") || link.hasAttribute("data-file-download") || link.classList.contains("disabled")) return;
      const destination = new URL(link.href, window.location.href);
      if (destination.origin !== window.location.origin || destination.hash || destination.pathname.includes("/download")) return;
      showLoader("Membuka halaman", "Menyiapkan data terbaru...");
    });
  });

  const siteRegister = document.querySelector("[data-site-register]");
  if (siteRegister) {
    const search = siteRegister.querySelector("[data-site-search]");
    const region = siteRegister.querySelector("[data-site-region]");
    const status = siteRegister.querySelector("[data-site-status]");
    const rows = [...siteRegister.querySelectorAll("[data-site-row]")];
    const count = siteRegister.querySelector("[data-site-count]");
    const empty = siteRegister.querySelector("[data-site-empty]");
    const applyFilters = () => {
      const query = search.value.trim().toLowerCase();
      let visible = 0;
      rows.forEach((row) => {
        const matches = (!query || row.dataset.search.includes(query))
          && (!region.value || row.dataset.region === region.value)
          && (!status.value || row.dataset.status === status.value);
        row.hidden = !matches;
        if (matches) visible += 1;
      });
      count.textContent = visible;
      empty.hidden = visible !== 0;
    };
    search.addEventListener("input", applyFilters);
    region.addEventListener("change", applyFilters);
    status.addEventListener("change", applyFilters);
  }
});
