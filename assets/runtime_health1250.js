/* Passive component warnings. The authenticated backend owns path validation. */
(function () {
  'use strict';
  if (window.RuntimeHealth1250) return;
  let banner, message, retry, boundInput;
  async function get(path) {
    const response = await fetch(path, {credentials: 'same-origin', cache: 'no-store'});
    if (!response.ok) throw new Error('运行检查暂不可用');
    return response.json();
  }
  function ensureBanner() {
    if (banner) return;
    const style = document.createElement('style');
    style.textContent = '.runtime-health1250{box-sizing:border-box;margin:12px 20px;padding:12px 16px;border:1px solid #c4b5fd;border-radius:10px;background:#f5f3ff;color:#4c1d95;display:flex;align-items:center;gap:12px;font-size:13px;line-height:1.6}.runtime-health1250[hidden]{display:none}.runtime-health1250 span{flex:1;white-space:pre-line}.runtime-health1250 button{background:#fff;color:#6d28d9;border:1px solid #c4b5fd;border-radius:6px;padding:6px 12px;cursor:pointer;flex-shrink:0}.runtime-draft-error1250{margin:6px 0;color:#b91c1c;font-size:12px;line-height:1.5}';
    document.head.append(style);
    banner = document.createElement('div');
    banner.className = 'runtime-health1250';
    banner.setAttribute('role', 'status');
    banner.setAttribute('aria-live', 'polite');
    banner.hidden = true;
    message = document.createElement('span');
    retry = document.createElement('button');
    retry.type = 'button';
    retry.textContent = '重新检查';
    retry.addEventListener('click', refresh);
    banner.append(message, retry);
    document.body.prepend(banner);
  }
  async function refresh() {
    ensureBanner();
    retry.disabled = true;
    try {
      const state = await get('/api/runtime/health');
      const warnings = ['draft_generator', 'ffmpeg'].map(key => state[key])
        .filter(component => component && component.status !== 'ready')
        .map(component => component.message || '运行组件需要检查');
      message.textContent = warnings.length ? warnings.join('；') : (state.ok ? '' : '运行组件检查未完整返回，请重新检查');
      banner.hidden = state.ok === true && warnings.length === 0;
    } catch (_) {
      message.textContent = '运行组件检查失败，请稍后重试；可继续编辑文字。';
      banner.hidden = false;
    } finally {
      retry.disabled = false;
    }
  }
  function validateDraftPath(value) {
    return get('/api/runtime/draft-path-check?' + new URLSearchParams({path: String(value || '').trim()}));
  }
  function bindDraftInput() {
    const input = document.getElementById('jy-draft-path');
    if (!input || boundInput === input) return;
    boundInput = input;
    const feedback = document.createElement('p');
    feedback.className = 'runtime-draft-error1250';
    feedback.id = 'runtime-draft-error1250';
    feedback.setAttribute('aria-live', 'polite');
    input.setAttribute('aria-describedby', feedback.id);
    input.insertAdjacentElement('afterend', feedback);
    let revision = 0, timer;
    async function check() {
      const current = ++revision;
      const value = input.value.trim();
      input.setCustomValidity('');
      feedback.textContent = '';
      if (!value) return;
      try {
        const result = await validateDraftPath(value);
        if (current !== revision || input.value.trim() !== value) return;
        const error = result.valid === false ? result.error || '剪映草稿目录无效' : '';
        input.setCustomValidity(error);
        feedback.textContent = error;
      } catch (_) {
        if (current === revision) feedback.textContent = '暂时无法检查目录，保存时会再次核对。';
      }
    }
    input.addEventListener('change', check);
    input.addEventListener('input', function () {
      ++revision;
      input.setCustomValidity('');
      feedback.textContent = '';
      clearTimeout(timer);
      timer = setTimeout(check, 250);
    });
  }
  async function mount() {
    bindDraftInput();
    await refresh();
  }
  window.RuntimeHealth1250 = {mount, refresh, validateDraftPath};
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
  else mount();
})();
