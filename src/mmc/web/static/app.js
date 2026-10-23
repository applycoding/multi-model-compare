(function () {
  const form = document.getElementById("compare-form");
  if (!form) return;
  const vendorList = document.getElementById("vendor-list");
  const submitBtn = document.getElementById("submit-btn");

  function updateVendors() {
    const vendors = new Set();
    form.querySelectorAll('input[name="models"]:checked').forEach((el) => {
      vendors.add(el.dataset.vendor);
    });
    const judge = document.getElementById("judge-select");
    if (judge && judge.value && judge.value !== "none") {
      const row = [...form.querySelectorAll('input[name="models"]')].find(
        (i) => i.value === judge.value,
      );
      if (row) vendors.add(row.dataset.vendor);
    }
    vendorList.textContent = [...vendors].sort().join(", ");
  }

  form.addEventListener("change", updateVendors);
  updateVendors();

  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    submitBtn.disabled = true;
    const el = document.createElement("p");
    el.id = "elapsed";
    el.textContent = "Running… 0s";
    form.appendChild(el);
    const start = Date.now();
    const timer = setInterval(() => {
      const s = Math.floor((Date.now() - start) / 1000);
      el.textContent = "Running… " + s + "s";
    }, 1000);
    const fd = new FormData(form);
    const token = String(fd.get("csrf_token") || "");
    fetch(form.action, {
      method: "POST",
      headers: { "X-CSRF-Token": token },
      body: fd,
      redirect: "follow",
    })
      .then((resp) => {
        clearInterval(timer);
        window.location.href = resp.url;
      })
      .catch(() => {
        clearInterval(timer);
        submitBtn.disabled = false;
      });
  });

  document.querySelectorAll("[data-copy]").forEach((btn) => {
    btn.addEventListener("click", () => {
      navigator.clipboard.writeText(btn.dataset.copy || "");
    });
  });
})();
