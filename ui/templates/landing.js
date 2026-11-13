// Landing backgrounds. Both are drawn from the demo race, shaped in Python:
// left  = the real lap-by-lap position chart drawing itself,
// right = five drivers' real fastest laps looping on the track outline.
(() => {
  const DATA = __DATA__;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  /*__CAR__*/

  function fitCanvas(canvas) {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const box = canvas.getBoundingClientRect();
    if (canvas.width !== Math.round(box.width * dpr) || canvas.height !== Math.round(box.height * dpr)) {
      canvas.width = Math.round(box.width * dpr);
      canvas.height = Math.round(box.height * dpr);
    }
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, box.width, box.height);
    return [ctx, box.width, box.height];
  }

  // progress: laps drawn so far (fractional)
  function drawLines(canvas, progress, alpha) {
    const [ctx, w, h] = fitCanvas(canvas);
    const laps = DATA.laps, n = DATA.lines.length;
    const px = lap => w * 0.06 + (lap / laps) * w * 0.88;
    const py = pos => h * 0.1 + ((pos - 1) / (n - 1)) * h * 0.5;
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    DATA.lines.forEach((line, i) => {
      const strong = i < 3;
      ctx.strokeStyle = `rgba(255,255,255,${(strong ? 0.5 : 0.17) * alpha})`;
      ctx.lineWidth = strong ? 2 : 1.25;
      ctx.beginPath();
      let last = null;
      for (let lap = 0; lap < line.length && lap <= progress; lap++) {
        if (line[lap] === null) break;
        const x = px(lap), y = py(line[lap]);
        lap === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        last = [x, y, lap];
      }
      if (last && last[2] + 1 < line.length && line[last[2] + 1] !== null && progress < laps) {
        const f = progress - last[2];
        last = [px(last[2] + f), py(line[last[2]] + (line[last[2] + 1] - line[last[2]]) * f)];
        ctx.lineTo(last[0], last[1]);
      }
      ctx.stroke();
      if (last && strong) {
        ctx.fillStyle = `rgba(255,255,255,${0.9 * alpha})`;
        ctx.beginPath(); ctx.arc(last[0], last[1], 3, 0, Math.PI * 2); ctx.fill();
      }
    });
  }

  function drawTrack(canvas, seconds) {
    const [ctx, w, h] = fitCanvas(canvas);
    const T = DATA.track;
    const scale = Math.min(w * 0.8, (h * 0.56) / T.aspect);
    const ox = (w - scale) / 2, oy = h * 0.07 + (h * 0.56 - scale * T.aspect) / 2;
    const X = v => ox + v * scale, Y = v => oy + v * scale;
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    ctx.strokeStyle = '#2B2D31';
    ctx.lineWidth = Math.max(7, scale * 0.016);
    ctx.beginPath();
    T.x.forEach((v, i) => (i ? ctx.lineTo(X(v), Y(T.y[i])) : ctx.moveTo(X(v), Y(T.y[i]))));
    ctx.closePath(); ctx.stroke();
    const size = Math.max(16, scale * 0.034);
    DATA.cars.forEach((car, k) => {
      const n = car.x.length;
      const t = reduced ? (k / DATA.cars.length) * car.seconds : (seconds * 2.5 + k * 9) % car.seconds;
      const f = (t / car.seconds) * (n - 1), i = Math.floor(f), j = Math.min(i + 1, n - 1), m = f - i;
      const x = X(car.x[i] + (car.x[j] - car.x[i]) * m), y = Y(car.y[i] + (car.y[j] - car.y[i]) * m);
      const a = Math.max(0, i - 1), b = Math.min(n - 1, i + 2);
      const heading = Math.atan2(car.y[b] - car.y[a], car.x[b] - car.x[a]);
      drawCar(ctx, x, y, heading, size, car.colour);
      ctx.font = '600 11px Inter, sans-serif'; ctx.fillStyle = '#1D1D1F';
      ctx.fillText(car.label, x + size * 0.6, y - size * 0.5);
    });
  }

  function start(lines, track) {
    const DRAW = 11, HOLD = 4;
    let t0 = performance.now();
    function frame(now) {
      if (!lines.isConnected) return;  // the page was left: stop the loop
      const s = (now - t0) / 1000, cycle = s % (DRAW + HOLD);
      const fade = cycle > DRAW + HOLD - 0.8 ? (DRAW + HOLD - cycle) / 0.8 : 1;
      drawLines(lines, Math.min(1, cycle / DRAW) * DATA.laps, fade);
      drawTrack(track, s);
      requestAnimationFrame(frame);
    }
    if (reduced) {
      const still = () => { drawLines(lines, DATA.laps, 1); drawTrack(track, 0); };
      still(); new ResizeObserver(still).observe(lines);
    } else {
      requestAnimationFrame(frame);
    }
  }

  // click: let the tile grow to full width, then let Streamlit handle the real click
  function bind(key) {
    const button = document.querySelector(`.st-key-${key} button`);
    if (!button || button.dataset.bound) return;
    button.dataset.bound = '1';
    button.addEventListener('click', event => {
      if (button.dataset.go || reduced) return;
      event.preventDefault(); event.stopImmediatePropagation();
      button.dataset.go = '1';
      button.closest('[data-testid="stColumn"]').classList.add('is-going');
      setTimeout(() => button.click(), 480);
    }, true);
  }

  const wait = setInterval(() => {
    const lines = document.getElementById('lt-lines'), track = document.getElementById('lt-track');
    if (!lines || !track || !document.querySelector('.st-key-go_races button')) return;
    clearInterval(wait);
    bind('go_analytics'); bind('go_races');
    if (!lines.dataset.live) { lines.dataset.live = '1'; start(lines, track); }
  }, 60);
  setTimeout(() => clearInterval(wait), 15000);
})();
