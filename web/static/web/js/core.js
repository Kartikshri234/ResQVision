/* ResQVision - core: state, API client, helpers, UI components, router. */
(function () {
  const SC = (window.SC = { state: { user: null, unread: 0, token: 0, timers: [] }, routes: [], actions: {}, forms: {}, ui: {}, fmt: {} });

  /* ---------- storage ---------- */
  SC.store = {
    get(k, d) { try { const v = localStorage.getItem('rv_' + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('rv_' + k, JSON.stringify(v)); } catch (e) { /* ignore */ } },
    del(k) { try { localStorage.removeItem('rv_' + k); } catch (e) { /* ignore */ } },
  };

  /* ---------- icons (Feather-style, 24px grid) ---------- */
  const ICONS = {
    resq: '<path d="M12 2.5l8 3v6c0 5-3.4 8.6-8 10-4.6-1.4-8-5-8-10v-6z"/><path d="M7.5 12h2.2l1.6-3.2 2.2 6.4 1.6-3.2h1.4"/>',
    home: '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
    alert: '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    map: '<polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/><line x1="8" y1="2" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="22"/>',
    bell: '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
    user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    chart: '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
    settings: '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
    camera: '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/>',
    plus: '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    check: '<polyline points="20 6 9 17 4 12"/>',
    x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    phone: '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>',
    pin: '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
    back: '<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>',
    chevron: '<polyline points="9 18 15 12 9 6"/>',
    logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
    search: '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    activity: '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    image: '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>',
    play: '<polygon points="5 3 19 12 5 21 5 3"/>',
    refresh: '<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>',
    lock: '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    mail: '<path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/>',
    shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    truck: '<rect x="1" y="3" width="15" height="13"/><polygon points="16 8 20 8 23 11 23 16 16 16 16 8"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/>',
    nav: '<polygon points="3 11 22 2 13 21 11 13 3 11"/>',
    trash: '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/>',
    edit: '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>',
    hospital: '<rect x="3" y="3" width="18" height="18" rx="3"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/>',
    video: '<polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>',
    list: '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>',
    zap: '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    server: '<rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/>',
    car: '<path d="M3 13l2-6a2 2 0 0 1 2-1h10a2 2 0 0 1 2 1l2 6v5h-3v-2H6v2H3z"/><circle cx="7.5" cy="14" r="1"/><circle cx="16.5" cy="14" r="1"/>',
    eye: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
    bed: '<path d="M2 4v16"/><path d="M2 8h18a2 2 0 0 1 2 2v10"/><path d="M2 17h20"/><path d="M6 8v9"/>',
    info: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
  };
  SC.icon = (name, cls) => `<svg class="ico ${cls || ''}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ICONS.info}</svg>`;

  /* ---------- helpers ---------- */
  SC.esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const esc = SC.esc;
  SC.fmt.dt = (iso) => (iso ? new Date(iso).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '-');
  SC.fmt.time = (iso) => (iso ? new Date(iso).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : '-');
  SC.fmt.ago = (iso) => {
    if (!iso) return '-';
    const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 60) return 'just now';
    if (s < 3600) return Math.floor(s / 60) + ' min ago';
    if (s < 86400) return Math.floor(s / 3600) + ' h ago';
    return Math.floor(s / 86400) + ' d ago';
  };
  SC.fmt.pct = (c) => Math.round(c || 0) + '%'; // the API already returns confidence as a percentage
  SC.fmt.initials = (n) => (n || '?').split(/\s+/).map((p) => p[0]).slice(0, 2).join('').toUpperCase();

  SC.STATUS = { detected: 'Detected', verification_pending: 'Verification Pending', confirmed: 'Confirmed', alert_sent: 'Alert Sent', accepted: 'Accepted', team_dispatched: 'Team Dispatched', arrived: 'Responders Arrived', resolved: 'Resolved', closed: 'Closed' };
  SC.STATUS_ORDER = Object.keys(SC.STATUS);
  SC.ALERT = { pending: 'Pending', accepted: 'Accepted', rejected: 'Rejected', dispatched: 'Dispatched', arrived: 'Arrived', resolved: 'Resolved', none: 'Not notified' };
  const STATUS_COLOR = { detected: 'orange', verification_pending: 'orange', confirmed: 'orange', alert_sent: 'red', accepted: '', team_dispatched: '', arrived: '', resolved: 'green', closed: 'gray' };
  const ALERT_COLOR = { pending: 'orange', accepted: '', dispatched: '', arrived: '', resolved: 'green', rejected: 'red', none: 'gray' };
  SC.SEV_COLOR = { high: '#D92D20', medium: '#F79009', low: '#12B76A' };

  SC.ui.sev = (s) => `<span class="badge ${s === 'high' ? 'red' : s === 'medium' ? 'orange' : 'green'}">${esc((s || '').toUpperCase())}</span>`;
  SC.ui.status = (s) => `<span class="badge ${STATUS_COLOR[s] || ''}">${esc(SC.STATUS[s] || s)}</span>`;
  SC.ui.alertStatus = (s) => `<span class="badge ${ALERT_COLOR[s] || ''}">${esc(SC.ALERT[s] || s)}</span>`;
  SC.ui.loading = (t) => `<div class="loading"><div class="spinner"></div>${esc(t || 'Loading...')}</div>`;
  SC.ui.empty = (title, sub, icon) => `<div class="empty">${SC.icon(icon || 'check')}<h3>${esc(title)}</h3><p class="small mt8">${esc(sub || '')}</p></div>`;
  SC.ui.section = (title, link, go) => `<div class="section-title"><h3>${esc(title)}</h3>${link ? `<a data-go="${go}">${esc(link)}</a>` : ''}</div>`;
  SC.ui.tile = (num, label, icon, color, go) => `<div class="tile ${color || ''}" ${go ? `data-go="${go}"` : ''}><div class="tico">${SC.icon(icon)}</div><div class="num">${num}</div><div class="lbl">${esc(label)}</div></div>`;
  SC.ui.tabs = (items, active) => `<div class="tabs">${items.map(([label, path]) => `<a data-go="${path}" class="${path === active ? 'active' : ''}">${esc(label)}</a>`).join('')}</div>`;
  SC.ui.accCard = (a, o) => {
    o = o || {};
    if (o.alert === undefined) o.alert = a.my_alert;
    const thumb = a.snapshot ? `style="background-image:url('${esc(a.snapshot)}')"` : '';
    const right = o.alert ? SC.ui.alertStatus(o.alert.status) : SC.ui.status(a.status);
    return `<div class="card clickable acc ${esc(a.severity)}" data-go="${o.go || '/accident/' + a.id}">
      <div class="thumb" ${thumb}>${a.snapshot ? '' : SC.icon('car', 'lg')}</div>
      <div class="grow"><div class="row between"><span class="id">${esc(a.accident_id)}</span>${SC.ui.sev(a.severity)}</div>
        <div class="small bold">${esc(a.accident_type || 'Road accident')}</div>
        <div class="small muted">${SC.icon('pin', 'sm')} ${esc(a.location || 'Unknown location')}</div>
        <div class="row wrap mt8" style="gap:6px">${right}<span class="tiny muted">${SC.fmt.ago(a.detected_at)} &middot; ${SC.fmt.pct(a.confidence)}${o.alert ? ' &middot; ' + Number(o.alert.distance_km).toFixed(1) + ' km' : ''}</span></div></div></div>`;
  };
  SC.ui.alertCard = (a) => SC.ui.accCard(a);

  SC.ui.field = (f) => {
    const v = f.value == null ? '' : f.value;
    if (f.type === 'checkbox') return `<label class="fld check"><input type="checkbox" name="${f.name}" ${v ? 'checked' : ''}> ${esc(f.label)}</label>`;
    let control;
    if (f.type === 'select') control = `<select name="${f.name}" ${f.required ? 'required' : ''}>${(f.options || []).map(([val, lab]) => `<option value="${esc(val)}" ${String(val) === String(v) ? 'selected' : ''}>${esc(lab)}</option>`).join('')}</select>`;
    else if (f.type === 'textarea') control = `<textarea name="${f.name}" rows="3" ${f.required ? 'required' : ''} placeholder="${esc(f.placeholder || '')}">${esc(v)}</textarea>`;
    else control = `<input name="${f.name}" type="${f.type || 'text'}" value="${esc(v)}" ${f.required ? 'required' : ''} ${f.step ? `step="${f.step}"` : ''} ${f.min != null ? `min="${f.min}"` : ''} ${f.max != null ? `max="${f.max}"` : ''} ${f.maxlength ? `maxlength="${f.maxlength}"` : ''} placeholder="${esc(f.placeholder || '')}" autocomplete="${f.autocomplete || 'off'}">`;
    return `<label class="fld">${esc(f.label)}${control}</label>`;
  };
  SC.formData = (form) => {
    const out = {};
    form.querySelectorAll('input[name],select[name],textarea[name]').forEach((el) => {
      if (el.type === 'checkbox') out[el.name] = el.checked;
      else if (el.type === 'number') out[el.name] = el.value === '' ? null : Number(el.value);
      else out[el.name] = el.value;
    });
    return out;
  };

  /* ---------- feedback: toast, modal, busy buttons ---------- */
  SC.toast = (msg, type, ms) => {
    const el = document.createElement('div');
    el.className = 'toast ' + (type || '');
    el.textContent = msg;
    document.getElementById('toasts').appendChild(el);
    setTimeout(() => el.remove(), ms || 3800);
  };
  SC.modalOpen = () => !!document.querySelector('#modal-root .modal-bg');
  SC.closeModal = () => { document.getElementById('modal-root').innerHTML = ''; };
  SC.modal = (title, html, mount) => {
    const root = document.getElementById('modal-root');
    root.innerHTML = `<div class="modal-bg" data-act="modal-bg"><div class="modal" role="dialog"><div class="row between"><h3>${esc(title)}</h3><button class="btn ghost sm" data-act="close-modal" aria-label="Close">${SC.icon('x', 'sm')}</button></div>${html}</div></div>`;
    const m = root.querySelector('.modal');
    if (mount) mount(m);
    return m;
  };
  SC.formModal = ({ title, fields, values, submit, onSubmit, note }) => {
    values = values || {};
    const html = `<form data-form="__modal">${note ? `<p class="small muted mb8">${esc(note)}</p>` : ''}${fields.map((f) => SC.ui.field({ ...f, value: values[f.name] })).join('')}<button class="btn" type="submit">${esc(submit || 'Save')}</button></form>`;
    SC.modal(title, html, (m) => {
      SC.forms.__modal = async (form) => {
        const btn = form.querySelector('button[type=submit]');
        btn.disabled = true;
        try { await onSubmit(SC.formData(form)); SC.closeModal(); } catch (e) { SC.toast(e.message, 'error'); btn.disabled = false; }
      };
      const first = m.querySelector('input,select,textarea'); if (first && first.type !== 'checkbox') first.focus();
    });
  };
  SC.confirm = (title, message, okLabel, onOk, danger) => {
    SC.modal(title, `<p class="muted mb8">${esc(message)}</p><div class="btnrow mt12"><button class="btn light" data-act="close-modal">Cancel</button><button class="btn ${danger ? 'red' : ''}" id="confirm-ok">${esc(okLabel || 'Confirm')}</button></div>`, (m) => {
      m.querySelector('#confirm-ok').onclick = async (e) => { e.target.disabled = true; try { await onOk(); SC.closeModal(); } catch (err) { SC.toast(err.message, 'error'); e.target.disabled = false; } };
    });
  };
  SC.run = async (btn, fn) => {
    if (btn) btn.disabled = true;
    try { return await fn(); } catch (e) { SC.toast(e.message || 'Something went wrong', 'error'); } finally { if (btn) btn.disabled = false; }
  };

  /* ---------- API client ---------- */
  class ApiError extends Error {}
  const errText = (data, status) => {
    if (!data) return 'Request failed (' + status + ')';
    if (typeof data === 'string') return data;
    if (data.error) return String(data.error);
    if (data.detail) return Array.isArray(data.detail) ? data.detail.join(' ') : String(data.detail);
    const k = Object.keys(data)[0];
    if (k) { const v = data[k]; return (k !== 'non_field_errors' ? k.replace(/_/g, ' ') + ': ' : '') + (Array.isArray(v) ? v.join(' ') : typeof v === 'object' ? JSON.stringify(v) : v); }
    return 'Request failed (' + status + ')';
  };
  SC.refreshToken = async () => {
    return false; // the app uses Django session cookies, so there is no token to refresh
  };
  SC.api = async (path, opts) => {
    opts = opts || {};
    const headers = {};
    const csrf = (document.cookie.match(/(?:^|; )csrftoken=([^;]*)/) || [])[1];
    if (csrf) headers['X-CSRFToken'] = decodeURIComponent(csrf);
    const init = { method: opts.method || 'GET', headers, credentials: 'same-origin' };
    if (opts.form) init.body = opts.form;
    else if (opts.body !== undefined) { headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(opts.body); }
    let res;
    try { res = await fetch('/api' + path, init); } catch (e) { throw new ApiError('Cannot reach the server. Check your connection.'); }
    let data = null;
    try { data = await res.json(); } catch (e) { /* no body */ }
    if (opts.auth !== false && SC.state.user && (res.status === 401 || (res.status === 403 && data && /credentials were not provided/i.test(String(data.detail || ''))))) {
      SC.logout(true);
      throw new ApiError('Your session expired. Please sign in again.');
    }
    if (!res.ok) throw new ApiError(errText(data, res.status));
    return data;
  };
  SC.get = (p) => SC.api(p);
  SC.post = (p, body) => SC.api(p, { method: 'POST', body: body || {} });
  SC.patch = (p, body) => SC.api(p, { method: 'PATCH', body });
  SC.del = (p) => SC.api(p, { method: 'DELETE' });

  /* ---------- session ---------- */
  SC.homeFor = (role) => ({ admin: '/admin/console', police: '/police/home', hospital: '/hospital/home' }[role || (SC.state.user && SC.state.user.role)] || '/ambulance');
  SC.setSession = (user) => { SC.state.user = user; };
  SC.logout = (silent) => {
    if (!silent) SC.api('/auth/logout/', { method: 'POST', body: {} }).catch(() => {});
    SC.state.user = null; SC.state.unread = 0;
    if (!silent) SC.toast('Signed out');
    SC.go('/login');
  };
  SC.loadUser = async () => {
    try { SC.state.user = await SC.api('/auth/me/'); } catch (e) { SC.state.user = null; }
    return SC.state.user;
  };

  /* ---------- maps (Leaflet + OpenStreetMap) ---------- */
  SC.makeMap = (el, o) => {
    if (!el) return null;
    if (!window.L) {
      const markers = o.markers || [];
      el.innerHTML = `<div class="map-offline"><b>Map unavailable offline</b><div class="small muted">Incident locations are still available below.</div>${markers.length ? `<ul>${markers.map((m) => `<li>${esc(m.glyph || 'Incident')} &middot; ${Number(m.lat).toFixed(4)}, ${Number(m.lng).toFixed(4)}</li>`).join('')}</ul>` : '<div class="small muted mt8">No locations to display.</div>'}</div>`;
      return null;
    }
    const map = L.map(el).setView(o.center || [28.6139, 77.2090], o.zoom || 13);
    const tileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap' }).addTo(map);
    let tileErrorShown = false;
    tileLayer.on('tileerror', () => {
      if (tileErrorShown) return;
      tileErrorShown = true;
      const notice = document.createElement('div');
      notice.className = 'map-offline';
      notice.innerHTML = '<b>Map tiles unavailable</b><div class="small muted">Markers remain available; check the network connection to restore the map background.</div>';
      el.appendChild(notice);
    });
    const pts = [];
    (o.markers || []).forEach((m) => {
      const icon = L.divIcon({ className: '', html: `<div class="pin" style="background:${m.color || '#0B2A5B'}"><span>${esc(m.glyph || '')}</span></div>`, iconSize: [30, 30], iconAnchor: [15, 30], popupAnchor: [0, -28] });
      const mk = L.marker([m.lat, m.lng], { icon }).addTo(map);
      if (m.popup) mk.bindPopup(m.popup);
      pts.push([m.lat, m.lng]);
    });
    (o.lines || []).forEach((l) => L.polyline(l.points, { color: l.color || '#163F82', dashArray: '6 8', weight: 4 }).addTo(map));
    if (pts.length > 1 && o.fit !== false) map.fitBounds(pts, { padding: [34, 34], maxZoom: 15 });
    else if (pts.length === 1) map.setView(pts[0], o.zoom || 15);
    setTimeout(() => map.invalidateSize(), 80);
    return map;
  };
  SC.gmapsLink = (lat, lng) => `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}&travelmode=driving`;
  SC.accidentMarker = (a) => ({ lat: a.latitude, lng: a.longitude, color: SC.SEV_COLOR[a.severity], glyph: '!', popup: `<b>${esc(a.accident_id)}</b><br>${esc(a.accident_type || a.status_label || '')}<br><a href="javascript:void(0)" onclick="SC.go('/accident/${a.id}')">View details</a>` });

  /* ---------- sound ---------- */
  SC.beep = () => {
    if (SC.store.get('sound', true) === false) return;
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      [0, 0.22].forEach((t) => { const o = ctx.createOscillator(); const g = ctx.createGain(); o.frequency.value = 880; o.connect(g); g.connect(ctx.destination); g.gain.setValueAtTime(0.15, ctx.currentTime + t); o.start(ctx.currentTime + t); o.stop(ctx.currentTime + t + 0.15); });
    } catch (e) { /* audio unavailable */ }
  };

  /* ---------- router ---------- */
  SC.route = (pattern, def) => {
    const keys = [];
    const re = new RegExp('^' + pattern.replace(/:([a-zA-Z]+)/g, (_, k) => { keys.push(k); return '([^/]+)'; }) + '$');
    SC.routes.push({ re, keys, def });
  };
  SC.go = (path) => { if (location.hash === '#' + path) SC.render(); else location.hash = '#' + path; };
  SC.clearTimers = () => { SC.state.timers.forEach(clearInterval); SC.state.timers = []; };

  SC.nav = {
    admin: [['Home', '/admin/console', 'home'], ['Accidents', '/admin/accidents', 'alert'], ['Services', '/admin/services', 'server'], ['Analytics', '/admin/analytics', 'chart'], ['Profile', '/profile', 'user']],
    police: [['Home', '/police/home', 'home'], ['Accidents', '/police/alerts', 'alert'], ['Map', '/map', 'map'], ['Notifications', '/notifications', 'bell'], ['Profile', '/profile', 'user']],
    hospital: [['Home', '/hospital/home', 'home'], ['Emergencies', '/hospital/alerts', 'alert'], ['Map', '/map', 'map'], ['Notifications', '/notifications', 'bell'], ['Profile', '/profile', 'user']],
  };

  // Desktop sidebar: the admin gets every section directly (strings are section headings).
  SC.sidenav = {
    admin: ['Administration', ['Admin console', '/admin/console', 'shield'], ['User accounts', '/admin/users', 'users'], ['System settings', '/admin/settings', 'settings'],
      'Services', ['Hospitals', '/admin/hospitals', 'hospital'], ['Police stations', '/admin/police-stations', 'shield'], ['Cameras', '/admin/cameras', 'camera'],
      'Monitoring', ['Accident dashboard', '/admin/home', 'home'], ['Live monitoring', '/admin/live', 'activity'], ['Accidents', '/admin/accidents', 'alert'], ['Map', '/map', 'map'], ['Analytics', '/admin/analytics', 'chart'],
      'Account', ['My profile', '/profile', 'user']],
  };

  // Each role gets its own portal name and colour theme (colours: body[data-role] in app.css).
  const PORTAL = {
    admin: ['Administrator Console', 'System administration, user accounts and oversight of all responders'],
    police: ['Police Control Room', 'Receive emergency alerts, accept incidents and dispatch patrol teams'],
    hospital: ['Hospital Emergency Desk', 'Receive emergency alerts, manage beds and dispatch ambulances'],
  };
  function brand(user) {
    const p = (user && PORTAL[user.role]) || ['ResQVision', 'AI-based Road Accident Detection & Emergency Response Portal'];
    document.body.dataset.role = user ? user.role : '';
    const n = document.getElementById('gh-name'), s = document.getElementById('gh-sub');
    if (n) n.textContent = p[0];
    if (s) s.textContent = p[1];
  }

  function chrome(def, params) {
    const top = document.getElementById('topbar');
    const nav = document.getElementById('bottomnav');
    const screen = document.getElementById('screen');
    const user = SC.state.user;
    const side = document.getElementById('sidebar');
    brand(user);
    screen.className = def.chrome === false ? 'bare' : '';
    if (def.chrome === false || !user) { top.hidden = true; nav.hidden = true; side.hidden = true; return; }
    const title = typeof def.title === 'function' ? def.title(params) : def.title || 'ResQVision';
    const tab = typeof def.tab === 'function' ? def.tab(user) : def.tab;
    const left = def.back ? `<button class="iconbtn" data-act="back" data-fallback="${def.back === true ? SC.homeFor() : def.back}" aria-label="Back">${SC.icon('back')}</button>` : `<div class="iconbtn" style="background:#fff;color:var(--navy)">${SC.icon('resq')}</div>`;
    const bell = tab === '/notifications' ? '' : `<button class="iconbtn" data-go="/notifications" aria-label="Notifications">${SC.icon('bell')}${SC.state.unread ? `<span class="dot">${SC.state.unread > 9 ? '9+' : SC.state.unread}</span>` : ''}</button>`;
    top.innerHTML = `${left}<div class="title">${esc(title)}</div>${bell}`;
    top.hidden = false;

    // Desktop sidebar (hidden by CSS on phones, where the bottom bar is used instead)
    const roleLabel = { admin: 'Administrator', police: 'Police', hospital: 'Hospital', ambulance: 'Ambulance' }[user.role] || user.role;
    const org = user.police_station_name || user.hospital_name || '';
    const sideItems = SC.sidenav[user.role] || SC.nav[user.role] || [];
    const curPath = (location.hash.slice(1) || '/').split('?')[0];
    const inPath = (p) => curPath === p || curPath.indexOf(p + '/') === 0;
    const exact = sideItems.some((i) => typeof i !== 'string' && inPath(i[1]));
    const isActive = (p) => (exact ? inPath(p) : tab === p);
    side.innerHTML = `<div class="side-user"><div class="side-av">${esc(SC.fmt.initials(user.full_name))}</div><div class="grow"><b>${esc(user.full_name)}</b><div class="tiny">${esc(roleLabel)}${org ? ' &middot; ' + esc(org) : ''}</div></div></div>`
      + (sideItems.some((i) => typeof i === 'string') ? '' : '<div class="side-label">Menu</div>')
      + sideItems.map((it) => (typeof it === 'string' ? `<div class="side-label">${esc(it)}</div>` : `<a data-go="${it[1]}" class="${isActive(it[1]) ? 'active' : ''}">${SC.icon(it[2])}<span class="grow">${it[0]}</span>${it[0] === 'Notifications' && SC.state.unread ? `<span class="badge-dot">${SC.state.unread > 9 ? '9+' : SC.state.unread}</span>` : ''}</a>`)).join('')
      + (sideItems.indexOf('Account') >= 0 ? '' : '<div class="side-label">Account</div>') + `<a data-act="logout">${SC.icon('logout')}<span>Sign out</span></a>`;
    side.hidden = def.nav === false || !sideItems.length;
    const items = SC.nav[user.role];
    if (!items || def.nav === false) { nav.hidden = true; return; }
    nav.innerHTML = items.map(([label, path, ico]) => `<a data-go="${path}" class="${tab === path ? 'active' : ''}">${SC.icon(ico)}<span>${label}</span>${label === 'Notifications' && SC.state.unread ? `<span class="badge-dot">${SC.state.unread > 9 ? '9+' : SC.state.unread}</span>` : ''}</a>`).join('');
    nav.hidden = false;
  }
  SC.updateBadges = () => { const def = SC.state.def; if (def && SC.state.user) chrome(def, SC.state.params); };

  SC.render = async () => {
    const hash = location.hash.slice(1) || '/';
    const [path, qs] = hash.split('?');
    const q = Object.fromEntries(new URLSearchParams(qs || ''));
    let match = null;
    for (const r of SC.routes) { const m = r.re.exec(path); if (m) { match = { def: r.def, params: Object.fromEntries(r.keys.map((k, i) => [k, decodeURIComponent(m[i + 1])])) }; break; } }
    if (!match) return SC.go(SC.state.user ? SC.homeFor() : '/login');
    const { def, params } = match;
    SC.clearTimers();
    const user = SC.state.user;
    if (!def.public && !user) return SC.go('/login');
    if (def.roles && !def.roles.includes(user.role)) return SC.go(SC.homeFor());
    const token = ++SC.state.token;
    SC.state.def = def; SC.state.params = params; SC.state.query = q;
    const screen = document.getElementById('screen');
    chrome(def, params);
    SC.closeModal();
    screen.innerHTML = def.chrome === false ? '' : SC.ui.loading();
    const paint = async (first) => {
      const html = await def.render(params, q);
      if (token !== SC.state.token) return;
      screen.innerHTML = html;
      if (first) window.scrollTo(0, 0);
      if (def.mount) def.mount(screen, params, q);
    };
    try { await paint(true); } catch (e) {
      if (token !== SC.state.token) return;
      screen.innerHTML = `<div class="card center mt24"><h3>Something went wrong</h3><p class="muted small mt8">${esc(e.message)}</p><button class="btn mt16" data-act="reload">Try again</button></div>`;
      return;
    }
    if (def.live && SC.store.get('live', true) !== false) {
      SC.state.timers.push(setInterval(async () => {
        const ae = document.activeElement;
        if (SC.modalOpen() || (ae && /INPUT|TEXTAREA|SELECT/.test(ae.tagName)) || document.hidden) return;
        try { await paint(false); } catch (e) { /* keep last good screen */ }
      }, def.live));
    }
  };

  /* ---------- global event delegation ---------- */
  SC.actions.back = (el) => { if (history.length > 1) history.back(); else SC.go(el.dataset.fallback || SC.homeFor()); };
  SC.actions.reload = () => SC.render();
  SC.actions['close-modal'] = () => SC.closeModal();
  SC.actions['modal-bg'] = (el, e) => { if (e.target === el) SC.closeModal(); };
  SC.actions.logout = () => SC.logout();

  document.addEventListener('click', (e) => {
    const act = e.target.closest('[data-act]');
    if (act && SC.actions[act.dataset.act]) { SC.actions[act.dataset.act](act, e); return; }
    const go = e.target.closest('[data-go]');
    if (go) { e.preventDefault(); SC.go(go.dataset.go); }
  });
  document.addEventListener('submit', (e) => {
    const f = e.target.closest('form[data-form]');
    if (f && SC.forms[f.dataset.form]) { e.preventDefault(); SC.forms[f.dataset.form](f, e); }
  });
  window.addEventListener('hashchange', () => SC.render());
})();
