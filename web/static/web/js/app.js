/* App bootstrap: session restore, notification polling, first render. */
(function () {
  let pollTimer = null;
  let lastNotif = SC.store.get('lastNotif', 0);

  async function pollNotifications() {
    if (!SC.state.user || document.hidden) return;
    try {
      const r = await SC.api('/notifications/');
      const latest = r.items[0];
      const changed = r.unread !== SC.state.unread;
      SC.state.unread = r.unread;
      if (latest && latest.id > lastNotif) {
        const isFirst = lastNotif === 0 && !SC.state.pollPrimed;
        lastNotif = latest.id; SC.store.set('lastNotif', lastNotif);
        if (!isFirst && !latest.is_read) {
          SC.toast(latest.title + (latest.message ? ' - ' + latest.message : ''), latest.title.indexOf('🚨') === 0 ? 'alert' : '', 6000);
          SC.beep();
        }
      }
      SC.state.pollPrimed = true;
      if (changed) SC.updateBadges();
    } catch (e) { /* offline or logged out */ }
  }

  SC.afterLogin = () => {
    SC.state.pollPrimed = false;
    clearInterval(pollTimer);
    pollNotifications();
    pollTimer = setInterval(pollNotifications, 8000);
  };

  (async function boot() {
    await SC.loadUser();
    if (SC.state.user) SC.afterLogin();
    if (!location.hash || location.hash === '#') location.hash = '#/';
    SC.render();
  })();
})();
