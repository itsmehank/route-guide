import {vias} from './store.js';

/* 서버 호출. 모든 요청은 취소할 수 있어야 한다 — 입력이 바뀌면 이전 응답은 버린다. */

function getJson(url, signal){
  return fetch(url, {signal: signal}).then(function(r){
    return r.json().then(function(d){
      if (!r.ok || d.error) { var e = new Error(d.error || ('HTTP ' + r.status)); e.data = d; throw e; }
      return d;
    });
  });
}

export function searchPlaces(q, signal){
  return getJson('/api/search?q=' + encodeURIComponent(q), signal).then(function(d){ return d.places || []; });
}

function tripQuery(s){
  var q = 'start=' + s.origin.coord.join(',') + '&goal=' + s.goal.coord.join(',');
  var v = vias(s);
  if (v.length) q += '&waypoints=' + v.map(function(p){ return p.coord.join(','); }).join('|');
  return q;
}

export function fetchRoute(s, signal){
  return getJson('/api/route?' + tripQuery(s), signal);
}

function cmpQuery(s){
  var q = tripQuery(s) + '&o=' + encodeURIComponent(s.origin.title) + '&g=' + encodeURIComponent(s.goal.title);
  var v = vias(s);
  if (v.length) q += '&v=' + encodeURIComponent(v.map(function(p){ return p.title; }).join(', '));
  return q;
}

export function fetchEvaluation(s, signal){
  return getJson('/api/evaluate?' + cmpQuery(s), signal);
}

/* 서술 스트림 (SSE). handlers: {stage, partial, retry, done, fail}. 반환값의 close() 로 끊으면
   서버가 CLI 생성도 멈춘다. */
export function streamNarration(s, handlers){
  var es = new EventSource('/api/narrate?' + cmpQuery(s));
  var finished = false;
  ['stage', 'partial', 'retry', 'done', 'fail'].forEach(function(ev){
    es.addEventListener(ev, function(e){
      var data = {};
      try { data = JSON.parse(e.data); } catch (_) {}
      if (ev === 'done' || ev === 'fail'){ finished = true; es.close(); }
      if (handlers[ev]) handlers[ev](data);
    });
  });
  // 서버가 응답을 마치고 연결을 닫으면 EventSource 는 재연결을 시도한다 — 끝났으면 막는다
  es.onerror = function(){
    if (finished) return;
    es.close();
    if (handlers.fail) handlers.fail({error: '서버와의 연결이 끊겼어요.'});
  };
  return {close: function(){ finished = true; es.close(); }};
}
