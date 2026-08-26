document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.querySelector("[data-menu-toggle]");
  const sidebar = document.getElementById("sidebar");
  if (toggle && sidebar) {
    toggle.addEventListener("click", () => sidebar.classList.toggle("open"));
  }

  document.querySelectorAll("input[type=file]").forEach((input) => {
    input.addEventListener("change", () => {
      const label = input.closest("p")?.querySelector("label");
      if (label && input.files?.length) label.dataset.filename = input.files[0].name;
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
