// BSAI Theme Synchronization Script
// Reads theme preference from cookie set by BSAI app

(function() {
  'use strict';

  // Read cookie value
  function getCookie(name) {
    const value = '; ' + document.cookie;
    const parts = value.split('; ' + name + '=');
    if (parts.length === 2) {
      return parts.pop().split(';').shift();
    }
    return null;
  }

  // Apply theme based on cookie or default to dark
  function applyTheme() {
    const theme = getCookie('bsai-theme') || 'dark';
    const html = document.documentElement;

    if (theme === 'dark') {
      html.classList.add('bsai-dark');
      html.classList.remove('bsai-light');
    } else {
      html.classList.add('bsai-light');
      html.classList.remove('bsai-dark');
    }
  }

  // Apply immediately (before DOM ready to prevent flash)
  applyTheme();

  // Also apply on DOM ready in case script loads late
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', applyTheme);
  }
})();
