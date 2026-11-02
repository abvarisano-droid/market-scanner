/* Route changes for keyboard and screen reader users. The router (app.js) redraws #app on every hash change.
   #app used to be one big aria-live region, so each view was read out in full; instead, focus moves to the
   new view (a screen reader then reads its start) and the tab title names the view.
   Some views load their data after the route change (lookup, long-term, how it works) and can end in an error
   view. Redraws after focus has moved are spoken through #route-status: errors as an alert, a finished load politely. */
(function () {
  "use strict";
  var app = document.getElementById("app");
  if (!app) return;
  var base = document.title, focused = false, lastSaid = "";
  var live = document.getElementById("route-status");
  var ERROR = /unavailable|could not|hit a snag/i;
  function heading() {
    var h = app.querySelector("h1");
    return h ? (h.innerText || h.textContent).replace(/\s+/g, " ").trim() : "";
  }
  function title(t) { document.title = t && !/^Loading/.test(t) ? t + " | " + base : base; }
  function say(text, urgent) {
    if (!live || !text || text === lastSaid) return;
    lastSaid = text;
    live.setAttribute("role", urgent ? "alert" : "status");
    live.textContent = "";
    setTimeout(function () { live.textContent = text; }, 50);
  }
  function redrawn() {
    var t = heading();
    title(t);
    /* A redraw after focus moved to the view is a late load or a load error: say it, since focus will not move again. */
    if (focused && t && !/^Loading/.test(t)) {
      var lede = app.querySelector(".lede"), extra = lede ? (lede.innerText || lede.textContent).replace(/\s+/g, " ").trim() : "";
      var text = t + (extra ? " " + extra : "");
      say(text, ERROR.test(text));
    }
  }
  if (window.MutationObserver) new MutationObserver(redrawn).observe(app, { childList: true });
  /* The router draws the new view in the same hashchange event, so wait two frames before moving focus. */
  window.addEventListener("hashchange", function () {
    focused = false; lastSaid = "";
    if (live) live.textContent = ""; /* an old message must not linger into the next view */
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        app.setAttribute("tabindex", "-1");
        try { app.focus({ preventScroll: true }); } catch (e) { app.focus(); }
        focused = true;
      });
    });
  });
})();
