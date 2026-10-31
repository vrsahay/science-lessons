// Language button shown on the landing page and on every lesson.
(function () {
  var LANGS = [['as', 'অসমীয়া'], ['en', 'English'], ['hi', 'हिन्दी'], ['ja', '日本語']];
  var ALL_LESSONS = { as: 'সকলো পাঠ', en: 'All lessons', hi: 'सभी पाठ', ja: 'すべてのレッスン' };
  var LANGUAGE = { as: 'ভাষা', en: 'Language', hi: 'भाषा', ja: '言語' };
  var isLesson = !document.documentElement.hasAttribute('data-landing');
  var current = new URLSearchParams(location.search).get('language') || 'as';

  var style = document.createElement('style');
  style.textContent =
    '#lang-bar{position:fixed;left:50%;transform:translateX(-50%);top:calc(10px + env(safe-area-inset-top,0px));z-index:2147483000;display:flex;gap:6px;font:600 13px/1 "Noto Sans","Noto Sans Bengali","Noto Sans Devanagari","Noto Sans JP",system-ui,sans-serif}' +
    '#lang-bar a,#lang-bar button{display:inline-flex;align-items:center;gap:6px;height:34px;padding:0 12px;border:1px solid rgba(255,255,255,.28);border-radius:8px;background:#16202e;color:#fff;font:inherit;text-decoration:none;cursor:pointer;white-space:nowrap}' +
    '#lang-bar a:hover,#lang-bar button:hover{background:#26364b}' +
    '#lang-bar a:focus-visible,#lang-bar button:focus-visible{outline:2px solid #7cc4ff;outline-offset:2px}' +
    '#lang-menu{position:absolute;top:40px;right:0;min-width:130px;display:flex;flex-direction:column;gap:2px;padding:4px;border-radius:8px;background:#16202e;border:1px solid rgba(255,255,255,.28)}' +
    '#lang-menu[hidden]{display:none}' +
    '#lang-menu button{width:100%;border:0;background:transparent;justify-content:space-between}' +
    '#lang-menu button[aria-current="true"]{background:#2b6cb0}' +
    // Lessons keep pause and mute at the top right, so on phones the bar moves left and drops its extra words.
    '@media (max-width:640px){#lang-bar{left:calc(10px + env(safe-area-inset-left,0px));transform:none}#lang-menu{right:auto;left:0}.lang-extra{display:none}}';
  document.head.appendChild(style);

  var bar = document.createElement('div');
  bar.id = 'lang-bar';

  if (isLesson) {
    var back = document.createElement('a');
    back.href = '../?language=' + current;
    back.setAttribute('aria-label', ALL_LESSONS[current]);
    back.innerHTML = '←<span class="lang-extra"></span>';
    back.lastChild.textContent = ALL_LESSONS[current];
    bar.appendChild(back);
  }

  var wrap = document.createElement('div');
  wrap.style.position = 'relative';
  var btn = document.createElement('button');
  btn.type = 'button';
  btn.setAttribute('aria-haspopup', 'true');
  btn.setAttribute('aria-expanded', 'false');
  btn.setAttribute('aria-label', LANGUAGE[current]);
  var label = LANGS.filter(function (l) { return l[0] === current; })[0];
  btn.innerHTML = '<span class="lang-extra"></span><span></span>';
  btn.firstChild.textContent = LANGUAGE[current] + ':';
  btn.lastChild.textContent = (label ? label[1] : current) + ' ▾';

  var menu = document.createElement('div');
  menu.id = 'lang-menu';
  menu.hidden = true;
  LANGS.forEach(function (l) {
    var item = document.createElement('button');
    item.type = 'button';
    item.lang = l[0];
    item.textContent = l[1];
    if (l[0] === current) item.setAttribute('aria-current', 'true');
    item.addEventListener('click', function () {
      try { localStorage.setItem('siteLanguage', l[0]); } catch (e) {}
      var p = new URLSearchParams(location.search);
      p.set('language', l[0]);
      location.search = p.toString();
    });
    menu.appendChild(item);
  });

  function setOpen(open) {
    menu.hidden = !open;
    btn.setAttribute('aria-expanded', String(open));
  }
  btn.addEventListener('click', function (e) { e.stopPropagation(); setOpen(menu.hidden); });
  document.addEventListener('click', function () { setOpen(false); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') setOpen(false); });

  wrap.appendChild(btn);
  wrap.appendChild(menu);
  bar.appendChild(wrap);
  document.body.appendChild(bar);
})();
