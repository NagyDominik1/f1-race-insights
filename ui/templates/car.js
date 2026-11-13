// Original top-down single-seater silhouette, drawn with canvas paths.
// x, y: centre in canvas pixels; heading in radians (0 = pointing right); size = car length in pixels.
function drawCar(ctx, x, y, heading, size, colour, outline) {
  const L = size, W = size * 0.46;
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(heading);
  ctx.lineJoin = 'round';
  // wheels
  ctx.fillStyle = '#1D1D1F';
  const wl = L * 0.2, ww = W * 0.24;
  [[L * 0.27, -W / 2], [L * 0.27, W / 2 - ww], [-L * 0.36, -W / 2], [-L * 0.36, W / 2 - ww]]
    .forEach(([wx, wy]) => { ctx.beginPath(); ctx.roundRect(wx - wl / 2, wy, wl, ww, ww * 0.35); ctx.fill(); });
  ctx.fillStyle = colour;
  ctx.strokeStyle = outline || 'rgba(29,29,31,.55)';
  ctx.lineWidth = Math.max(0.6, L * 0.035);
  // front wing
  ctx.beginPath(); ctx.roundRect(L * 0.4, -W * 0.46, L * 0.09, W * 0.92, L * 0.02); ctx.fill(); ctx.stroke();
  // rear wing
  ctx.beginPath(); ctx.roundRect(-L * 0.5, -W * 0.38, L * 0.1, W * 0.76, L * 0.02); ctx.fill(); ctx.stroke();
  // body: narrow nose, wide sidepods, tapered engine cover
  ctx.beginPath();
  ctx.moveTo(L * 0.5, 0);
  ctx.lineTo(L * 0.3, -W * 0.09);
  ctx.lineTo(L * 0.12, -W * 0.14);
  ctx.lineTo(L * 0.02, -W * 0.34);
  ctx.lineTo(-L * 0.22, -W * 0.3);
  ctx.lineTo(-L * 0.42, -W * 0.12);
  ctx.lineTo(-L * 0.42, W * 0.12);
  ctx.lineTo(-L * 0.22, W * 0.3);
  ctx.lineTo(L * 0.02, W * 0.34);
  ctx.lineTo(L * 0.12, W * 0.14);
  ctx.lineTo(L * 0.3, W * 0.09);
  ctx.closePath(); ctx.fill(); ctx.stroke();
  // cockpit
  ctx.fillStyle = 'rgba(29,29,31,.85)';
  ctx.beginPath(); ctx.ellipse(-L * 0.02, 0, L * 0.085, W * 0.1, 0, 0, Math.PI * 2); ctx.fill();
  ctx.restore();
}
