(() => {
  const svg = document.getElementById('stadium-svg');
  const viewport = document.getElementById('viewport');
  const fieldLayer = document.getElementById('field-layer');
  const layer = document.getElementById('seats-layer');
  const tooltip = document.getElementById('seat-tooltip');
  const btnIn = document.getElementById('zoom-in');
  const btnOut = document.getElementById('zoom-out');
  const sectorDetail = document.getElementById('sector-detail');
  const sectorTitle = document.getElementById('sector-title');
  const sectorCaption = document.getElementById('sector-caption');
  const sectorGrid = document.getElementById('sector-grid');
  const sectorBack = document.getElementById('sector-back');
  const cartPanel = document.getElementById('cart-panel');
  const cartList = document.getElementById('cart-list');
  const cartTotal = document.getElementById('cart-total');
  const checkoutBtn = document.getElementById('checkout-btn');
  const data = window.SEATING;
  if (!svg || !viewport || !layer || !fieldLayer || !data) return;
  
  // Store for selected seats: Set of "SECTOR:ROW:SEAT" strings
  const selectedSeats = new Set();
  const seatPrices = {}; // Cache prices: "SECTOR:ROW:SEAT" => price

  const COLORS = { VIP:'#ef4444', STANDARD:'#f59e0b', FAN:'#10b981', TAKEN:'#9ca3af' };
  const TEXT = { VIP:8, STANDARD:9, FAN:10 };

  // Tooltip behavior: fixed to viewport, follows cursor
  const showTip = (e, text) => {
    tooltip.textContent = text;
    tooltip.style.display = 'block';
    const pad = 12;
    let x = e.clientX + pad;
    let y = e.clientY + pad;
    // prevent overflow
    const w = tooltip.offsetWidth || 160;
    const h = tooltip.offsetHeight || 30;
    if (x + w > window.innerWidth - 8) x = window.innerWidth - w - 8;
    if (y + h > window.innerHeight - 8) y = window.innerHeight - h - 8;
    tooltip.style.position = 'fixed';
    tooltip.style.left = x + 'px';
    tooltip.style.top = y + 'px';
  };
  const hideTip = () => { tooltip.style.display = 'none'; };

  // Zoom handling
  const center = { x:300, y:300 };
  let scale = 0.85;
  const applyTransform = () => {
    viewport.setAttribute('transform', `translate(${center.x},${center.y}) scale(${scale}) translate(${-center.x},${-center.y})`);
  };
  const clamp = (v,min,max)=>Math.max(min,Math.min(max,v));
  btnIn?.addEventListener('click', ()=>{ scale = clamp(scale*1.15, 0.6, 2.5); applyTransform(); });
  btnOut?.addEventListener('click', ()=>{ scale = clamp(scale/1.15, 0.6, 2.5); applyTransform(); });
  applyTransform();

  // Draw rectangular football field
  function drawField() {
    const fieldW = 360;
    const fieldH = 220;
    const x = center.x - fieldW/2;
    const y = center.y - fieldH/2;
    // clear previous
    while (fieldLayer.firstChild) fieldLayer.removeChild(fieldLayer.firstChild);
    const stripeW = fieldW/8;
    for (let i=0;i<8;i++){
      const rect = document.createElementNS('http://www.w3.org/2000/svg','rect');
      rect.setAttribute('x', String(x + i*stripeW));
      rect.setAttribute('y', String(y));
      rect.setAttribute('width', String(stripeW));
      rect.setAttribute('height', String(fieldH));
      rect.setAttribute('fill', i%2===0 ? '#2ca25f' : '#28a058');
      rect.setAttribute('opacity','0.85');
      fieldLayer.appendChild(rect);
    }
    const outline = document.createElementNS('http://www.w3.org/2000/svg','rect');
    outline.setAttribute('x', String(x));
    outline.setAttribute('y', String(y));
    outline.setAttribute('width', String(fieldW));
    outline.setAttribute('height', String(fieldH));
    outline.setAttribute('fill','none');
    outline.setAttribute('stroke','#e5f4ea');
    outline.setAttribute('stroke-width','6');
    fieldLayer.appendChild(outline);

    // Midline
    const mid = document.createElementNS('http://www.w3.org/2000/svg','line');
    mid.setAttribute('x1', String(center.x));
    mid.setAttribute('y1', String(y));
    mid.setAttribute('x2', String(center.x));
    mid.setAttribute('y2', String(y + fieldH));
    mid.setAttribute('stroke','#e5f4ea');
    mid.setAttribute('stroke-width','4');
    fieldLayer.appendChild(mid);

    // Center circle
    const circle = document.createElementNS('http://www.w3.org/2000/svg','circle');
    circle.setAttribute('cx', String(center.x));
    circle.setAttribute('cy', String(center.y));
    circle.setAttribute('r', '28');
    circle.setAttribute('fill','none');
    circle.setAttribute('stroke','#e5f4ea');
    circle.setAttribute('stroke-width','4');
    fieldLayer.appendChild(circle);
  }
  drawField();

  const order = ['VIP','STANDARD','FAN'];
  // Instead of drawing каждое место на арене — рисуем «сектора-дуги»,
  // а подробные места показываем ниже, в гриде.
  layer.innerHTML = '';

  // normalize layout keys (accept vip/standard/fan in any case) and fallback defaults
  const rawLayout = (data && data.layout) ? data.layout : {};
  const layout = {};
  Object.keys(rawLayout || {}).forEach(k => layout[k.toUpperCase()] = rawLayout[k]);
  if (!layout['VIP'] && !layout['STANDARD'] && !layout['FAN']) {
    layout['VIP'] = { rows: 6, seats_per_row: 48, price_coef: 2.0 };
    layout['STANDARD'] = { rows: 10, seats_per_row: 72, price_coef: 1.0 };
    layout['FAN'] = { rows: 8, seats_per_row: 64, price_coef: 0.7 };
  }

  const centerAngles = {
    EAST: -Math.PI,      // справа
    NORTH: -Math.PI/2,   // сверху
    WEST: 0,             // слева
    SOUTH: Math.PI/2     // снизу
  };
  const tribunes = ['NORTH','EAST','SOUTH','WEST'];
  const tribunesByCat = {
    VIP: tribunes,
    STANDARD: ['NORTH','SOUTH'],
    FAN: ['EAST','WEST']
  };
  const segmentCount = { VIP: 8, STANDARD: 12, FAN: 16 };
  const ringsByCat = { VIP: 1, STANDARD: 2, FAN: 1 };
  const standardOffsets = [-124, 92];
  const colorByRing = {
    STANDARD: ['#f59e0b', '#f59e0b'],
    VIP: ['#ef4444'],
    FAN: ['#10b981']
  };

  // Taken set for uniqueness checks
  const taken = new Set(data.taken.map(([s, r, n]) => `${s}:${r}:${n}`));

  // Helpers for ring sizes (увеличен зазор от поля, чтобы дуги не залезали на газон)
  const fieldRx = 180, fieldRy = 110;
  const basePadding = 130;
  const ringThickness = 18;
  const tierOffset = { VIP:0, STANDARD:1, FAN:3 };
  const rxFor = (cat) => fieldRx + basePadding + tierOffset[cat]*70;
  const ryFor = (cat) => fieldRy + basePadding + tierOffset[cat]*52;

  function drawOutline(){
    const outline = document.createElementNS('http://www.w3.org/2000/svg','ellipse');
    outline.setAttribute('cx','300'); outline.setAttribute('cy','300');
    outline.setAttribute('rx', String(fieldRx + basePadding + tierOffset['FAN']*70 + 36));
    outline.setAttribute('ry', String(fieldRy + basePadding + tierOffset['FAN']*52 + 28));
    outline.setAttribute('fill','none');
    outline.setAttribute('stroke','#e5e7eb');
    outline.setAttribute('stroke-width','24');
    outline.setAttribute('opacity','0.6');
    layer.appendChild(outline);
  }

  function sweepPath(cx, cy, rx1, ry1, rx2, ry2, a1, a2) {
    const p = (rx, ry, a) => [cx + rx*Math.cos(a), cy + ry*Math.sin(a)];
    const [x1,y1] = p(rx1, ry1, a1);
    const [x2,y2] = p(rx1, ry1, a2);
    const [x3,y3] = p(rx2, ry2, a2);
    const [x4,y4] = p(rx2, ry2, a1);
    const laf = (a2 - a1) % (2*Math.PI) > Math.PI ? 1 : 0;
    return `M ${x1} ${y1} A ${rx1} ${ry1} 0 ${laf} 1 ${x2} ${y2}
            L ${x3} ${y3} A ${rx2} ${ry2} 0 ${laf} 0 ${x4} ${y4} Z`;
  }

  function sectorCode(cat, tribune, idx, ringIndex) {
    // cat-VIP/STD/FAN + первая буква трибуны + порядковый + номер кольца если есть
    const c = cat === 'STANDARD' ? 'STD' : cat;
    const ring = ringIndex !== undefined && ringIndex > 0 ? `-R${ringIndex}` : '';
    return `${c}-${tribune[0]}${String(idx+1).padStart(2,'0')}${ring}`;
  }

  function drawArena() {
    // фоновые эллипсы трибун (серые), текстовые подписи
    const labelMap = { NORTH:'Северная трибуна', SOUTH:'Южная трибуна', EAST:'Восточная трибуна', WEST:'Западная трибуна' };
    Object.entries(labelMap).forEach(([key, label])=>{
      const t = document.createElementNS('http://www.w3.org/2000/svg','text');
      const pos = {
        NORTH:[300, 60, 'middle'],
        SOUTH:[300, 560, 'middle'],
        EAST:[540, 310, 'start'],
        WEST:[60, 310, 'end']
      }[key];
      t.setAttribute('x', String(pos[0]));
      t.setAttribute('y', String(pos[1]));
      t.setAttribute('text-anchor', pos[2]);
      t.setAttribute('style','font-size:12px;fill:#475569;font-weight:700');
      t.textContent = label;
      layer.appendChild(t);
    });

    // дуги-сектора
    let drawn = 0;
    order.forEach(cat => {
      if (!layout[cat]) return;
      const catTribunes = tribunesByCat[cat] || tribunes;
      const perTribune = Math.floor(segmentCount[cat] / catTribunes.length);
      const rings = ringsByCat[cat] || 1;
      for (let ringIndex = 0; ringIndex < rings; ringIndex++) {
        const base = ringIndex * (ringThickness * 2 + 8);
        const ringOffset = cat === 'STANDARD' ? standardOffsets[ringIndex] : base;
        const rxOuter = rxFor(cat) + ringThickness + ringOffset;
        const ryOuter = ryFor(cat) + ringThickness + ringOffset * 0.8;
        const rxInner = rxFor(cat) - ringThickness + ringOffset;
        const ryInner = ryFor(cat) - ringThickness + ringOffset * 0.8;
        catTribunes.forEach((trib)=>{
          const baseAngle = centerAngles[trib];
          const spread = Math.PI/2 * 0.9; // ширина трибуны
          for (let i=0;i<perTribune;i++){
            const start = baseAngle - spread/2 + (i)*(spread/perTribune);
            const end   = baseAngle - spread/2 + (i+1)*(spread/perTribune);
            const path = document.createElementNS('http://www.w3.org/2000/svg','path');
            path.setAttribute('d', sweepPath(300,300, rxOuter,ryOuter, rxInner,ryInner, start, end));
            const palette = colorByRing[cat] || [];
            path.setAttribute('fill', palette[ringIndex] || COLORS[cat]);
            path.setAttribute('opacity','0.75');
            path.setAttribute('stroke','#cbd5e1');
            path.setAttribute('stroke-width','2');
            const code = sectorCode(cat, trib, i, ringIndex);
            path.dataset.code = code;
            path.dataset.cat = cat;
            path.dataset.trib = trib;
            path.dataset.ringIndex = ringIndex;
            path.dataset.sectorIndex = i + (catTribunes.indexOf(trib) * perTribune) + (ringIndex * catTribunes.length * perTribune);
            path.style.cursor = 'pointer';
            path.addEventListener('pointermove', (e)=>{
              showTip(e, `${code} • ${cat}`);
            });
            path.addEventListener('pointerleave', hideTip);
            path.addEventListener('click', (e)=>{
              renderSectorDetail(code, cat, path.dataset.sectorIndex);
            });
            layer.appendChild(path);
            drawn++;
          }
        });
      }
    });
    if (!drawn) {
      const msg = document.createElementNS('http://www.w3.org/2000/svg','text');
      msg.setAttribute('x','300'); msg.setAttribute('y','300');
      msg.setAttribute('text-anchor','middle');
      msg.setAttribute('style','font-size:14px;fill:#6b7280');
      msg.textContent = 'Нет данных схемы: проверьте layout матча';
      layer.appendChild(msg);
    }
  }

  function renderSectorDetail(code, cat, sectorIndexStr) {
    // показываем грид мест для выбранного сектора
    const cfg = layout[cat];
    if (!cfg) return;
    const rows = Number(cfg.rows) || 1;
    const perRow = Number(cfg.seats_per_row) || 1;
    const rings = ringsByCat[cat] || 1;
    const actualSegments = segmentCount[cat] * rings;
    
    const sectorIndex = Number(sectorIndexStr) || 0;
    const basePerSegment = Math.floor(perRow / actualSegments);
    const remainder = perRow % actualSegments;
    const perSegment = sectorIndex < remainder ? basePerSegment + 1 : basePerSegment;
    
    const priceCoef = Number(cfg.price_coef) || 1.0;
    const basePrice = data.basePrice || 1000; // получаем basePrice из data
    const price = Math.round(basePrice * priceCoef);
    
    sectorTitle.textContent = `Сектор ${code}`;
    sectorCaption.textContent = `${cat}. Рядов: ${rows}, мест в ряду: ~${perSegment}`;
    sectorGrid.innerHTML = '';
    sectorDetail.style.display = 'block';

    for (let r=1; r<=rows; r++){
      const rowWrapper = document.createElement('div');
      rowWrapper.className = 'row-wrapper';
      
      const rowLabel = document.createElement('div');
      rowLabel.className = 'row-label';
      rowLabel.textContent = `Ряд ${r}`;
      
      const rowDiv = document.createElement('div');
      rowDiv.className = 'row';
      for (let s=1; s<=perSegment; s++){
        const key = `${code}:${r}:${s}`;
        const isTaken = taken.has(key);
        const isSelected = selectedSeats.has(key);
        const cell = document.createElement('div');
        cell.className = 'seat' + (isTaken ? ' taken' : '') + (isSelected ? ' selected' : '');
        cell.dataset.key = key;
        cell.dataset.price = price;
        
        if (isTaken) {
          cell.textContent = s;
          cell.style.cursor = 'not-allowed';
        } else {
          const seatBtn = document.createElement('button');
          seatBtn.type = 'button';
          seatBtn.textContent = s;
          seatBtn.className = 'seat-btn';
          seatBtn.addEventListener('click', (e) => {
            e.preventDefault();
            toggleSeat(key, price, code, r, s, cat);
          });
          
          // поверх кнопки - для удаления
          const deleteBtn = document.createElement('button');
          deleteBtn.type = 'button';
          deleteBtn.className = 'seat-delete-btn';
          deleteBtn.innerHTML = '✕';
          deleteBtn.style.display = isSelected ? 'block' : 'none';
          deleteBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            toggleSeat(key, price, code, r, s, cat);
          });
          
          cell.appendChild(seatBtn);
          cell.appendChild(deleteBtn);
        }
        rowDiv.appendChild(cell);
      }
      rowWrapper.appendChild(rowLabel);
      rowWrapper.appendChild(rowDiv);
      sectorGrid.appendChild(rowWrapper);
    }
    // прокрутка к блоку
    sectorDetail.scrollIntoView({ behavior:'smooth', block:'start' });
  }

  function toggleSeat(key, price, sector, row, seat, category) {
    if (selectedSeats.has(key)) {
      selectedSeats.delete(key);
      seatPrices[key] = undefined;
    } else {
      selectedSeats.add(key);
      seatPrices[key] = price;
    }
    // Обновляем визуализацию
    const seatCell = document.querySelector(`[data-key="${key}"]`);
    if (seatCell) {
      const deleteBtn = seatCell.querySelector('.seat-delete-btn');
      if (selectedSeats.has(key)) {
        seatCell.classList.add('selected');
        if (deleteBtn) deleteBtn.style.display = 'block';
      } else {
        seatCell.classList.remove('selected');
        if (deleteBtn) deleteBtn.style.display = 'none';
      }
    }
    updateCart();
  }

  function updateCart() {
    if (!cartPanel) return;
    
    // Рассчитываем общую сумму
    let total = 0;
    selectedSeats.forEach(key => {
      total += seatPrices[key] || 0;
    });
    
    // Очищаем список
    cartList.innerHTML = '';
    
    if (selectedSeats.size === 0) {
      cartPanel.style.display = 'none';
      return;
    }
    
    cartPanel.style.display = 'block';
    
    // Добавляем места в корзину
    selectedSeats.forEach(key => {
      const [sector, row, seat] = key.split(':');
      const price = seatPrices[key] || 0;
      const item = document.createElement('div');
      item.className = 'cart-item';
      item.innerHTML = `
        <span>${sector} ряд ${row} место ${seat}</span>
        <span class="price">${price} ₽</span>
        <button type="button" class="remove-btn" data-key="${key}">✕</button>
      `;
      
      item.querySelector('.remove-btn').addEventListener('click', () => {
        toggleSeat(key, price, sector, row, seat, '');
      });
      
      cartList.appendChild(item);
    });
    
    // Обновляем общую сумму
    cartTotal.textContent = `${total} ₽`;
    
    // Показываем кнопку оформления
    if (checkoutBtn) {
      checkoutBtn.addEventListener('click', checkout);
    }
  }

  function checkout() {
    if (selectedSeats.size === 0) {
      alert('Пожалуйста, выберите хотя бы одно место');
      return;
    }
    
    // Отправляем все места для бронирования
    const seats = Array.from(selectedSeats).map(key => {
      const [sector, row, seat] = key.split(':');
      return {
        sector,
        row: parseInt(row),
        seat: parseInt(seat),
        price: seatPrices[key] || 0
      };
    });
    
    // Отправляем POST запрос
    fetch(`/match/${data.matchId}/reserve-multiple`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ seats: seats })
    })
    .then(response => {
      if (response.status === 302 || response.ok) {
        // Редирект на корзину
        window.location.href = '/cart';
      } else {
        return response.text().then(text => {
          throw new Error(text);
        });
      }
    })
    .catch(error => {
      console.error('Error:', error);
      alert('Ошибка при резервировании мест: ' + (error.message || 'неизвестная ошибка'));
    });
  }

  sectorBack?.addEventListener('click', ()=>{
    sectorDetail.style.display = 'none';
    hideTip();
  });

  drawOutline();
  drawArena();
})();
