// BenchStock front-end helpers (no dependencies)
(function () {
  "use strict";

  // Confirm before destructive form posts:  <form data-confirm="...">
  document.addEventListener("submit", function (e) {
    var msg = e.target.getAttribute && e.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  // Image hover previews: load the picture only when first hovered
  document.addEventListener("mouseover", function (e) {
    var a = e.target.closest && e.target.closest("a.thumbnail");
    if (!a) return;
    var img = a.querySelector("img[data-src]");
    if (img) { img.src = img.getAttribute("data-src"); img.removeAttribute("data-src"); }
  });

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
