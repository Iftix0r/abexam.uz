(function () {
  'use strict';
  var bar;
  var value = 0;
  var timer;
  var pending = 0;

  function ensure() {
    if (bar) return bar;
    bar = document.createElement('div');
    bar.id = 'ab-top-loader';
    bar.setAttribute('role', 'progressbar');
    bar.setAttribute('aria-label', 'Sahifa yuklanmoqda');
    bar.innerHTML = '<span></span>';
    document.documentElement.appendChild(bar);
    return bar;
  }

  function paint() {
    ensure().style.transform = 'scaleX(' + (value / 100) + ')';
  }

  function start() {
    pending += 1;
    if (pending > 1) return;
    clearTimeout(timer);
    value = 7;
    ensure().classList.add('is-loading');
    paint();
    timer = setInterval(function () {
      if (value < 84) {
        value += Math.max(0.6, (84 - value) * 0.075);
        paint();
      }
    }, 180);
  }

  function done(force) {
    pending = force ? 0 : Math.max(0, pending - 1);
    if (pending) return;
    clearInterval(timer);
    value = 100;
    paint();
    setTimeout(function () {
      if (!bar) return;
      bar.classList.remove('is-loading');
      setTimeout(function () { value = 0; paint(); }, 220);
    }, 120);
  }

  window.AbTopLoader = { start: start, done: done };
  start();
  window.addEventListener('load', function () { done(true); });
  window.addEventListener('pageshow', function () { done(true); });
  window.addEventListener('beforeunload', start);

  document.addEventListener('click', function (event) {
    var link = event.target.closest && event.target.closest('a[href]');
    if (!link || event.defaultPrevented || event.button > 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    var url;
    try { url = new URL(link.href, location.href); } catch (_) { return; }
    if (url.origin !== location.origin || link.target === '_blank' || link.hasAttribute('download') || url.hash && url.pathname === location.pathname && url.search === location.search) return;
    start();
  }, true);

  document.addEventListener('submit', function () { start(); }, true);

  if (window.fetch) {
    var nativeFetch = window.fetch;
    window.fetch = function () {
      start();
      return nativeFetch.apply(this, arguments).finally(function () { done(false); });
    };
  }
})();
