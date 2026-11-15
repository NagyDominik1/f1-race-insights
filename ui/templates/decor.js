// Abstract hero backdrops, drawn on one canvas from the selected session's data (shaped in Python).
//   circuit: the circuit outline, very large and faint, with one red light point travelling
//            along it and leaving a fading trail, like a long exposure
//   flow:    a few drivers' smoothed lap-time series as large, slowly drifting lines, with
//            one soft red glow following the quickest
// Decoration only: no pointer events, nothing drawn while the tab is hidden, a single still
// frame when reduced motion is requested, and the loop stops when the page is left.
(() => {
  const DATA = __DATA__;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

  function fit(canvas) {
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5), box = canvas.getBoundingClientRect();
    if (canvas.width !== Math.round(box.width * dpr) || canvas.height !== Math.round(box.height * dpr)) {
      canvas.width = Math.round(box.width * dpr); canvas.height = Math.round(box.height * dpr);
    }
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, box.width, box.height);
    return [ctx, box.width, box.height];
  }
  function glow(ctx, x, y, radius) {
    const halo = ctx.createRadialGradient(x, y, 0, x, y, radius);
    halo.addColorStop(0, 'rgba(255, 70, 50, .55)'); halo.addColorStop(0.35, 'rgba(225, 6, 0, .2)'); halo.addColorStop(1, 'rgba(225, 6, 0, 0)');
    ctx.fillStyle = halo; ctx.beginPath(); ctx.arc(x, y, radius, 0, 7); ctx.fill();
    ctx.fillStyle = 'rgba(255, 225, 215, .95)'; ctx.beginPath(); ctx.arc(x, y, 1.8, 0, 7); ctx.fill();
  }

  // ---------- circuit ----------
  function circuit(canvas, t) {
    const [ctx, w, h] = fit(canvas);
    const T = DATA.track, n = T.x.length;
    const size = Math.max(w * 0.66, h * 1.12), cx = w * 0.66, cy = h * 0.42, turn = -0.2;
    const cos = Math.cos(turn), sin = Math.sin(turn);
    const P = i => {   // outline point i, scaled up, slightly rotated, centred right of the title
      const x = (T.x[i % n] - 0.5) * size, y = (T.y[i % n] - T.aspect / 2) * size;
      return [cx + x * cos - y * sin, cy + x * sin + y * cos];
    };
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    ctx.strokeStyle = 'rgba(255, 255, 255, .085)'; ctx.lineWidth = 2;
    ctx.beginPath();
    for (let i = 0; i <= n; i++) { const [x, y] = P(i); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }
    ctx.stroke();
    // the light point: one lap of the outline per minute, with a trail over the last sixth of the lap
    const head = ((t / 60) % 1) * n, tail = Math.round(n / 6);
    for (let k = tail; k >= 1; k--) {
      const a = P(Math.floor(head - k + n)), b = P(Math.floor(head - k + 1 + n)), strength = 1 - k / tail;
      ctx.strokeStyle = `rgba(225, 6, 0, ${(0.5 * strength * strength).toFixed(3)})`; ctx.lineWidth = 1 + 2 * strength;
      ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
    }
    const i = Math.floor(head), u = head - i, a = P(i), b = P(i + 1);
    glow(ctx, a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, 26);
  }

  // ---------- flow ----------
  function flow(canvas, t) {
    const [ctx, w, h] = fit(canvas);
    const lines = DATA.flow;
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    lines.forEach((values, k) => {
      const n = values.length, drift = Math.sin(t * 0.05 + k * 1.7) * 36, rise = Math.sin(t * 0.07 + k) * 9;
      const base = h * (0.2 + 0.56 * (k + 0.5) / lines.length) + rise, swing = h * 0.34;
      const X = i => -w * 0.06 + drift + (i / (n - 1)) * w * 1.12, Y = i => base + (values[i] - 0.5) * swing;
      ctx.strokeStyle = `rgba(165, 195, 255, ${k === 0 ? 0.2 : 0.1})`; ctx.lineWidth = k === 0 ? 1.8 : 1.4;
      ctx.beginPath(); ctx.moveTo(X(0), Y(0));
      for (let i = 1; i < n - 1; i++) ctx.quadraticCurveTo(X(i), Y(i), (X(i) + X(i + 1)) / 2, (Y(i) + Y(i + 1)) / 2);
      ctx.lineTo(X(n - 1), Y(n - 1)); ctx.stroke();
      if (k === 0) {   // the glow walks along the quickest driver's line, end to end in about 80 seconds
        const f = ((t / 80) % 1) * (n - 1), i = Math.floor(f), u = f - i, j = Math.min(n - 1, i + 1);
        glow(ctx, X(i) + (X(j) - X(i)) * u, Y(i) + (Y(j) - Y(i)) * u, 30);
      }
    });
  }

  const SCENES = {circuit, flow};
  const wait = setInterval(() => {
    const canvas = document.getElementById('hero-art');
    if (!canvas) return;
    clearInterval(wait);
    if (canvas.dataset.live) return;
    canvas.dataset.live = '1';
    const scene = SCENES[DATA.scene];
    if (reduced) {
      const still = () => scene(canvas, 23);
      still(); new ResizeObserver(still).observe(canvas);
      return;
    }
    const t0 = performance.now() - 23000;   // start part-way, so the trail is already there
    let last = 0;
    (function frame(now) {
      if (!canvas.isConnected) return;                           // page left: stop
      if (!document.hidden && now - last > 33) { scene(canvas, (now - t0) / 1000); last = now; }  // ~30 fps is plenty
      requestAnimationFrame(frame);
    })(performance.now());
  }, 60);
  setTimeout(() => clearInterval(wait), 15000);
})();
