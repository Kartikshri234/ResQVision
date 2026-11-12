/* Core screens: accident details, evidence viewer, map & location, status tracking, timeline, map tab. */
(function () {
  const { esc, icon } = SC;
  const tabFor = (u) => ({ admin: '/admin/accidents', police: '/police/alerts', hospital: '/hospital/alerts' }[u.role]);
  SC.haversine = (a, b, c, d) => {
    const R = 6371, rad = (x) => (x * Math.PI) / 180;
    const dp = rad(c - a), dl = rad(d - b);
    const h = Math.sin(dp / 2) ** 2 + Math.cos(rad(a)) * Math.cos(rad(c)) * Math.sin(dl / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  };
  // The response screens are keyed by the accident id; the alert id comes from a.my_alert.
  const respondPath = (a) => (a.my_alert.kind === 'police' ? '/police/dispatch/' : '/hospital/respond/') + a.id;
  SC.respondPath = respondPath;
  const stepper = (steps) => `<div class="steps">${steps.map((s) => `<div class="step ${s.state}"><div class="pt">${s.state === 'done' ? icon('check') : ''}</div><b>${esc(s.label)}</b>${s.sub ? `<div class="small muted">${esc(s.sub)}</div>` : ''}</div>`).join('')}</div>`;
  SC.ui.stepper = stepper;
  const subnav = (id, active) => `<div class="chips"><a class="chip ${active === 'detail' ? 'active' : ''}" data-go="/accident/${id}">Details</a><a class="chip ${active === 'map' ? 'active' : ''}" data-go="/accident/${id}/map">Location</a><a class="chip ${active === 'status' ? 'active' : ''}" data-go="/accident/${id}/status">Status</a><a class="chip ${active === 'timeline' ? 'active' : ''}" data-go="/accident/${id}/timeline">Timeline</a><a class="chip ${active === 'evidence' ? 'active' : ''}" data-go="/evidence/${id}">Evidence</a></div>`;
  // Admins get every alert; police / hospital users only get their own (a.my_alert).
  const alertsOf = (a) => a.alerts || (a.my_alert ? [a.my_alert] : []);

  /* 30. Accident details */
  SC.route('/accident/:id', {
    title: 'Accident Details', back: true, tab: tabFor, live: 8000,
    render: async ({ id }) => {
      const a = await SC.get(`/accidents/${id}/`);
      const u = SC.state.user;
      const mine = a.my_alert;
      const evidence = a.snapshot
        ? `<div class="evidence" data-go="/evidence/${a.id}" style="background-image:url('${esc(a.snapshot)}')"><span class="tag">${icon('camera', 'sm')} ${esc(a.camera || 'Mobile camera')}${a.is_simulated ? ' &middot; simulated' : ''}</span></div>`
        : `<div class="evidence" data-go="/evidence/${a.id}">${icon('image', 'lg')}<span class="tag">No snapshot</span></div>`;
      const alertRows = (kind) => {
        const list = alertsOf(a).filter((x) => x.kind === kind);
        if (!list.length) return `<div class="small muted">${a.alerts ? 'Not notified' : 'Handled by another organisation'}</div>`;
        return list.map((x) => `<div class="row between small" style="padding:6px 0"><span>${esc(x.org)} <span class="muted">${Number(x.distance_km).toFixed(1)} km</span></span>${SC.ui.alertStatus(x.status)}</div>${x.reject_reason ? `<div class="tiny muted">Reason: ${esc(x.reject_reason)}</div>` : ''}${x.team_name ? `<div class="tiny muted">Team: ${esc(x.team_name)}</div>` : ''}${x.ambulance ? `<div class="tiny muted">Ambulance: ${esc(x.ambulance)}</div>` : ''}`).join('');
      };
      let actions = '';
      if (u.role === 'admin') {
        if (['detected', 'verification_pending'].includes(a.status)) actions += `<div class="card mt16" style="border:1.5px solid var(--orange)"><b>Verification needed</b><p class="small muted mt8">AI confidence is below the auto-alert threshold. Review the evidence, then confirm or dismiss.</p><div class="btnrow mt12"><button class="btn green" data-act="acc-op" data-op="confirm" data-id="${a.id}">Confirm &amp; alert</button><button class="btn light" data-act="acc-op" data-op="dismiss" data-id="${a.id}">False alarm</button></div></div>`;
        else if (a.status !== 'closed') actions += `<button class="btn ghost mt16" data-act="acc-op" data-op="close" data-id="${a.id}">Close incident</button>`;
      } else if (mine) {
        if (mine.status === 'pending') actions += `<div class="card mt16" style="border:1.5px solid var(--red)"><b>Emergency alert for ${esc(mine.org)}</b><p class="small muted mt8">${Number(mine.distance_km).toFixed(1)} km from your location. Accept to take responsibility for the response.</p><div class="btnrow mt12"><button class="btn green" data-act="accept-alert" data-id="${mine.id}">Accept</button><button class="btn light" data-act="reject-alert" data-id="${mine.id}">Reject</button></div></div>`;
        else if (['accepted', 'dispatched', 'arrived'].includes(mine.status)) actions += `<button class="btn mt16" data-go="${respondPath(a)}">${icon('zap')} Manage response (${esc(SC.ALERT[mine.status])})</button>`;
        else if (mine.status === 'rejected') actions += `<div class="card mt16 small muted">You rejected this alert: ${esc(mine.reject_reason)}</div>`;
      }
      return `${subnav(a.id, 'detail')}${evidence}
        <div class="card mt12"><div class="row between"><div><div class="muted small">Accident ID</div><h2>${esc(a.accident_id)}</h2></div><div class="ring" style="--p:${Math.round(a.confidence)}"><div>${SC.fmt.pct(a.confidence)}</div></div></div>
          <div class="row wrap mt12" style="gap:6px">${SC.ui.sev(a.severity)}${SC.ui.status(a.status)}</div>
          <dl class="kv mt16"><dt>Type</dt><dd>${esc(a.accident_type || '-')}</dd><dt>Location</dt><dd>${esc(a.location || '-')}</dd><dt>Detected</dt><dd>${SC.fmt.dt(a.detected_at)}</dd><dt>Camera</dt><dd>${esc(a.camera ? a.camera + ' - ' + a.camera_name : 'Mobile / GPS')}</dd><dt>Vehicles</dt><dd>${esc(a.vehicles || '-')}</dd><dt>People detected</dt><dd>${a.people_count}</dd><dt>Coordinates</dt><dd>${a.latitude.toFixed(5)}, ${a.longitude.toFixed(5)}</dd></dl>
          <p class="tiny muted mt12">${icon('info', 'sm')} Severity is an AI-generated estimate, not a confirmed medical assessment.</p></div>
        <div class="section-title"><h3>Response status</h3></div>
        <div class="grid2"><div class="card"><div class="row between mb8"><b class="small">${icon('shield', 'sm')} Police</b>${SC.ui.alertStatus(a.police_status)}</div>${alertRows('police')}</div>
        <div class="card"><div class="row between mb8"><b class="small">${icon('hospital', 'sm')} Hospital</b>${SC.ui.alertStatus(a.hospital_status)}</div>${alertRows('hospital')}</div></div>
        ${actions}
        <a class="btn light mt12" target="_blank" rel="noopener" href="${SC.gmapsLink(a.latitude, a.longitude)}">${icon('nav')} Route to accident (Google Maps)</a>`;
    },
  });

  /* Alert actions: every response goes through POST /alerts/<id>/respond/ */
  SC.respond = (alertId, body) => SC.post(`/alerts/${alertId}/respond/`, body);
  SC.actions['accept-alert'] = (el) => SC.run(el, async () => { await SC.respond(el.dataset.id, { action: 'accept' }); SC.toast('Incident accepted', 'success'); SC.render(); });
  SC.actions['reject-alert'] = (el) => {
    const id = el.dataset.id;
    SC.formModal({ title: 'Reject incident', submit: 'Reject incident', note: 'A reason is required so the next nearest service can be alerted.', fields: [{ label: 'Reason', name: 'reason', type: 'textarea', required: true, placeholder: 'e.g. No units available' }], onSubmit: async (d) => { await SC.respond(id, { action: 'reject', reason: d.reason }); SC.toast('Incident rejected'); SC.render(); } });
  };
  SC.actions['acc-op'] = (el) => {
    const { op, id } = el.dataset;
    const text = { confirm: ['Confirm accident', 'Alerts will be sent to nearby police stations and hospitals.', 'Confirm & alert'], dismiss: ['Dismiss as false alarm', 'The detection will be closed and no alerts will be sent.', 'Dismiss'], close: ['Close incident', 'Mark this incident as closed. Any open responses are completed.', 'Close'] }[op];
    SC.confirm(text[0], text[1], text[2], async () => {
      if (op === 'confirm') await SC.post(`/accidents/${id}/confirm/`);
      else await SC.post(`/accidents/${id}/close/`, op === 'dismiss' ? { reason: 'False alarm' } : {});
      SC.toast('Updated', 'success'); SC.render();
    }, op === 'dismiss');
  };

  /* 31. Evidence viewer */
  SC.route('/evidence/:id', {
    title: 'Evidence Viewer', back: true, tab: tabFor,
    render: async ({ id }) => {
      const a = await SC.get(`/accidents/${id}/`);
      const media = (a.snapshot ? `<img src="${esc(a.snapshot)}" alt="Accident snapshot" style="width:100%;border-radius:16px;background:#1b2a41">` : SC.ui.empty('No snapshot stored', 'The AI service did not attach an image.', 'image'))
        + (a.video ? `<video src="${esc(a.video)}" controls playsinline preload="metadata" style="width:100%;border-radius:16px;margin-top:12px;background:#000"></video>` : '<div class="card flat mt12 small muted center">No video clip available for this accident.</div>');
      return `${subnav(a.id, 'evidence')}${media}
        <div class="card mt12"><dl class="kv"><dt>Accident ID</dt><dd>${esc(a.accident_id)}</dd><dt>Timestamp</dt><dd>${new Date(a.detected_at).toLocaleString('en-IN')}</dd><dt>Camera ID</dt><dd>${esc(a.camera || 'Mobile / GPS')}</dd><dt>Confidence</dt><dd>${SC.fmt.pct(a.confidence)}</dd></dl>
        <div class="btnrow mt12">${a.snapshot ? `<a class="btn light sm" href="${esc(a.snapshot)}" download>${icon('download', 'sm')} Snapshot</a>` : ''}${a.video ? `<a class="btn light sm" href="${esc(a.video)}" download>${icon('download', 'sm')} Video</a>` : ''}</div></div>`;
    },
  });

  /* 32. Map and location (single accident) */
  SC.route('/accident/:id/map', {
    title: 'Map & Location', back: true, tab: tabFor,
    render: async ({ id }) => {
      const [a, m] = await Promise.all([SC.get(`/accidents/${id}/`), SC.get('/map/')]);
      SC.state.mapData = { a, m };
      const rank = (list, kind) => list.filter((o) => o.is_active).map((o) => ({ ...o, kind, d: SC.haversine(a.latitude, a.longitude, o.latitude, o.longitude) })).sort((x, y) => x.d - y.d).slice(0, 5);
      const near = [...rank(m.police, 'police'), ...rank(m.hospitals, 'hospital')];
      const notified = new Set(alertsOf(a).map((x) => x.org));
      return `${subnav(a.id, 'map')}<div class="map" id="map"></div>
        <div class="card mt12"><b>${esc(a.accident_id)}</b> &middot; ${esc(a.location || '')}<div class="small muted mt8">${a.latitude.toFixed(5)}, ${a.longitude.toFixed(5)}</div>
        <a class="btn mt12" target="_blank" rel="noopener" href="${SC.gmapsLink(a.latitude, a.longitude)}">${icon('nav')} Open route in Google Maps</a></div>
        ${SC.ui.section('Nearest services')}
        <div class="list">${near.map((o) => `<div class="card row"><span style="color:${o.kind === 'police' ? 'var(--navy)' : 'var(--green)'}">${icon(o.kind === 'police' ? 'shield' : 'hospital', 'lg')}</span><div class="grow"><b class="small">${esc(o.name)}</b><div class="tiny muted">${o.d.toFixed(1)} km away${o.kind === 'hospital' ? (o.accepting_emergencies ? ' &middot; accepting emergencies' : ' &middot; not accepting emergencies') : ''}</div></div>${notified.has(o.name) ? '<span class="badge green">Notified</span>' : ''}</div>`).join('')}</div>`;
    },
    mount: (el) => {
      const { a, m } = SC.state.mapData;
      const markers = [SC.accidentMarker(a)]
        .concat(m.police.filter((s) => s.is_active).map((s) => ({ lat: s.latitude, lng: s.longitude, color: '#0B2A5B', glyph: 'P', popup: `<b>${esc(s.name)}</b><br>Police station` })))
        .concat(m.hospitals.filter((h) => h.is_active).map((h) => ({ lat: h.latitude, lng: h.longitude, color: '#12B76A', glyph: 'H', popup: `<b>${esc(h.name)}</b><br>Hospital` })));
      const lines = (a.alerts || []).map((al) => { const o = (al.kind === 'police' ? m.police : m.hospitals).find((x) => x.name === al.org); return o ? { points: [[a.latitude, a.longitude], [o.latitude, o.longitude]], color: al.kind === 'police' ? '#163F82' : '#12B76A' } : null; }).filter(Boolean);
      SC.makeMap(el.querySelector('#map'), { center: [a.latitude, a.longitude], markers, lines, zoom: 14 });
    },
  });

  /* 33. Status tracking */
  SC.route('/accident/:id/status', {
    title: 'Status Tracking', back: true, tab: tabFor, live: 8000,
    render: async ({ id }) => {
      const a = await SC.get(`/accidents/${id}/`);
      const path = ['detected', 'confirmed', 'alert_sent', 'accepted', 'team_dispatched', 'arrived', 'resolved', 'closed'];
      if (a.status === 'verification_pending') path.splice(1, 0, 'verification_pending');
      const cur = SC.STATUS_ORDER.indexOf(a.status);
      const steps = path.map((s) => { const i = SC.STATUS_ORDER.indexOf(s); return { label: SC.STATUS[s], state: s === a.status ? 'current' : i < cur ? 'done' : 'todo' }; });
      const track = (kind, title, ico) => {
        const list = alertsOf(a).filter((x) => x.kind === kind);
        if (!list.length) return `<div class="card"><b>${icon(ico, 'sm')} ${title}</b><p class="small muted mt8">${a.alerts ? 'Not notified yet.' : 'Handled by another organisation.'}</p></div>`;
        return list.map((al) => {
          const seq = ['pending', 'accepted', 'dispatched', 'arrived', 'resolved'];
          const rej = al.status === 'rejected';
          const ci = seq.indexOf(al.status);
          const items = rej ? [{ label: 'Alert received', state: 'done' }, { label: 'Rejected', state: 'current', sub: al.reject_reason }] : seq.map((s, i) => ({ label: SC.ALERT[s], state: i < ci || al.status === 'resolved' ? 'done' : i === ci ? 'current' : 'todo', sub: i === 2 && (al.team_name || al.ambulance) ? (al.team_name ? 'Team ' + al.team_name : 'Ambulance ' + al.ambulance) : '' }));
          return `<div class="card mt12"><div class="row between mb8"><b>${icon(ico, 'sm')} ${esc(al.org)}</b>${SC.ui.alertStatus(al.status)}</div>${stepper(items)}</div>`;
        }).join('');
      };
      return `${subnav(a.id, 'status')}<div class="card"><div class="row between mb8"><h3>${esc(a.accident_id)} overall</h3>${SC.ui.status(a.status)}</div>${stepper(steps)}</div>
        ${SC.ui.section('Police response')}${track('police', 'Police', 'shield')}${SC.ui.section('Hospital response')}${track('hospital', 'Hospital', 'hospital')}`;
    },
  });

  /* 34. Accident timeline */
  SC.route('/accident/:id/timeline', {
    title: 'Accident Timeline', back: true, tab: tabFor, live: 8000,
    render: async ({ id }) => {
      const a = await SC.get(`/accidents/${id}/`);
      const events = a.timeline.slice().reverse();
      return `${subnav(a.id, 'timeline')}<div class="card"><h3 class="mb8">${esc(a.accident_id)} &middot; ${esc(a.accident_type || 'Accident')}</h3>
        ${events.length ? `<div class="steps mt12">${events.map((e, i) => `<div class="step ${i === 0 ? 'current' : 'done'}"><div class="pt">${i === 0 ? '' : icon('check')}</div><b>${esc(e.message)}</b><div class="tiny muted">${SC.fmt.dt(e.at)}${e.actor ? ' &middot; ' + esc(e.actor) : ''}</div></div>`).join('')}</div>` : SC.ui.empty('No events yet')}</div>`;
    },
  });

  /* Map tab: all active incidents and emergency services */
  SC.route('/map', {
    title: 'Map', tab: '/map', roles: ['police', 'hospital', 'admin'],
    render: async () => {
      const [m, active] = await Promise.all([SC.get('/map/'), SC.get('/accidents/?view=active')]);
      SC.state.mapAll = m;
      return `<div class="chips" id="layers"><span class="chip active" data-layer="accidents">Accidents (${m.accidents.length})</span><span class="chip active" data-layer="hospitals">Hospitals</span><span class="chip active" data-layer="police">Police</span>${m.cameras.length ? '<span class="chip" data-layer="cameras">Cameras</span>' : ''}</div>
        <div class="map full" id="map"></div>
        ${SC.ui.section('Active incidents')}<div class="list">${active.length ? active.map((a) => SC.ui.accCard(a)).join('') : SC.ui.empty('No active incidents', 'Detected accidents will appear on the map.', 'map')}</div>`;
    },
    mount: (el) => {
      const d = SC.state.mapAll;
      const map = SC.makeMap(el.querySelector('#map'), { markers: [], center: [28.6139, 77.2090] });
      if (!map) return;
      const mk = (m) => L.marker([m.lat, m.lng], { icon: L.divIcon({ className: '', html: `<div class="pin" style="background:${m.color}"><span>${m.glyph}</span></div>`, iconSize: [30, 30], iconAnchor: [15, 30], popupAnchor: [0, -28] }) }).bindPopup(m.popup);
      const groups = {
        accidents: L.layerGroup(d.accidents.map((a) => mk(SC.accidentMarker(a)))),
        hospitals: L.layerGroup(d.hospitals.filter((h) => h.is_active).map((h) => mk({ lat: h.latitude, lng: h.longitude, color: '#12B76A', glyph: 'H', popup: `<b>${esc(h.name)}</b><br>${h.accepting_emergencies ? 'Accepting emergencies' : 'Not accepting emergencies'}` }))),
        police: L.layerGroup(d.police.filter((s) => s.is_active).map((s) => mk({ lat: s.latitude, lng: s.longitude, color: '#0B2A5B', glyph: 'P', popup: `<b>${esc(s.name)}</b><br>Police station` }))),
        cameras: L.layerGroup(d.cameras.map((c) => mk({ lat: c.latitude, lng: c.longitude, color: '#667085', glyph: 'C', popup: `<b>${esc(c.camera_id)}</b><br>${esc(c.name)}` }))),
      };
      ['accidents', 'hospitals', 'police'].forEach((k) => groups[k].addTo(map));
      const pts = [].concat(d.accidents.map((a) => [a.latitude, a.longitude]), d.hospitals.map((h) => [h.latitude, h.longitude]), d.police.map((s) => [s.latitude, s.longitude]));
      if (pts.length) map.fitBounds(pts, { padding: [30, 30], maxZoom: 14 });
      el.querySelectorAll('[data-layer]').forEach((chip) => (chip.onclick = () => {
        const g = groups[chip.dataset.layer];
        if (map.hasLayer(g)) { map.removeLayer(g); chip.classList.remove('active'); } else { g.addTo(map); chip.classList.add('active'); }
      }));
    },
  });
})();
