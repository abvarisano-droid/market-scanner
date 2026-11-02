/* Route changes for keyboard and screen reader users. The router (app.js) redraws #app on every hash change.
   #app used to be one big aria-live region, so each view was read out in full; instead, focus moves to the
   new view (a screen reader then reads its start) and the tab title names the view. */
(function () {
  "use strict";
  var app = document.getElementById("app");
  if (!app) return;
  var base = document.title;
  function title() {
    var h = app.querySelector("h1"), t = h ? (h.innerText || h.textContent).replace(/\s+/g, " ").trim() : "";
    document.title = t && !/^Loading/.test(t) ? t + " | " + base : base;
  }
  if (window.MutationObserver) new MutationObserver(title).observe(app, { childList: true });
  /* The router draws the new view in the same hashchange event, so wait two frames before moving focus. */
  window.addEventListener("hashchange", function () {
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        app.setAttribute("tabindex", "-1");
        try { app.focus({ preventScroll: true }); } catch (e) { app.focus(); }
      });
    });
  });
})();
