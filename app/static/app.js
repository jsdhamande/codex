const state = {
  token: null,
  me: null,
  features: {},
  view: 'dashboard',
  analysisSymbol: 'NSE:INFY',
};

const navItems = ['dashboard', 'trade', 'watchlist', 'analysis', 'portfolio', 'alerts', 'configuration', 'admin'];


function normalizeSymbol(value) {
  const raw = (value || '').trim().toUpperCase();
  if (!raw) return '';
  return raw.includes(':') ? raw : `NSE:${raw}`;
}

function formatInr(price) {
  if (!Number.isFinite(price)) return '--';
  return `₹${price.toFixed(2)}`;
}

async function updateQuote(symbolInputId, priceInputId, quoteLabelId) {
  const input = document.getElementById(symbolInputId);
  const symbol = normalizeSymbol(input?.value || '');
  if (!symbol) return;
  try {
    const quote = await api(`/api/quote?symbol=${encodeURIComponent(symbol)}`);
    if (priceInputId) {
      const priceInput = document.getElementById(priceInputId);
      if (priceInput && Number(quote.price) > 0) priceInput.value = Number(quote.price).toFixed(2);
    }
    if (quoteLabelId) {
      const label = document.getElementById(quoteLabelId);
      if (label) label.innerText = `Current price: ${formatInr(Number(quote.price))}`;
    }
  } catch (e) {
    const label = document.getElementById(quoteLabelId);
    if (label) label.innerText = 'Current price: unavailable';
  }
}

function attachStockAssist(symbolInputId, listId, quoteLabelId, priceInputId = null) {
  const input = document.getElementById(symbolInputId);
  const list = document.getElementById(listId);
  if (!input || !list) return;
  input.setAttribute('list', listId);

  const refreshSuggestions = async () => {
    const q = input.value.trim();
    try {
      const data = await api(`/api/stock-search?q=${encodeURIComponent(q)}&limit=8`);
      list.innerHTML = (data.results || []).map((r) => `<option value="${r.symbol}">${r.name || r.symbol}</option>`).join('');
    } catch (_e) {
      list.innerHTML = '';
    }
  };

  input.addEventListener('input', refreshSuggestions);
  input.addEventListener('focus', refreshSuggestions);
  input.addEventListener('change', () => updateQuote(symbolInputId, priceInputId, quoteLabelId));
  refreshSuggestions();
}


function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  return fetch(path, { ...options, headers }).then(async (r) => {
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.detail || 'Request failed');
    return body;
  });
}

function renderNav() {
  const nav = document.getElementById('navList');
  nav.innerHTML = '';
  navItems.forEach((i) => {
    if (i === 'admin' && state.me.user.role !== 'admin') return;
    if (i !== 'admin' && !state.features[i]) return;
    const li = document.createElement('li');
    li.className = 'nav-item';
    li.innerHTML = `<a class="nav-link ${state.view === i ? 'active': ''}">${i.toUpperCase()}</a>`;
    li.onclick = () => { state.view = i; renderNav(); renderView(); };
    nav.appendChild(li);
  });
}

function card(title, value) {
  return `<div class="col-md-4"><div class="card card-soft p-3"><h6>${title}</h6><h3>${value}</h3></div></div>`;
}

async function renderDashboard() {
  const d = await api('/api/dashboard');
  if (d.role === 'admin') {
    return `<div class="row g-3">${card('Users', d.users_count)}${card('Executed Trades Today', d.todays_executed_trades)}${card('Aggregate Holdings', d.aggregate_holdings_positions)}</div>`;
  }
  return `<div class="row g-3">${card('Orders Today', d.todays_orders)}${card('Holdings', d.holding_positions)}${card('Funds', d.fund_balance.toFixed(2))}</div>`;
}

async function renderTrade() {
  const users = state.me.user.role === 'admin' ? await api('/api/users') : [];
  const orders = await api('/api/orders');
  return `
  <div class="card card-soft p-3 mb-3">
    <h5>Place Trade</h5>
    <div class="row g-2 align-items-end">
      <div class="col-md-3"><input id="tSymbol" class="form-control" placeholder="Symbol e.g. NSE:INFY"/><datalist id="tSymbolList"></datalist><small id="tQuote" class="text-muted">Current price: --</small></div>
      <div class="col-md-2"><select id="tSide" class="form-select"><option value="buy">Buy</option><option value="sell">Sell</option></select></div>
      <div class="col-md-2"><input id="tQty" class="form-control" type="number" value="1"/></div>
      <div class="col-md-2"><input id="tPrice" class="form-control" type="number" value="100"/></div>
      ${state.me.user.role === 'admin' ? `<div class="col-md-2"><select id="tUsers" class="form-select" multiple>${users.filter(u=>u.role==='user').map(u=>`<option value='${u.id}'>${u.username}</option>`).join('')}</select></div>`: ''}
      <div class="col-md-1"><button id="placeTrade" class="btn btn-primary w-100">Submit</button></div>
    </div>
  </div>
  <div class="card card-soft p-3">
    <h5>Orders</h5>
    <div class="table-wrap"><table class="table"><thead><tr><th>ID</th><th>User</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Status</th><th>Action</th></tr></thead>
    <tbody>${orders.map(o=>`<tr><td>${o.id}</td><td>${o.username || state.me.user.username}</td><td>${o.symbol}</td><td>${o.side}</td><td>${o.quantity}</td><td>${o.status}</td><td>${state.me.user.role==='admin' && o.status==='open' ? `<button class='btn btn-sm btn-success' onclick='window.execOrder(${o.id})'>Execute</button>`:''}</td></tr>`).join('')}</tbody></table></div>
  </div>`;
}

async function renderWatchlist() {
  const lists = await api('/api/watchlists');
  return `<div class='card card-soft p-3 mb-3'><h5>Create Watchlist</h5><div class='d-flex gap-2'><input id='wName' class='form-control' placeholder='Long term'/><button id='createW' class='btn btn-primary'>Create</button></div></div>
  ${lists.map(w => `<div class='card card-soft p-3 mb-2'><h6>${w.name} (#${w.id})</h6><p>${(w.symbols||[]).join(', ') || 'No symbols yet'}</p><div class='d-flex gap-2 align-items-end'><div class='w-100'><input id='sym-${w.id}' class='form-control' placeholder='Add symbol'/><datalist id='sym-list-${w.id}'></datalist><small id='sym-quote-${w.id}' class='text-muted'>Current price: --</small></div><button class='btn btn-outline-primary' onclick='window.addSym(${w.id})'>Add</button></div></div>`).join('')}`;
}

function renderAnalysis() {
  return `<div class='card card-soft p-3'><h5>Analysis</h5><p>Search any stock and load the TradingView chart (Kite backed).</p><div class='row g-2 mb-2 align-items-end'><div class='col-md-5'><input id='analysisSymbol' class='form-control' placeholder='NSE:INFY' value='${state.analysisSymbol || 'NSE:INFY'}'/><datalist id='analysisSymbolList'></datalist><small id='analysisQuote' class='text-muted'>Current price: --</small></div><div class='col-md-2'><button id='loadAnalysisSymbol' class='btn btn-outline-primary'>Load Chart</button></div></div><div id='tvchart' style='height:520px'></div></div>`;
}

function buildTradingViewDatafeed() {
  return {
    onReady: async (cb) => {
      const config = await api('/api/tradingview/config');
      setTimeout(() => cb(config), 0);
    },
    searchSymbols: async (userInput, exchange, symbolType, onResult) => {
      try {
        const data = await api(`/api/stock-search?q=${encodeURIComponent(userInput || '')}&exchange=${encodeURIComponent(exchange || 'NSE')}&limit=15`);
        onResult((data.results || []).map((r) => ({
          symbol: r.symbol,
          full_name: r.symbol,
          description: r.name || r.symbol,
          exchange: (r.symbol.split(':')[0] || 'NSE'),
          ticker: r.symbol,
          type: symbolType || 'stock',
        })));
      } catch (_e) {
        onResult([]);
      }
    },
    resolveSymbol: async (symbolName, onResolve, onError) => {
      try {
        const info = await api(`/api/tradingview/symbols?symbol=${encodeURIComponent(symbolName)}`);
        onResolve(info);
      } catch (e) {
        onError(e.message);
      }
    },
    getBars: async (symbolInfo, resolution, periodParams, onHistory, onError) => {
      try {
        const from = periodParams.from || Math.floor(Date.now() / 1000) - (7 * 24 * 60 * 60);
        const to = periodParams.to || Math.floor(Date.now() / 1000);
        const data = await api(`/api/tradingview/history?symbol=${encodeURIComponent(symbolInfo.ticker || symbolInfo.name)}&resolution=${encodeURIComponent(String(resolution))}&from=${from}&to=${to}`);
        if (data.s !== 'ok') {
          onHistory([], { noData: true });
          return;
        }

        const bars = data.t.map((t, i) => ({
          time: t * 1000,
          open: data.o[i],
          high: data.h[i],
          low: data.l[i],
          close: data.c[i],
          volume: data.v[i],
        }));
        onHistory(bars, { noData: bars.length === 0 });
      } catch (e) {
        onError(e.message);
      }
    },
    subscribeBars: () => {},
    unsubscribeBars: () => {},
  };
}

async function renderPortfolio() {
  const p = await api('/api/portfolio');
  const conditional = await api('/api/conditional-orders');
  return `<div class='card card-soft p-3 mb-3'><h5>Holdings</h5><table class='table'><thead><tr><th>User</th><th>Symbol</th><th>Qty</th><th>Avg Price</th></tr></thead><tbody>${p.holdings.map(h=>`<tr><td>${h.username || state.me.user.username}</td><td>${h.symbol}</td><td>${h.quantity}</td><td>${h.avg_price}</td></tr>`).join('')}</tbody></table></div>
  <div class='card card-soft p-3 mb-3'><h5>Portfolio Review Action</h5><div class='row g-2'><div class='col'><input id='cSymbol' class='form-control' placeholder='Symbol'/><datalist id='cSymbolList'></datalist><small id='cQuote' class='text-muted'>Current price: --</small></div><div class='col'><select id='cAction' class='form-select'><option value='buy_more'>Buy More</option><option value='sell_qty'>Sell Quantity</option><option value='buy_if'>Buy if</option><option value='sell_if'>Sell if</option></select></div><div class='col'><select id='cType' class='form-select'><option value='closes_above'>Price closes above</option><option value='closes_below'>Price closes below</option><option value='reaches'>Price reaches</option></select></div><div class='col'><input id='cValue' class='form-control' type='number' placeholder='Trigger value'/></div><div class='col'><input id='cQty' class='form-control' type='number' value='1'/></div><div class='col'><button id='addCond' class='btn btn-primary'>Add</button></div></div></div>
  <div class='card card-soft p-3'><h5>Conditional Orders</h5><ul>${conditional.map(c=>`<li>${c.symbol} ${c.action} when ${c.condition_type} ${c.trigger_value} qty ${c.quantity}</li>`).join('')}</ul></div>`;
}

async function renderAlerts() {
  const alerts = await api('/api/alerts');
  return `<div class='card card-soft p-3 mb-3'><h5>Create Alert</h5><div class='row g-2'><div class='col'><input id='aSymbol' class='form-control' placeholder='NSE:RELIANCE'/><datalist id='aSymbolList'></datalist><small id='aQuote' class='text-muted'>Current price: --</small></div><div class='col'><select id='aCond' class='form-select'><option value='reaches'>Price reaches to</option><option value='closes_above'>Price closes above</option><option value='closes_below'>Price closes below</option></select></div><div class='col'><input id='aValue' type='number' class='form-control' placeholder='value'/></div><div class='col'><select id='aDur' class='form-select'><option>15m</option><option>30m</option><option>1h</option><option>4h</option><option>1d</option><option>1w</option><option>1mo</option></select></div><div class='col'><button id='createAlert' class='btn btn-primary'>Create</button></div></div></div>
  <div class='card card-soft p-3'><h5>Active Alerts</h5><ul>${alerts.map(a=>`<li>${a.symbol} ${a.condition} ${a.value} (${a.duration})</li>`).join('')}</ul></div>`;
}

async function renderConfiguration() {
  const funds = await api('/api/funds');
  const kite = await api('/api/kite/config');
  return `<div class='card card-soft p-3 mb-3'><h5>Configuration</h5><p>Fund balance: <strong>${funds.balance.toFixed(2)}</strong></p><div class='d-flex gap-2'><input id='maxInvest' type='number' class='form-control' placeholder='Max investment per stock'/><button id='saveMax' class='btn btn-primary'>Save</button></div></div>
  <div class='card card-soft p-3'>
    <h5>Kite Broker Setup</h5>
    <p class='mb-1'>Configure Kite once with API key + API secret, then use <strong>Login with Kite</strong> to fetch the access token automatically.</p>
    <small class='text-muted d-block mb-3'>Connection status: ${kite.is_connected ? `Connected as ${kite.kite_user_name || 'Kite user'}` : 'Not connected'}</small>
    <div class='row g-2 mb-2'>
      <div class='col-md-5'><input id='kiteApiKey' class='form-control' placeholder='Kite API Key'/></div>
      <div class='col-md-5'><input id='kiteApiSecret' type='password' class='form-control' placeholder='Kite API Secret'/></div>
      <div class='col-md-2'><button id='saveKiteConfig' class='btn btn-outline-primary w-100'>Save</button></div>
    </div>
    <button id='kiteLogin' class='btn btn-primary'>Login with Kite</button>
  </div>`;
}

async function renderAdmin() {
  const users = await api('/api/users');
  return `<div class='card card-soft p-3 mb-3'><h5>User Management</h5><div class='row g-2'><div class='col'><input id='nUser' class='form-control' placeholder='username'/></div><div class='col'><input id='nPass' class='form-control' placeholder='password'/></div><div class='col'><select id='nRole' class='form-select'><option value='user'>user</option><option value='admin'>admin</option></select></div><div class='col'><button id='createUser' class='btn btn-primary'>Add User</button></div></div></div>
  <div class='card card-soft p-3'><table class='table'><thead><tr><th>ID</th><th>User</th><th>Role</th><th>Max/Stock</th><th>Features</th><th></th></tr></thead><tbody>${users.map(u=>`<tr><td>${u.id}</td><td>${u.username}</td><td>${u.role}</td><td>${u.max_investment_per_stock}</td><td>${['dashboard','trade','watchlist','analysis','portfolio','alerts','configuration'].map(f=>`<label class='me-2'><input type='checkbox' onchange='window.toggleFeature(${u.id},"${f}", this.checked)' checked/>${f}</label>`).join('')}</td><td>${u.role==='user'?`<button class='btn btn-danger btn-sm' onclick='window.delUser(${u.id})'>Delete</button>`:''}</td></tr>`).join('')}</tbody></table></div>`;
}

async function renderView() {
  const content = document.getElementById('content');
  document.getElementById('screenTitle').innerText = state.view.toUpperCase();
  const mapping = {
    dashboard: renderDashboard,
    trade: renderTrade,
    watchlist: renderWatchlist,
    analysis: async () => renderAnalysis(),
    portfolio: renderPortfolio,
    alerts: renderAlerts,
    configuration: renderConfiguration,
    admin: renderAdmin,
  };
  content.innerHTML = await mapping[state.view]();

  bindActions();
  if (state.view === 'analysis' && window.TradingView) {
    const symbol = state.analysisSymbol || 'NSE:INFY';
    new TradingView.widget({
      autosize: true,
      symbol,
      interval: '60',
      datafeed: buildTradingViewDatafeed(),
      container_id: 'tvchart',
      theme: 'light',
      style: '1',
      locale: 'en',
      toolbar_bg: '#f1f3f6',
      enable_publishing: false,
      hide_top_toolbar: false,
      withdateranges: true,
      studies: [],
    });
  }
}

function bindActions() {
  document.getElementById('placeTrade')?.addEventListener('click', async () => {
    try {
      const selected = Array.from(document.getElementById('tUsers')?.selectedOptions || []).map(o => Number(o.value));
      await api('/api/trades', { method: 'POST', body: JSON.stringify({
        symbol: normalizeSymbol(document.getElementById('tSymbol').value),
        side: document.getElementById('tSide').value,
        quantity: Number(document.getElementById('tQty').value),
        price: Number(document.getElementById('tPrice').value),
        user_ids: selected.length ? selected : null,
      }) });
      renderView();
    } catch (e) { alert(e.message); }
  });

  document.getElementById('createW')?.addEventListener('click', async () => {
    await api('/api/watchlists', { method: 'POST', body: JSON.stringify({ name: document.getElementById('wName').value }) });
    renderView();
  });

  document.getElementById('createAlert')?.addEventListener('click', async () => {
    await api('/api/alerts', { method: 'POST', body: JSON.stringify({
      symbol: normalizeSymbol(document.getElementById('aSymbol').value),
      condition: document.getElementById('aCond').value,
      value: Number(document.getElementById('aValue').value),
      duration: document.getElementById('aDur').value,
    }) });
    renderView();
  });

  document.getElementById('addCond')?.addEventListener('click', async () => {
    await api('/api/conditional-orders', { method: 'POST', body: JSON.stringify({
      symbol: normalizeSymbol(document.getElementById('cSymbol').value),
      action: document.getElementById('cAction').value,
      condition_type: document.getElementById('cType').value,
      trigger_value: Number(document.getElementById('cValue').value),
      quantity: Number(document.getElementById('cQty').value),
    }) });
    renderView();
  });

  document.getElementById('saveMax')?.addEventListener('click', async () => {
    await api(`/api/users/${state.me.user.id}/max-investment`, { method: 'PUT', body: JSON.stringify({ value: Number(document.getElementById('maxInvest').value) }) });
    alert('Saved');
  });


  document.getElementById('saveKiteConfig')?.addEventListener('click', async () => {
    try {
      await api('/api/kite/config', { method: 'PUT', body: JSON.stringify({
        api_key: document.getElementById('kiteApiKey').value.trim(),
        api_secret: document.getElementById('kiteApiSecret').value.trim(),
      }) });
      alert('Kite API credentials saved.');
      renderView();
    } catch (e) {
      alert(e.message);
    }
  });

  document.getElementById('kiteLogin')?.addEventListener('click', async () => {
    try {
      const data = await api('/api/kite/login-url', { method: 'POST' });
      const popup = window.open(data.url, 'kite-login', 'width=640,height=780');
      if (!popup) {
        alert('Popup blocked. Please allow popups and retry Kite login.');
      }
    } catch (e) {
      alert(e.message);
    }
  });



  attachStockAssist('tSymbol', 'tSymbolList', 'tQuote', 'tPrice');
  attachStockAssist('aSymbol', 'aSymbolList', 'aQuote');
  attachStockAssist('cSymbol', 'cSymbolList', 'cQuote');
  updateQuote('tSymbol', 'tPrice', 'tQuote');

  document.getElementById('loadAnalysisSymbol')?.addEventListener('click', async () => {
    state.analysisSymbol = normalizeSymbol(document.getElementById('analysisSymbol').value);
    if (!state.analysisSymbol) return;
    renderView();
  });
  attachStockAssist('analysisSymbol', 'analysisSymbolList', 'analysisQuote');

  document.querySelectorAll('input[id^="sym-"]').forEach((el) => {
    const wid = el.id.replace('sym-', '');
    attachStockAssist(`sym-${wid}`, `sym-list-${wid}`, `sym-quote-${wid}`);
  });

  document.getElementById('createUser')?.addEventListener('click', async () => {
    await api('/api/users', { method: 'POST', body: JSON.stringify({ username: nUser.value, password: nPass.value, role: nRole.value, initial_funds: 100000 })});
    renderView();
  });
}

window.execOrder = async (id) => { await api(`/api/orders/${id}/execute`, { method: 'POST' }); renderView(); };
window.delUser = async (id) => { await api(`/api/users/${id}`, { method: 'DELETE' }); renderView(); };
window.toggleFeature = async (uid, feature, enabled) => { await api(`/api/users/${uid}/features/${feature}`, { method: 'PUT', body: JSON.stringify({enabled}) }); };
window.addSym = async (id) => {
  const el = document.getElementById(`sym-${id}`);
  await api(`/api/watchlists/${id}/items`, { method: 'POST', body: JSON.stringify({ symbol: normalizeSymbol(el.value) }) });
  renderView();
};

document.getElementById('loginBtn').addEventListener('click', async () => {
  try {
    const data = await api('/api/login', { method: 'POST', body: JSON.stringify({ username: username.value, password: password.value }) });
    state.token = data.token;
    state.features = data.features;
    state.me = await api('/api/me');
    loginPane.classList.add('d-none');
    mainPane.classList.remove('d-none');
    whoami.innerText = `${state.me.user.username} (${state.me.user.role})`;
    renderNav();
    renderView();
  } catch (e) {
    loginError.innerText = e.message;
  }
});


window.addEventListener('message', async (event) => {
  if (event.origin !== window.location.origin) return;
  if (event.data?.type !== 'kite-auth') return;
  if (!event.data.requestToken || event.data.status !== 'success') {
    alert('Kite login failed or cancelled.');
    return;
  }

  try {
    const result = await api('/api/kite/exchange-session', {
      method: 'POST',
      body: JSON.stringify({ request_token: event.data.requestToken }),
    });
    alert(`Kite connected successfully${result.kite_user_name ? ` as ${result.kite_user_name}` : ''}.`);
    if (state.view === 'configuration') renderView();
  } catch (e) {
    alert(e.message);
  }
});

document.getElementById('logoutBtn').addEventListener('click', () => location.reload());
