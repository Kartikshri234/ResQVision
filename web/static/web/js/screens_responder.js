/* Police and hospital screens: dashboards, alert lists, dispatch / response management, ambulances, capacity. */
(function () {
  const { esc, icon } = SC;
  const POLICE = ['police'], HOSP = ['hospital', 'ambulance'];
  const POLICE_TABS = [['New Alerts', '/police/alerts'], ['Active', '/police/active'], ['History', '/police/history']];
  const HOSP_TABS = [['Alerts', '/hospital/alerts'], ['Response', '/hospital/response'], ['History', '/hospital/history']];
  const mineStatus = (a) => (a.my_alert ? a.my_alert.status : '');

  const quick = (items) => `<div class="grid2 mt12">${items.map(([label, ico, go]) => `<div class="card clickable row" data-go="${go}"><span class="tico" style="color:var(--navy)">${icon(ico, 'lg')}</span><b class="small">${esc(label)}</b></div>`).join('')}</div>`;
  const newBanner = (n, go) => (n ? `<div class="alertbar mt12" data-go="${go}">${icon('alert', 'lg')}<div class="grow"><b>${n} new emergency alert${n > 1 ? 's' : ''}</b><div class="small">Tap to review and respond</div></div>${icon('chevron')}</div>` : '');
  const withQuick = (a) => `<div>${SC.ui.accCard(a)}${mineStatus(a) === 'pending' ? `<div class="btnrow mt8"><button class="btn sm green" data-act="accept-alert" data-id="${a.my_alert.id}">Accept</button><button class="btn sm light" data-act="reject-alert" data-id="${a.my_alert.id}">Reject</button></div>` : ''}</div>`;
  const notLinked = (what) => SC.ui.empty(`No ${what} linked`, `Ask an administrator to link your account to a ${what}.`, what === 'hospital' ? 'hospital' : 'shield');

  /* 18. Police dashboard */
  SC.route('/police/home', {
    title: 'Police Dashboard', tab: '/police/home', roles: POLICE, live: 8000,
    render: async () => {
      const s = await SC.get('/dashboard/');
      if (!s.org) return notLinked('police station');
      const pending = s.recent.filter((a) => mineStatus(a) === 'pending');
      const progress = s.recent.filter((a) => ['accepted', 'dispatched', 'arrived'].includes(mineStatus(a)));
      return `<div class="hero"><div class="small muted">${esc(SC.state.user.full_name)}</div><h2>${esc(s.org)}</h2><p class="small muted mt8">On duty &middot; ${s.active} active incident${s.active === 1 ? '' : 's'}</p></div>
        ${newBanner(s.new, '/police/alerts')}
        <div class="grid2 mt12">${SC.ui.tile(s.new, 'New alerts', 'bell', s.new ? 'red' : '', '/police/alerts')}${SC.ui.tile(s.active, 'Active incidents', 'zap', 'orange', '/police/active')}${SC.ui.tile(s.resolved, 'Resolved', 'check', 'green', '/police/history')}${SC.ui.tile(s.rejected, 'Rejected', 'x', '', '/police/history')}</div>
        ${quick([['New alerts', 'bell', '/police/alerts'], ['Active incidents', 'zap', '/police/active'], ['Live map', 'map', '/map'], ['Incident history', 'clock', '/police/history']])}
        ${SC.ui.section('Needs your response', 'See all', '/police/alerts')}<div class="list">${pending.length ? pending.map(withQuick).join('') : SC.ui.empty('No pending alerts', 'You are all caught up.', 'check')}</div>
        ${progress.length ? `${SC.ui.section('In progress', 'See all', '/police/active')}<div class="list">${progress.map((a) => SC.ui.accCard(a)).join('')}</div>` : ''}`;
    },
  });

  /* Alert list screens (19, 20, 23 police | 25, 26, 29 hospital) */
  const listScreen = (cfg) => SC.route(cfg.path, {
    title: cfg.title, tab: cfg.tab, roles: cfg.roles, live: cfg.group === 'history' ? 0 : 6000,
    render: async () => {
      const list = await SC.get('/accidents/?view=' + cfg.group);
      return `${SC.ui.tabs(cfg.tabs, cfg.path)}<div class="list">${list.length ? list.map(cfg.group === 'new' ? withQuick : (a) => SC.ui.accCard(a)).join('') : SC.ui.empty(cfg.empty[0], cfg.empty[1], cfg.icon)}</div>`;
    },
  });
  listScreen({ path: '/police/alerts', title: 'New Alerts', group: 'new', tab: '/police/alerts', roles: POLICE, tabs: POLICE_TABS, icon: 'bell', empty: ['No new alerts', 'New accident alerts for your station will appear here.'] });
  listScreen({ path: '/police/active', title: 'Active Incidents', group: 'active', tab: '/police/alerts', roles: POLICE, tabs: POLICE_TABS, icon: 'zap', empty: ['No active incidents', 'Accepted incidents appear here until resolved.'] });
  listScreen({ path: '/police/history', title: 'Incident History', group: 'history', tab: '/police/alerts', roles: POLICE, tabs: POLICE_TABS, icon: 'clock', empty: ['No history yet', 'Resolved and rejected incidents are listed here.'] });
  listScreen({ path: '/hospital/alerts', title: 'Emergency Alerts', group: 'new', tab: '/hospital/alerts', roles: HOSP, tabs: HOSP_TABS, icon: 'bell', empty: ['No emergency alerts', 'Nearby accident alerts will appear here.'] });
  listScreen({ path: '/hospital/response', title: 'Response Management', group: 'active', tab: '/hospital/alerts', roles: HOSP, tabs: HOSP_TABS, icon: 'truck', empty: ['No active responses', 'Accepted emergencies are managed here.'] });
  listScreen({ path: '/hospital/history', title: 'Emergency History', group: 'history', tab: '/hospital/alerts', roles: HOSP, tabs: HOSP_TABS, icon: 'clock', empty: ['No history yet', 'Completed and rejected emergencies are listed here.'] });

  /* 21. Dispatch team (police) and ambulance response (hospital) share one workflow screen.
     The route is keyed by the accident id; the alert is the signed-in organisation's `my_alert`. */
  const FLOW = {
    police: ['Alert received', 'Incident accepted', 'Team dispatched', 'Reached location', 'Incident resolved'],
    hospital: ['Emergency received', 'Emergency accepted', 'Ambulance dispatched', 'Arrived at scene', 'Emergency completed'],
  };
  const TEAM_PRESETS = ['Patrol Team Alpha', 'Patrol Team Bravo', 'Rapid Response Unit', 'Traffic Control Unit'];
  const respond = (role, path) => SC.route(path, {
    title: role === 'police' ? 'Dispatch Team' : 'Response Management', back: true, tab: role === 'police' ? '/police/alerts' : '/hospital/alerts', roles: role === 'police' ? POLICE : HOSP, live: 8000,
    render: async ({ id }) => {
      const a = await SC.get(`/accidents/${id}/`);
      const al = a.my_alert;
      if (!al) return SC.ui.empty('Not assigned to you', 'This incident was not routed to your organisation.', 'alert');
      const cur = { pending: 1, accepted: 2, dispatched: 3, arrived: 4, resolved: 5, rejected: -1 }[al.status];
      const steps = FLOW[role].map((label, i) => ({ label, state: i < cur ? 'done' : i === cur ? 'current' : 'todo', sub: i === 2 && (al.team_name || al.ambulance) ? (al.team_name || al.ambulance) : '' }));
      let body = '';
      if (al.status === 'pending') {
        let avail = '';
        if (role === 'hospital') {
          const h = await SC.get('/hospital/me/');
          avail = `<div class="card flat mt12 small">${icon('bed', 'sm')} Availability check: <b>${h.available_beds}/${h.total_beds}</b> beds free &middot; ${h.ambulances_available} ambulance(s) ready &middot; emergency intake ${h.accepting_emergencies ? '<b style="color:var(--green)">open</b>' : '<b style="color:var(--red)">closed</b>'}</div>`;
        }
        body = `${avail}<div class="btnrow mt12"><button class="btn green" data-act="accept-alert" data-id="${al.id}">Accept</button><button class="btn light" data-act="reject-alert" data-id="${al.id}">Reject</button></div>`;
      } else if (al.status === 'accepted') {
        if (role === 'police') {
          body = `<form data-form="dispatch-team" data-alert="${al.id}" class="mt12"><label class="fld">Response team
            <input name="team_name" list="team-list" required maxlength="100" placeholder="e.g. Patrol Team Alpha" autocomplete="off"><datalist id="team-list">${TEAM_PRESETS.map((t) => `<option value="${esc(t)}">`).join('')}</datalist></label>
            <div class="chips">${TEAM_PRESETS.map((t) => `<span class="chip" data-act="team-preset" data-team="${esc(t)}">${esc(t)}</span>`).join('')}</div>
            <button class="btn green mt8" type="submit">${icon('zap')} Dispatch team now</button></form>`;
        } else {
          const all = await SC.get('/ambulances/');
          const free = all.filter((x) => x.status === 'available');
          const picks = free.map((t) => `<div class="pick" data-act="pick" data-id="${t.id}"><span>${icon('truck', 'lg')}</span><div class="grow"><b class="small">${esc(t.vehicle_number)}</b><div class="tiny muted">${esc(t.driver_name || 'No driver set')}</div></div><span class="badge green">available</span></div>`).join('');
          body = `<div class="section-title"><h3>Assign ambulance</h3><a data-go="/hospital/ambulances">Manage</a></div>
            ${free.length ? `<div class="list" id="picks">${picks}</div>` : `<div class="card flat small muted">No ambulance is free right now. You can still dispatch emergency staff.</div>`}
            <button class="btn green mt12" data-act="dispatch-amb" data-id="${al.id}" data-free="${free.length}">${icon('zap')} ${free.length ? 'Dispatch selected ambulance' : 'Dispatch emergency staff'}</button>`;
        }
      } else if (al.status === 'dispatched') {
        body = `<button class="btn mt12" data-act="set-state" data-id="${al.id}" data-action="arrive">${icon('pin')} Mark: reached the location</button>`;
      } else if (al.status === 'arrived') {
        body = `<button class="btn green mt12" data-act="set-state" data-id="${al.id}" data-action="resolve">${icon('check')} ${role === 'police' ? 'Resolve incident' : 'Mark emergency completed'}</button>`;
      } else if (al.status === 'resolved') {
        body = `<div class="card mt12 center" style="background:var(--green-bg)"><b style="color:#027A48">${icon('check')} Response completed</b></div>`;
      } else {
        body = `<div class="card mt12 small muted">You rejected this alert: ${esc(al.reject_reason)}</div>`;
      }
      return `${SC.ui.accCard(a, { alert: null })}
        <div class="card mt12"><div class="row between mb8"><h3>Response workflow</h3>${SC.ui.alertStatus(al.status)}</div>${al.status === 'rejected' ? '' : SC.ui.stepper(steps)}${body}</div>
        <a class="btn light mt12" target="_blank" rel="noopener" href="${SC.gmapsLink(a.latitude, a.longitude)}">${icon('nav')} Route to accident (${Number(al.distance_km).toFixed(1)} km)</a>
        <div class="btnrow mt12"><button class="btn ghost" data-go="/accident/${a.id}/map">${icon('map', 'sm')} Map</button><button class="btn ghost" data-go="/accident/${a.id}/timeline">${icon('clock', 'sm')} Timeline</button></div>`;
    },
  });
  respond('police', '/police/dispatch/:id');
  respond('hospital', '/hospital/respond/:id');

  SC.actions.pick = (el) => { document.querySelectorAll('#picks .pick').forEach((p) => p.classList.remove('sel')); el.classList.add('sel'); };
  SC.actions['team-preset'] = (el) => { const input = document.querySelector('form[data-form=dispatch-team] [name=team_name]'); if (input) input.value = el.dataset.team; };
  SC.forms['dispatch-team'] = (form) => SC.run(form.querySelector('button[type=submit]'), async () => {
    await SC.respond(form.dataset.alert, { action: 'dispatch', team_name: SC.formData(form).team_name });
    SC.toast('Team dispatched', 'success'); SC.render();
  });
  SC.actions['dispatch-amb'] = (el) => SC.run(el, async () => {
    const body = { action: 'dispatch' };
    if (Number(el.dataset.free) > 0) {
      const sel = document.querySelector('#picks .pick.sel');
      if (!sel) throw new Error('Select an ambulance first.');
      body.ambulance_id = Number(sel.dataset.id);
    }
    await SC.respond(el.dataset.id, body);
    SC.toast('Dispatched', 'success'); SC.render();
  });
  SC.actions['set-state'] = (el) => SC.run(el, async () => { await SC.respond(el.dataset.id, { action: el.dataset.action }); SC.toast('Status updated', 'success'); SC.render(); });

  /* 27. Ambulance management */
  const AMB_STATUS = [['available', 'Available'], ['maintenance', 'Under maintenance'], ['dispatched', 'On mission (busy)']];
  const ambBadge = (s) => `<span class="badge ${s === 'available' ? 'green' : s === 'dispatched' ? 'orange' : 'gray'}">${esc(s)}</span>`;
  SC.route('/hospital/ambulances', {
    title: 'Ambulance Management', back: '/hospital/home', tab: '/hospital/home', roles: HOSP,
    render: async () => {
      const items = await SC.get('/ambulances/');
      SC.state.amb = items;
      const free = items.filter((i) => i.status === 'available').length;
      return `<div class="grid2">${SC.ui.tile(free, 'Available', 'truck', 'green')}${SC.ui.tile(items.length - free, 'Busy / maintenance', 'clock', 'orange')}</div>
        <div class="list mt12">${items.length ? items.map((t) => `<div class="card"><div class="row between"><b>${icon('truck', 'sm')} ${esc(t.vehicle_number)}</b>${ambBadge(t.status)}</div><div class="small muted mt8">${esc(t.driver_name || 'No driver set')}${t.driver_phone ? ' &middot; <a href="tel:' + esc(t.driver_phone) + '">' + esc(t.driver_phone) + '</a>' : ''}</div>
          <div class="btnrow mt12"><button class="btn sm light" data-act="amb-edit" data-id="${t.id}">${icon('edit', 'sm')} Edit</button><button class="btn sm ghost" style="color:var(--red)" data-act="amb-del" data-id="${t.id}">${icon('trash', 'sm')}</button></div></div>`).join('') : SC.ui.empty('No ambulances registered', 'Tap + to add one.', 'truck')}</div>
        <button class="fab" data-act="amb-add" aria-label="Add">${icon('plus', 'lg')}</button>`;
    },
  });
  const ambForm = (item) => SC.formModal({
    title: item ? 'Edit ambulance' : 'Add ambulance', submit: item ? 'Save changes' : 'Create', values: item ? { ...item } : { status: 'available' },
    fields: [{ label: 'Vehicle number', name: 'vehicle_number', required: true }, { label: 'Driver name', name: 'driver_name' }, { label: 'Driver phone', name: 'driver_phone', type: 'tel' }].concat(item ? [{ label: 'Status', name: 'status', type: 'select', options: AMB_STATUS }] : []),
    onSubmit: async (d) => { if (item) await SC.patch(`/ambulances/${item.id}/`, d); else await SC.post('/ambulances/', d); SC.toast('Saved', 'success'); SC.render(); },
  });
  SC.actions['amb-add'] = () => ambForm(null);
  SC.actions['amb-edit'] = (el) => ambForm(SC.state.amb.find((i) => String(i.id) === el.dataset.id));
  SC.actions['amb-del'] = (el) => SC.confirm('Delete ambulance', 'This cannot be undone.', 'Delete', async () => { await SC.del(`/ambulances/${el.dataset.id}/`); SC.toast('Deleted'); SC.render(); }, true);

  /* 24. Hospital dashboard */
  SC.route('/hospital/home', {
    title: 'Hospital Dashboard', tab: '/hospital/home', roles: HOSP, live: 8000,
    render: async () => {
      const s = await SC.get('/dashboard/');
      const h = s.hospital;
      if (!h) return notLinked('hospital');
      const pct = h.total_beds ? Math.round((h.available_beds / h.total_beds) * 100) : 0;
      const pending = s.recent.filter((a) => mineStatus(a) === 'pending');
      const progress = s.recent.filter((a) => ['accepted', 'dispatched', 'arrived'].includes(mineStatus(a)));
      return `<div class="hero"><div class="small muted">${esc(SC.state.user.full_name)}</div><h2>${esc(h.name)}</h2>
          <div class="row between mt12"><div><div class="small muted">Emergency availability</div><b>${h.accepting_emergencies ? 'Accepting emergencies' : 'Not accepting'}</b></div><label class="switch"><input type="checkbox" data-act="toggle-emergency" ${h.accepting_emergencies ? 'checked' : ''}><span></span></label></div></div>
        ${newBanner(s.new, '/hospital/alerts')}
        <div class="grid2 mt12">${SC.ui.tile(s.new, 'New emergencies', 'bell', s.new ? 'red' : '', '/hospital/alerts')}${SC.ui.tile(s.active, 'Active responses', 'truck', 'orange', '/hospital/response')}${SC.ui.tile(s.resolved, 'Completed', 'check', 'green', '/hospital/history')}${SC.ui.tile(`${h.ambulances_available}/${h.ambulances}`, 'Ambulances ready', 'truck', '', '/hospital/ambulances')}</div>
        <div class="card mt12 clickable" data-go="/hospital/capacity"><div class="row between"><b>${icon('bed', 'sm')} Bed capacity</b><span class="small bold">${h.available_beds}/${h.total_beds} free</span></div><div class="progress mt8"><i style="width:${pct}%"></i></div></div>
        ${quick([['Emergency alerts', 'bell', '/hospital/alerts'], ['Response management', 'activity', '/hospital/response'], ['Ambulances', 'truck', '/hospital/ambulances'], ['Capacity', 'bed', '/hospital/capacity']])}
        ${SC.ui.section('Needs your response', 'See all', '/hospital/alerts')}<div class="list">${pending.length ? pending.map(withQuick).join('') : SC.ui.empty('No pending emergencies', 'You are all caught up.', 'check')}</div>
        ${progress.length ? `${SC.ui.section('In progress', 'See all', '/hospital/response')}<div class="list">${progress.map((a) => SC.ui.accCard(a)).join('')}</div>` : ''}`;
    },
  });
  document.addEventListener('change', (e) => {
    const t = e.target.closest('[data-act=toggle-emergency]');
    if (!t) return;
    SC.patch('/hospital/me/', { accepting_emergencies: t.checked }).then(() => { SC.toast(t.checked ? 'Now accepting emergencies' : 'Emergency intake paused', 'success'); SC.render(); }).catch((err) => { t.checked = !t.checked; SC.toast(err.message, 'error'); });
  });

  /* 28. Capacity management */
  SC.route('/hospital/capacity', {
    title: 'Capacity Management', back: '/hospital/home', tab: '/hospital/home', roles: HOSP,
    render: async () => {
      const h = await SC.get('/hospital/me/');
      const stepper = (name, label, val) => `<div class="card"><div class="row between"><b>${label}</b><div class="stepper"><button data-act="step" data-f="${name}" data-d="-1" aria-label="decrease">&minus;</button><span class="val" id="v-${name}">${val}</span><button data-act="step" data-f="${name}" data-d="1" aria-label="increase">+</button></div></div></div>`;
      return `<div class="card"><div class="row between"><div><b>Emergency services</b><div class="small muted">Turn off when you cannot take new emergencies</div></div><label class="switch"><input type="checkbox" id="cap-emerg" ${h.accepting_emergencies ? 'checked' : ''}><span></span></label></div></div>
        <div class="list mt12">${stepper('total_beds', 'Total beds', h.total_beds)}${stepper('available_beds', 'Available beds', h.available_beds)}</div>
        <button class="btn mt16" data-act="save-capacity">Save capacity</button>`;
    },
  });
  SC.actions.step = (el) => {
    const span = document.getElementById('v-' + el.dataset.f);
    span.textContent = Math.max(0, Number(span.textContent) + Number(el.dataset.d));
  };
  SC.actions['save-capacity'] = (el) => SC.run(el, async () => {
    await SC.patch('/hospital/me/', { accepting_emergencies: document.getElementById('cap-emerg').checked, total_beds: Number(document.getElementById('v-total_beds').textContent), available_beds: Number(document.getElementById('v-available_beds').textContent) });
    SC.toast('Capacity updated', 'success');
  });
})();
