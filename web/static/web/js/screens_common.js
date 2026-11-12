/* Common screens: splash, onboarding, login, signup, forgot password, OTP, profile, settings, notifications. */
(function () {
  const { esc, icon } = SC;
  const logo = (cls) => `<div class="logo ${cls || ''}">${icon('shield')}</div>`;

  /* 1. Splash */
  SC.route('/', {
    public: true, chrome: false,
    render: async () => `<div class="splash">${logo()}<h1>ResQVision</h1><p style="color:#B9CBEA">AI road accident detection &amp; emergency response</p><div class="spinner" style="border-color:rgba(255,255,255,.25);border-top-color:#fff;margin-top:24px"></div></div>`,
    mount: () => {
      setTimeout(() => {
        if ((location.hash || '#/') !== '#/' && location.hash !== '') return;
        if (SC.state.user) SC.go(SC.homeFor());
        else SC.go(SC.store.get('onboarded') ? '/login' : '/onboarding');
      }, 1300);
    },
  });

  /* 2. Onboarding */
  const SLIDES = [
    ['camera', 'Detect accidents automatically', 'AI watches CCTV and video feeds, spots collisions in seconds and keeps the evidence.'],
    ['bell', 'Alert the right responders', 'Nearby police stations and hospitals are notified at once with location, severity and photos.'],
    ['activity', 'Coordinate every response', 'Accept, dispatch teams and ambulances, and track each incident until it is resolved.'],
  ];
  SC.state.onb = 0;
  SC.route('/onboarding', {
    public: true, chrome: false,
    render: async () => {
      const i = SC.state.onb; const s = SLIDES[i];
      return `<div class="onb"><div class="row between"><span class="muted bold">ResQVision</span><a data-act="onb-skip" class="bold">Skip</a></div>
        <div class="art"><div>${icon(s[0])}</div></div>
        <h1 class="center">${esc(s[1])}</h1><p class="muted center mt12">${esc(s[2])}</p>
        <div class="dots">${SLIDES.map((_, k) => `<i class="${k === i ? 'on' : ''}"></i>`).join('')}</div>
        <button class="btn" data-act="onb-next">${i === SLIDES.length - 1 ? 'Get started' : 'Next'}</button></div>`;
    },
  });
  SC.actions['onb-next'] = () => { if (SC.state.onb >= SLIDES.length - 1) { SC.state.onb = 0; SC.store.set('onboarded', true); SC.go('/login'); } else { SC.state.onb++; SC.render(); } };
  SC.actions['onb-skip'] = () => { SC.state.onb = 0; SC.store.set('onboarded', true); SC.go('/login'); };

  /* 3. Login (username or e-mail) */
  const DEMO = [['Admin', 'admin', 'Admin@123'], ['Police', 'police_cp', 'Police@123'], ['Hospital', 'hosp_aiims', 'Hospital@123']];
  SC.route('/login', {
    public: true, chrome: false,
    render: async () => `<div class="authpage">${logo('sm')}<h1 class="mt16">Welcome back</h1><p class="muted mt8 mb8">Sign in to the ResQVision emergency platform.</p>
      <form data-form="login" class="mt24">
        ${SC.ui.field({ label: 'Username or email', name: 'username', required: true, autocomplete: 'username', placeholder: 'e.g. police_cp' })}
        ${SC.ui.field({ label: 'Password', name: 'password', type: 'password', required: true, autocomplete: 'current-password', placeholder: 'Your password' })}
        <div class="row between mb8"><a data-go="/forgot" class="small bold">Forgot password?</a></div>
        <button class="btn" type="submit">Sign in</button></form>
      <p class="center small muted mt24">New police or hospital user? <a data-go="/signup" class="bold">Create an account</a></p>
      ${window.RV_CONFIG.demo ? `<div class="demo-box"><div class="small bold">Test accounts (run "python manage.py seed_demo" first)</div>${DEMO.map((d) => `<button class="btn sm light" data-act="fill-demo" data-user="${d[1]}" data-pass="${d[2]}">${d[0]}</button>`).join('')}</div>` : ''}</div>`,
  });
  SC.actions['fill-demo'] = (el) => { const f = document.querySelector('form[data-form=login]'); f.username.value = el.dataset.user; f.password.value = el.dataset.pass; };
  SC.forms.login = (form) => SC.run(form.querySelector('button[type=submit]'), async () => {
    const d = SC.formData(form);
    const user = await SC.api('/auth/login/', { method: 'POST', body: { username: d.username, password: d.password }, auth: false });
    SC.setSession(user);
    SC.afterLogin();
    SC.go(SC.homeFor());
  });

  /* 4. Signup */
  const orgOptions = (role) => ((role === 'hospital' ? SC.state.orgs.hospitals : SC.state.orgs.police_stations) || []).map((o) => [o.id, o.name]);
  SC.route('/signup', {
    public: true, chrome: false,
    render: async () => {
      SC.state.orgs = await SC.api('/auth/organizations/', { auth: false });
      return `<div class="authpage"><a data-go="/login" class="row small bold">${icon('back', 'sm')} Back to sign in</a><h1 class="mt16">Create account</h1>
        <p class="muted mt8 mb8">Accounts are reviewed by an administrator before first sign-in.</p>
        <form data-form="signup" class="mt16">
          ${SC.ui.field({ label: 'First name', name: 'first_name', required: true })}
          ${SC.ui.field({ label: 'Last name', name: 'last_name' })}
          ${SC.ui.field({ label: 'Username', name: 'username', required: true, autocomplete: 'username' })}
          ${SC.ui.field({ label: 'Email', name: 'email', type: 'email', required: true })}
          ${SC.ui.field({ label: 'Phone', name: 'phone', type: 'tel' })}
          ${SC.ui.field({ label: 'I am a', name: 'role', type: 'select', options: [['police', 'Police officer'], ['hospital', 'Hospital staff']] })}
          ${SC.ui.field({ label: 'Organization', name: 'organization', type: 'select', options: orgOptions('police'), required: true })}
          ${SC.ui.field({ label: 'Password (min 8 characters)', name: 'password', type: 'password', required: true, autocomplete: 'new-password' })}
          <button class="btn" type="submit">Create account</button></form></div>`;
    },
    mount: (el) => {
      const form = el.querySelector('form');
      form.role.onchange = () => { form.organization.innerHTML = orgOptions(form.role.value).map(([id, name]) => `<option value="${id}">${esc(name)}</option>`).join(''); };
    },
  });
  SC.forms.signup = (form) => SC.run(form.querySelector('button[type=submit]'), async () => {
    const d = SC.formData(form);
    const body = { username: d.username, email: d.email, first_name: d.first_name, last_name: d.last_name, phone: d.phone, role: d.role, password: d.password };
    body[d.role === 'hospital' ? 'hospital' : 'police_station'] = Number(d.organization);
    const res = await SC.api('/auth/signup/', { method: 'POST', body, auth: false });
    SC.toast(res.detail, 'success', 6000);
    SC.go('/login');
  });

  /* 5. Forgot password -> 6. OTP -> reset */
  SC.route('/forgot', {
    public: true, chrome: false,
    render: async () => `<div class="authpage"><a data-go="/login" class="row small bold">${icon('back', 'sm')} Back to sign in</a><h1 class="mt16">Forgot password?</h1>
      <p class="muted mt8">Enter your username, email or phone and we will issue a 6-digit verification code.</p>
      <form data-form="forgot" class="mt24">${SC.ui.field({ label: 'Username, email or phone', name: 'identifier', required: true })}<button class="btn" type="submit">Send code</button></form></div>`,
  });
  SC.forms.forgot = (form) => SC.run(form.querySelector('button[type=submit]'), async () => {
    const d = SC.formData(form);
    const res = await SC.api('/auth/forgot-password/', { method: 'POST', body: { identifier: d.identifier }, auth: false });
    SC.state.resetId = d.identifier;
    SC.toast(res.dev_otp ? `Development mode - your code is ${res.dev_otp}` : res.detail, 'success', 9000);
    SC.go('/otp');
  });
  SC.route('/otp', {
    public: true, chrome: false,
    render: async () => `<div class="authpage"><a data-go="/forgot" class="row small bold">${icon('back', 'sm')} Back</a><h1 class="mt16">Verify your code</h1>
      <p class="muted mt8">Enter the 6-digit code for <b>${esc(SC.state.resetId || 'your account')}</b>. In development it is shown on screen and printed in the server console.</p>
      <form data-form="otp" class="mt24"><label class="fld">Verification code<input class="otp-input" name="code" inputmode="numeric" maxlength="6" pattern="[0-9]{6}" required autocomplete="one-time-code"></label>
      <button class="btn" type="submit">Verify</button></form></div>`,
  });
  SC.forms.otp = (form) => SC.run(form.querySelector('button[type=submit]'), async () => {
    const code = SC.formData(form).code;
    await SC.api('/auth/verify-otp/', { method: 'POST', body: { identifier: SC.state.resetId, code }, auth: false });
    SC.state.resetCode = code;
    SC.go('/reset');
  });
  SC.route('/reset', {
    public: true, chrome: false,
    render: async () => `<div class="authpage"><h1>Set a new password</h1><p class="muted mt8">Choose a strong password of at least 8 characters.</p>
      <form data-form="reset" class="mt24">${SC.ui.field({ label: 'New password', name: 'p1', type: 'password', required: true, autocomplete: 'new-password' })}${SC.ui.field({ label: 'Confirm password', name: 'p2', type: 'password', required: true, autocomplete: 'new-password' })}<button class="btn" type="submit">Update password</button></form></div>`,
  });
  SC.forms.reset = (form) => SC.run(form.querySelector('button[type=submit]'), async () => {
    const d = SC.formData(form);
    if (d.p1 !== d.p2) throw new Error('Passwords do not match.');
    const res = await SC.api('/auth/reset-password/', { method: 'POST', body: { identifier: SC.state.resetId, code: SC.state.resetCode, new_password: d.p1 }, auth: false });
    SC.toast(res.detail, 'success');
    SC.go('/login');
  });

  /* 7. Profile */
  SC.route('/profile', {
    title: 'Profile', tab: '/profile',
    render: async () => {
      const u = SC.state.user;
      const org = u.police_station_name || u.hospital_name || '';
      const roleLabel = { admin: 'Administrator', police: 'Police', hospital: 'Hospital', ambulance: 'Ambulance' }[u.role];
      return `<div class="card center"><div class="avatar">${esc(SC.fmt.initials(u.full_name))}</div><h2 class="mt12">${esc(u.full_name)}</h2><p class="muted small">${esc(u.email || u.username)}</p>
        <div class="row wrap mt12" style="justify-content:center"><span class="badge">${esc(roleLabel)}</span>${org ? `<span class="badge gray">${esc(org)}</span>` : ''}</div></div>
        <div class="card mt16"><dl class="kv"><dt>Username</dt><dd>${esc(u.username)}</dd><dt>Phone</dt><dd>${esc(u.phone || '-')}</dd><dt>Member since</dt><dd>${SC.fmt.dt(u.date_joined)}</dd></dl></div>
        <div class="card mt16 menu">
          <div class="mi" data-act="edit-profile">${icon('edit')}<span class="grow">Edit profile</span>${icon('chevron')}</div>
          <div class="mi" data-act="change-password">${icon('lock')}<span class="grow">Change password</span>${icon('chevron')}</div>
          <a data-go="/settings">${icon('settings')}<span class="grow">Settings</span>${icon('chevron')}</a>
          ${u.role === 'admin' ? `<a data-go="/admin/settings">${icon('server')}<span class="grow">System settings</span>${icon('chevron')}</a>` : ''}
          <div class="mi" data-act="logout" style="color:var(--red)">${icon('logout')}<span class="grow">Sign out</span></div></div>`;
    },
  });
  SC.actions['edit-profile'] = () => {
    const u = SC.state.user;
    SC.formModal({
      title: 'Edit profile', submit: 'Save changes', values: { first_name: u.first_name, last_name: u.last_name, email: u.email, phone: u.phone },
      fields: [{ label: 'First name', name: 'first_name', required: true }, { label: 'Last name', name: 'last_name' }, { label: 'Email', name: 'email', type: 'email' }, { label: 'Phone', name: 'phone', type: 'tel' }],
      onSubmit: async (d) => { SC.state.user = await SC.patch('/auth/me/', d); SC.toast('Profile updated', 'success'); SC.render(); },
    });
  };
  SC.actions['change-password'] = () => SC.formModal({ title: 'Change password', submit: 'Update password', fields: [{ label: 'Current password', name: 'old_password', type: 'password', required: true }, { label: 'New password', name: 'new_password', type: 'password', required: true }], onSubmit: async (d) => { await SC.post('/auth/change-password/', d); SC.toast('Password changed', 'success'); } });

  /* 8. Settings (per-device preferences) */
  SC.route('/settings', {
    title: 'Settings', back: '/profile', tab: '/profile',
    render: async () => {
      const row = (key, label, sub) => `<div class="row between" style="padding:12px 0;border-bottom:1px solid var(--line)"><div><div class="bold">${label}</div><div class="small muted">${sub}</div></div><label class="switch"><input type="checkbox" data-pref="${key}" ${SC.store.get(key, true) !== false ? 'checked' : ''}><span></span></label></div>`;
      return `<div class="card">${row('sound', 'Alert sound', 'Play a tone when a new emergency alert arrives')}${row('live', 'Auto-refresh', 'Keep lists and dashboards updated every few seconds')}</div>
        <div class="card mt16"><h3>About</h3><p class="small muted mt8">ResQVision v1.0 &middot; AI-based road accident detection and emergency response. AI severity values are estimates, not confirmed medical assessments.</p>
        ${SC.state.user.role === 'admin' ? `<a class="btn light mt12" href="/admin/" target="_blank">Open Django admin</a>` : ''}</div>`;
    },
    mount: (el) => el.querySelectorAll('[data-pref]').forEach((c) => (c.onchange = () => SC.store.set(c.dataset.pref, c.checked))),
  });

  /* 9. Notifications */
  SC.route('/notifications', {
    title: 'Notifications', tab: '/notifications', live: 10000,
    render: async () => {
      const res = await SC.get('/notifications/');
      const list = res.items;
      SC.state.unread = res.unread; SC.updateBadges();
      const alertish = (n) => n.title.indexOf('🚨') === 0;
      return `<div class="row between mb8"><span class="muted small">${res.unread} unread</span>${res.unread ? '<button class="btn sm light" data-act="read-all">Mark all read</button>' : ''}</div>
        <div class="list">${list.length ? list.map((n) => `<div class="card clickable notif ${n.is_read ? '' : 'unread'}" data-act="open-notif" data-id="${n.id}" data-acc="${n.accident_id || ''}">
          <div class="row" style="align-items:flex-start"><span style="color:${alertish(n) ? 'var(--red)' : 'var(--navy)'}">${icon(alertish(n) ? 'alert' : 'info')}</span>
          <div class="grow"><div class="row between"><b class="small">${esc(n.title)}</b><span class="tiny muted">${SC.fmt.ago(n.created_at)}</span></div>
          <div class="small muted mt8">${esc(n.message)}</div></div></div></div>`).join('') : SC.ui.empty('No notifications', 'New emergency alerts will appear here.', 'bell')}</div>`;
    },
  });
  SC.actions['read-all'] = async () => { await SC.post('/notifications/read/'); SC.state.unread = 0; SC.render(); };
  SC.actions['open-notif'] = async (el) => {
    SC.post(`/notifications/${el.dataset.id}/read/`).catch(() => {});
    if (el.dataset.acc) SC.go('/accident/' + el.dataset.acc);
    else el.classList.remove('unread');
  };

  /* Ambulance role (future module) */
  SC.route('/ambulance', {
    title: 'Ambulance', roles: ['ambulance'],
    render: async () => `<div class="card center mt24">${icon('truck', 'lg')}<h2 class="mt12">Responder module coming soon</h2><p class="muted mt8 small">Ambulance dispatch, navigation and mission history are planned for a future version. Your hospital dispatcher can already assign ambulances from the Hospital dashboard.</p><button class="btn mt16" data-act="logout">Sign out</button></div>`,
  });
})();
