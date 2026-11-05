if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {}));
}
// Ask before destructive actions: <form data-confirm="Are you sure?">
document.addEventListener("submit", (e) => {
  const msg = e.target.dataset && e.target.dataset.confirm;
  if (msg && !window.confirm(msg)) e.preventDefault();
});
// Mobile sidebar toggle
const menu = document.getElementById("menu"), side = document.getElementById("side");
if (menu && side) menu.addEventListener("click", () => side.classList.toggle("open"));
// Live filter: <input data-filter="#list"> hides children of #list that don't match
document.querySelectorAll("input[data-filter]").forEach((box) => {
  box.addEventListener("input", () => {
    const q = box.value.trim().toLowerCase();
    document.querySelectorAll(box.dataset.filter + " > *").forEach((el) => {
      el.style.display = el.textContent.toLowerCase().includes(q) ? "" : "none";
    });
  });
});
// "Select all" checkbox: <input type="checkbox" data-all="name">
document.querySelectorAll("input[data-all]").forEach((box) => {
  box.addEventListener("change", () => {
    document.querySelectorAll(`input[name="${box.dataset.all}"]`).forEach((c) => {
      if (c.closest("label").style.display !== "none") c.checked = box.checked;
    });
  });
});
