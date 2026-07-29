/* Ponteggio della demo. NON fa parte del prodotto: in React questa logica
   vive nei componenti. Serve solo perché i file HTML si possano usare a mano. */
(function () {
  var root = document.documentElement;
  var t = document.getElementById('theme');
  if (t) t.addEventListener('click', function () {
    var dark = root.getAttribute('data-theme') === 'dark';
    root.setAttribute('data-theme', dark ? 'light' : 'dark');
    t.textContent = dark ? 'Tema scuro' : 'Tema chiaro';
  });

  document.querySelectorAll('.tab').forEach(function (tab) {
    tab.addEventListener('click', function () {
      document.querySelectorAll('.tab').forEach(function (x) { x.classList.toggle('is-active', x === tab); });
      document.querySelectorAll('.tabpanel').forEach(function (p) {
        p.hidden = p.dataset.panel !== tab.dataset.tab;
      });
    });
  });

  function settle(card, ok) {
    card.classList.remove('is-flagged');
    card.classList.toggle('is-confirmed', ok);
    card.classList.toggle('is-discarded', !ok);
    var foot = card.querySelector('.task__actions');
    if (!foot) return;
    var s = document.createElement('span');
    s.className = 'task__settled' + (ok ? ' is-ok' : '');
    s.innerHTML = (ok ? 'confermata' : 'scartata') + ' <button class="btn--link">annulla</button>';
    foot.replaceWith(s);
  }
  document.querySelectorAll('.task').forEach(function (card) {
    var b = card.querySelectorAll('.task__actions .btn');
    if (b[0]) b[0].addEventListener('click', function (e) { e.stopPropagation(); settle(card, true); });
    if (b[2]) b[2].addEventListener('click', function (e) { e.stopPropagation(); settle(card, false); });
  });

  /* Ritmo da tastiera: C conferma, X scarta, J/K scorrono, Invio apre le prove. */
  var i = -1;
  var cards = Array.prototype.slice.call(document.querySelectorAll('.task'));
  document.addEventListener('keydown', function (e) {
    if (!cards.length || /INPUT|TEXTAREA/.test(e.target.tagName)) return;
    var k = e.key.toLowerCase();
    if (k === 'j') i = Math.min(cards.length - 1, i + 1);
    else if (k === 'k') i = Math.max(0, i - 1);
    else if (k === 'c' && cards[i]) settle(cards[i], true);
    else if (k === 'x' && cards[i]) settle(cards[i], false);
    else return;
    e.preventDefault();
    cards.forEach(function (c, n) { c.classList.toggle('is-selected', n === i); });
  });

  document.querySelectorAll('.navitem').forEach(function (n) {
    n.addEventListener('click', function () {
      document.querySelectorAll('.navitem').forEach(function (x) { x.classList.toggle('is-active', x === n); });
      document.querySelectorAll('[data-secpanel]').forEach(function (p) { p.hidden = p.dataset.secpanel !== n.dataset.sec; });
    });
  });

  /* Il consenso non si salta: senza spunta il pulsante resta spento. */
  document.querySelectorAll('[data-consent]').forEach(function (c) {
    c.addEventListener('click', function () {
      var on = c.classList.toggle('is-on');
      var go = c.closest('.modal').querySelector('[data-go]');
      if (go) go.disabled = !on;
    });
  });

  document.querySelectorAll('.segment').forEach(function (s) {
    s.addEventListener('click', function (e) {
      if (e.target.tagName !== 'BUTTON') return;
      s.querySelectorAll('button').forEach(function (b) { b.classList.toggle('is-on', b === e.target); });
    });
  });
  document.querySelectorAll('.switch').forEach(function (s) {
    s.addEventListener('click', function () { s.classList.toggle('is-on'); });
  });
})();
