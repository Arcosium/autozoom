"""화면 템플릿. 컨셉: '속기록 원장(ledger)' — 종이·잉크·괘선, 단일 주묵 액센트.

의도적으로 카드/필배지/글로우를 쓰지 않는다(사장 지시: AI 티 나는 디자인 금지).
상태는 색 배지가 아니라 괘선 + 활자 + 작은 사각 마커로 표현한다.
"""
from __future__ import annotations

import html
import re

CSS = """
:root{
  --paper:#f7f6f2; --ink:#16150f; --ink-2:#4b483d; --ink-3:#8a8676;
  --rule:#d9d5c7; --rule-2:#ebe8dd; --accent:#a8332a; --accent-soft:#f0e2e0;
  --ok:#3f6b45; --wait:#8a8676;
  --space:8px;
}
@media (prefers-color-scheme: dark){
  :root{ --paper:#14140f; --ink:#eceada; --ink-2:#b3b0a0; --ink-3:#7b7869;
         --rule:#33322a; --rule-2:#242319; --accent:#e0685c; --accent-soft:#2b1e1c; }
}
:root[data-theme=dark]{ --paper:#14140f; --ink:#eceada; --ink-2:#b3b0a0; --ink-3:#7b7869;
  --rule:#33322a; --rule-2:#242319; --accent:#e0685c; --accent-soft:#2b1e1c; }
:root[data-theme=light]{ --paper:#f7f6f2; --ink:#16150f; --ink-2:#4b483d; --ink-3:#8a8676;
  --rule:#d9d5c7; --rule-2:#ebe8dd; --accent:#a8332a; --accent-soft:#f0e2e0; }

*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font-family:"Noto Serif KR",'Apple SD Gothic Neo',serif;
  font-size:16px;line-height:1.6;-webkit-text-size-adjust:100%}
.mono{font-family:"Fira Code",ui-monospace,SFMono-Regular,Menlo,monospace;
  font-variant-numeric:tabular-nums}
.wrap{max-width:1100px;margin:0 auto;padding:0 24px 96px}

header.masthead{border-bottom:2px solid var(--ink);margin-bottom:0;padding:40px 0 12px}
.masthead h1{font-size:30px;letter-spacing:-.01em;margin:0 0 4px;font-weight:700}
.masthead p{margin:0;color:var(--ink-2);font-size:14px}
.masthead .meta{float:right;text-align:right;color:var(--ink-3);font-size:12px;
  letter-spacing:.14em;text-transform:uppercase}

h2.rule{font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:var(--ink-3);
  font-weight:600;margin:40px 0 0;padding-bottom:6px;border-bottom:1px solid var(--rule);
  display:flex;align-items:baseline;justify-content:space-between;gap:16px}
.rule-act{display:flex;align-items:center;gap:12px;text-transform:none;letter-spacing:0}
.filed{font-size:12px;color:var(--ok);letter-spacing:0;text-transform:none}
button:disabled{opacity:.5;cursor:wait}

form.compose{display:grid;grid-template-columns:1fr 170px 190px auto;gap:16px;align-items:end;
  padding:24px 0;border-bottom:1px solid var(--rule)}
label{display:block;font-size:12px;letter-spacing:.12em;text-transform:uppercase;
  color:var(--ink-3);margin-bottom:6px;font-weight:600}
input[type=url],input[type=text],input[type=datetime-local]{
  width:100%;padding:10px 2px;border:0;border-bottom:1px solid var(--ink-2);
  background:transparent;color:var(--ink);font-size:15px;font-family:inherit;
  min-height:44px;border-radius:0}
input:focus{outline:0;border-bottom-color:var(--accent);
  box-shadow:0 1px 0 0 var(--accent)}
input:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.hint{font-size:12px;color:var(--ink-3);margin-top:6px}

button{font-family:inherit;font-size:14px;cursor:pointer;border-radius:0;
  min-height:44px;padding:11px 20px;transition:background .18s ease,color .18s ease}
button.primary{background:var(--ink);color:var(--paper);border:1px solid var(--ink);font-weight:600}
button.primary:hover{background:var(--accent);border-color:var(--accent)}
button.ghost{background:transparent;color:var(--accent);border:1px solid var(--accent);
  padding:7px 14px;min-height:36px;font-size:13px}
button.ghost:hover{background:var(--accent);color:var(--paper)}
button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

table{width:100%;border-collapse:collapse;margin-top:8px}
th{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);
  text-align:left;font-weight:600;padding:10px 12px 10px 0;white-space:nowrap;
  border-bottom:1px solid var(--rule)}
td{padding:14px 12px 14px 0;border-bottom:1px solid var(--rule-2);vertical-align:top;font-size:15px}
tr:hover td{background:var(--rule-2)}
td.num{width:1%;white-space:nowrap;color:var(--ink-3);font-size:13px}
a{color:inherit;text-decoration:none;border-bottom:1px solid var(--rule)}
a:hover{border-bottom-color:var(--accent);color:var(--accent)}

.mark{display:inline-block;width:7px;height:7px;margin-right:8px;vertical-align:baseline;
  background:var(--ink-3)}
.mark.live{background:var(--accent);animation:pulse 1.8s ease-in-out infinite}
.mark.done{background:var(--ok)}
.mark.fail{background:var(--accent);opacity:.45}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
@media (prefers-reduced-motion:reduce){.mark.live{animation:none}*{transition:none!important}}
.state{font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-2);
  white-space:nowrap;font-weight:600}
.url{color:var(--ink-3);font-size:12px;word-break:break-all;display:block;margin-top:3px}

.empty{padding:56px 0;text-align:center;color:var(--ink-3)}
.empty::before{content:"—";display:block;font-size:24px;margin-bottom:8px;color:var(--rule)}

.summary{margin-top:16px;font-size:17px;line-height:1.75;max-width:70ch}
.summary h2{font-size:13px;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);
  margin:32px 0 8px;font-weight:700}
.summary ul{padding-left:20px;margin:8px 0}
.summary li{margin:5px 0}
.mytodo{margin-top:20px;padding:18px 22px;background:var(--accent-soft);
  border-left:3px solid var(--accent)}
.mytodo-h{display:block;font-size:12px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--accent);font-weight:700;margin-bottom:8px}
.mytodo ul{margin:0;padding-left:20px}
.mytodo li{margin:6px 0;font-size:16px;line-height:1.65}
.mytodo.none{background:transparent;border-left-color:var(--rule)}
.mytodo.none .mytodo-h{color:var(--ink-3)}
.mytodo.none p{margin:0;color:var(--ink-3);font-size:14px}

.qa{margin-top:16px;max-width:70ch}
.qa-form{display:flex;gap:12px;align-items:stretch}
.qa-form input{flex:1;padding:10px 2px;border:0;border-bottom:1px solid var(--ink-2);
  background:transparent;color:var(--ink);font-family:inherit;font-size:15px;min-height:44px}
.qa-form input:disabled{opacity:.45;border-bottom-style:dashed}
.qa-item{margin-top:22px;padding-bottom:18px;border-bottom:1px solid var(--rule-2)}
.qa-q{margin:0 0 8px;font-weight:600;font-size:15px}
.qa-q::before{content:"묻다 ";font-size:11px;letter-spacing:.14em;color:var(--accent);
  font-weight:700;vertical-align:2px}
.qa-a{color:var(--ink-2);font-size:15px;line-height:1.75}
.qa-a p{margin:6px 0}
.qa-a ul{margin:6px 0;padding-left:20px}
.qa-a li{margin:3px 0}
.qa-a.pending{color:var(--ink-3);font-style:italic}

.transcript{white-space:pre-wrap;font-size:14px;line-height:1.9;color:var(--ink-2);
  border-left:2px solid var(--rule);padding-left:20px;margin-top:12px}
details>summary{cursor:pointer;font-size:12px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--ink-3);padding:12px 0;font-weight:600}
.log{font-size:13px;line-height:1.8;color:var(--ink-3);white-space:pre-wrap;
  max-height:340px;overflow:auto}
.back{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);
  border:0;display:inline-block;margin:28px 0 0}

@media (max-width:760px){
  .wrap{padding:0 18px 72px}
  form.compose{grid-template-columns:1fr;gap:20px}
  .masthead .meta{float:none;text-align:left;margin-top:8px}
  .masthead h1{font-size:24px}
  th:nth-child(4),td:nth-child(4){display:none}
}
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=Fira+Code:wght@400;500&family=Noto+Serif+KR:wght@400;600;700&display=swap">')

STATE_KO = {
    "scheduled": ("대기 예약", "wait"), "queued": ("입장 준비", "live"),
    "joining": ("입장 중", "live"), "recording": ("녹음 중", "live"),
    "transcribing": ("전사 중", "live"), "summarizing": ("요약 중", "live"),
    "done": ("완료", "done"), "failed": ("실패", "fail"), "stopped": ("중단", "fail"),
}
ACTIVE = {"scheduled", "queued", "joining", "recording", "transcribing", "summarizing"}


def _e(s) -> str:
    return html.escape(str(s or ""))


BOLD = re.compile(r"\*\*(.+?)\*\*")


def _bold(s: str) -> str:
    return BOLD.sub(r"<strong>\1</strong>", s)


ORDERED = re.compile(r"^\d+[.)]\s+(.*)$")


def md_to_html(md: str) -> str:
    """요약·답변용 초소형 마크다운 변환(제목·목록·번호목록·강조·체크박스만)."""
    out, in_ul = [], False
    for line in (md or "").splitlines():
        s = line.strip()
        if s.startswith("## "):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<h2>{_e(s[3:])}</h2>")
            continue
        om = ORDERED.match(s)
        if s.startswith(("- ", "* ")) or om:
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            item = _e((om.group(1) if om else s[2:]).strip())
            item = item.replace("[ ]", "☐").replace("[x]", "☑")
            out.append(f"<li>{_bold(item)}</li>")
            continue
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if s:
            out.append(f"<p>{_bold(_e(s))}</p>")
    if in_ul:
        out.append("</ul>")
    return "\n".join(out)


MY_TODO = re.compile(r"^##\s*내 할 일\s*$", re.M)


def split_my_todo(summary: str) -> tuple[list[str], str]:
    """요약에서 '## 내 할 일' 블록만 떼어낸다 → (내 할 일 항목들, 나머지 요약)."""
    lines = (summary or "").splitlines()
    todo: list[str] = []
    rest: list[str] = []
    inside = False
    for line in lines:
        if MY_TODO.match(line.strip()):
            inside = True
            continue
        if inside and line.strip().startswith("## "):
            inside = False
        if inside:
            s = line.strip()
            if s.startswith(("- ", "* ")):
                item = re.sub(r"^\[[ x]\]\s*", "", s[2:].strip())
                if item and item != "없음":
                    todo.append(item)
        else:
            rest.append(line)
    return todo, "\n".join(rest)


def my_todo_block(items: list[str]) -> str:
    if not items:
        return ('<div class="mytodo none"><span class="mytodo-h">내가 할 일</span>'
                '<p>이 회의에서 나에게 배정된 일은 없다.</p></div>')
    lis = "".join(f"<li>{_bold(_e(x))}</li>" for x in items)
    return (f'<div class="mytodo"><span class="mytodo-h">내가 할 일 · {len(items)}건</span>'
            f'<ul>{lis}</ul></div>')


def qa_block(job: dict) -> str:
    import json as _json

    history = []
    try:
        history = _json.loads(job.get("qa") or "[]")
    except Exception:
        history = []
    past = "".join(
        f'<div class="qa-item"><p class="qa-q">{_e(h.get("q"))}</p>'
        f'<div class="qa-a">{md_to_html(h.get("a") or "")}</div></div>'
        for h in history)
    disabled = "" if (job.get("transcript") or "").strip() else " disabled"
    hint = ("" if not disabled else
            '<div class="hint">전사가 끝나야 질문할 수 있다.</div>')
    return f"""<h2 class="rule">이 회의에 묻기</h2>
<div class="qa">
  <div class="qa-form">
    <input id="q" type="text" placeholder="예: 내가 언제까지 뭘 하기로 했지?"{disabled}
           onkeydown="if(event.key==='Enter')askAI('{job['id']}')">
    <button class="ghost" onclick="askAI('{job['id']}')"{disabled}>묻기</button>
  </div>
  {hint}
  <div id="qa-list">{past}</div>
</div>"""


def page(title: str, body: str) -> str:
    return f"""<!doctype html><html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)}</title>{FONTS}<style>{CSS}</style></head>
<body><div class="wrap">{body}</div></body></html>"""


def masthead(sub: str) -> str:
    return f"""<header class="masthead">
  <div class="meta mono">AUTO&nbsp;ZOOM</div>
  <h1>회의 속기록</h1><p>{_e(sub)}</p></header>"""


def row(j: dict) -> str:
    label, mark = STATE_KO.get(j["status"], (j["status"], ""))
    when = j.get("scheduled_at") or j.get("created_at") or ""
    dur = j.get("duration_s") or 0
    dur_s = f"{int(dur) // 60}분" if dur else "—"
    title = j.get("title") or "제목 없음"
    stop = (f'<button class="ghost" onclick="stop(\'{j["id"]}\')">'
            f'{"예약 취소" if j["status"] == "scheduled" else "퇴장"}</button>'
            if j["status"] in ACTIVE else "")
    return f"""<tr>
  <td><span class="mark {mark}"></span><span class="state">{_e(label)}</span></td>
  <td><a href="/jobs/{j['id']}">{_e(title)}</a><span class="url mono">{_e(j['url'][:78])}</span></td>
  <td class="num mono">{_e(when).replace('T', ' ')[:16]}</td>
  <td class="num mono">{dur_s}</td>
  <td class="num">{stop}</td></tr>"""


def index(jobs: list[dict]) -> str:
    rows = "".join(row(j) for j in jobs)
    table = f"""<table><thead><tr>
      <th>상태</th><th>회의</th><th>예약·생성</th><th>길이</th><th></th>
    </tr></thead><tbody>{rows}</tbody></table>""" if jobs else \
        '<div class="empty">아직 기록이 없다. 위에 회의 링크를 넣어 시작한다.</div>'

    body = masthead("줌 링크를 넣으면 봇이 카메라·마이크를 끈 채 참석해 녹음하고, "
                    "회의가 끝나면 전문과 요약을 남긴다.") + f"""
<form class="compose" method="post" action="/jobs">
  <div>
    <label for="url">회의 링크</label>
    <input id="url" name="url" type="url" required
           placeholder="https://us05web.zoom.us/j/000000000?pwd=…">
    <div class="hint">Zoom 회의(/j/)·웨비나(/w/) 링크 모두 가능</div>
  </div>
  <div>
    <label for="bot">입장 이름</label>
    <input id="bot" name="bot_name" type="text" placeholder="회의록봇" maxlength="30">
    <div class="hint">참가자에게 보이는 이름</div>
  </div>
  <div>
    <label for="at">입장 시각</label>
    <input id="at" name="scheduled_at" type="datetime-local">
    <div class="hint">비우면 즉시 입장</div>
  </div>
  <button class="primary" type="submit">봇 보내기</button>
</form>
<h2 class="rule">기록</h2>
{table}
<script>
async function stop(id){{
  if(!confirm('봇을 회의에서 내보낼까요? 그때까지 녹음분으로 요약이 만들어집니다.')) return;
  await fetch('/api/jobs/'+id+'/stop',{{method:'POST'}});
  location.reload();
}}
const busy = {str(any(j['status'] in ACTIVE for j in jobs)).lower()};
if (busy) setTimeout(()=>location.reload(), 10000);
</script>"""
    return page("회의 속기록 · auto_zoom", body)


def detail(j: dict) -> str:
    label, mark = STATE_KO.get(j["status"], (j["status"], ""))
    parts = [masthead(j.get("title") or "제목 없음")]
    parts.append(f"""<p style="margin-top:20px">
      <span class="mark {mark}"></span><span class="state">{_e(label)}</span>
      <span class="url mono">{_e(j['url'])}</span></p>""")
    if j.get("reason"):
        parts.append(f'<p class="hint">종료 사유 · {_e(j["reason"])}</p>')
    if j["status"] in ACTIVE:
        parts.append(f"""<p><button class="ghost" onclick="stop('{j['id']}')">
          {"예약 취소" if j["status"] == "scheduled" else "회의에서 퇴장"}</button></p>""")

    if j.get("summary"):
        if j.get("coresight_slug"):
            action = (f'<span class="filed">Coresight 등재됨 · '
                      f'<span class="mono">{_e(j["coresight_slug"])}</span></span>'
                      f'<button class="ghost" onclick="toCoresight(\'{j["id"]}\')">다시 올리기</button>')
        else:
            action = (f'<button class="ghost" onclick="toCoresight(\'{j["id"]}\')">'
                      f'Coresight에 올리기</button>')
        todo, rest = split_my_todo(j["summary"])
        parts.append(f'<h2 class="rule">요약<span class="rule-act">{action}</span></h2>')
        parts.append(my_todo_block(todo))
        parts.append(f'<div class="summary">{md_to_html(rest)}</div>')
    parts.append(qa_block(j))
    if j.get("transcript"):
        parts.append('<h2 class="rule">원문</h2>'
                     f'<div class="transcript mono">{_e(j["transcript"])}</div>')
    parts.append('<details><summary>진행 로그</summary>'
                 f'<div class="log mono">{_e(j.get("log"))}</div></details>')
    parts.append('<a class="back" href="/">← 목록으로</a>')
    parts.append(f"""<script>
async function stop(id){{
  if(!confirm('봇을 회의에서 내보낼까요?')) return;
  await fetch('/api/jobs/'+id+'/stop',{{method:'POST'}}); location.reload();
}}
async function askAI(id){{
  const box = document.getElementById('q');
  const q = (box.value||'').trim();
  if(!q) return;
  const list = document.getElementById('qa-list');
  const el = document.createElement('div');
  el.className = 'qa-item';
  el.innerHTML = '<p class="qa-q"></p><div class="qa-a pending">읽는 중…</div>';
  el.querySelector('.qa-q').textContent = q;
  list.appendChild(el);
  box.value = ''; box.disabled = true;
  try {{
    const r = await fetch('/api/jobs/'+id+'/ask', {{
      method:'POST', headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{question: q}})
    }});
    const d = await r.json();
    const a = el.querySelector('.qa-a');
    a.classList.remove('pending');
    if (d.ok) {{ a.innerHTML = d.answer_html; }}
    else {{ a.textContent = '실패: ' + (d.error||''); }}
  }} catch (e) {{
    const a = el.querySelector('.qa-a');
    a.classList.remove('pending'); a.textContent = '요청 실패: ' + e;
  }}
  box.disabled = false; box.focus();
}}
async function toCoresight(id){{
  const btn = event.currentTarget;
  btn.disabled = true; btn.textContent = '올리는 중…';
  try {{
    const r = await fetch('/api/jobs/'+id+'/coresight',{{method:'POST'}});
    const d = await r.json();
    if (d.ok) {{ location.reload(); }}
    else {{ btn.disabled = false; btn.textContent = '실패 · 다시 시도';
            alert('Coresight 업로드 실패\\n' + (d.error||'')); }}
  }} catch (e) {{
    btn.disabled = false; btn.textContent = '실패 · 다시 시도'; alert('요청 실패: ' + e);
  }}
}}
if ({str(j["status"] in ACTIVE).lower()}) setTimeout(()=>location.reload(), 10000);
</script>""")
    return page(f"{j.get('title') or '회의'} · auto_zoom", "".join(parts))
