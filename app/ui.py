"""화면 템플릿. 컨셉: '속기록 원장(ledger)' — 종이·잉크·괘선, 단일 주묵 액센트.

의도적으로 카드/필배지/글로우를 쓰지 않는다(사장 지시: AI 티 나는 디자인 금지).
상태는 색 배지가 아니라 괘선 + 활자 + 작은 사각 마커로 표현한다.
"""
from __future__ import annotations

import html
import json
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

nav.tabs{display:flex;border-bottom:1px solid var(--rule)}
nav.tabs button{background:transparent;border:0;border-radius:0;min-height:48px;
  padding:14px 2px;margin:0 28px -1px 0;font-size:13px;letter-spacing:.14em;
  font-weight:600;color:var(--ink-3);border-bottom:2px solid transparent}
nav.tabs button:hover{color:var(--accent)}
nav.tabs button.on{color:var(--ink);border-bottom-color:var(--accent)}

h2.rule{font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:var(--ink-3);
  font-weight:600;margin:40px 0 0;padding-bottom:6px;border-bottom:1px solid var(--rule);
  display:flex;align-items:baseline;justify-content:space-between;gap:16px}
.rule-act{display:flex;align-items:center;gap:12px;text-transform:none;letter-spacing:0}
.filed{font-size:12px;color:var(--ok);letter-spacing:0;text-transform:none}
button:disabled{opacity:.5;cursor:wait}

form.compose{display:grid;grid-template-columns:1fr 170px 190px auto;gap:18px 20px;align-items:end;
  padding:24px 0;border-bottom:1px solid var(--rule)}
form.compose .wide{grid-column:1 / -1}   /* 회의 링크는 한 줄 전체를 쓴다 */
label{display:block;font-size:12px;letter-spacing:.12em;text-transform:uppercase;
  color:var(--ink-3);margin-bottom:6px;font-weight:600}
input[type=url],input[type=text],input[type=password],input[type=datetime-local]{
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
.when-sm{display:none}   /* 좁은 화면에서만 제목 아래로 내려오는 날짜 (아래 미디어쿼리) */

.rec{display:flex;gap:18px;align-items:center;flex-wrap:wrap;padding:22px 0;
  border-bottom:1px solid var(--rule)}
.rec input{flex:1;min-width:200px;padding:10px 2px;border:0;
  border-bottom:1px solid var(--ink-2);background:transparent;color:var(--ink);
  font-family:inherit;font-size:15px;min-height:44px}
#rectime{font-size:22px;color:var(--ink-3);min-width:76px}
#rectime.on{color:var(--accent)}
button.recording{background:var(--accent);border-color:var(--accent)}

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

.acct{float:right;clear:right;text-align:right;color:var(--ink-3);font-size:12px;
  letter-spacing:.08em;margin-top:6px}
.acct form{display:inline}
button.link{background:transparent;border:0;color:var(--ink-3);font-size:12px;
  letter-spacing:.08em;padding:0;min-height:0;border-bottom:1px solid var(--rule)}
button.link:hover{color:var(--accent);border-bottom-color:var(--accent)}
button.danger{color:var(--accent);border-color:var(--rule)}

form.sheet{max-width:400px;margin:0 auto;display:grid;gap:22px}
form.sheet button.primary{justify-self:start;padding:11px 32px}
.msg{padding:12px 0;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);
  font-size:14px}
.msg.fail{color:var(--accent)}
.msg.ok{color:var(--ok)}

form.retitle{display:flex;gap:12px;align-items:flex-end;margin-top:18px;max-width:560px}
form.retitle input{flex:1}

@media (max-width:760px){
  .wrap{padding:0 18px 72px}
  .acct{float:none;text-align:left}
  form.compose{grid-template-columns:1fr;gap:20px}
  .masthead .meta{float:none;text-align:left;margin-top:8px}
  .masthead h1{font-size:24px}
  /* 폰 폭에선 nowrap 인 날짜·길이 열이 제목을 3줄로 짓눌렀다 → 두 열을 접고 날짜는 제목 밑으로 */
  th:nth-child(3),td:nth-child(3),th:nth-child(4),td:nth-child(4){display:none}
  .when-sm{display:block;color:var(--ink-3);font-size:12px;margin-top:4px}
  /* zoom URL 은 break-all 로 6줄까지 늘어나 한 기록이 화면을 다 먹는다 → 한 줄로 자른다 */
  .url{display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden}
}
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=Fira+Code:wght@400;500&family=Noto+Serif+KR:wght@400;600;700&display=swap">')

STATE_KO = {
    "scheduled": ("대기 예약", "wait"), "queued": ("입장 준비", "live"),
    "joining": ("입장 중", "live"), "recording": ("녹음 중", "live"),
    "downloading": ("받는 중", "live"),
    "transcribing": ("전사 중", "live"), "summarizing": ("요약 중", "live"),
    "done": ("완료", "done"), "failed": ("실패", "fail"), "stopped": ("중단", "fail"),
}
ACTIVE = {"scheduled", "queued", "joining", "recording", "downloading",
          "transcribing", "summarizing"}


def _is_zoom(j: dict) -> bool:
    """퇴장·예약취소 버튼은 줌 봇 잡에만 뜻이 있다 — 링크 전사·직접 녹음엔 나갈 회의가 없다."""
    return "zoom.us" in (j.get("url") or "")


def _e(s) -> str:
    return html.escape(str(s or ""))


def _json_str(s) -> str:
    """onclick="…" 속성 안에 넣을 JS 문자열 리터럴(따옴표까지 이스케이프)."""
    return html.escape(json.dumps(str(s or "")))


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


def masthead(sub: str, user: str = "", admin: bool = False) -> str:
    acct = ""
    if user:
        adm = ' <a href="/admin">승인 관리</a> ·' if admin else ""
        acct = (f'<div class="acct mono">{_e(user)} ·{adm}'
                f' <form method="post" action="/logout"><button class="link">로그아웃</button>'
                f'</form></div>')
    return f"""<header class="masthead">
  <div class="meta mono">AUTO&nbsp;ZOOM</div>{acct}
  <h1>회의 속기록</h1><p>{_e(sub)}</p></header>"""


def login(err: str = "") -> str:
    msg = f'<div class="msg fail">{_e(err)}</div>' if err else ""
    body = masthead("승인된 계정만 입장할 수 있다.") + f"""
<h2 class="rule">로그인</h2>
<form class="sheet" method="post" action="/login" style="margin-top:32px">
  {msg}
  <div><label for="u">아이디</label>
       <input id="u" name="username" type="text" autocomplete="username" required></div>
  <div><label for="p">비밀번호</label>
       <input id="p" name="password" type="password" autocomplete="current-password" required></div>
  <button class="primary" type="submit">입장</button>
  <p class="hint">계정이 없으면 <a href="/signup">가입 신청</a> 후 관리자 승인을 기다린다.</p>
</form>"""
    return page("로그인 · auto_zoom", body)


def signup(err: str = "") -> str:
    msg = f'<div class="msg fail">{_e(err)}</div>' if err else ""
    body = masthead("관리자가 승인한 사람만 쓸 수 있다.") + f"""
<h2 class="rule">가입 신청</h2>
<form class="sheet" method="post" action="/signup" style="margin-top:32px">
  {msg}
  <div><label for="u">아이디</label>
       <input id="u" name="username" type="text" autocomplete="username" required></div>
  <div><label for="p">비밀번호</label>
       <input id="p" name="password" type="password" autocomplete="new-password" required></div>
  <button class="primary" type="submit">신청</button>
  <p class="hint">신청 후 관리자 승인을 받아야 로그인된다. <a href="/login">로그인으로</a></p>
</form>"""
    return page("가입 신청 · auto_zoom", body)


def notice(msg: str, ok: bool, link: str = "/login", link_text: str = "로그인으로") -> str:
    body = masthead("") + f"""
<div class="sheet" style="margin-top:48px">
  <div class="msg {'ok' if ok else 'fail'}">{_e(msg)}</div>
  <p class="hint" style="margin-top:20px"><a href="{link}">{_e(link_text)}</a></p>
</div>"""
    return page("알림 · auto_zoom", body)


USER_STATE_KO = {"pending": "승인 대기", "approved": "사용 중", "rejected": "거절됨"}


def admin(users: list[dict], me: str) -> str:
    def actions(u: dict) -> str:
        buttons = []
        if u["status"] != "approved":
            buttons.append(("approve", "승인", "ghost"))
        if u["status"] != "rejected" and u["username"] != me:
            buttons.append(("reject", "거절", "ghost"))
        if u["username"] != me:
            buttons.append(("remove", "삭제", "ghost danger"))
        return "".join(
            f'<form method="post" action="/admin/{a}" style="display:inline">'
            f'<input type="hidden" name="username" value="{_e(u["username"])}">'
            f'<button class="{cls}" type="submit">{label}</button></form> '
            for a, label, cls in buttons)

    rows = "".join(f"""<tr>
      <td><span class="state">{_e(USER_STATE_KO.get(u["status"], u["status"]))}</span></td>
      <td>{_e(u["username"])}{' · 관리자' if u.get("role") == "admin" else ''}</td>
      <td class="num">{actions(u)}</td></tr>""" for u in users)
    body = masthead("가입 신청을 승인·거절한다.", me, True) + f"""
<h2 class="rule">계정</h2>
<table><thead><tr><th>상태</th><th>아이디</th><th></th></tr></thead>
<tbody>{rows}</tbody></table>
<a class="back" href="/">← 목록으로</a>"""
    return page("승인 관리 · auto_zoom", body)


def row(j: dict) -> str:
    label, mark = STATE_KO.get(j["status"], (j["status"], ""))
    when = j.get("scheduled_at") or j.get("created_at") or ""
    dur = j.get("duration_s") or 0
    dur_s = f"{int(dur) // 60}분" if dur else "—"
    title = j.get("title") or "제목 없음"
    if j["status"] in ACTIVE and _is_zoom(j):
        act = (f'<button class="ghost" onclick="stop(\'{j["id"]}\')">'
               f'{"예약 취소" if j["status"] == "scheduled" else "퇴장"}</button>')
    else:
        act = (f'<button class="ghost danger" onclick="del(\'{j["id"]}\','
               f'{_json_str(title)})">삭제</button>')
    return f"""<tr>
  <td><span class="mark {mark}"></span><span class="state">{_e(label)}</span></td>
  <td><a href="/jobs/{j['id']}">{_e(title)}</a>
      <span class="url mono">{_e(j['url'][:78]) if j.get('url') else '직접 녹음'}</span>
      <span class="when-sm mono">{_e(when).replace('T', ' ')[:16]}</span></td>
  <td class="num mono">{_e(when).replace('T', ' ')[:16]}</td>
  <td class="num mono">{dur_s}</td>
  <td class="num">{act}</td></tr>"""


def index(jobs: list[dict], user: str = "", admin: bool = False) -> str:
    rows = "".join(row(j) for j in jobs)
    table = f"""<table><thead><tr>
      <th>상태</th><th>회의</th><th>예약·생성</th><th>길이</th><th></th>
    </tr></thead><tbody>{rows}</tbody></table>""" if jobs else \
        '<div class="empty">아직 기록이 없다. 위에 회의 링크를 넣어 시작한다.</div>'

    body = masthead("이 기기로 녹음하거나, 줌에 봇을 보내거나, 영상 링크를 넣는다. "
                    "어느 쪽이든 전문과 요약, 질의응답이 남는다.", user, admin) + f"""
<nav class="tabs">
  <button id="tb-rec" class="on" onclick="showTab('rec')">녹음</button>
  <button id="tb-zoom" onclick="showTab('zoom')">줌 봇</button>
  <button id="tb-media" onclick="showTab('media')">링크 전사</button>
</nav>
<section id="tab-rec">
  <div class="rec">
    <button id="recbtn" class="primary" onclick="toggleRec()">● 녹음 시작</button>
    <span id="rectime" class="mono">00:00</span>
    <input id="rectitle" type="text" maxlength="80" placeholder="제목(선택)">
  </div>
  <div class="hint">이 기기의 마이크로 바로 녹음한다. 정지하면 전사·요약·질의응답까지 그대로 이어진다.</div>
</section>
<section id="tab-zoom" hidden>
  <form class="compose" method="post" action="/jobs">
    <div class="wide">
      <label for="url">회의 링크</label>
      <input id="url" name="url" type="url" required
             placeholder="https://us05web.zoom.us/j/000000000?pwd=…">
      <div class="hint">Zoom 회의(/j/)·웨비나(/w/) 링크 모두 가능. 봇이 카메라·마이크를 끈 채 참석해 녹음한다</div>
    </div>
    <div>
      <label for="title">제목</label>
      <input id="title" name="title" type="text" placeholder="예: 주간 전략 회의" maxlength="80">
      <div class="hint">기록 목록에 표시된다. 나중에 바꿀 수 있다</div>
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
</section>
<section id="tab-media" hidden>
  <form class="compose" method="post" action="/media">
    <div class="wide">
      <label for="murl">영상 링크</label>
      <input id="murl" name="url" type="url" required
             placeholder="https://www.youtube.com/watch?v=…">
      <div class="hint">유튜브·대부분의 동영상 사이트·mp4 직접 링크 — 소리만 내려받아 전사한다</div>
    </div>
    <div>
      <label for="mtitle">제목</label>
      <input id="mtitle" name="title" type="text" placeholder="비우면 영상 제목" maxlength="80">
      <div class="hint">비우면 영상 제목을 그대로 쓴다</div>
    </div>
    <button class="primary" type="submit">전사 시작</button>
  </form>
</section>
<h2 class="rule">기록</h2>
{table}
<script>
function showTab(k){{
  for (const t of ['rec','zoom','media']){{
    document.getElementById('tab-'+t).hidden = t !== k;
    document.getElementById('tb-'+t).classList.toggle('on', t === k);
  }}
  history.replaceState(null, '', location.pathname + '#' + k);
}}
// 해시로 탭을 기억한다 — 10초 자동 새로고침에도 유지되고, 링크로 공유해도 그 탭이 열린다.
showTab(['zoom','media'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'rec');
let mr = null, chunks = [], t0 = 0, timer = null;
function recIdle(text){{
  const b = document.getElementById('recbtn');
  b.disabled = false; b.textContent = text || '● 녹음 시작'; b.classList.remove('recording');
  document.getElementById('rectime').classList.remove('on');
}}
async function toggleRec(){{
  if (mr && mr.state === 'recording') {{ mr.stop(); return; }}
  let stream;
  try {{
    stream = await navigator.mediaDevices.getUserMedia({{audio:true}});
  }} catch (e) {{ alert('마이크를 쓸 수 없습니다.\\n' + e); return; }}
  chunks = [];
  mr = new MediaRecorder(stream, {{audioBitsPerSecond: 32000}});
  mr.ondataavailable = e => {{ if (e.data && e.data.size) chunks.push(e.data); }};
  mr.onstop = async () => {{
    clearInterval(timer);
    stream.getTracks().forEach(t => t.stop());
    const btn = document.getElementById('recbtn');
    btn.disabled = true; btn.textContent = '올리는 중…'; btn.classList.remove('recording');
    const type = mr.mimeType || 'audio/webm';
    const fd = new FormData();
    fd.append('audio', new Blob(chunks, {{type}}), type.includes('mp4') ? 'rec.m4a' : 'rec.webm');
    fd.append('title', document.getElementById('rectitle').value || '');
    try {{
      const r = await fetch('/api/record', {{method:'POST', body: fd}});
      const d = await r.json();
      if (d.ok) {{ location.href = '/jobs/' + d.id; return; }}
      alert('업로드 실패: ' + (d.error || r.status));
    }} catch (e) {{ alert('업로드 실패: ' + e); }}
    recIdle('● 다시 녹음');
  }};
  mr.start(5000);            // 5초 조각 — 브라우저가 통짜 버퍼를 안고 있지 않게
  t0 = Date.now();
  timer = setInterval(() => {{
    const s = (Date.now() - t0) / 1000 | 0;
    document.getElementById('rectime').textContent =
      ('0' + (s / 60 | 0)).slice(-2) + ':' + ('0' + s % 60).slice(-2);
  }}, 1000);
  const btn = document.getElementById('recbtn');
  btn.textContent = '■ 녹음 정지'; btn.classList.add('recording');
  document.getElementById('rectime').classList.add('on');
}}
async function stop(id){{
  if(!confirm('봇을 회의에서 내보낼까요?\\n입장 전이라면 이 기록은 삭제됩니다.')) return;
  await fetch('/api/jobs/'+id+'/stop',{{method:'POST'}});
  location.reload();
}}
async function del(id, title){{
  if(!confirm('['+title+'] 기록을 삭제할까요?\\n녹음·원문·요약이 모두 지워지고 되돌릴 수 없습니다.')) return;
  await fetch('/api/jobs/'+id,{{method:'DELETE'}});
  location.reload();
}}
const busy = {str(any(j['status'] in ACTIVE for j in jobs)).lower()};
// 진행 중인 잡이 있으면 자동 갱신하되, 녹음 중엔 절대 새로고침하지 않는다(녹음이 죽는다).
if (busy) setInterval(()=>{{ if(!(mr && mr.state === 'recording')) location.reload(); }}, 10000);
</script>"""
    return page("회의 속기록 · auto_zoom", body)


def detail(j: dict, user: str = "", admin: bool = False) -> str:
    label, mark = STATE_KO.get(j["status"], (j["status"], ""))
    parts = [masthead(j.get("title") or "제목 없음", user, admin)]
    parts.append(f"""<p style="margin-top:20px">
      <span class="mark {mark}"></span><span class="state">{_e(label)}</span>
      <span class="url mono">{_e(j['url']) if j.get('url') else '직접 녹음'}</span></p>""")
    if j.get("reason"):
        parts.append(f'<p class="hint">종료 사유 · {_e(j["reason"])}</p>')
    # 제목 고치기 — JS 없이 폼 하나로 끝낸다(저장 후 이 화면으로 되돌아온다).
    parts.append(f"""<form class="retitle" method="post" action="/jobs/{j['id']}/title">
      <div style="flex:1"><label for="t">제목</label>
        <input id="t" name="title" type="text" maxlength="80" placeholder="제목 없음"
               value="{_e(j.get('title'))}"></div>
      <button class="ghost" type="submit">제목 저장</button></form>""")
    if j["status"] in ACTIVE and _is_zoom(j):
        parts.append(f"""<p><button class="ghost" onclick="stop('{j['id']}')">
          {"예약 취소" if j["status"] == "scheduled" else "회의에서 퇴장"}</button></p>""")
    else:
        parts.append(f'<p><button class="ghost danger" onclick="del(\'{j["id"]}\','
                     f'{_json_str(j.get("title") or "제목 없음")})">기록 삭제</button></p>')

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
  if(!confirm('봇을 회의에서 내보낼까요?\\n입장 전이라면 이 기록은 삭제됩니다.')) return;
  await fetch('/api/jobs/'+id+'/stop',{{method:'POST'}});
  location.href = '/';
}}
async function del(id, title){{
  if(!confirm('['+title+'] 기록을 삭제할까요?\\n녹음·원문·요약이 모두 지워지고 되돌릴 수 없습니다.')) return;
  await fetch('/api/jobs/'+id,{{method:'DELETE'}});
  location.href = '/';
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
