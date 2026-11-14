/* App bootstrap: session restore, notification polling, first render. */
(function () {
  let pollTimer = null;
  const BASE_TITLE = document.title;
  // The last notification this user has been told about. Stored PER USER: ids are global, so one shared value
  // would make the next person on the same PC miss every alert older than the previous user's last one.
  const keyFor = () => 'lastNotif_' + (SC.state.user ? SC.state.user.id : 0);
  let lastNotif = 0;

  function titleBadge() {
    document.title = (SC.state.user && SC.state.unread ? '(' + SC.state.unread + ') ' : '') + BASE_TITLE;
  }

  async function pollNotifications() {
    if (!SC.state.user) { document.title = BASE_TITLE; return; }
    // Deliberately keeps polling while the tab is in the background: an emergency alert must still beep and
    // show "(n)" in the tab title when the dispatcher is looking at another window.
    try {
      const r = await SC.api('/notifications/');
      const changed = r.unread !== SC.state.unread;
      SC.state.unread = r.unread;
      const firstEver = !SC.state.pollPrimed && lastNotif === 0;   // nothing seen before: do not replay history
      const fresh = r.items.filter((n) => n.id > lastNotif && !n.is_read);
      const newest = r.items.reduce((m, n) => Math.max(m, n.id), lastNotif);
      if (!firstEver && fresh.length) {
        fresh.slice(0, 3).reverse().forEach((n) => SC.toast(n.title + (n.message ? ' - ' + n.message : ''), n.title.indexOf('🚨') === 0 ? 'alert' : '', 6000));
        if (fresh.length > 3) SC.toast('+' + (fresh.length - 3) + ' more notifications', '', 6000);
        SC.beep();
      }
      if (newest > lastNotif) { lastNotif = newest; SC.store.set(keyFor(), lastNotif); }
      SC.state.pollPrimed = true;
      if (changed) SC.updateBadges();
      titleBadge();
    } catch (e) { /* offline or logged out */ }
  }

  SC.afterLogin = () => {
    SC.state.pollPrimed = false;
    lastNotif = SC.store.get(keyFor(), 0);
    clearInterval(pollTimer);
    pollNotifications();
    pollTimer = setInterval(pollNotifications, 8000);
  };

  document.addEventListener('visibilitychange', () => { if (!document.hidden) pollNotifications(); });

  (async function boot() {
    await SC.loadUser();
    if (SC.state.user) SC.afterLogin();
    if (!location.hash || location.hash === '#') location.hash = '#/';
    SC.render();
  })();
})();
