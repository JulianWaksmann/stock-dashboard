// Dibujo del informe de cartera. Recibe el informe ya calculado en Python
// (cartera/informe.py) y solo le da formato: acá no se suma ni se reparte nada.
// Los textos que vienen del Excel (tickers, descripciones) son datos de quien
// subió el archivo: van siempre por textContent, nunca por innerHTML.

const D3_URL = 'https://cdn.jsdelivr.net/npm/d3@7.9.0/+esm';
let d3p = null;
const cargarD3 = () => (d3p = d3p || import(D3_URL));

const nf0 = new Intl.NumberFormat('es-AR', { maximumFractionDigits: 0 });
const nf2 = new Intl.NumberFormat('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const nfp = new Intl.NumberFormat('es-AR', { maximumFractionDigits: 4 });
const MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
const MESL = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const OCULTO = '****';

export default function (component) {
  const { data, parentElement: root } = component;
  if (!data) return;
  const $ = (s) => root.querySelector(s);
  const $$ = (s) => root.querySelectorAll(s);
  const bz = $('.bz');
  // El estado de la interfaz sobrevive a las re-ejecuciones de Streamlit.
  const st = (root.__bz = root.__bz || { sel: null, k: 'total', dir: -1, q: '', clase: '', oculto: false, mix: 'activo' });

  // ---------- formato (con montos ocultables) ----------
  const usd = (v) => (v < 0 ? '−' : '') + 'US$ ' + (st.oculto ? OCULTO : nf0.format(Math.abs(Math.round(v))));
  const sgn = (v) => (Math.round(v) > 0 ? '+' : '') + usd(v);
  const usd2 = (v) => (v > 0 ? '+' : v < 0 ? '−' : '') + 'US$ ' + (st.oculto ? OCULTO : nf2.format(Math.abs(v)));
  const usdC = (v) => 'US$ ' + (st.oculto ? OCULTO : nf2.format(v));
  const num = (v) => (st.oculto ? OCULTO : nfp.format(v));
  const num2 = (v) => (st.oculto ? OCULTO : nf2.format(v));
  const pct = (v) => (v == null ? '—' : (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toLocaleString('es-AR', { maximumFractionDigits: 1 }) + '%');
  const pn = (v) => (v > 0.005 ? 'pos' : v < -0.005 ? 'neg' : '');
  const dfmt = (s) => (s ? s.slice(8, 10) + '/' + s.slice(5, 7) + '/' + s.slice(0, 4) : '');
  const cssVar = (n) => getComputedStyle(bz).getPropertyValue(n).trim();
  const td = (tr, text, cls) => { const c = document.createElement('td'); c.textContent = text; if (cls) c.className = cls; tr.appendChild(c); return c; };
  const vacio = (el, txt) => { el.replaceChildren(); const d = document.createElement('div'); d.className = 'bz-empty'; d.textContent = txt; el.appendChild(d); };
  const setTxt = (sel, t, cls) => { const el = $(sel); el.textContent = t; if (cls !== undefined) el.className = el.className.replace(/ ?(pos|neg)\b/g, '') + (cls ? ' ' + cls : ''); };

  let d3 = null;
  const tipFor = (box) => { let t = box.querySelector('.bz-tip'); if (!t) { t = document.createElement('div'); t.className = 'bz-tip'; t.hidden = true; box.appendChild(t); } return t; };
  const showTip = (box, tip, ev, head, lines) => {
    tip.replaceChildren();
    const h = document.createElement('div'); h.className = 'h'; h.textContent = head; tip.appendChild(h);
    for (const [color, label, val] of lines) {
      const r = document.createElement('div'); r.className = 'r';
      if (color) { const i = document.createElement('i'); i.style.background = color; r.appendChild(i); }
      const s = document.createElement('span'); s.textContent = (label ? label + ': ' : '') + val; r.appendChild(s); tip.appendChild(r);
    }
    tip.hidden = false;
    const b = box.getBoundingClientRect(); let x = ev.clientX - b.left + 12; const y = ev.clientY - b.top + 12;
    if (x + tip.offsetWidth > b.width) x = Math.max(0, ev.clientX - b.left - tip.offsetWidth - 12);
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
  };
  const clean = (g) => g.attr('font-size', null).attr('font-family', null)
    .call((s) => s.selectAll('text').attr('fill', 'var(--bz-muted)').style('font-size', 'var(--fs-cap)'))
    .call((s) => s.selectAll('.domain').attr('stroke', 'var(--bz-line-strong)'))
    .call((s) => s.selectAll('.tick line').attr('stroke', 'var(--bz-line)'));
  const textW = (svg, s) => { const t = svg.append('text').style('font-size', 'var(--fs-cap)').text(s); const w = t.node().getComputedTextLength(); t.remove(); return w; };
  const serie = (leg, series) => { leg.replaceChildren(); for (const [, n, c] of series) { const s = document.createElement('span'); const i = document.createElement('i'); i.style.background = c; s.append(i, n); leg.appendChild(s); } };

  // ---------- cabecera ----------
  function fillHero() {
    const k = data.kpis;
    const anioFin = (data.fecha_corte || '').slice(0, 4);
    $('#eyebrow').textContent = 'Tu historia en ' + (data.brokers.length ? data.brokers.join(' y ') : 'tus brokers') + (k.primer_anio ? ' · ' + k.primer_anio + (k.primer_anio !== anioFin ? ' a ' + anioFin : '') : '');
    $('#titulo').textContent = !k.primer_anio
      ? 'Todavía no cerraste operaciones'
      : (k.total >= 0 ? 'Ganaste ' : 'Perdiste ') + usd(Math.abs(k.total)) + ' desde ' + k.primer_anio;
    const p = $('#takeaway'); p.replaceChildren();
    const b = (t) => { const e = document.createElement('b'); e.textContent = t; return e; };
    if (!k.primer_anio && k.posiciones) p.append('Lo que tenés en cartera se muestra al costo hasta que lo vendas.');
    // "Mejor año" y "el que más aportó" solo tienen sentido si hubo ganancia.
    if (k.mejor_anio && k.mejor_anio_total > 0) {
      p.append('Tu mejor año fue ', b(k.mejor_anio), ' con ', b(usd(k.mejor_anio_total)), ' y el activo que más aportó fue ', b(k.mejor_ticker), '. ');
    }
    if (Math.abs(k.renta) >= 0.5) p.append('Dividendos, cupones e intereses sumaron ', b(usd(k.renta)), '.');
    setTxt('#k-total', sgn(k.total));
    setTxt('#k-ventas', sgn(k.ventas));
    setTxt('#k-ventas-n', data.estilo.ventas ? data.estilo.ventas + ' lotes vendidos' : 'Sin ventas');
    setTxt('#k-renta', sgn(k.renta));
    setTxt('#k-cartera', usd(k.cartera_costo));
    setTxt('#k-cartera-n', k.posiciones ? k.posiciones + ' activos en cartera' : 'Sin posiciones abiertas');
    const raros = data.no_reconocidos.length;
    const av = $('#aviso'); av.hidden = !raros;
    av.textContent = raros ? raros + (raros === 1 ? ' movimiento no se pudo interpretar y quedó' : ' movimientos no se pudieron interpretar y quedaron') + ' fuera de los totales. Están listados al final.' : '';
  }

  // ---------- tabla de activos ----------
  const tkRows = data.por_ticker, opRows = data.operaciones;
  if (!st.sel || !tkRows.some((r) => r.ticker === st.sel)) st.sel = tkRows[0] && tkRows[0].ticker;
  const claseSel = $('#tk-clase');

  function fillMaster() {
    const tb = $('#t-tk tbody'); tb.replaceChildren();
    const q = st.q.trim().toLowerCase();
    const rows = tkRows.filter((r) => (!st.clase || r.clase === st.clase) && (!q || (r.ticker + ' ' + r.descripcion).toLowerCase().includes(q)))
      .sort((a, b) => { const A = a[st.k], B = b[st.k]; return (A < B ? -1 : A > B ? 1 : 0) * st.dir; });
    const max = Math.max(1, ...tkRows.map((r) => Math.abs(r.total)));
    for (const r of rows) {
      const tr = document.createElement('tr'); tr.tabIndex = 0; tr.setAttribute('aria-selected', String(r.ticker === st.sel));
      td(tr, r.ticker, 'l bz-tk');
      td(tr, r.clase, 'l bz-hide-sm muted');
      td(tr, r.vendio ? sgn(r.compraventa) : '—', r.vendio ? pn(r.compraventa) : 'muted');
      td(tr, r.renta ? sgn(r.renta) : '—', (r.renta ? pn(r.renta) : 'muted') + ' bz-hide-sm');
      const T = r.total;
      const c = td(tr, '', pn(T)); const wrap = document.createElement('span'); wrap.className = 'bz-barcell';
      const track = document.createElement('span'); track.className = 'bz-track'; const bar = document.createElement('span');
      const w = (Math.abs(T) / max) * 28; bar.style.width = Math.max(T ? 1.5 : 0, w) + 'px';
      bar.style.left = T >= 0 ? '28px' : (28 - w) + 'px';
      bar.style.background = T >= 0 ? 'var(--bz-pos)' : 'var(--bz-neg)';
      track.appendChild(bar); const val = document.createElement('span'); val.textContent = sgn(T);
      wrap.append(track, val); c.appendChild(wrap);
      const pick = () => { st.sel = r.ticker; fillMaster(); fillDetail(); };
      tr.onclick = pick;
      tr.onkeydown = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(); } };
      tb.appendChild(tr);
    }
    $$('#t-tk th').forEach((th) => { const b = th.querySelector('button'); th.setAttribute('aria-sort', b.dataset.k === st.k ? (st.dir > 0 ? 'ascending' : 'descending') : 'none'); });
  }
  $$('#t-tk th button').forEach((b) => { b.onclick = () => {
    if (st.k === b.dataset.k) st.dir *= -1; else { st.k = b.dataset.k; st.dir = b.dataset.num ? -1 : 1; }
    fillMaster();
  }; });
  const search = $('#tk-search'); search.value = st.q; search.oninput = (e) => { st.q = e.target.value; fillMaster(); };
  const clases = [...new Set(tkRows.map((r) => r.clase))].sort();
  claseSel.replaceChildren(new Option('Todos los tipos', ''), ...clases.map((c) => new Option(c, c)));
  claseSel.value = st.clase;
  claseSel.onchange = () => { st.clase = claseSel.value; fillMaster(); if (d3) drawClases(); };

  function fillDetail() {
    const r = tkRows.find((x) => x.ticker === st.sel);
    $('#dt-tk').textContent = r ? r.ticker : '—';
    $('#dt-sub').textContent = r ? r.descripcion + ' · ' + r.clase : '—';
    if (!r) return;
    setTxt('#st-cv', r.vendio ? sgn(r.compraventa) : '—', pn(r.compraventa));
    setTxt('#st-re', r.renta ? sgn(r.renta) : '—', pn(r.renta));
    setTxt('#st-to', sgn(r.total), pn(r.total));
    setTxt('#st-co', r.costo_vendido ? usd(r.costo_vendido) : '—', '');
    setTxt('#st-rd', pct(r.rendimiento), r.rendimiento == null ? '' : pn(r.rendimiento));
    setTxt('#st-ab', r.cartera_cant ? usd(r.cartera_costo) : '—', '');
    $('#dt-note').textContent = r.cartera_cant
      ? 'Seguís teniendo ' + num(r.cartera_cant) + ', que te costaron ' + usd(r.cartera_costo) + '.'
      : (r.operaciones ? 'Ya no tenés este activo en cartera.' : '');

    const variosBrokers = data.brokers.length > 1;
    $$('#t-ops .c-b').forEach((th) => { th.hidden = !variosBrokers; });
    const ops = opRows.filter((o) => o.ticker === r.ticker).sort((a, b) => a.fecha.localeCompare(b.fecha) || a.id - b.id);
    const hasV = ops.some((o) => o.movimiento === 'Venta');
    $$('#t-ops .c-v').forEach((th) => { th.hidden = !hasV; });
    const tb = $('#t-ops tbody'); tb.replaceChildren();
    const precio = (v, cur) => (v == null ? '' : nfp.format(v) + (cur === 'USD' ? ' US$' : ' $'));
    for (const o of ops) {
      const tr = document.createElement('tr'); const v = o.movimiento === 'Venta';
      td(tr, dfmt(o.fecha), 'l');
      if (variosBrokers) td(tr, o.broker, 'l muted');
      const tc = td(tr, '', 'l'); const p = document.createElement('span'); p.className = 'bz-pill' + (v ? ' venta' : ''); p.textContent = o.movimiento; tc.appendChild(p);
      if (hasV) {
        td(tr, v ? dfmt(o.fecha_compra) : '', 'l muted');
        td(tr, v && o.cantidad != null ? num(o.cantidad) : '');
        td(tr, v ? precio(o.precio_compra, o.moneda_compra) + ' → ' + precio(o.precio_venta, o.moneda_venta) : '');
      }
      // Una venta usa dos dólares (el de la compra y el de la venta); un cobro, uno.
      const mep = (x) => (x ? nf2.format(x) : '—');
      td(tr, v && o.mep_compra ? mep(o.mep_compra) + ' → ' + mep(o.mep_venta) : mep(o.mep_venta), 'muted');
      if (hasV) td(tr, v && o.costo_usd != null ? num2(o.costo_usd) : '');
      td(tr, v ? (o.venta_usd == null ? '' : num2(o.venta_usd)) : (o.cobro_usd == null ? '' : num2(o.cobro_usd)));
      td(tr, o.gastos_usd ? num2(o.gastos_usd) : '', 'muted');
      td(tr, usd2(o.resultado_usd), pn(o.resultado_usd));
      tb.appendChild(tr);
    }
  }

  // ---------- gráficos ----------
  function drawAnios() {
    const el = $('#chart-anio'); el.replaceChildren();
    const rows = data.por_anio;
    const series = [['ventas', 'Compraventa', 'var(--bz-d2)'], ['renta', 'Dividendos, cupones e intereses', 'var(--bz-d4)']];
    serie($('#leg-anio'), series);
    if (!rows.length) return vacio(el, 'Todavía no hay ventas ni cobros.');
    const W = el.clientWidth || 500, H = 250;
    const svg = d3.select(el).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const max = d3.max(rows, (r) => Math.max(0, r.ventas) + Math.max(0, r.renta)) || 1;
    const min = d3.min(rows, (r) => Math.min(0, r.ventas) + Math.min(0, r.renta)) || 0;
    const y = d3.scaleLinear([min, max * 1.12], [H - 26, 8]).nice();
    const ml = Math.max(...y.ticks(5).map((t) => textW(svg, usd(t)))) + 10;
    const x = d3.scaleBand(rows.map((r) => r.anio), [ml, W - 4]).padding(0.35);
    const bw = Math.min(x.bandwidth(), 56), off = (x.bandwidth() - bw) / 2;
    svg.append('g').attr('transform', `translate(${ml},0)`).call(d3.axisLeft(y).ticks(5).tickFormat(usd).tickSize(-(W - ml - 4))).call(clean).call((g) => g.select('.domain').remove());
    svg.append('g').attr('transform', `translate(0,${y(0)})`).call(d3.axisBottom(x).tickSize(0).tickPadding(8)).call(clean);
    const tip = tipFor(el);
    rows.forEach((r) => {
      let up = 0, down = 0; const g = svg.append('g'); const x0 = x(r.anio) + off;
      series.forEach(([k, , c]) => {
        const v = r[k]; if (!v) return;
        const y0 = v >= 0 ? up : down, y1 = y0 + v; if (v >= 0) up = y1; else down = y1;
        g.append('rect').attr('x', x0).attr('width', bw).attr('y', y(Math.max(y0, y1))).attr('height', Math.abs(y(y0) - y(y1))).attr('fill', c).attr('rx', 3);
      });
      g.append('text').attr('x', x0 + bw / 2).attr('y', y(up) - 6).attr('text-anchor', 'middle').attr('fill', 'var(--bz-ink)').style('font-size', 'var(--fs-cap)').style('font-weight', 600).text(usd(r.total));
      g.append('rect').attr('x', x(r.anio)).attr('width', x.bandwidth()).attr('y', 0).attr('height', H).attr('fill', 'transparent')
        .on('mousemove', (ev) => showTip(el, tip, ev, r.anio, [[series[0][2], 'Compraventa', usd(r.ventas)], [series[1][2], 'Renta', usd(r.renta)], [null, 'Total', usd(r.total)]]))
        .on('mouseleave', () => { tip.hidden = true; });
    });
  }

  function drawClases() {
    const el = $('#chart-clase'); el.replaceChildren();
    const rows = data.por_clase;
    if (!rows.length) return vacio(el, 'Todavía no hay ventas ni cobros.');
    const W = el.clientWidth || 500, rowH = 28, H = rows.length * rowH + 8;
    const svg = d3.select(el).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const ml = Math.max(...rows.map((r) => textW(svg, r.clase))) + 12;
    const vw = Math.max(...rows.map((r) => textW(svg, sgn(r.resultado)))) + 8;
    const ext = [Math.min(0, d3.min(rows, (r) => r.resultado)), Math.max(0, d3.max(rows, (r) => r.resultado))];
    const x = d3.scaleLinear(ext, [ml + (ext[0] < 0 ? vw : 0), W - vw]);
    const y = d3.scaleBand(rows.map((r) => r.clase), [4, H - 4]).padding(0.3);
    const tip = tipFor(el);
    rows.forEach((r) => {
      const v = r.resultado, pos = v >= 0, active = st.clase === r.clase;
      const g = svg.append('g').attr('class', 'bz-clase-row').attr('tabindex', 0).attr('role', 'button').attr('aria-pressed', String(active));
      const by = y(r.clase), bh = Math.min(y.bandwidth(), 18);
      g.append('rect').attr('x', 0).attr('y', by - 4).attr('width', W).attr('height', bh + 8).attr('fill', 'transparent');
      g.append('text').attr('x', 0).attr('y', by + bh / 2).attr('dy', '0.35em').attr('fill', 'var(--bz-ink)').style('font-size', 'var(--fs-cap)').style('font-weight', active ? 700 : 400).text(r.clase);
      g.append('rect').attr('class', 'bar').attr('x', Math.min(x(0), x(v))).attr('width', Math.max(1, Math.abs(x(v) - x(0)))).attr('y', by).attr('height', bh).attr('rx', 3)
        .attr('fill', pos ? 'var(--bz-pos)' : 'var(--bz-neg)').attr('opacity', st.clase && !active ? 0.35 : 1);
      g.append('text').attr('x', pos ? x(v) + 6 : x(v) - 6).attr('text-anchor', pos ? 'start' : 'end').attr('y', by + bh / 2).attr('dy', '0.35em').attr('fill', 'var(--bz-muted)').style('font-size', 'var(--fs-cap)').text(sgn(v));
      const toggle = () => { st.clase = active ? '' : r.clase; claseSel.value = st.clase; fillMaster(); drawClases(); $('#activos').scrollIntoView({ block: 'start', behavior: 'smooth' }); };
      g.on('click', toggle).on('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); toggle(); } })
        .on('mousemove', (ev) => showTip(el, tip, ev, r.clase, [[null, 'Resultado', sgn(v)]])).on('mouseleave', () => { tip.hidden = true; });
    });
    svg.append('line').attr('x1', x(0)).attr('x2', x(0)).attr('y1', 0).attr('y2', H).attr('stroke', 'var(--bz-line-strong)');
  }

  function drawMix() {
    const el = $('#chart-mix'); el.replaceChildren();
    const rows = data.cartera_mix.filter((r) => r.grupo === st.mix);
    if (!rows.length) return;
    // Seis tonos: los grupos que sobran repiten el último, que es el de "resto".
    const tonos = ['var(--bz-d1)', 'var(--bz-d2)', 'var(--bz-d3)', 'var(--bz-d4)', 'var(--bz-d5)', 'var(--bz-d6)'];
    const pal = rows.map((_, i) => tonos[Math.min(i, tonos.length - 1)]);
    const total = data.kpis.cartera_costo;
    const box = document.createElement('div'); box.className = 'bz-donut-svg'; el.appendChild(box);
    const S = 180, R = S / 2, r0 = R * 0.62;
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${S} ${S}`).style('max-width', S + 'px');
    const g = svg.append('g').attr('transform', `translate(${R},${R})`);
    const arcs = d3.pie().sort(null).value((r) => r.costo).padAngle(0.012)(rows);
    const arc = d3.arc().innerRadius(r0).outerRadius(R - 2).cornerRadius(2);
    const arcH = d3.arc().innerRadius(r0).outerRadius(R + 2).cornerRadius(2);
    const c1 = g.append('text').attr('text-anchor', 'middle').attr('dy', '-0.2em').attr('fill', 'var(--bz-ink)').style('font-weight', 700).style('font-size', '15px').text(usd(total));
    const c2 = g.append('text').attr('text-anchor', 'middle').attr('dy', '1.25em').attr('fill', 'var(--bz-muted)').style('font-size', '10px').text('al costo');
    const reset = () => { c1.text(usd(total)); c2.text('al costo'); g.selectAll('path').attr('d', arc).attr('opacity', 1); };
    const hl = (i) => {
      g.selectAll('path').attr('d', (d, j) => (j === i ? arcH(d) : arc(d))).attr('opacity', (d, j) => (j === i ? 1 : 0.45));
      c1.text(rows[i].peso.toLocaleString('es-AR') + '%'); c2.text(rows[i].nombre.length > 18 ? rows[i].nombre.slice(0, 17) + '…' : rows[i].nombre);
    };
    g.selectAll('path').data(arcs).join('path').attr('d', arc).attr('fill', (d, i) => pal[i]).attr('stroke', 'var(--bz-card)').attr('stroke-width', 1)
      .on('mouseenter', (ev, d) => hl(d.index)).on('mouseleave', reset);
    const list = document.createElement('div'); list.className = 'bz-donut-list'; el.appendChild(list);
    rows.forEach((r, i) => {
      const it = document.createElement('div'); it.className = 'bz-donut-item';
      const sw = document.createElement('i'); sw.style.background = pal[i];
      const n = document.createElement('span'); n.className = 'n'; n.textContent = r.nombre;
      const p = document.createElement('span'); p.className = 'p'; p.textContent = r.peso.toLocaleString('es-AR') + '%';
      const v = document.createElement('span'); v.className = 'v'; v.textContent = usd(r.costo);
      it.append(sw, n, p, v); it.onmouseenter = () => hl(i); it.onmouseleave = reset;
      list.appendChild(it);
    });
  }
  const segA = $('#mix-activo'), segT = $('#mix-tipo');
  const setMix = (gr) => { st.mix = gr; segA.setAttribute('aria-pressed', String(gr === 'activo')); segT.setAttribute('aria-pressed', String(gr === 'tipo')); if (d3) drawMix(); };
  segA.onclick = () => setMix('activo'); segT.onclick = () => setMix('tipo');
  setMix(st.mix);

  function drawCal() {
    const el = $('#chart-cal'); el.replaceChildren();
    const rows = data.mensual;
    if (!rows.length) return vacio(el, 'Todavía no hay ventas ni cobros.');
    const years = [...new Set(rows.map((r) => r.anio))].sort();
    const W = el.clientWidth || 700, lw = 44, ch = 34, gap = 4, H = 22 + years.length * (ch + gap);
    const cw = (W - lw - 11 * gap) / 12;
    const svg = d3.select(el).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const max = d3.max(rows, (r) => Math.abs(r.resultado)) || 1;
    const soft = cssVar('--bz-soft');
    const ip = d3.interpolateRgb(soft, cssVar('--bz-pos')), ineg = d3.interpolateRgb(soft, cssVar('--bz-neg'));
    const byKey = new Map(rows.map((r) => [r.anio + '-' + r.m, r]));
    MESES.forEach((m, i) => svg.append('text').attr('x', lw + i * (cw + gap) + cw / 2).attr('y', 12).attr('text-anchor', 'middle').attr('fill', 'var(--bz-muted)').style('font-size', 'var(--fs-cap)').text(cw < 30 ? m[0] : m));
    const tip = tipFor(el);
    years.forEach((yr, yi) => {
      const yy = 22 + yi * (ch + gap);
      svg.append('text').attr('x', 0).attr('y', yy + ch / 2).attr('dy', '0.35em').attr('fill', 'var(--bz-ink)').style('font-size', 'var(--fs-cap)').style('font-weight', 600).text(yr);
      for (let m = 1; m <= 12; m++) {
        const r = byKey.get(yr + '-' + m); const x = lw + (m - 1) * (cw + gap);
        const t = r ? Math.min(1, Math.sqrt(Math.abs(r.resultado) / max)) : 0;
        const fill = !r ? 'var(--bz-line)' : r.resultado >= 0 ? ip(0.12 + 0.88 * t) : ineg(0.12 + 0.88 * t);
        const g = svg.append('g');
        g.append('rect').attr('x', x).attr('y', yy).attr('width', cw).attr('height', ch).attr('rx', 6).attr('fill', fill).attr('opacity', r ? 1 : 0.5);
        if (r && cw >= 40) {
          g.append('text').attr('x', x + cw / 2).attr('y', yy + ch / 2).attr('dy', '0.35em').attr('text-anchor', 'middle')
            .attr('fill', t > 0.55 ? '#FFFFFF' : 'var(--bz-ink)').style('font-size', '11px').style('font-weight', 600)
            .text(((v) => (v > 0 ? '+' : v < 0 ? '−' : ''))(Math.round(r.resultado)) + (st.oculto ? OCULTO : nf0.format(Math.abs(Math.round(r.resultado)))));
        }
        if (r) g.on('mousemove', (ev) => showTip(el, tip, ev, MESES[m - 1] + ' ' + yr, [[null, 'Resultado', usd2(r.resultado)]])).on('mouseleave', () => { tip.hidden = true; });
      }
    });
  }

  function drawScatter() {
    const el = $('#chart-scatter'); el.replaceChildren();
    const rows = data.ventas_rend;
    if (!rows.length) return vacio(el, 'Todavía no hay ventas para comparar.');
    const W = el.clientWidth || 500, H = 296, mb = 48, mt = 8, mr = 10;
    const svg = d3.select(el).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const y = d3.scaleLinear(d3.extent(rows, (r) => r.rend), [H - mb, mt]).nice();
    const fp = (v) => (v > 0 ? '+' : '') + v + '%';
    const ml = Math.max(...y.ticks(5).map((t) => textW(svg, fp(t)))) + 10;
    const x = d3.scaleLinear([0, d3.max(rows, (r) => r.dias) || 1], [ml, W - mr]).nice();
    const rr = d3.scaleSqrt([0, d3.max(rows, (r) => r.costo) || 1], [2.5, 16]);
    svg.append('g').attr('transform', `translate(${ml},0)`).call(d3.axisLeft(y).ticks(5).tickFormat(fp).tickSize(-(W - ml - mr))).call(clean).call((g) => g.select('.domain').remove());
    svg.append('g').attr('transform', `translate(0,${H - mb})`).call(d3.axisBottom(x).ticks(Math.max(3, Math.floor((W - ml) / 80))).tickFormat((d) => d + ' d')).call(clean);
    svg.append('line').attr('x1', ml).attr('x2', W - mr).attr('y1', y(0)).attr('y2', y(0)).attr('stroke', 'var(--bz-line-strong)').attr('stroke-dasharray', '4 3');
    svg.append('text').attr('x', W - mr).attr('y', H - 2).attr('text-anchor', 'end').attr('fill', 'var(--bz-muted)').style('font-size', 'var(--fs-cap)').text('días que tuviste el activo');
    const tip = tipFor(el);
    svg.append('g').selectAll('circle').data([...rows].sort((a, b) => b.costo - a.costo)).join('circle')
      .attr('cx', (r) => x(r.dias)).attr('cy', (r) => y(r.rend)).attr('r', (r) => rr(r.costo))
      .attr('fill', (r) => (r.resultado >= 0 ? 'var(--bz-pos)' : 'var(--bz-neg)')).attr('fill-opacity', 0.45)
      .attr('stroke', (r) => (r.resultado >= 0 ? 'var(--bz-pos)' : 'var(--bz-neg)')).attr('stroke-width', 1)
      .on('mousemove', (ev, r) => { d3.select(ev.currentTarget).attr('fill-opacity', 0.9); showTip(el, tip, ev, r.ticker + ' · ' + dfmt(r.fecha), [[null, 'Días', String(r.dias)], [null, 'Invertido', usd(r.costo)], [null, 'Resultado', usd2(r.resultado)], [null, 'Rendimiento', pct(r.rend)]]); })
      .on('mouseleave', (ev) => { d3.select(ev.currentTarget).attr('fill-opacity', 0.45); tip.hidden = true; });
  }

  function drawRenta() {
    const el = $('#chart-renta'); el.replaceChildren();
    const rows = data.renta_trim;
    const series = [['dividendos', 'Dividendos', 'var(--bz-d3)'], ['cupones', 'Cupones', 'var(--bz-d1)'], ['intereses', 'Intereses caución', 'var(--bz-d5)']];
    serie($('#leg-renta'), series);
    if (!rows.length || !rows.some((r) => r.total)) return vacio(el, 'Todavía no cobraste renta.');
    const W = el.clientWidth || 500, H = 250;
    const svg = d3.select(el).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const y = d3.scaleLinear([Math.min(0, d3.min(rows, (r) => r.total)), d3.max(rows, (r) => r.total) * 1.1 || 1], [H - 26, 8]).nice();
    const ml = Math.max(...y.ticks(5).map((t) => textW(svg, usd(t)))) + 10;
    const x = d3.scaleBand(rows.map((r) => r.trimestre), [ml, W - 4]).padding(0.25);
    svg.append('g').attr('transform', `translate(${ml},0)`).call(d3.axisLeft(y).ticks(5).tickFormat(usd).tickSize(-(W - ml - 4))).call(clean).call((g) => g.select('.domain').remove());
    svg.append('g').attr('transform', `translate(0,${y(0)})`).call(d3.axisBottom(x).tickSize(0).tickPadding(8).tickFormat((d) => (d.endsWith('T1') || d === rows[0].trimestre ? d.slice(0, 4) : ''))).call(clean);
    const tip = tipFor(el);
    rows.forEach((r) => {
      let up = 0, down = 0; const g = svg.append('g');
      series.forEach(([k, , c]) => {
        const v = r[k]; if (!v) return; const y0 = v >= 0 ? up : down, y1 = y0 + v; if (v >= 0) up = y1; else down = y1;
        g.append('rect').attr('x', x(r.trimestre)).attr('width', x.bandwidth()).attr('y', y(Math.max(y0, y1))).attr('height', Math.max(0.5, Math.abs(y(y0) - y(y1)))).attr('fill', c).attr('rx', 2);
      });
      g.append('rect').attr('x', x(r.trimestre)).attr('width', x.bandwidth()).attr('y', 0).attr('height', H).attr('fill', 'transparent')
        .on('mousemove', (ev) => showTip(el, tip, ev, r.trimestre.replace('-T', ' · T'), [[series[0][2], 'Dividendos', usd2(r.dividendos)], [series[1][2], 'Cupones', usd2(r.cupones)], [series[2][2], 'Intereses', usd2(r.intereses)], [null, 'Total', usd2(r.total)]]))
        .on('mouseleave', () => { tip.hidden = true; });
    });
  }

  // ---------- bloques sin d3 ----------
  function fillCobros() {
    const c = data.calendario_cobros;
    setTxt('#c-total', usdC(c.total)); setTxt('#c-mes', usdC(c.mensual));
    setTxt('#c-yoc', c.yoc == null ? '—' : c.yoc.toLocaleString('es-AR') + '%');
    setTxt('#c-yoc-n', c.pagan.length ? 'sobre ' + usd(c.costo_pagan) + ' invertidos en ' + c.pagan.join(', ') : '');
    setTxt('#c-prox', c.proximo_mes ? MESL[Number(c.proximo_mes.slice(5, 7)) - 1] + ' ' + c.proximo_mes.slice(0, 4) : '—');
    setTxt('#c-prox-n', c.proximo_mes ? c.proximo_tickers.join(', ') + ' · ' + usdC(c.proximo_total) : '');
    const el = $('#cal-div'); el.replaceChildren();
    // Doce meses "Sin cobros" no dicen nada que no diga una línea.
    const hay = c.pagos.length > 0;
    $('.bz-cobros-kpis').hidden = !hay; el.hidden = !hay;
    if (!hay) {
      $('#sin-cobro').textContent = 'Con lo que tenés hoy no cobraste dividendos ni cupones en los últimos 12 meses, así que no hay cobros para proyectar.';
      return;
    }
    const y0 = Number(c.desde.slice(0, 4)), m0 = Number(c.desde.slice(5, 7)) - 1;
    const meses = [];
    for (let i = 0; i < 12; i++) meses.push(new Date(Date.UTC(y0, m0 + i, 1)).toISOString().slice(0, 7));
    const tot = (k) => c.pagos.filter((r) => r.mes === k).reduce((s, r) => s + r.monto_usd, 0);
    const max = Math.max(...meses.map(tot)) || 1;
    for (const k of meses) {
      const pays = c.pagos.filter((r) => r.mes === k); const t = tot(k);
      const cell = document.createElement('div'); cell.className = 'bz-mes' + (pays.length ? '' : ' vacio') + (k === c.proximo_mes ? ' prox' : '');
      const head = document.createElement('div'); head.className = 'bz-mes-head';
      const nm = document.createElement('span'); nm.className = 'bz-mes-nombre'; nm.textContent = MESL[Number(k.slice(5, 7)) - 1].replace(/^./, (s) => s.toUpperCase());
      const yr = document.createElement('span'); yr.className = 'bz-mes-anio'; yr.textContent = k.slice(0, 4);
      head.append(nm, yr);
      if (k === c.proximo_mes) { const tag = document.createElement('span'); tag.className = 'bz-mes-tag'; tag.textContent = 'Próximo'; head.appendChild(tag); }
      const val = document.createElement('div'); val.className = 'bz-mes-total'; val.textContent = pays.length ? usdC(t) : 'Sin cobros';
      const bar = document.createElement('div'); bar.className = 'bz-mes-bar'; const fill = document.createElement('span'); fill.style.width = (t / max) * 100 + '%'; bar.appendChild(fill);
      const chips = document.createElement('div'); chips.className = 'bz-mes-chips';
      for (const p of pays) {
        const chp = document.createElement('span'); chp.className = 'bz-chip ' + (p.tipo === 'Cupón' ? 'cupon' : 'div');
        chp.title = p.tipo + ' estimado el ' + dfmt(p.fecha_est) + ', según lo cobrado el ' + dfmt(p.base);
        const tk = document.createElement('b'); tk.textContent = p.ticker; const am = document.createElement('span'); am.textContent = usdC(p.monto_usd);
        chp.append(tk, am); chips.appendChild(chp);
      }
      cell.append(head, val, bar, chips); el.appendChild(cell);
    }
    $('#sin-cobro').textContent = c.sin_cobro.length ? 'Sin cobros en los últimos 12 meses, así que no se proyectan: ' + c.sin_cobro.join(', ') + '.' : '';
  }

  function fillTiles() {
    const e = data.estilo, el = $('#tiles'); el.replaceChildren();
    const tile = (label, value, note) => {
      const t = document.createElement('div'); t.className = 'bz-tile';
      const l = document.createElement('span'); l.className = 'bz-tile-label'; l.textContent = label;
      const v = document.createElement('span'); v.className = 'bz-tile-value'; v.textContent = value;
      const n = document.createElement('span'); n.className = 'bz-tile-note'; n.textContent = note;
      t.append(l, v, n); el.appendChild(t);
    };
    if (!e.ventas) { tile('Ventas', '—', 'Todavía no vendiste nada: los patrones aparecen con las primeras ventas.'); return; }
    tile('Tasa de acierto', e.acierto_pct + '%', e.ganadoras + ' de ' + e.ventas + ' ventas cerraron en ganancia; ' + e.perdedoras + ' en pérdida.');
    tile('Ganancia vs. pérdida promedio', '+' + usd(e.ganancia_media) + ' / ' + usd(e.perdida_media),
      e.payoff == null ? 'Sin ventas en pérdida.' : 'Una venta ganadora deja en promedio ' + e.payoff.toLocaleString('es-AR', { maximumFractionDigits: 1 }) + ' veces lo que te saca una perdedora.');
    if (e.dias_ganadoras != null && e.dias_perdedoras != null) {
      tile('Cuánto aguantás', e.dias_ganadoras + ' vs ' + e.dias_perdedoras + ' días', e.dias_ganadoras >= e.dias_perdedoras
        ? 'Mantuviste las ganadoras más tiempo que las perdedoras.'
        : 'Vendiste las ganadoras más rápido que las perdedoras.');
    }
    tile('Lo que se llevaron las comisiones', usd(e.gastos), e.gastos_pct == null ? 'Sobre ventas y cobros.' : e.gastos_pct + '% de lo que ganaste antes de comisiones y derechos.');
    if (e.top_pct != null && e.top_tickers.length) {
      const t = e.top_tickers;
      tile('Concentración', e.top_pct + '%', 'de tu ganancia vino de ' + (t.length > 1 ? t.slice(0, -1).join(', ') + ' y ' + t[t.length - 1] : t[0]) + '.');
    }
    tile('Renta pasiva, últimos 12 meses', usd(e.renta_12m), e.renta_var_pct != null
      ? pct(e.renta_var_pct) + ' contra los 12 meses anteriores (' + usd(e.renta_12m_previos) + ').'
      : 'Primer año con renta.');
  }

  function fillTop(sel, rows) {
    const tb = $(sel); tb.replaceChildren();
    for (const r of rows) {
      const tr = document.createElement('tr');
      td(tr, r.ticker, 'l bz-tk'); td(tr, dfmt(r.fecha), 'l muted'); td(tr, String(r.dias), 'muted');
      td(tr, pct(r.rend), pn(r.rend)); td(tr, usd2(r.resultado), pn(r.resultado));
      tb.appendChild(tr);
    }
    if (!rows.length) { const tr = document.createElement('tr'); td(tr, 'Sin ventas para mostrar.', 'l muted').colSpan = 5; tb.appendChild(tr); }
  }

  function fillAnual() {
    const rows = data.rendimiento_anual;
    const conRend = rows.filter((r) => r.rendimiento != null);
    setTxt('#a-tir', data.tir == null ? '—' : pct(data.tir));
    const mejor = conRend.reduce((a, b) => (!a || b.rendimiento > a.rendimiento ? b : a), null);
    const peor = conRend.reduce((a, b) => (!a || b.rendimiento < a.rendimiento ? b : a), null);
    setTxt('#a-mejor', mejor ? mejor.anio + ' · ' + pct(mejor.rendimiento) : '—', mejor ? pn(mejor.rendimiento) : '');
    setTxt('#a-peor', peor && conRend.length > 1 ? peor.anio + ' · ' + pct(peor.rendimiento) : '—', peor && conRend.length > 1 ? pn(peor.rendimiento) : '');
    $('#anual-nota').textContent = data.renta_sin_capital
      ? 'Los intereses de caución de Balanz (' + usd(data.renta_sin_capital) + ') cuentan en los totales pero no acá: Balanz no informa cuánto se colocó en cada una.'
      : '';
    const tb = $('#t-anual tbody'); tb.replaceChildren();
    const max = Math.max(1, ...conRend.map((r) => Math.abs(r.rendimiento)));
    for (const r of rows) {
      const tr = document.createElement('tr');
      const c = td(tr, r.anio, 'l bz-tk');
      if (r.parcial) {
        const tag = document.createElement('span'); tag.className = 'bz-anio-tag';
        const desde = r.desde.slice(5, 7) !== '01' || r.desde.slice(8) !== '01', m = (s) => MESES[Number(s.slice(5, 7)) - 1].toLowerCase();
        tag.textContent = desde ? 'desde ' + m(r.desde) : 'a ' + m(r.hasta);
        c.appendChild(tag);
      }
      td(tr, sgn(r.compraventa), pn(r.compraventa) + ' bz-hide-sm');
      td(tr, sgn(r.renta), pn(r.renta) + ' bz-hide-sm');
      td(tr, sgn(r.resultado), pn(r.resultado));
      td(tr, usd(r.capital), 'muted');
      td(tr, pct(r.rendimiento), r.rendimiento == null ? 'muted' : pn(r.rendimiento));
      const bc = td(tr, '', 'bz-hide-sm'); const track = document.createElement('span'); track.className = 'bz-rbar';
      if (r.rendimiento != null) {
        const bar = document.createElement('span'); const w = (Math.abs(r.rendimiento) / max) * 45;
        bar.style.width = Math.max(1.5, w) + 'px'; bar.style.left = r.rendimiento >= 0 ? '45px' : (45 - w) + 'px';
        bar.style.background = r.rendimiento >= 0 ? 'var(--bz-pos)' : 'var(--bz-neg)'; track.appendChild(bar);
      }
      bc.appendChild(track); tb.appendChild(tr);
    }
  }

  function fillRaros() {
    const rows = data.no_reconocidos, sec = $('#raros');
    sec.hidden = !rows.length;
    const tb = $('#tb-raros'); tb.replaceChildren();
    for (const r of rows) {
      const tr = document.createElement('tr');
      td(tr, r.broker, 'l muted'); td(tr, dfmt(r.fecha), 'l muted'); td(tr, r.ticker, 'l bz-tk'); td(tr, r.movimiento, 'l'); td(tr, r.motivo, 'l muted');
      tb.appendChild(tr);
    }
  }

  // ---------- todo junto ----------
  const notaMejores = $('#nota-mejores');
  notaMejores.textContent = 'Por resultado en dólares de cada lote vendido.' + (data.excluidos.length
    ? ' ' + data.excluidos.join(' y ') + (data.excluidos.length === 1 ? ' queda' : ' quedan') + ' afuera: un cambio de ratio dejó lotes con costo cero que distorsionan la comparación.'
    : '');

  // Sin posiciones abiertas la tarjeta de cartera no dice nada: se saca y la
  // grilla reparte el ancho entre las otras dos. Tiene que ser antes de
  // dibujar, porque cada gráfico toma el ancho de su tarjeta.
  $('#chart-mix').closest('.bz-card').hidden = !data.cartera_mix.length;
  const drawCharts = () => { if (!d3) return; drawAnios(); drawClases(); drawMix(); drawCal(); drawScatter(); drawRenta(); };
  const renderAll = () => { fillHero(); fillMaster(); fillDetail(); fillCobros(); fillTiles(); fillTop('#tb-mejores', data.mejores); fillTop('#tb-peores', data.peores); fillAnual(); fillRaros(); drawCharts(); };

  const eye = $('#bz-eye');
  const syncEye = () => {
    bz.classList.toggle('bz-oculto', st.oculto);
    eye.setAttribute('aria-pressed', String(st.oculto));
    eye.setAttribute('aria-label', st.oculto ? 'Mostrar montos' : 'Ocultar montos'); eye.title = eye.getAttribute('aria-label');
    eye.querySelector('.lbl').textContent = st.oculto ? 'Mostrar montos' : 'Ocultar montos';
  };
  eye.onclick = () => { st.oculto = !st.oculto; syncEye(); renderAll(); };
  syncEye();
  renderAll();

  let vivo = true, ancho = bz.clientWidth;
  const ro = new ResizeObserver(() => { if (bz.clientWidth !== ancho) { ancho = bz.clientWidth; drawCharts(); } });
  ro.observe(bz);
  cargarD3().then((m) => { if (vivo) { d3 = m; drawCharts(); } }).catch(() => {
    for (const id of ['#chart-anio', '#chart-clase', '#chart-mix', '#chart-cal', '#chart-scatter', '#chart-renta']) vacio($(id), 'No se pudieron cargar los gráficos.');
  });
  return () => { vivo = false; ro.disconnect(); };
}
