// Private Bench Stock front-end helpers (no dependencies)
(function () {
  "use strict";

  // Confirm before destructive form posts:  <form data-confirm="...">
  document.addEventListener("submit", function (e) {
    var msg = e.target.getAttribute && e.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  // Hover popups (image preview, comment). They are position:fixed and placed here so they
  // stay inside the window: to the right of the icon (or left if no room), and shifted up
  // when the row is near the bottom. They never change the page size, so nothing jumps.
  var POPUP = "a.thumbnail, td.comment";
  var open = null;

  function place(anchor, pop) {
    var r = anchor.getBoundingClientRect(), m = 8;
    var w = pop.offsetWidth, h = pop.offsetHeight;
    var preferLeft = anchor.matches("td.comment");
    var left = preferLeft ? r.left - w - m : r.right + m;
    if (left + w > window.innerWidth - m) left = r.left - w - m;
    if (left < m) left = Math.min(r.right + m, window.innerWidth - w - m);
    var top = r.top - 10;
    if (top + h > window.innerHeight - m) top = window.innerHeight - h - m;
    pop.style.left = Math.max(m, left) + "px";
    pop.style.top = Math.max(m, top) + "px";
  }

  function close() {
    if (open) { open.pop.classList.remove("open"); open = null; }
  }

  document.addEventListener("mouseover", function (e) {
    var anchor = e.target.closest && e.target.closest(POPUP);
    if (!anchor) return;
    var pop = anchor.querySelector(".imgB, .commentText");
    if (!pop || (open && open.pop === pop)) return;
    close();
    var img = pop.querySelector("img[data-src]");       // load the picture only when first hovered
    if (img) {
      img.addEventListener("load", function () { if (open && open.pop === pop) place(anchor, pop); });
      img.src = img.getAttribute("data-src");
      img.removeAttribute("data-src");
    }
    pop.classList.add("open");
    open = { anchor: anchor, pop: pop };
    place(anchor, pop);
  });

  document.addEventListener("mouseout", function (e) {
    if (open && !open.anchor.contains(e.relatedTarget)) close();
  });
  window.addEventListener("scroll", close, true);
  window.addEventListener("resize", close);

  // Instant client-side filter for long tables:  <input class="tableFilter" data-table="id">
  document.querySelectorAll("input.tableFilter").forEach(function (input) {
    var table = document.getElementById(input.getAttribute("data-table"));
    if (!table) return;
    var rows = Array.prototype.slice.call(table.tBodies[0].rows);
    var text = rows.map(function (r) { return r.textContent.toLowerCase(); });
    input.addEventListener("input", function () {
      var words = input.value.toLowerCase().split(/\s+/).filter(Boolean);
      rows.forEach(function (r, i) {
        r.hidden = !words.every(function (w) { return text[i].indexOf(w) !== -1; });
      });
    });
  });

  // Autocomplete:  <input data-suggest="field">  -> /api/suggest/<field>?term=
  var n = 0;
  document.querySelectorAll("input[data-suggest]").forEach(function (input) {
    var list = document.createElement("datalist");
    list.id = "suggest-" + (++n);
    input.setAttribute("list", list.id);
    input.after(list);
    var timer, last = null;
    input.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(function () {
        var term = input.value.trim();
        if (term === last || term.length < 1) return;
        last = term;
        fetch("/api/suggest/" + input.getAttribute("data-suggest") + "?term=" + encodeURIComponent(term),
              { credentials: "same-origin" })
          .then(function (r) { return r.ok ? r.json() : []; })
          .then(function (items) {
            list.innerHTML = "";
            items.forEach(function (v) {
              var o = document.createElement("option");
              o.value = v;
              list.appendChild(o);
            });
          });
      }, 180);
    });
  });

  // Upload page: drag & drop and selected-file list
  var zone = document.getElementById("dropZone"), fileInput = document.getElementById("fileInput");
  if (zone && fileInput) {
    var show = function () {
      var names = Array.prototype.map.call(fileInput.files, function (f) { return f.name; });
      document.getElementById("fileList").textContent = names.length ? names.join(", ") : "";
    };
    fileInput.addEventListener("change", show);
    ["dragenter", "dragover"].forEach(function (t) {
      zone.addEventListener(t, function (e) { e.preventDefault(); zone.classList.add("over"); });
    });
    ["dragleave", "drop"].forEach(function (t) {
      zone.addEventListener(t, function (e) { e.preventDefault(); zone.classList.remove("over"); });
    });
    zone.addEventListener("drop", function (e) { fileInput.files = e.dataTransfer.files; show(); });
  }
})();
