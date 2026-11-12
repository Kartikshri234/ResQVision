/* Admin screens: dashboard, live monitoring, accidents, services (hospitals / police / cameras / users), analytics, system settings. */
(function () {
  const { esc, icon } = SC;
  const ADMIN = ['admin'];
  const SERVICE_TABS = [['Hospitals', '/admin/hospitals'], ['Police', '/admin/police-stations'], ['Cameras', '/admin/cameras'], ['Users', '/admin/users']];

  const bars = (values, labels) => {
    const max = Math.max(1, ...values);
    return `<div class="bars">${values.map((v, i) => `<div class="b"><span>${v || ''}</span><i style="height:${Math.round((v / max) * 82)}%"></i><span>${esc(labels[i])}</span></div>`).join('')}</div>`;
  };
  const hbars = (items) => {
    const max = Math.max(1, ...items.map((i) => i.count));
    return items.length ? items.map((i) => `<div class="hbar"><div class="row between"><span>${esc(i.label)}</span><b>${i.count}</b></div><div class="track"><i style="width:${(i.count / max) * 100}%"></i></div></div>`).join('') : '<p class="small muted">No data yet.</p>';
  };

  /* 10. Admin dashboard */
  SC.route('/admin/home', {
    title: 'Admin Dashboard', tab: '/admin/home', roles: ADMIN, live: 15000,
    render: async () => {
      const [s, m] = await Promise.all([SC.get('/dashboard/'), SC.get('/map/')]);
      SC.state.adminHome = { s, m };
      const days = s.daily.map((t) => t.date.split(' ')[0]);
      return `<div class="hero"><div class="small muted">Welcome back</div><h2>${esc(SC.state.user.first_name || SC.state.user.username)}</h2>
          <div class="row mt12"><button class="btn sm" style="background:#fff;color:var(--navy)" data-act="simulate">${icon('zap', 'sm')} Simulate accident</button><button class="btn sm" style="background:rgba(255,255,255,.15)" data-go="/admin/live">${icon('activity', 'sm')} Live monitoring</button></div></div>
        ${s.verification_pending ? `<div class="alertbar mt12" data-go="/admin/live">${icon('alert')}<div class="grow"><b>${s.verification_pending} detection${s.verification_pending > 1 ? 's' : ''} awaiting verification</b><div class="small">Low-confidence AI events need your review.</div></div>${icon('chevron')}</div>` : ''}
        <div class="grid2 mt12">${SC.ui.tile(s.total, 'Total accidents', 'alert', '', '/admin/accidents')}${SC.ui.tile(s.active, 'Active accidents', 'zap', 'red', '/admin/accidents?f=active')}
        ${SC.ui.tile(s.pending_responses, 'Pending responses', 'clock', 'orange', '/admin/live')}${SC.ui.tile(s.resolved, 'Resolved', 'check', 'green', '/admin/accidents?f=history')}
        ${SC.ui.tile(s.hospitals, 'Hospitals', 'hospital', '', '/admin/hospitals')}${SC.ui.tile(s.police, 'Police stations', 'shield', '', '/admin/police-stations')}</div>
        ${SC.ui.section('Accident locations')}<div class="map sm" id="map"></div>
        ${SC.ui.section('Last 7 days')}<div class="card">${bars(s.daily.map((t) => t.count), days)}</div>
        ${SC.ui.section('Recent accident alerts', 'View all', '/admin/accidents')}<div class="list">${s.recent.length ? s.recent.map((a) => SC.ui.accCard(a)).join('') : SC.ui.empty('No accidents yet', 'Use "Simulate accident" to try the workflow.', 'alert')}</div>`;
    },
    mount: (el) => { const { m } = SC.state.adminHome; SC.makeMap(el.querySelector('#map'), { markers: m.accidents.map(SC.accidentMarker), center: [28.6139, 77.2090], zoom: 11 }); },
  });
  SC.actions.simulate = async () => {
    let cams;
    try { cams = await SC.get('/cameras/'); } catch (e) { SC.toast(e.message, 'error'); return; }
    SC.formModal({
      title: 'Simulate accident', submit: 'Send simulated accident',
      note: 'Creates a test accident at a camera and runs the real alert pipeline. Tick "low confidence" to test the admin verification queue.',
      values: { camera_id: '', low_confidence: false },
      fields: [{ label: 'Camera', name: 'camera_id', type: 'select', options: [['', 'Random camera']].concat(cams.filter((c) => c.is_active).map((c) => [c.id, `${c.camera_id} - ${c.name}`])) }, { label: 'Low confidence (needs admin verification)', name: 'low_confidence', type: 'checkbox' }],
      onSubmit: async (d) => {
        const body = { low_confidence: d.low_confidence };
        if (d.camera_id) body.camera_id = Number(d.camera_id);
        const a = await SC.post('/simulate/', body);
        SC.toast(`${a.accident_id} created`, 'success');
        SC.go('/accident/' + a.id);
      },
    });
  };

  /* 11. Live monitoring */
  SC.route('/admin/live', {
    title: 'Live Monitoring', back: '/admin/home', tab: '/admin/home', roles: ADMIN, live: 5000,
    render: async () => {
      const [cams, active, pending] = await Promise.all([SC.get('/cameras/'), SC.get('/accidents/?view=active'), SC.get('/accidents/?view=new')]);
      const on = cams.filter((c) => c.is_active).length;
      return `<div class="grid2">${SC.ui.tile(`${on}/${cams.length}`, 'Cameras active', 'camera', on ? 'green' : 'orange')}${SC.ui.tile(active.length, 'Live accidents', 'zap', active.length ? 'red' : '')}</div>
        ${pending.length ? `${SC.ui.section('Awaiting verification')}<div class="list">${pending.map((a) => `<div class="card">${SC.ui.accCard(a).replace('card clickable', 'card flat clickable')}<div class="btnrow mt12"><button class="btn sm green" data-act="acc-op" data-op="confirm" data-id="${a.id}">Confirm &amp; alert</button><button class="btn sm light" data-act="acc-op" data-op="dismiss" data-id="${a.id}">False alarm</button></div></div>`).join('')}</div>` : ''}
        ${SC.ui.section('Active incidents')}<div class="list">${active.length ? active.map((a) => SC.ui.accCard(a)).join('') : SC.ui.empty('All clear', 'No active accidents right now.', 'check')}</div>
        ${SC.ui.section('CCTV cameras')}<div class="list">${cams.map((c) => `<div class="card row"><span style="color:${c.is_active ? 'var(--green)' : '#98A2B3'}">${icon('camera', 'lg')}</span><div class="grow"><b class="small">${esc(c.camera_id)} &middot; ${esc(c.name)}</b><div class="tiny muted">${esc(c.road_name || '')}</div></div><span class="badge ${c.is_active ? 'green' : 'gray'}">${c.is_active ? 'Active' : 'Inactive'}</span></div>`).join('')}</div>`;
    },
  });

  /* 12. Accidents list with filters */
  SC.state.accFilter = { q: '', f: 'all', severity: '' };
  const FILTERS = [['all', 'All'], ['active', 'Active'], ['new', 'Verification'], ['history', 'Resolved / closed']];
  const accQuery = () => {
    const f = SC.state.accFilter; const p = new URLSearchParams();
    if (f.q) p.set('q', f.q);
    if (f.f !== 'all') p.set('view', f.f);
    if (f.severity) p.set('severity', f.severity);
    return '/accidents/?' + p.toString();
  };
  SC.route('/admin/accidents', {
    title: 'Accidents', tab: '/admin/accidents', roles: ADMIN, live: 10000,
    render: async (_, q) => {
      if (q.f) { SC.state.accFilter.f = q.f; }
      const f = SC.state.accFilter;
      const list = await SC.get(accQuery());
      return `<div class="searchbox">${icon('search')}<input id="acc-q" placeholder="Search ID, location, type" value="${esc(f.q)}"></div>
        <div class="chips mt8">${FILTERS.map(([v, l]) => `<span class="chip ${f.f === v ? 'active' : ''}" data-act="acc-filter" data-key="f" data-val="${v}">${l}</span>`).join('')}</div>
        <div class="chips">${[['', 'Any severity'], ['high', 'High'], ['medium', 'Medium'], ['low', 'Low']].map(([v, l]) => `<span class="chip ${f.severity === v ? 'active' : ''}" data-act="acc-filter" data-key="severity" data-val="${v}">${l}</span>`).join('')}</div>
        <div class="muted small mb8">${list.length} accident${list.length === 1 ? '' : 's'}</div>
        <div class="list">${list.length ? list.map((a) => SC.ui.accCard(a)).join('') : SC.ui.empty('No accidents found', 'Try another filter.', 'search')}</div>`;
    },
    mount: (el) => {
      const input = el.querySelector('#acc-q'); let t;
      input.oninput = () => { clearTimeout(t); t = setTimeout(() => { SC.state.accFilter.q = input.value.trim(); SC.render().then(() => { const i = document.getElementById('acc-q'); if (i) { i.focus(); i.setSelectionRange(i.value.length, i.value.length); } }); }, 350); };
    },
  });
  SC.actions['acc-filter'] = (el) => { SC.state.accFilter[el.dataset.key] = el.dataset.val; if (location.hash.includes('?')) location.hash = '#/admin/accidents'; else SC.render(); };

  /* 13-15. Services: generic CRUD screens */
  const crud = (cfg) => SC.route(cfg.path, {
    title: cfg.title, tab: '/admin/services', roles: ADMIN,
    render: async () => {
      const deps = cfg.deps ? await cfg.deps() : {};
      const items = await SC.get(cfg.endpoint);
      SC.state.crud = { cfg, items, deps };
      return `${SC.ui.tabs(SERVICE_TABS, cfg.path)}
        <div class="list">${items.length ? items.map((i) => cfg.card(i, deps)).join('') : SC.ui.empty('Nothing here yet', 'Tap + to add one.', cfg.icon)}</div>
        <button class="fab" data-act="crud-add" aria-label="Add">${icon('plus', 'lg')}</button>`;
    },
  });
  const openForm = (item) => {
    const { cfg, deps } = SC.state.crud;
    const isNew = !item;
    const values = item ? { ...item, ...(cfg.toForm ? cfg.toForm(item) : {}) } : { ...(cfg.defaults || {}) };
    SC.formModal({
      title: (isNew ? 'Add ' : 'Edit ') + cfg.noun, submit: isNew ? 'Create' : 'Save changes', values,
      fields: cfg.fields(deps, isNew),
      onSubmit: async (d) => {
        (cfg.nullable || []).forEach((k) => { if (d[k] === '' || d[k] === undefined) d[k] = null; else if (d[k] != null) d[k] = Number(d[k]); });
        if (d.password === '') delete d.password;
        if (isNew) await SC.post(cfg.endpoint, d); else await SC.patch(`${cfg.endpoint}${item.id}/`, d);
        SC.toast(cfg.noun + ' saved', 'success'); SC.render();
      },
    });
  };
  SC.actions['crud-add'] = () => openForm(null);
  SC.actions['crud-edit'] = (el) => openForm(SC.state.crud.items.find((i) => String(i.id) === el.dataset.id));
  SC.actions['crud-del'] = (el) => {
    const { cfg } = SC.state.crud;
    SC.confirm('Delete ' + cfg.noun, 'This cannot be undone.', 'Delete', async () => { await SC.del(`${cfg.endpoint}${el.dataset.id}/`); SC.toast('Deleted'); SC.render(); }, true);
  };
  SC.actions['crud-patch'] = (el) => SC.run(el, async () => { await SC.patch(`${SC.state.crud.cfg.endpoint}${el.dataset.id}/`, JSON.parse(el.dataset.body)); SC.render(); });
  const editBtns = (i) => `<div class="btnrow mt12"><button class="btn sm light" data-act="crud-edit" data-id="${i.id}">${icon('edit', 'sm')} Edit</button><button class="btn sm ghost" style="color:var(--red)" data-act="crud-del" data-id="${i.id}">${icon('trash', 'sm')} Delete</button></div>`;
  const coord = { step: 'any', type: 'number', required: true };
  const activeBadge = (i) => `<span class="badge ${i.is_active ? 'green' : 'gray'}">${i.is_active ? 'Active' : 'Inactive'}</span>`;
  const accountField = (kind) => ({ label: `Login account (username of a ${kind} user)`, name: 'account_username', placeholder: 'optional' });

  SC.route('/admin/services', { title: 'Services', tab: '/admin/services', roles: ADMIN, render: async () => { setTimeout(() => SC.go('/admin/hospitals'), 0); return ''; } });

  crud({
    path: '/admin/hospitals', endpoint: '/hospitals/', title: 'Hospitals', noun: 'hospital', icon: 'hospital',
    defaults: { accepting_emergencies: true, is_active: true, total_beds: 0, available_beds: 0 },
    toForm: (h) => ({ account_username: h.account }),
    fields: () => [{ label: 'Name', name: 'name', required: true }, { label: 'Address', name: 'address' }, { label: 'Phone', name: 'phone', type: 'tel' }, { ...coord, label: 'Latitude', name: 'latitude' }, { ...coord, label: 'Longitude', name: 'longitude' }, { label: 'Total beds', name: 'total_beds', type: 'number', min: 0, required: true }, { label: 'Available beds', name: 'available_beds', type: 'number', min: 0, required: true }, { label: 'Accepting emergencies', name: 'accepting_emergencies', type: 'checkbox' }, { label: 'Active', name: 'is_active', type: 'checkbox' }, accountField('hospital')],
    card: (h) => `<div class="card"><div class="row between"><b>${esc(h.name)}</b>${activeBadge(h)}</div><div class="small muted mt8">${icon('pin', 'sm')} ${esc(h.address || 'No address')} &middot; ${h.latitude.toFixed(4)}, ${h.longitude.toFixed(4)}</div>
      <div class="row wrap mt8" style="gap:6px"><span class="badge ${h.accepting_emergencies ? 'green' : 'orange'}">${h.accepting_emergencies ? 'Accepting emergencies' : 'Not accepting'}</span><span class="badge">${h.available_beds}/${h.total_beds} beds</span><span class="badge">${h.ambulances_available}/${h.ambulances} ambulances</span><span class="badge gray">${h.account ? 'Login: ' + esc(h.account) : 'No login linked'}</span></div>${editBtns(h)}</div>`,
  });
  crud({
    path: '/admin/police-stations', endpoint: '/police-stations/', title: 'Police Stations', noun: 'police station', icon: 'shield',
    defaults: { is_active: true },
    toForm: (s) => ({ account_username: s.account }),
    fields: () => [{ label: 'Name', name: 'name', required: true }, { label: 'Address', name: 'address' }, { label: 'Phone', name: 'phone', type: 'tel' }, { ...coord, label: 'Latitude', name: 'latitude' }, { ...coord, label: 'Longitude', name: 'longitude' }, { label: 'Active', name: 'is_active', type: 'checkbox' }, accountField('police')],
    card: (s) => `<div class="card"><div class="row between"><b>${esc(s.name)}</b>${activeBadge(s)}</div><div class="small muted mt8">${icon('pin', 'sm')} ${esc(s.address || 'No address')} &middot; ${s.latitude.toFixed(4)}, ${s.longitude.toFixed(4)}</div>
      <div class="row wrap mt8" style="gap:6px"><span class="badge">${esc(s.phone || 'No phone')}</span><span class="badge gray">${s.account ? 'Login: ' + esc(s.account) : 'No login linked'}</span></div>${editBtns(s)}</div>`,
  });
  crud({
    path: '/admin/cameras', endpoint: '/cameras/', title: 'CCTV Cameras', noun: 'camera', icon: 'camera',
    defaults: { is_active: true },
    fields: () => [{ label: 'Camera ID (used by the AI service)', name: 'camera_id', required: true }, { label: 'Camera name', name: 'name', required: true }, { label: 'Road / area name', name: 'road_name' }, { ...coord, label: 'Latitude', name: 'latitude' }, { ...coord, label: 'Longitude', name: 'longitude' }, { label: 'Stream URL (RTSP / HTTP)', name: 'stream_url' }, { label: 'Active', name: 'is_active', type: 'checkbox' }],
    card: (c) => `<div class="card"><div class="row between"><b>${icon('camera', 'sm')} ${esc(c.camera_id)}</b>${activeBadge(c)}</div><div class="small mt8">${esc(c.name)}</div><div class="small muted">${esc(c.road_name || '')} &middot; ${c.latitude.toFixed(4)}, ${c.longitude.toFixed(4)}</div>${editBtns(c)}</div>`,
  });
  crud({
    path: '/admin/users', endpoint: '/users/', title: 'Users', noun: 'user', icon: 'users',
    defaults: { role: 'police', is_active: true, is_approved: true },
    nullable: ['police_station', 'hospital'],
    deps: async () => { const [stations, hospitals] = await Promise.all([SC.get('/police-stations/'), SC.get('/hospitals/')]); return { stations, hospitals }; },
    fields: (d, isNew) => [{ label: 'Username', name: 'username', required: true, autocomplete: 'off' }, { label: 'First name', name: 'first_name', required: true }, { label: 'Last name', name: 'last_name' }, { label: 'Email', name: 'email', type: 'email' }, { label: 'Phone', name: 'phone', type: 'tel' },
      { label: 'Role', name: 'role', type: 'select', options: [['admin', 'Admin'], ['police', 'Police'], ['hospital', 'Hospital'], ['ambulance', 'Ambulance']] },
      { label: 'Police station (police users)', name: 'police_station', type: 'select', options: [['', '- none -']].concat(d.stations.map((s) => [s.id, s.name])) },
      { label: 'Hospital (hospital users)', name: 'hospital', type: 'select', options: [['', '- none -']].concat(d.hospitals.map((h) => [h.id, h.name])) },
      { label: isNew ? 'Password (min 8)' : 'New password (leave blank to keep)', name: 'password', type: 'password', required: isNew, autocomplete: 'new-password' },
      { label: 'Approved', name: 'is_approved', type: 'checkbox' }, { label: 'Active', name: 'is_active', type: 'checkbox' }],
    card: (u) => `<div class="card"><div class="row between"><b>${esc(u.full_name)}</b><span class="badge">${esc(u.role)}</span></div><div class="small muted mt8">${esc(u.username)}${u.email ? ' &middot; ' + esc(u.email) : ''}${u.police_station_name || u.hospital_name ? ' &middot; ' + esc(u.police_station_name || u.hospital_name) : ''}</div>
      <div class="row wrap mt8" style="gap:6px">${u.is_approved ? '<span class="badge green">Approved</span>' : '<span class="badge orange">Awaiting approval</span>'}${u.is_active ? '' : '<span class="badge gray">Deactivated</span>'}</div>
      <div class="btnrow mt12">${!u.is_approved ? `<button class="btn sm green" data-act="crud-patch" data-id="${u.id}" data-body='{"is_approved":true}'>Approve</button>` : ''}<button class="btn sm light" data-act="crud-edit" data-id="${u.id}">${icon('edit', 'sm')} Edit</button><button class="btn sm ghost" style="color:var(--red)" data-act="crud-del" data-id="${u.id}">${icon('trash', 'sm')}</button></div></div>`,
  });

  /* 16. Analytics */
  SC.route('/admin/analytics', {
    title: 'Analytics', tab: '/admin/analytics', roles: ADMIN,
    render: async () => {
      const d = await SC.get('/analytics/');
      const sev = { high: 0, medium: 0, low: 0, ...d.severity };
      const total = sev.high + sev.medium + sev.low;
      const a = total ? (sev.high / total) * 100 : 0, b = total ? a + (sev.medium / total) * 100 : 0;
      const donut = total ? `conic-gradient(var(--red) 0 ${a}%, var(--orange) ${a}% ${b}%, var(--green) ${b}% 100%)` : 'var(--lblue)';
      const statusItems = Object.keys(d.status).map((k) => ({ label: SC.STATUS[k] || k, count: d.status[k] }));
      return `<div class="grid2">${SC.ui.tile(d.ai.detections, 'AI detections', 'alert')}${SC.ui.tile(d.ai.avg_confidence + '%', 'Avg AI confidence', 'activity', 'green')}${SC.ui.tile(d.alerts.acceptance_rate + '%', 'Alert response rate', 'check')}${SC.ui.tile(d.ai.pending_verification, 'Pending verification', 'clock', 'orange')}</div>
        ${SC.ui.section('Accidents - last 14 days')}<div class="card">${bars(d.daily.map((t) => t.count), d.daily.map((t) => t.date.split(' ')[0]))}</div>
        ${SC.ui.section('Severity (AI estimate)')}<div class="card row"><div class="donut" style="background:${donut}"><div>${total}</div></div><div class="legend small"><p><i style="background:var(--red)"></i>High: ${sev.high}</p><p class="mt8"><i style="background:var(--orange)"></i>Medium: ${sev.medium}</p><p class="mt8"><i style="background:var(--green)"></i>Low: ${sev.low}</p></div></div>
        ${SC.ui.section('By accident type')}<div class="card">${hbars(d.types.map((t) => ({ label: t.accident_type, count: t.n })))}</div>
        ${SC.ui.section('By status')}<div class="card">${hbars(statusItems)}</div>
        ${SC.ui.section('By hour of day')}<div class="card">${bars(d.hours, d.hours.map((_, h) => (h % 6 === 0 ? h : '')))}</div>
        ${SC.ui.section('Emergency responses')}<div class="card"><dl class="kv"><dt>Alerts sent</dt><dd>${d.alerts.total}</dd><dt>Responded</dt><dd>${d.alerts.responded}</dd><dt>Rejected</dt><dd>${d.alerts.rejected}</dd></dl></div>
        ${SC.ui.section('AI detection statistics')}<div class="card"><dl class="kv"><dt>Auto-verified</dt><dd>${d.ai.auto_verified}</dd><dt>Simulated</dt><dd>${d.ai.simulated}</dd><dt>Active cameras</dt><dd>${d.ai.cameras}</dd></dl></div>`;
    },
  });

  /* 17. System settings */
  SC.route('/admin/settings', {
    title: 'System Settings', back: '/profile', tab: '/profile', roles: ADMIN,
    render: async () => {
      const s = await SC.get('/settings/');
      return `<form data-form="sys-settings" class="card"><h3 class="mb8">Alert rules</h3>
        ${SC.ui.field({ label: 'AI confidence needed to alert automatically (%)', name: 'min_confidence', type: 'number', step: '1', min: 0, max: 100, value: s.min_confidence, required: true })}
        ${SC.ui.field({ label: 'Auto-alert when confidence is high enough', name: 'auto_alert', type: 'checkbox', value: s.auto_alert })}
        ${SC.ui.field({ label: 'Alert radius (km)', name: 'notify_radius_km', type: 'number', step: '0.5', min: 1, value: s.notify_radius_km, required: true })}
        ${SC.ui.field({ label: 'Police stations to notify', name: 'max_police', type: 'number', min: 1, max: 10, value: s.max_police, required: true })}
        ${SC.ui.field({ label: 'Hospitals to notify', name: 'max_hospitals', type: 'number', min: 1, max: 10, value: s.max_hospitals, required: true })}
        <button class="btn" type="submit">Save settings</button></form>
        <div class="card mt16"><h3>AI service connection</h3><p class="small muted mt8">Point the Python AI service at this endpoint and send the shared key in the <code>X-API-Key</code> header (set <code>AI_SERVICE_API_KEY</code> on the server).</p><dl class="kv mt12"><dt>Events</dt><dd>${esc(location.origin)}/api/ingest/</dd></dl></div>
        <button class="btn light mt16" data-act="simulate">${icon('zap')} Simulate accident</button>`;
    },
  });
  SC.forms['sys-settings'] = (form) => SC.run(form.querySelector('button[type=submit]'), async () => { await SC.patch('/settings/', SC.formData(form)); SC.toast('Settings saved', 'success'); });
})();
