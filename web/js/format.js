/* 표기·이스케이프·아이콘 — 화면 어디서나 같은 규칙으로 쓴다. */

export function esc(s){
  return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
  });
}
export function km(m){ return m >= 1000 ? (m/1000).toFixed(1)+'km' : Math.round(m)+'m'; }
export function mins(n){ n = Math.round(n); return n>=60 ? Math.floor(n/60)+'시간'+(n%60 ? ' '+(n%60)+'분' : '') : n+'분'; }
export function won(v){ return (v||0).toLocaleString('ko-KR')+'원'; }
// "1시간 22분" → 숫자만 크게
export function minsHtml(n){ return esc(mins(n)).replace(/(\d+)(시간|분)/g, '$1<small>$2</small>'); }

export var CONG = [
  {name:'정보없음', color:'#8b95a1', dark:'#5f676f'},
  {name:'원활',    color:'#04c75b', dark:'#02893f'},
  {name:'서행',    color:'#ffa000', dark:'#b06e00'},
  {name:'혼잡',    color:'#ee3f3f', dark:'#a52626'}
];

// 출발·경유·도착 색은 지도 핀·입력칸·단계 목록이 모두 같은 값을 쓴다
export var END = {
  origin:   {label:'출발', color:'#2e6ff2'},
  waypoint: {label:'경유', color:'#f5a623'},
  goal:     {label:'도착', color:'#e8452c'}
};

// 위험 지점 유형 (hazards.py 의 type 과 1:1). 순서 = 화면에서 위로 올릴 순서(사고 이력 먼저)
// tone: acc 사고 이력(빨간 삼각형) · ice 결빙(파란 삼각형) · cam 단속카메라 · zone 보호구역(제한속도 표지)
export var HZ = {
  frequentzoneFreezing:{label:'결빙 사고 다발',     tone:'ice'},
  frequentzoneLg:      {label:'교통사고 다발',      tone:'acc'},
  pedstrians:          {label:'보행자 사고 다발',   tone:'acc'},
  frequentzoneChild:   {label:'어린이 사고 다발',   tone:'acc'},
  frequentzoneOldman:  {label:'노인 사고 다발',     tone:'acc'},
  frequentzoneBicycle: {label:'자전거 사고 다발',   tone:'acc'},
  accident_schoolzone: {label:'스쿨존 사고 다발',   tone:'acc'},
  speed_camera:        {label:'과속 단속카메라',     tone:'cam'},
  school_zone:         {label:'어린이보호구역',     tone:'zone'},
  senior_zone:         {label:'노인보호구역',       tone:'zone'}
};
export var HZ_ORDER = Object.keys(HZ);
export function hzInfo(type){ return HZ[type] || {label:type, tone:'acc'}; }

function speedOf(text){ var m = /제한속도\s*(\d+)/.exec(text || ''); return m ? m[1] : ''; }

// 지도·범례에 쓰는 아이콘. 운전자가 도로에서 보는 표지 모양을 따른다.
export function hzIcon(type, text){
  var tone = hzInfo(type).tone;
  if (tone === 'zone'){                        // 제한속도 표지: 빨간 테두리 원 + 숫자
    return '<span class="hzi zone">' + (speedOf(text) || '30') + '</span>';
  }
  if (tone === 'cam'){                         // 카메라
    return '<span class="hzi cam"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M4 7h3l1.5-2h7L17 7h3a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1zm8 2.5A3.8 3.8 0 1 0 12 17a3.8 3.8 0 0 0 0-7.5z"/></svg></span>';
  }
  // 사고 이력: 주의 표지(삼각형). 결빙은 파란색 + 눈 결정
  return '<span class="hzi tri ' + tone + '"><svg viewBox="0 0 24 22" aria-hidden="true"><path d="M12 1.5 23 20.5H1z" fill="currentColor" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/>'
    + (tone === 'ice' ? '<text x="12" y="17.5" text-anchor="middle" font-size="10" fill="#fff">❄</text>'
                      : '<rect x="10.9" y="7.5" width="2.2" height="6.5" rx="1" fill="#fff"/><circle cx="12" cy="16.6" r="1.3" fill="#fff"/>')
    + '</svg></span>';
}

export function glyph(type, text){
  if (type === 88) return '◉';
  if (type === 87) return '◈';
  if (type >= 121 && type <= 123) return '⤴';
  if (type === 1) return '↑';
  if (type === 2) return '↰';
  if (type === 3) return '↱';
  if (/유턴/.test(text)) return '↶';
  if (/좌회전|왼쪽/.test(text)) return '↰';
  if (/우회전|오른쪽/.test(text)) return '↱';
  if (/출구|진출/.test(text)) return '↗';
  if (/진입/.test(text)) return '↖';
  if (/목적지|도착/.test(text)) return '◉';
  return '↑';
}

// 서버·API 오류를 사용자 언어로. 원문은 콘솔로 보낸다.
export function friendlyError(d){
  console.warn('[route-guide] 오류 원문', d);
  var msg = (d && (d.error || d.message)) || '';
  if (/same|동일|출발지와 도착지/.test(msg)) return '출발지와 도착지가 같아요.';
  if (d && d.status === 401) return '지도 서버 인증에 실패했어요. .env 키를 확인해 주세요.';
  if (d && d.status >= 500) return '지도 서버가 잠시 응답하지 않아요. 잠시 후 다시 시도해 주세요.';
  if (/Failed to fetch|NetworkError/.test(msg)) return '로컬 서버에 연결할 수 없어요. serve.py 가 실행 중인지 확인해 주세요.';
  return '경로를 찾지 못했어요. 출발지·도착지를 확인해 주세요.';
}
