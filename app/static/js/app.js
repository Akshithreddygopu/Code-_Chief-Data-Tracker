/* CodeChef Class Performance Tracker — UI behaviours */
(function () {
  "use strict";

  var root = document.documentElement;
  var THEME_KEY = "cct-theme";

  /* ---------- Theme (light / dark) ---------- */

  function currentTheme() {
    return root.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function syncThemeUi() {
    var dark = currentTheme() === "dark";
    document.querySelectorAll("[data-theme-icon]").forEach(function (icon) {
      icon.className = dark ? "bi bi-sun-fill" : "bi bi-moon-stars-fill";
    });
    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      btn.setAttribute("aria-pressed", dark ? "true" : "false");
      btn.setAttribute("title", dark ? "Switch to light mode" : "Switch to dark mode");
    });
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", dark ? "#0a101c" : "#0b1220");
  }

  function themeColor(name, fallback) {
    var value = getComputedStyle(root).getPropertyValue(name).trim();
    return value || fallback;
  }

  function applyChartDefaults() {
    if (!window.Chart) return;
    Chart.defaults.color = themeColor("--chart-text", "#64748b");
    Chart.defaults.borderColor = themeColor("--border", "#e4e9f2");
    Chart.defaults.font.family =
      'Inter, "Segoe UI", system-ui, -apple-system, sans-serif';
    Chart.defaults.font.size = 12;
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.boxWidth = 8;
    Chart.defaults.plugins.legend.labels.padding = 14;
    Chart.defaults.elements.line.tension = 0.35;
    Chart.defaults.elements.point.radius = 2.5;
  }

  function applyTheme(theme, persist) {
    root.setAttribute("data-theme", theme === "dark" ? "dark" : "light");
    if (persist) {
      try { localStorage.setItem(THEME_KEY, theme); } catch (e) { /* ignore */ }
    }
    syncThemeUi();
    applyChartDefaults();
    window.dispatchEvent(new CustomEvent("themechange", {
      detail: { theme: theme }
    }));
  }

  document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      applyTheme(currentTheme() === "dark" ? "light" : "dark", true);
    });
  });

  /* Charts can ask for the live palette, e.g. grids and ticks. */
  window.cctChartTheme = function () {
    return {
      text: themeColor("--chart-text", "#64748b"),
      grid: themeColor("--grid-line", "#eef2f8"),
      border: themeColor("--border", "#e4e9f2"),
      primary: "#2563eb",
      cyan: "#06b6d4"
    };
  };

  /* Templates call this after Chart.js has loaded. */
  window.cctApplyChartDefaults = applyChartDefaults;

  syncThemeUi();
  applyChartDefaults();

  /* ---------- Sidebar (mobile off-canvas) ---------- */
  var sidebar = document.getElementById("sidebar");
  var backdrop = document.getElementById("sidebarBackdrop");

  function openSidebar() {
    if (!sidebar) return;
    sidebar.classList.add("open");
    if (backdrop) backdrop.classList.add("show");
    document.body.style.overflow = "hidden";
  }

  function closeSidebar() {
    if (!sidebar) return;
    sidebar.classList.remove("open");
    if (backdrop) backdrop.classList.remove("show");
    document.body.style.overflow = "";
  }

  document.querySelectorAll("[data-sidebar-toggle]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      sidebar && sidebar.classList.contains("open") ? closeSidebar() : openSidebar();
    });
  });
  if (backdrop) backdrop.addEventListener("click", closeSidebar);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeSidebar();
  });

  /* ---------- Flash messages: dismiss + auto-hide ---------- */
  document.querySelectorAll(".flash").forEach(function (el) {
    var close = el.querySelector(".flash-close");
    if (close) {
      close.addEventListener("click", function () {
        el.style.opacity = "0";
        setTimeout(function () { el.remove(); }, 160);
      });
    }
    setTimeout(function () {
      if (!el.isConnected) return;
      el.style.transition = "opacity .3s, transform .3s";
      el.style.opacity = "0";
      el.style.transform = "translateY(-4px)";
      setTimeout(function () { el.remove(); }, 320);
    }, 6000);
  });

  /* ---------- Confirm-before-submit ---------- */
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      var message = form.getAttribute("data-confirm") || "Are you sure?";
      if (!window.confirm(message)) {
        e.preventDefault();
      }
    });
  });

  /* ---------- Loading state for long-running forms (e.g. sync) ---------- */
  document.querySelectorAll("form[data-loading]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      // A cancelled confirmation must not leave the button spinning.
      if (e.defaultPrevented) return;
      var button = form.querySelector('button[type="submit"]');
      if (!button) return;
      button.dataset.originalHtml = button.innerHTML;
      button.disabled = true;
      button.innerHTML =
        '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Working…';
    });
  });

  window.addEventListener("pageshow", function () {
    document.querySelectorAll("form[data-loading] button[disabled]").forEach(function (btn) {
      btn.disabled = false;
      if (btn.dataset.originalHtml) btn.innerHTML = btn.dataset.originalHtml;
    });
  });

  /* ---------- Show selected filename in upload dropzones ---------- */
  document.querySelectorAll("[data-file-input]").forEach(function (input) {
    input.addEventListener("change", function () {
      var target = document.querySelector(input.getAttribute("data-file-input"));
      if (!target) return;
      target.textContent = input.files && input.files[0]
        ? input.files[0].name
        : "No file selected";
    });
  });
})();
