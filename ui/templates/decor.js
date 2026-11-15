// Animated hero bands, drawn on one canvas from real demo-race numbers shaped in Python.
//   dataroom:  the screen wall of a dim engineering room, each screen a small live chart
//   trackside: a faint trophy and, every 10 to 12 seconds, a car streaking past
// Decoration only: the canvas never receives pointer events and stops when the page is left,
// the tab is hidden, or reduced motion is requested.
(() => {
  const DATA = __DATA__;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  /*__CAR__*/

  function fit(canvas) {
    const dpr = Math.min(window.devicePixelRatio || 1, 2), box = canvas.getBoundingClientRect();
    if (canvas.width !== Math.round(box.width * dpr) || canvas.height !== Math.round(box.height * dpr)) {
      canvas.width = Math.round(box.width * dpr); canvas.height = Math.round(box.height * dpr);
    }
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, box.width, box.height);
    return [ctx, box.width, box.height];
  }
  const INKBLUE = 'rgba(190, 214, 255,', RED = '#E10600';

  // ---------- data room ----------
  function screen(ctx, x, y, w, h, body) {
    ctx.save();
    ctx.shadowColor = 'rgba(80, 140, 255, .45)'; ctx.shadowBlur = 22;
    ctx.fillStyle = 'rgba(120, 165, 255, .09)';
    ctx.beginPath(); ctx.roundRect(x, y, w, h, 7); ctx.fill();
    ctx.shadowBlur = 0;
    ctx.strokeStyle = 'rgba(150, 190, 255, .28)'; ctx.lineWidth = 1; ctx.stroke();
    ctx.beginPath(); ctx.roundRect(x, y, w, h, 7); ctx.clip();
    body(x + 9, y + 9, w - 18, h - 18);
    ctx.restore();
  }
  function series(ctx, values, x, y, w, h, upTo, colour, width) {
    const n = values.length, end = Math.min(n - 1, upTo);
    ctx.strokeStyle = colour; ctx.lineWidth = width; ctx.lineJoin = 'round';
    ctx.beginPath();
    for (let i = 0; i <= end; i++) {
      const px = x + (i / (n - 1)) * w, py = y + h - values[i] * h;
      i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
    }
    ctx.stroke();
    if (end >= 0) { ctx.fillStyle = RED; ctx.beginPath(); ctx.arc(x + (end / (n - 1)) * w, y + h - values[end] * h, 2.4, 0, 7); ctx.fill(); }
  }
  function dataroom(canvas, t) {
    const [ctx, w, h] = fit(canvas);
    const narrow = w < 700;
    const left = narrow ? w * 0.08 : w * 0.46, right = w - 26, top = 24;
    const W = right - left, H = h - top - (narrow ? 20 : 86);  // the row of buttons stays clear below the wall
    ctx.globalAlpha = narrow ? 0.3 : 1;
    const lap = (t * 5) % (DATA.laps + 18), lines = DATA.lines, cars = DATA.cars, T = DATA.track;

    screen(ctx, left, top, W * 0.25, H * 0.46, (x, y, sw, sh) => {                       // lap times of two drivers
      series(ctx, DATA.pace[0], x, y, sw, sh, lap, INKBLUE + '.9)', 1.4);
      series(ctx, DATA.pace[1], x, y, sw, sh, lap - 2, INKBLUE + '.45)', 1.2);
    });
    screen(ctx, left, top + H * 0.54, W * 0.25, H * 0.46, (x, y, sw, sh) => {            // gap to the fastest lap, per driver
      const n = DATA.gaps.length, bw = sw / n, hot = Math.floor(t * 1.5) % n;
      DATA.gaps.forEach((g, i) => {
        const bh = (0.15 + 0.85 * g) * sh * (0.9 + 0.1 * Math.sin(t * 2 + i));
        ctx.fillStyle = i === hot ? RED : INKBLUE + '.6)';
        ctx.fillRect(x + i * bw + 1, y + sh - bh, Math.max(1.5, bw - 2), bh);
      });
    });
    screen(ctx, left + W * 0.28, top, W * 0.4, H, (x, y, sw, sh) => {                    // track map with two cars
      const scale = Math.min(sw, sh / T.aspect) * 0.92, ox = x + (sw - scale) / 2, oy = y + (sh - scale * T.aspect) / 2;
      ctx.strokeStyle = INKBLUE + '.75)'; ctx.lineWidth = 2; ctx.lineJoin = 'round';
      ctx.beginPath(); T.x.forEach((v, i) => (i ? ctx.lineTo(ox + v * scale, oy + T.y[i] * scale) : ctx.moveTo(ox + v * scale, oy + T.y[i] * scale)));
      ctx.closePath(); ctx.stroke();
      cars.slice(0, 2).forEach((car, k) => {
        const n = car.x.length, i = Math.floor(((t * 4 + k * 3) % car.seconds) / car.seconds * (n - 1));
        ctx.fillStyle = k ? '#FFFFFF' : RED;
        ctx.beginPath(); ctx.arc(ox + car.x[i] * scale, oy + car.y[i] * scale, 3.2, 0, 7); ctx.fill();
      });
    });
    screen(ctx, left + W * 0.71, top, W * 0.29, H * 0.56, (x, y, sw, sh) => {            // positions lap by lap
      lines.slice(0, 8).forEach((line, i) => {
        ctx.strokeStyle = INKBLUE + (i < 2 ? '.9)' : '.35)'); ctx.lineWidth = i < 2 ? 1.5 : 1;
        ctx.beginPath();
        for (let l = 0; l < line.length && l <= lap; l++) {
          if (line[l] === null) break;
          const px = x + (l / DATA.laps) * sw, py = y + ((Math.min(line[l], 10) - 1) / 9) * sh;
          l ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
        }
        ctx.stroke();
      });
    });
    screen(ctx, left + W * 0.71, top + H * 0.64, W * 0.29, H * 0.36, (x, y, sw, sh) => { // lap counter
      const now = Math.max(1, Math.min(DATA.laps, Math.floor(lap)));
      ctx.fillStyle = INKBLUE + '.55)'; ctx.font = '500 10px Inter, sans-serif'; ctx.textBaseline = 'top'; ctx.fillText('Lap', x, y);
      ctx.fillStyle = INKBLUE + '.95)'; ctx.font = `700 ${Math.min(30, sh * 0.62)}px Inter, sans-serif`;
      ctx.fillText(String(now), x, y + 12);
      ctx.fillStyle = INKBLUE + '.35)'; ctx.fillRect(x, y + sh - 3, sw, 2);
      ctx.fillStyle = RED; ctx.fillRect(x, y + sh - 3, sw * now / DATA.laps, 2);
    });
    ctx.globalAlpha = 1;
    // the wall dims towards the page title on the left, so text always reads
    const fade = ctx.createLinearGradient(w * 0.38, 0, w * 0.86, 0);
    fade.addColorStop(0, 'rgba(11, 30, 63, 1)'); fade.addColorStop(0.3, 'rgba(11, 30, 63, .8)');
    fade.addColorStop(0.7, 'rgba(11, 30, 63, .3)'); fade.addColorStop(1, 'rgba(11, 30, 63, 0)');
    ctx.fillStyle = fade; ctx.fillRect(0, 0, w * 0.86, h);
  }

  // ---------- track side ----------
  function trophy(ctx, cx, cy, s) {  // a generic two-handled cup
    ctx.fillStyle = 'rgba(255, 255, 255, .075)'; ctx.strokeStyle = 'rgba(255, 255, 255, .075)';
    ctx.beginPath(); ctx.moveTo(cx - 34 * s, cy - 52 * s); ctx.lineTo(cx + 34 * s, cy - 52 * s);
    ctx.bezierCurveTo(cx + 34 * s, cy + 6 * s, cx + 14 * s, cy + 16 * s, cx + 7 * s, cy + 20 * s);
    ctx.lineTo(cx + 7 * s, cy + 36 * s); ctx.lineTo(cx + 22 * s, cy + 42 * s); ctx.lineTo(cx + 22 * s, cy + 52 * s);
    ctx.lineTo(cx - 22 * s, cy + 52 * s); ctx.lineTo(cx - 22 * s, cy + 42 * s); ctx.lineTo(cx - 7 * s, cy + 36 * s);
    ctx.lineTo(cx - 7 * s, cy + 20 * s);
    ctx.bezierCurveTo(cx - 14 * s, cy + 16 * s, cx - 34 * s, cy + 6 * s, cx - 34 * s, cy - 52 * s);
    ctx.closePath(); ctx.fill();
    ctx.lineWidth = 6 * s; ctx.lineCap = 'round';
    [-1, 1].forEach(side => {
      ctx.beginPath(); ctx.moveTo(cx + side * 34 * s, cy - 42 * s);
      ctx.bezierCurveTo(cx + side * 62 * s, cy - 42 * s, cx + side * 58 * s, cy - 4 * s, cx + side * 27 * s, cy - 6 * s); ctx.stroke();
    });
  }
  let pass = null, nextAt = 2.5;
  function trackside(canvas, t) {
    const [ctx, w, h] = fit(canvas);
    trophy(ctx, w < 700 ? w * 0.8 : w * 0.64, h * 0.54, Math.min(1.45, h / 160));
    if (reduced) return;
    if (!pass && t >= nextAt) {
      const colours = DATA.colours;
      pass = {start: t, dir: Math.random() < 0.5 ? 1 : -1, colour: colours[Math.floor(Math.random() * colours.length)],
              y: h * (0.2 + Math.random() * 0.2)};  // above the page title, never across it
    }
    if (!pass) return;
    const DURATION = 1.15, p = (t - pass.start) / DURATION;
    if (p >= 1) { pass = null; nextAt = t + 10 + Math.random() * 2; return; }
    const size = 40, span = w + 500, x = pass.dir > 0 ? -250 + span * p : w + 250 - span * p;
    const tail = x - pass.dir * 300, trail = ctx.createLinearGradient(tail, 0, x, 0);
    trail.addColorStop(0, 'rgba(255,255,255,0)'); trail.addColorStop(1, pass.colour);
    ctx.globalAlpha = 0.5; ctx.fillStyle = trail;
    ctx.fillRect(Math.min(tail, x), pass.y - 5, Math.abs(x - tail), 10);
    for (let k = 5; k >= 1; k--) {   // motion blur: fading copies behind the car
      ctx.globalAlpha = 0.11 * (6 - k) / 5;
      drawCar(ctx, x - pass.dir * k * 9, pass.y, pass.dir > 0 ? 0 : Math.PI, size, pass.colour);
    }
    ctx.globalAlpha = 0.9;
    drawCar(ctx, x, pass.y, pass.dir > 0 ? 0 : Math.PI, size, pass.colour);
    ctx.globalAlpha = 1;
  }

  const SCENES = {dataroom, trackside};
  const wait = setInterval(() => {
    const canvas = document.getElementById('hero-art');
    if (!canvas) return;
    clearInterval(wait);
    if (canvas.dataset.live) return;
    canvas.dataset.live = '1';
    const scene = SCENES[canvas.dataset.scene];
    if (reduced) {
      const still = () => scene(canvas, 9);
      still(); new ResizeObserver(still).observe(canvas);
      return;
    }
    const t0 = performance.now();
    (function frame(now) {
      if (!canvas.isConnected) return;                      // page left: stop
      if (!document.hidden) scene(canvas, (now - t0) / 1000);  // tab hidden: skip drawing
      requestAnimationFrame(frame);
    })(t0);
  }, 60);
  setTimeout(() => clearInterval(wait), 15000);
})();
