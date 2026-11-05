/* Score entry: swipe/Previous/Next between students, live totals, saving without leaving the page. */
(function () {
  const deck = document.getElementById("slides");
  if (!deck) return;
  const slides = Array.from(deck.querySelectorAll(".slide"));
  const counter = document.getElementById("counter");
  const jump = document.getElementById("jump");
  let current = 0;

  const whole = (x) => Math.floor(x + 0.5);                 // .5 rounds up, same rule as the server

  function liveTotals(slide) {
    slide.querySelectorAll("tr[data-csub]").forEach((row) => {
      const inputs = Array.from(row.querySelectorAll("input[data-max]:not([disabled])"));
      if (!inputs.length) return;
      let sum = 0, any = false, bad = false;
      inputs.forEach((i) => {
        const raw = i.value.trim().replace(",", ".");
        const v = parseFloat(raw), max = parseFloat(i.dataset.max);
        const invalid = raw !== "" && (isNaN(v) || v < 0 || v > max);
        i.classList.toggle("bad", invalid); bad = bad || invalid;
        if (raw !== "" && !invalid) { sum += (v / max) * parseFloat(i.dataset.weight); any = true; }
      });
      const cell = row.querySelector("[data-total]");
      const weightTotal = parseFloat(row.dataset.weightTotal) || 100;
      if (!bad) cell.textContent = any ? String(whole(sum * 100 / weightTotal)) : "";
      cell.classList.add("draft");
    });
  }

  function setStatus(slide, text, cls) {
    const s = slide.querySelector("[data-status]");
    s.textContent = text; s.className = "status " + (cls || "");
  }

  async function save(slide) {
    const form = slide;
    if (form.querySelector("input.bad")) { setStatus(slide, "Fix the red boxes first.", "err"); return false; }
    setStatus(slide, "Saving…");
    try {
      const res = await fetch(form.action, { method: "POST", body: new FormData(form),
        headers: { "X-Requested-With": "fetch" }, credentials: "same-origin" });
      const data = await res.json();
      if (!data.ok) { setStatus(slide, data.error || "Could not save.", "err"); return false; }
      Object.entries(data.rows).forEach(([csub, r]) => {
        const row = slide.querySelector(`tr[data-csub="${csub}"]`);
        if (!row) return;
        row.querySelector("[data-total]").textContent = r.total; row.querySelector("[data-total]").classList.remove("draft");
        row.querySelector("[data-grade]").textContent = r.grade; row.querySelector("[data-pos]").textContent = r.position;
      });
      slide.querySelector("[data-average]").textContent = data.average || "–";
      slide.querySelector("[data-position]").textContent = data.position || "–";
      slide.dataset.dirty = "";
      slide.querySelectorAll("input.dirty").forEach((i) => i.classList.remove("dirty"));
      setStatus(slide, data.changed ? "Saved ✓" : "Saved ✓ (no changes)", "ok");
      return true;
    } catch (e) { setStatus(slide, "No connection. Not saved.", "err"); return false; }
  }

  function show(i, smooth) {
    i = Math.max(0, Math.min(slides.length - 1, i));
    deck.style.scrollBehavior = smooth === false ? "auto" : "smooth";
    deck.scrollTo({ left: slides[i].offsetLeft - deck.offsetLeft, behavior: smooth === false ? "auto" : "smooth" });
    update(i);
  }
  function update(i) {
    if (i === current) return;
    const left = slides[current];
    current = i;
    if (left && left.dataset.dirty) save(left);               // moving away: save quietly in the background
    if (counter) counter.textContent = `Student ${i + 1} of ${slides.length}`;
    if (jump) jump.value = String(i);
  }

  slides.forEach((slide, idx) => {
    slide.addEventListener("input", (e) => {
      if (e.target.matches("input[data-max]")) { e.target.classList.add("dirty"); liveTotals(slide); }
      slide.dataset.dirty = "1"; setStatus(slide, "Unsaved changes");
    });
    slide.addEventListener("keydown", (e) => {                // Enter = next box, last box = Save & next
      if (e.key !== "Enter" || !e.target.matches("input[data-max]")) return;
      e.preventDefault();
      const boxes = Array.from(slide.querySelectorAll("input[data-max]:not([disabled])"));
      const k = boxes.indexOf(e.target);
      if (k < boxes.length - 1) { boxes[k + 1].focus(); boxes[k + 1].select(); }
      else { const adv = slide.querySelector("[data-advance]") || slide.querySelector("[data-save]"); adv.click(); }
    });
    slide.addEventListener("submit", async (e) => {
      e.preventDefault();
      const advance = e.submitter && e.submitter.hasAttribute("data-advance");
      const ok = await save(slide);
      if (ok && advance) show(idx + 1);
    });
    const prev = slide.querySelector("[data-prev]");
    if (prev) prev.addEventListener("click", () => show(idx - 1));
  });

  // keep `current` right when the user swipes / scrolls the deck by hand
  let t; deck.addEventListener("scroll", () => { clearTimeout(t); t = setTimeout(() => {
    const i = Math.round(deck.scrollLeft / Math.max(1, slides[0].getBoundingClientRect().width + 16)); update(Math.max(0, Math.min(slides.length - 1, i)));
  }, 80); });
  if (jump) jump.addEventListener("change", () => show(parseInt(jump.value, 10)));
  window.addEventListener("beforeunload", (e) => { if (slides.some((s) => s.dataset.dirty)) { e.preventDefault(); e.returnValue = ""; } });

  const start = parseInt(deck.dataset.start || "0", 10);
  if (start > 0) { current = -1; show(start, false); current = start; if (counter) counter.textContent = `Student ${start + 1} of ${slides.length}`; if (jump) jump.value = String(start); }
  slides.forEach(liveTotals);
  slides.forEach((s) => s.querySelectorAll("[data-total]").forEach((c) => c.classList.remove("draft")));
})();
