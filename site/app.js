/* A disconnected visual preview. No requests, storage, or machine access. */
(() => {
  'use strict';

  const button = document.getElementById('preview-switch');
  const plate = document.querySelector('.switch-plate');
  const state = document.getElementById('preview-state');
  const label = document.getElementById('preview-label');
  const hint = document.getElementById('preview-hint');
  if (!button || !plate || !state || !label || !hint) return;

  // A native button provides Enter, Space, touch, and assistive-tech activation.
  // Keep its accessible name stable; aria-pressed carries the current state.
  button.disabled = false;
  hint.textContent = 'Press the switch to preview ON. Nothing on your machine changes.';

  button.addEventListener('click', () => {
    const on = button.getAttribute('aria-pressed') !== 'true';
    button.setAttribute('aria-pressed', String(on));
    plate.dataset.state = on ? 'on' : 'off';
    state.textContent = on ? 'ON' : 'OFF';
    label.textContent = on ? 'Native full access' : 'Saved settings';
    hint.textContent = on
      ? 'Preview ON. In the app, ON changes the selected runtime’s execution settings.'
      : 'Preview OFF. In the app, OFF restores settings—not running tasks or OS grants.';
  });
})();
