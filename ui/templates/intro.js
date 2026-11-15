// Intro splash timeline. Shown once per browser session (sessionStorage); any key, click or tap leaves it.
(() => {
  const KEY = 'ri_intro_seen';
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const wait = setInterval(() => {
    const intro = document.getElementById('ri-intro');
    if (!intro) return;
    clearInterval(wait);
    if (intro.dataset.bound) return;
    intro.dataset.bound = '1';
    let seen = false;
    try { seen = sessionStorage.getItem(KEY) === '1'; } catch (e) { /* storage blocked: show the intro */ }
    if (seen) { intro.remove(); return; }

    const timers = [];
    const later = (ms, fn) => timers.push(setTimeout(fn, ms));
    const leave = () => {
      timers.forEach(clearTimeout);
      try { sessionStorage.setItem(KEY, '1'); } catch (e) { /* ignore */ }
      document.removeEventListener('keydown', leave, true);
      intro.classList.add('leave');
      setTimeout(() => intro.remove(), 480);
    };
    document.addEventListener('keydown', leave, true);
    intro.addEventListener('click', leave);
    intro.addEventListener('touchend', leave, {passive: true});

    if (reduced) { intro.classList.add('still', 'ready'); return; }
    const lamps = [...intro.querySelectorAll('.ri-lights i')];
    const STEP = 600, FIRST = 400, out = FIRST + lamps.length * STEP + 250;
    lamps.forEach((lamp, i) => later(FIRST + i * STEP, () => lamp.classList.add('on')));  // one by one, 0.6 s apart
    later(out, () => lamps.forEach(lamp => lamp.classList.remove('on')));                  // lights out
    later(out + 120, () => intro.classList.add('go'));                                     // stripe, then the logo
    later(out + 1400, () => intro.classList.add('ready'));                                 // "Press any key" at about 5 s
  }, 40);
  setTimeout(() => clearInterval(wait), 10000);
})();
