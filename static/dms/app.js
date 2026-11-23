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
  window.addEventListener("focus", hideLoader);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") hideLoader();
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
      const inlineConfirmation = event.submitter?.dataset.confirmInline;
      if (inlineConfirmation && !window.confirm(inlineConfirmation)) {
        event.preventDefault();
        return;
      }
      if (event.submitter?.hasAttribute("data-clear-drive-link")) {
        const driveInput = form.querySelector('input[name="drive_folder_url"]');
        if (driveInput) driveInput.value = "";
      }
      const uploadInput = form.matches("[data-upload-form]")
        ? form.querySelector("input[type=file]")
        : null;
      if (uploadInput) {
        const fileCount = uploadInput.files?.length || 0;
        const totalBytes = [...(uploadInput.files || [])]
          .reduce((total, file) => total + file.size, 0);
        const totalMB = (totalBytes / (1024 * 1024)).toFixed(1);
        const submitter = event.submitter;
        const intent = submitter?.dataset.uploadIntent || "draft";
        const intentLabel = {
          draft: "Menyimpan draft",
          review: "Mengunggah untuk review",
          signed: "Mengunggah dokumen signed",
        }[intent];
        window.setTimeout(() => {
          form.querySelectorAll("[data-upload-button]").forEach((button) => {
            button.disabled = true;
          });
          if (submitter) submitter.textContent = "Sedang mengunggah...";
        }, 0);
        showLoader(
          intentLabel,
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
      if (link.target === "_blank" || link.hasAttribute("download") || link.hasAttribute("data-file-download") || link.hasAttribute("data-external-navigation") || link.classList.contains("disabled")) return;
      const destination = new URL(link.href, window.location.href);
      if (destination.origin !== window.location.origin || destination.hash || destination.pathname.includes("/download") || destination.pathname.includes("/preview")) return;
      showLoader("Membuka halaman", "Menyiapkan data terbaru...");
    });
  });

  document.querySelectorAll("[data-copy-link]").forEach((button) => {
    button.addEventListener("click", async () => {
      const original = button.textContent;
      try {
        await navigator.clipboard.writeText(button.dataset.copyLink);
        button.textContent = "✓ Link tersalin";
      } catch (_) {
        const helper = document.createElement("textarea");
        helper.value = button.dataset.copyLink;
        helper.style.position = "fixed";
        helper.style.opacity = "0";
        document.body.appendChild(helper);
        helper.select();
        document.execCommand("copy");
        helper.remove();
        button.textContent = "✓ Link tersalin";
      }
      window.setTimeout(() => { button.textContent = original; }, 1800);
    });
  });

  const photoLibrary = document.querySelector("[data-photo-library]");
  if (photoLibrary) {
    const search = photoLibrary.querySelector("[data-photo-search]");
    const region = photoLibrary.querySelector("[data-photo-region]");
    const status = photoLibrary.querySelector("[data-photo-status]");
    const items = [...photoLibrary.querySelectorAll("[data-photo-site]")];
    const details = [...photoLibrary.querySelectorAll("[data-photo-detail]")];
    const empty = photoLibrary.querySelector("[data-photo-empty]");
    const normalize = (value) => String(value || "").normalize("NFKD").toLowerCase().trim();
    const activateSite = (siteId, updateUrl = true) => {
      items.forEach((item) => {
        const active = item.dataset.photoSite === String(siteId);
        item.classList.toggle("active", active);
        item.setAttribute("aria-selected", String(active));
      });
      details.forEach((detail) => {
        detail.hidden = detail.dataset.photoDetail !== String(siteId);
      });
      if (updateUrl && siteId) {
        const url = new URL(window.location.href);
        url.searchParams.set("site", siteId);
        window.history.replaceState({}, "", url);
      }
    };
    const applyPhotoFilters = () => {
      const query = normalize(search?.value);
      const selectedRegion = normalize(region?.value);
      const selectedStatus = normalize(status?.value);
      const visibleItems = items.filter((item) => {
        const matches = (!query || normalize(item.dataset.search).includes(query))
          && (!selectedRegion || normalize(item.dataset.region) === selectedRegion)
          && (!selectedStatus || normalize(item.dataset.status) === selectedStatus);
        item.hidden = !matches;
        return matches;
      });
      if (empty) empty.hidden = visibleItems.length !== 0;
      const activeVisible = visibleItems.some((item) => item.classList.contains("active"));
      if (!activeVisible && visibleItems[0]) activateSite(visibleItems[0].dataset.photoSite);
      if (!visibleItems.length) details.forEach((detail) => { detail.hidden = true; });
    };
    items.forEach((item) => {
      item.addEventListener("click", () => activateSite(item.dataset.photoSite));
    });
    search?.addEventListener("input", applyPhotoFilters);
    search?.addEventListener("search", applyPhotoFilters);
    region?.addEventListener("change", applyPhotoFilters);
    status?.addEventListener("change", applyPhotoFilters);
    activateSite(photoLibrary.dataset.selectedSite, false);
    applyPhotoFilters();
  }

  const siteRegister = document.querySelector("[data-site-register]");
  if (siteRegister) {
    const search = siteRegister.querySelector("[data-site-search]");
    const region = siteRegister.querySelector("[data-site-region]");
    const status = siteRegister.querySelector("[data-site-status]");
    const reset = siteRegister.querySelector("[data-site-reset]");
    const rows = [...siteRegister.querySelectorAll("[data-site-row]")];
    const count = siteRegister.querySelector("[data-site-count]");
    const empty = siteRegister.querySelector("[data-site-empty]");
    const normalize = (value) => String(value || "").normalize("NFKD").toLowerCase().trim();
    const showRow = (row, visible) => {
      row.hidden = !visible;
      row.classList.toggle("is-filtered-out", !visible);
    };
    const applyFilters = () => {
      const query = normalize(search?.value);
      const selectedRegion = normalize(region?.value);
      const selectedStatus = normalize(status?.value);
      let visible = 0;
      rows.forEach((row) => {
        const matches = (!query || normalize(row.dataset.search).includes(query))
          && (!selectedRegion || normalize(row.dataset.region) === selectedRegion)
          && (!selectedStatus || normalize(row.dataset.status) === selectedStatus);
        showRow(row, matches);
        if (matches) visible += 1;
      });
      if (count) count.textContent = visible;
      if (empty) empty.hidden = visible !== 0;
    };
    search?.addEventListener("input", applyFilters);
    search?.addEventListener("search", applyFilters);
    region?.addEventListener("change", applyFilters);
    status?.addEventListener("change", applyFilters);
    reset?.addEventListener("click", () => {
      if (search) search.value = "";
      if (region) region.value = "";
      if (status) status.value = "";
      applyFilters();
      search?.focus();
    });
    applyFilters();
  }

  const controlRegister = document.querySelector("[data-control-register]");
  if (controlRegister) {
    const search = controlRegister.querySelector("[data-control-search]");
    const type = controlRegister.querySelector("[data-control-type]");
    const status = controlRegister.querySelector("[data-control-status]");
    const pic = controlRegister.querySelector("[data-control-pic]");
    const reset = controlRegister.querySelector("[data-control-reset]");
    const quickButtons = [...controlRegister.querySelectorAll("[data-control-quick]")];
    const rows = [...controlRegister.querySelectorAll("[data-control-row]")];
    const count = controlRegister.querySelector("[data-control-count]");
    const empty = controlRegister.querySelector("[data-control-empty]");
    const normalize = (value) => String(value || "").normalize("NFKD").toLowerCase().trim();
    const applyFilters = () => {
      const query = normalize(search?.value);
      const selectedType = normalize(type?.value);
      const selectedStatus = normalize(status?.value);
      const selectedPic = normalize(pic?.value);
      let visible = 0;
      rows.forEach((row) => {
        const rowStatus = selectedType
          ? normalize(row.dataset[selectedType])
          : normalize(row.dataset.overall);
        const matches = (!query || normalize(row.dataset.search).includes(query))
          && (!selectedStatus || rowStatus === selectedStatus)
          && (!selectedPic || normalize(row.dataset.pic) === selectedPic);
        row.hidden = !matches;
        row.classList.toggle("is-filtered-out", !matches);
        if (matches) visible += 1;
      });
      if (count) count.textContent = visible;
      if (empty) empty.hidden = visible !== 0;
      quickButtons.forEach((button) => {
        button.classList.toggle("active", normalize(button.dataset.controlQuick) === selectedStatus);
      });
    };
    search?.addEventListener("input", applyFilters);
    search?.addEventListener("search", applyFilters);
    type?.addEventListener("change", applyFilters);
    status?.addEventListener("change", applyFilters);
    pic?.addEventListener("change", applyFilters);
    quickButtons.forEach((button) => {
      button.addEventListener("click", () => {
        if (status) {
          status.value = status.value === button.dataset.controlQuick
            ? ""
            : button.dataset.controlQuick;
        }
        applyFilters();
      });
    });
    reset?.addEventListener("click", () => {
      if (search) search.value = "";
      if (type) type.value = "";
      if (status) status.value = "";
      if (pic) pic.value = "";
      applyFilters();
      search?.focus();
    });
    applyFilters();
  }

  const equipmentList = document.querySelector("[data-equipment-list]");
  const equipmentTemplate = document.getElementById("fatp-equipment-template");
  const renumberEquipment = () => {
    equipmentList?.querySelectorAll("[data-equipment-row]").forEach((row, index) => {
      const number = row.querySelector(".fatp-drag-handle, .fatp-row-number");
      if (number) number.textContent = String(index + 1).padStart(2, "0");
    });
  };
  document.querySelector("[data-add-equipment]")?.addEventListener("click", () => {
    if (!equipmentList || !equipmentTemplate) return;
    const row = equipmentTemplate.content.firstElementChild.cloneNode(true);
    equipmentList.appendChild(row);
    renumberEquipment();
    row.querySelector('input[name="equipment_name"]')?.focus();
  });
  equipmentList?.addEventListener("click", (event) => {
    const remove = event.target.closest("[data-remove-equipment]");
    if (!remove) return;
    const rows = equipmentList.querySelectorAll("[data-equipment-row]");
    const row = remove.closest("[data-equipment-row]");
    if (rows.length === 1) {
      row.querySelectorAll("input").forEach((input) => {
        input.value = input.type === "number" ? "1" : "";
      });
      row.querySelector('input[name="equipment_name"]')?.focus();
    } else {
      row.remove();
    }
    renumberEquipment();
  });
  renumberEquipment();

  document.querySelectorAll("[data-fatp-photo-upload]").forEach((form) => {
    const input = form.querySelector('input[type="file"]');
    const previews = form.querySelector("[data-fatp-pending-previews]");
    input?.addEventListener("change", () => {
      if (!previews) return;
      previews.replaceChildren();
      [...(input.files || [])].forEach((file) => {
        const chip = document.createElement("span");
        chip.textContent = file.name;
        previews.appendChild(chip);
      });
      previews.hidden = !input.files?.length;
      const headline = input.closest("label")?.querySelector("b");
      if (headline && input.files?.length) {
        headline.textContent = `${input.files.length} foto siap di-upload`;
      }
    });
  });
});
