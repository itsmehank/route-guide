/* 장소 자동완성 — ARIA combobox 패턴.
   포커스는 입력칸에 두고 ↑↓ 로 후보를 옮기며 Enter 로 고른다. Esc 는 닫기.
   결과가 없거나 오류가 나면 목록 자리에 그 사실을 보여준다(예전엔 조용히 닫혔다). */
import {esc} from './format.js';
import {searchPlaces} from './api.js';
import {distM} from './geo.js';

var FAR_KM = 80;   // 기준점에서 이보다 먼 후보는 뒤로 보낸다 (수도권에서 '판교역 장항선' 같은 것)

function distText(m){ return m >= 10000 ? Math.round(m/1000) + 'km' : (m/1000).toFixed(1) + 'km'; }

/* opts: {input, list, field, onPick(place), onClear(), reference() → [lon,lat]|null, status(msg)} */
export function bindSearch(opts){
  var input = opts.input, list = opts.list;
  var timer = null, ctrl = null, last = '', items = [], active = -1;

  input.setAttribute('role', 'combobox');
  input.setAttribute('aria-autocomplete', 'list');
  input.setAttribute('aria-expanded', 'false');
  input.setAttribute('aria-controls', list.id);
  list.setAttribute('role', 'listbox');

  function close(){
    list.hidden = true; list.innerHTML = ''; items = []; active = -1;
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
  }

  function place(){
    // 입력칸 바로 아래에 붙인다 (inputs 박스 기준)
    list.style.top = (opts.field.offsetTop + opts.field.offsetHeight + 4) + 'px';
  }

  function message(text, tone){
    list.innerHTML = '<li class="sg-msg' + (tone ? ' ' + tone : '') + '" role="presentation">' + text + '</li>';
    list.hidden = false; items = []; active = -1;
    input.setAttribute('aria-expanded', 'false');
    place();
  }

  function render(places, query){
    var ref = opts.reference();
    var rows = places.map(function(p, i){
      return {p: p, i: i, d: ref ? distM(ref, p.coord) : null};
    });
    if (ref) rows.sort(function(a, b){
      var fa = a.d > FAR_KM*1000, fb = b.d > FAR_KM*1000;
      return fa === fb ? a.i - b.i : (fa ? 1 : -1);      // 관련도 순서는 지키고, 먼 곳만 뒤로
    });
    items = rows.map(function(r){ return r.p; });
    active = -1;
    list.innerHTML = '<li class="sg-head" role="presentation">\'' + esc(query) + '\' 검색 결과 ' + items.length + '건</li>'
      + rows.map(function(r, k){
          var p = r.p;
          var cat = p.kind === 'address' ? '주소' : (p.category || '').split('>').pop();
          return '<li role="option" id="' + list.id + '-' + k + '" data-k="' + k + '" aria-selected="false">'
            + '<span class="nm">' + esc(p.title) + '</span>'
            + '<span class="ct">' + esc(cat) + (r.d !== null ? ' · ' + distText(r.d) : '') + '</span>'
            + '<span class="ad">' + esc(p.road_address || p.jibun_address || '') + '</span></li>';
        }).join('');
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
    place();
    opts.status(items.length + '개 후보가 있어요. 위아래 화살표로 고를 수 있어요.');
  }

  function setActive(k){
    var opt = list.querySelectorAll('[role=option]');
    if (!opt.length) return;
    active = (k + opt.length) % opt.length;
    opt.forEach(function(o, j){ o.setAttribute('aria-selected', j === active ? 'true' : 'false'); });
    input.setAttribute('aria-activedescendant', opt[active].id);
    opt[active].scrollIntoView({block: 'nearest'});
  }

  function pick(k){
    var p = items[k]; if (!p) return;
    input.value = p.title; last = p.title;
    close();
    opts.onPick(p);
  }

  function run(q){
    if (ctrl) ctrl.abort();
    ctrl = new AbortController();
    searchPlaces(q, ctrl.signal).then(function(places){
      if (input.value.trim() !== q) return;            // 그 사이 더 입력했으면 버린다
      if (document.activeElement !== input) return;
      if (!places.length) return message('\'' + esc(q) + '\' 검색 결과가 없어요.<br><small>철자를 확인하거나 도로명 주소로 검색해 보세요.</small>');
      render(places, q);
    }).catch(function(e){
      if (e.name === 'AbortError') return;
      console.warn('[route-guide] 검색 실패', e);
      message('검색 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요.', 'err');
    });
  }

  list.addEventListener('mousedown', function(e){ e.preventDefault(); });   // blur 보다 먼저 잡는다
  list.addEventListener('click', function(e){
    var li = e.target.closest('[role=option]');
    if (li) pick(+li.dataset.k);
  });

  // 한 글자부터 바로 반응한다. 호출 억제는 짧은 디바운스 + 이전 요청 취소 + 서버 캐시가 담당한다.
  input.addEventListener('input', function(){
    var q = input.value.trim();
    opts.onClear();
    clearTimeout(timer);
    if (!q){ close(); last = ''; return; }
    if (q === last) return;
    last = q;
    timer = setTimeout(function(){ run(q); }, 110);
  });
  input.addEventListener('keydown', function(e){
    if (e.key === 'ArrowDown'){ e.preventDefault(); if (items.length) setActive(active + 1); return; }
    if (e.key === 'ArrowUp'){ e.preventDefault(); if (items.length) setActive(active - 1); return; }
    if (e.key === 'Escape'){ close(); return; }
    if (e.key !== 'Enter') return;
    e.preventDefault();
    clearTimeout(timer);
    if (items.length) return pick(active >= 0 ? active : 0);
    var q = input.value.trim();
    if (q) { last = q; run(q); }
  });
  input.addEventListener('focus', function(){
    var q = input.value.trim();
    if (q && !opts.hasValue()) run(q);
  });
  input.addEventListener('blur', function(){ setTimeout(close, 120); });

  return {close: close};
}
