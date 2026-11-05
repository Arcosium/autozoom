"""화면 템플릿. 컨셉: '편집실 타임코드 데크' — 원문은 타임코드 열과 발화로, 기록은 트랙 목록으로,
진행은 수집·전사·요약 세 칸 미터로 보인다. 색은 차가운 회색 바탕과 청록 강조색.

카드 격자·필 배지·글로우·그라데이션을 쓰지 않는다(사장 지시: AI 티 나는 디자인 금지).
"""
from __future__ import annotations

import html
import json
import re
from urllib.parse import urlsplit

CSS = """
:root{
  --bg:#e9eef2; --surface:#fff; --ink:#172128; --ink-2:#45545f; --ink-3:#5d6d78;
  --rule:#cbd5dd; --rule-2:#dce3e9; --accent:#08756b; --accent-soft:#e0f2ee;
  --danger:#b42318; --danger-soft:#fdecea;
  --on-ink:#fff; --on-accent:#fff;
}
@media (prefers-color-scheme: dark){
  :root{ --bg:#151c21; --surface:#1d272e; --ink:#e9eef2; --ink-2:#b4c2cc; --ink-3:#95a7b3;
         --rule:#36444e; --rule-2:#2a3740; --accent:#62cbbb; --accent-soft:#183c37;
         --danger:#f2867a; --danger-soft:#3a1f1c;
         --on-ink:#151c21; --on-accent:#151c21; }
}

*{box-sizing:border-box}
[hidden]{display:none!important}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:"Noto Sans KR",Arial,sans-serif;font-size:16px;line-height:1.6;
  word-break:keep-all;overflow-wrap:break-word;font-variant-numeric:tabular-nums}
.wrap{max-width:1240px;margin:0 auto;padding:0 32px 96px}
a{color:inherit;text-decoration-color:var(--rule);text-underline-offset:3px}
a:hover{color:var(--accent);text-decoration-color:currentColor}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}

/* 상단 막대: 브랜드 + 계정. 브랜드 앞 점은 녹음 표시등 */
.bar{display:flex;align-items:center;justify-content:space-between;gap:16px;
  min-height:64px;border-bottom:1px solid var(--rule)}
.brand{display:inline-flex;align-items:center;gap:10px;text-decoration:none;color:var(--ink);
  font-family:"Arial Black",Arial,sans-serif;font-weight:900;font-size:18px;letter-spacing:-.01em}
.brand::before{content:"";width:10px;height:10px;border-radius:50%;background:var(--accent)}
.brand:hover{color:var(--ink)}
.acct{display:flex;align-items:center;justify-content:flex-end;flex-wrap:wrap;gap:4px 18px;
  font-size:14px;color:var(--ink-2)}
.acct form{display:inline}
.who{color:var(--ink-3)}

.head{padding:36px 0 28px}
.head h1{margin:0;font-size:34px;line-height:1.25;font-weight:700;letter-spacing:-.02em;
  text-wrap:balance}
.head p{margin:8px 0 0;color:var(--ink-2);max-width:62ch}
/* 하위 화면에서 목록으로 나가는 문. 원문이 길면 아래쪽 링크는 폰에서 닿지 않아 위에도 둔다 */
.backbtn{display:inline-flex;align-items:center;min-height:36px;margin-bottom:8px;
  font-size:14px;color:var(--ink-2);text-decoration:none}
.backbtn:hover{color:var(--accent)}

h2.sec{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px 12px;
  margin:44px 0 0;padding-bottom:10px;border-bottom:1px solid var(--ink);
  font-size:18px;line-height:1.4;font-weight:700}
h2.sec+.hint{margin-top:12px}
.count{margin-left:8px;font-size:14px;font-weight:400;color:var(--ink-3)}
.sec-act{display:flex;align-items:center;flex-wrap:wrap;gap:12px;font-size:13px;font-weight:400}
.filed{color:var(--ink-2)}

/* 목록 화면: 왼쪽 입력 콘솔, 오른쪽 기록 */
.desk{display:grid;grid-template-columns:400px minmax(0,1fr);gap:48px;align-items:start}
.console{position:sticky;top:24px;background:var(--surface);border:1px solid var(--rule);
  border-radius:6px}
.archive h2.sec{margin-top:0}

/* 탭이 넷이라 좁은 폭에선 이름이 두 줄로 접혔다. 줄이지 말고 정 모자라면 가로로 밀리게 둔다 */
nav.tabs{display:flex;border-bottom:1px solid var(--rule);overflow-x:auto;scrollbar-width:none}
nav.tabs::-webkit-scrollbar{display:none}
nav.tabs button{flex:1 0 auto;background:transparent;border:0;border-radius:0;min-height:48px;
  padding:12px;margin-bottom:-1px;font-size:14px;font-weight:500;color:var(--ink-3);
  border-bottom:2px solid transparent;white-space:nowrap}
nav.tabs button:hover{color:var(--ink)}
nav.tabs button.on{color:var(--ink);font-weight:700;border-bottom-color:var(--accent)}
.pane{display:grid;gap:18px;padding:24px}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:14px}

label{display:block;margin-bottom:6px;font-size:13px;font-weight:500;color:var(--ink-2)}
input[type=url],input[type=text],input[type=password],input[type=datetime-local]{
  width:100%;min-height:44px;padding:10px 12px;border:1px solid var(--rule);border-radius:4px;
  background:var(--bg);color:var(--ink);font:inherit;font-size:15px}
input::placeholder{color:var(--ink-3)}
input:focus{outline:0;border-color:var(--ink);background:var(--surface)}
input:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
input:disabled{opacity:.5;cursor:not-allowed}
input[type=file]{width:100%;padding:14px;border:1px dashed var(--rule);border-radius:4px;
  background:var(--bg);color:var(--ink-2);font:inherit;font-size:14px}
input[type=file]::file-selector-button{margin-right:12px;padding:6px 12px;cursor:pointer;
  border:1px solid var(--rule);border-radius:4px;background:var(--surface);color:var(--ink);
  font:inherit;font-size:14px}
.hint{max-width:70ch;margin:6px 0 0;font-size:13px;line-height:1.55;color:var(--ink-3)}

button{font:inherit;font-size:15px;cursor:pointer;border-radius:4px;min-height:44px;
  padding:10px 18px;transition:background-color .16s ease,border-color .16s ease,
  color .16s ease,transform .1s ease}
button:active:not(:disabled){transform:translateY(1px)}
button:disabled{opacity:.5;cursor:wait}
button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
button.primary{background:var(--ink);color:var(--on-ink);border:1px solid var(--ink);font-weight:500}
button.primary:hover{background:var(--ink-2);border-color:var(--ink-2)}
button.ghost{min-height:36px;padding:6px 14px;font-size:14px;background:transparent;
  color:var(--ink);border:1px solid var(--rule)}
button.ghost:hover{border-color:var(--ink)}
button.danger{color:var(--danger)}
button.danger:hover{border-color:var(--danger);background:var(--danger-soft)}
button.link{min-height:0;padding:0;background:transparent;border:0;color:var(--ink-2);
  font-size:14px;text-decoration:underline;text-decoration-color:var(--rule);text-underline-offset:3px}
button.link:hover{color:var(--accent);text-decoration-color:currentColor}
.full{width:100%}

/* 녹음 탭: 큰 시계와 REC 버튼 */
.clock{font-size:52px;font-weight:300;line-height:1;letter-spacing:-.02em;color:var(--ink-3)}
.clock.on{color:var(--accent)}
button.recbtn{width:100%;background:var(--accent);color:var(--on-accent);
  border:1px solid var(--accent);font-weight:700}
button.recbtn:hover{background:color-mix(in srgb,var(--accent) 86%,#000)}
button.recbtn.recording{background:var(--ink);border-color:var(--ink);color:var(--on-ink)}

/* 기록 목록 */
table{width:100%;border-collapse:collapse}
th{padding:14px 12px 10px 0;border-bottom:1px solid var(--rule);text-align:left;
  font-size:13px;font-weight:500;color:var(--ink-3);white-space:nowrap}
td{padding:16px 12px 16px 0;border-bottom:1px solid var(--rule-2);vertical-align:top;font-size:15px}
tbody tr:hover td{background:var(--surface)}
td.num{width:1%;white-space:nowrap;font-size:14px;color:var(--ink-2)}
td.act{width:1%;white-space:nowrap;text-align:right;padding-right:0}
td.act form{display:inline}
.title{font-weight:500;text-decoration:none}
.src{display:block;margin-top:2px;word-break:break-all;font-family:Arial,sans-serif;
  font-size:13px;color:var(--ink-3)}
.when-sm{display:none;margin-top:4px;font-size:13px;color:var(--ink-3)}

/* 진행 미터: 수집·전사·요약. 지난 칸은 잉크, 지금 칸은 신호색 */
.status{display:flex;align-items:center;gap:10px;white-space:nowrap}
.meter{display:inline-flex;gap:3px}
.meter i{position:relative;overflow:hidden;width:12px;height:4px;background:var(--rule)}
.meter i.on{background:var(--ink)}
.meter i.now::after{content:"";position:absolute;inset:0;background:var(--accent);
  transform-origin:left;animation:fill 1.6s ease-in-out infinite}
@keyframes fill{from{transform:scaleX(0)}to{transform:scaleX(1)}}
.state{font-size:14px;color:var(--ink-2)}
.state.live{color:var(--ink);font-weight:500}
.state.fail{color:var(--danger)}
@media (prefers-reduced-motion:reduce){.meter i.now::after{animation:none}*{transition:none!important}}

.empty{padding:48px 0;color:var(--ink-3)}
.empty strong{display:block;margin-bottom:4px;font-size:17px;color:var(--ink)}
.pagination{display:flex;flex-wrap:wrap;align-items:center;gap:4px;margin-top:24px}
.pagination a,.pagination span{display:inline-flex;align-items:center;justify-content:center;
  min-width:36px;min-height:40px;padding:6px 10px;border-radius:3px;font-size:14px;text-decoration:none}
.pagination a:hover{background:var(--surface)}
.pagination a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.pagination [aria-current]{background:var(--accent);color:var(--on-accent);font-weight:700}

/* 기록 화면: 왼쪽 요약·질문, 오른쪽 원문(근거) */
.meta{display:flex;flex-wrap:wrap;align-items:center;gap:6px 16px;margin:-16px 0 24px;
  font-size:14px;color:var(--ink-2)}
.meta .url{font-family:Arial,sans-serif;color:var(--ink-3);word-break:break-all}
.reason{margin:10px 0 0;font-size:14px;color:var(--danger)}
.tools{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:16px;
  padding:20px 0;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule)}
form.retitle{display:flex;align-items:flex-end;gap:10px;flex:1 1 360px;max-width:560px}
form.retitle>div{flex:1}
.tools-act{display:flex;flex-wrap:wrap;gap:10px}
.paper{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,440px);gap:56px;align-items:start}
.source{position:sticky;top:24px}

.summary{max-width:68ch;font-size:16px;line-height:1.75}
.summary h2{margin:28px 0 6px;font-size:15px;font-weight:700}
.summary>h2:first-child{margin-top:20px;font-size:13px;font-weight:500;color:var(--ink-3)}
.summary>h2:first-child+p{margin:4px 0 0;font-size:20px;line-height:1.55;font-weight:500;
  text-wrap:pretty}
.summary p{margin:6px 0}
.summary ul{margin:6px 0;padding-left:20px}
.summary li{margin:4px 0}

.mytodo{margin-top:20px;padding:18px 20px;background:var(--surface);border:1px solid var(--rule);
  border-radius:6px}
.mytodo-h{display:block;margin-bottom:6px;font-size:15px;font-weight:700}
.mytodo-h b{color:var(--accent)}
.mytodo ul{list-style:none;margin:0;padding:0}
.mytodo li{position:relative;margin:8px 0;padding-left:26px;line-height:1.6}
.mytodo li::before{content:"";position:absolute;left:0;top:.3em;width:14px;height:14px;
  border:1.5px solid var(--ink-2);border-radius:3px}
.mytodo.none{background:transparent}
.mytodo.none p{margin:0;font-size:14px;color:var(--ink-3)}

.qa{max-width:68ch;margin-top:16px}
.qa-form{display:flex;gap:10px;align-items:stretch}
.qa-form input{flex:1}
.qa-form input:disabled{border-style:dashed}
.qa-item{padding:18px 0;border-bottom:1px solid var(--rule-2)}
.qa-q{margin:0 0 6px;font-size:15px;font-weight:700}
.qa-a{font-size:15px;line-height:1.75;color:var(--ink-2)}
.qa-a p{margin:6px 0}
.qa-a ul{margin:6px 0;padding-left:20px}
.qa-a li{margin:3px 0}
.qa-a.pending{color:var(--ink-3)}

.transcript{max-height:calc(100dvh - 120px);overflow:auto;margin-top:8px;
  font-size:14px;line-height:1.7;color:var(--ink-2)}
.transcript p{display:grid;grid-template-columns:68px minmax(0,1fr);gap:12px;margin:0;padding:5px 0}
.transcript p:hover{background:var(--surface)}
.tc{padding-top:1px;font-size:13px;color:var(--ink-3)}
.source .empty{padding:28px 0}

details{margin-top:44px;border-top:1px solid var(--rule)}
details:not([open]) .log{display:none}
details>summary{cursor:pointer;padding:14px 0;font-size:14px;font-weight:500;color:var(--ink-2)}
.log{max-height:340px;overflow:auto;padding:14px;white-space:pre-wrap;
  background:var(--surface);border:1px solid var(--rule);border-radius:4px;
  font-size:12.5px;line-height:1.7;color:var(--ink-3)}
.back{display:inline-block;margin-top:28px;font-size:14px;color:var(--ink-2);text-decoration:none}

/* 로그인·가입·알림 */
.gate{display:grid;grid-template-columns:minmax(0,1fr) 400px;gap:64px;align-items:start;padding-top:64px}
.gate h1{margin:0 0 16px;font-size:40px;line-height:1.2;font-weight:700;letter-spacing:-.02em}
.lede{max-width:46ch;margin:0;font-size:17px;color:var(--ink-2)}
.lede+.lede{margin-top:12px}
.sheet{display:grid;gap:18px;padding:28px;background:var(--surface);border:1px solid var(--rule);
  border-radius:6px}
.sheet h2{margin:0;font-size:20px}
.sheet button.primary{justify-self:start;padding:10px 32px}
.msg{padding:12px 14px;border-radius:4px;background:var(--bg);font-size:14px}
.msg.fail{color:var(--danger);background:var(--danger-soft)}

/* 승인 관리 */
.inline{display:flex;flex-wrap:wrap;align-items:center;gap:14px;padding:18px 0}
.inline input{flex:1;min-width:200px}
.screen{display:block;width:100%;max-width:1280px;border:1px solid var(--rule);cursor:crosshair}

@media (max-width:900px){
  .desk,.paper,.gate{grid-template-columns:minmax(0,1fr);gap:32px}
  .console,.source{position:static}
  .transcript{max-height:none}
  .gate{padding-top:32px}
}
@media (max-width:760px){
  .wrap{padding:0 18px 72px}
  .head{padding:24px 0 20px}
  .head h1{font-size:26px}
  .gate h1{font-size:30px}
  .clock{font-size:44px}
  .pane{padding:20px}
  .pair{grid-template-columns:1fr}
  /* 폰 폭에선 날짜·길이 열이 제목을 짓누른다 → 두 열을 접고 날짜는 제목 밑으로 */
  th:nth-child(3),td:nth-child(3),th:nth-child(4),td:nth-child(4){display:none}
  .when-sm{display:block}
  td .status{flex-direction:column;align-items:flex-start;gap:6px}
  .tools{align-items:stretch}
}
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=Noto+Sans+KR:wght@300;400;500;700&display=swap">'
         '<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27'
         ' viewBox=%270 0 16 16%27%3E%3Ccircle cx=%278%27 cy=%278%27 r=%276%27'
         ' fill=%27%2308756b%27/%3E%3C/svg%3E">')

STATE_KO = {
    "scheduled": ("대기 예약", "wait"), "queued": ("입장 준비", "live"),
    "joining": ("입장 중", "live"), "recording": ("녹음 중", "live"),
    "downloading": ("받는 중", "live"),
    "transcribing": ("전사 중", "live"), "summarizing": ("요약 중", "live"),
    "done": ("완료", "done"), "failed": ("실패", "fail"), "stopped": ("중단", "fail"),
}
ACTIVE = {"scheduled", "queued", "joining", "recording", "downloading",
          "transcribing", "summarizing"}
# 먼 미래의 예약만 있어도 목록 전체를 10초마다 새로고침하면 작성 중인 폼이 지워진다.
# 실제 상태가 빠르게 바뀌는 작업만 자동 갱신한다.
AUTO_REFRESH = ACTIVE - {"scheduled"}
# 진행 미터의 지금 칸(0 수집 · 1 전사 · 2 요약). 완료는 세 칸 모두 채운다.
STAGE = {"queued": 0, "joining": 0, "recording": 0, "downloading": 0,
         "transcribing": 1, "summarizing": 2, "done": 3}


def _e(s) -> str:
    return html.escape(str(s or ""))


def _json_str(s) -> str:
    """onclick="…" 속성 안에 넣을 JS 문자열 리터럴(따옴표까지 이스케이프)."""
    return html.escape(json.dumps(str(s or "")))


def _when(j: dict) -> str:
    return (j.get("scheduled_at") or j.get("created_at") or "").replace("T", " ")[:16]


def _dur(sec) -> str:
    """길이를 타임코드로(42:10, 1:02:33). 없으면 '-'."""
    s = int(sec or 0)
    if not s:
        return "-"
    h, m = divmod(s // 60, 60)
    return f"{h}:{m:02d}:{s % 60:02d}" if h else f"{m}:{s % 60:02d}"


def _source(u: str) -> str:
    """목록용 출처는 호스트만 둔다(줌 pwd·긴 회의 번호가 폰에서 줄을 넘겼다). 전체 주소는 기록 화면에 있다."""
    return (urlsplit(u).hostname or u).removeprefix("www.")


def status_html(status: str) -> str:
    label, kind = STATE_KO.get(status, (status, ""))
    n = STAGE.get(status, -1)
    cells = "".join(f'<i class="{"on" if k < n else "now" if k == n else ""}"></i>'
                    for k in range(3))
    return (f'<span class="status"><span class="meter" title="수집 · 전사 · 요약">{cells}</span>'
            f'<span class="state {kind}">{_e(label)}</span></span>')


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


TIMECODE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s?(.*)$")


def transcript_html(text: str) -> str:
    """'[00:01:23] 발화' 줄을 타임코드 열 + 발화로 나눈다. 타임코드가 없는 줄은 발화만."""
    out = []
    for line in (text or "").splitlines():
        m = TIMECODE.match(line.strip())
        tc, body = (m.group(1), m.group(2)) if m else ("", line.strip())
        if body:
            out.append(f'<p><span class="tc">{tc}</span><span>{_e(body)}</span></p>')
    return "".join(out)


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
    return (f'<div class="mytodo"><span class="mytodo-h">내가 할 일 <b>{len(items)}건</b></span>'
            f'<ul>{lis}</ul></div>')


def qa_block(job: dict) -> str:
    history = []
    try:
        history = json.loads(job.get("qa") or "[]")
    except Exception:
        history = []
    past = "".join(
        f'<div class="qa-item"><p class="qa-q">{_e(h.get("q"))}</p>'
        f'<div class="qa-a">{md_to_html(h.get("a") or "")}</div></div>'
        for h in history)
    disabled = "" if (job.get("transcript") or "").strip() else " disabled"
    hint = ("" if not disabled else
            '<p class="hint">전사가 끝나야 질문할 수 있다.</p>')
    return f"""<h2 class="sec">이 회의에 묻기</h2>
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


def topbar(user: str = "", admin: bool = False) -> str:
    acct = ""
    if user:
        adm = '<a href="/admin">승인 관리</a>' if admin else ""
        acct = (f'<nav class="acct"><span class="who">{_e(user)}</span>{adm}'
                f'<form method="post" action="/logout"><button class="link">로그아웃</button>'
                f'</form></nav>')
    return f'<header class="bar"><a class="brand" href="/">AutoZoom</a>{acct}</header>'


def head(title: str, sub: str = "", back: str = "") -> str:
    home = f'<a class="backbtn" href="{_e(back)}">← 기록 목록</a>' if back else ""
    lead = f"<p>{_e(sub)}</p>" if sub else ""
    return f'<div class="head">{home}<h1>{_e(title)}</h1>{lead}</div>'


INTRO = ('<p class="lede">줌 회의에 봇을 보내거나 이 기기로 녹음하거나 영상 링크나 파일을 넣으면, '
         '타임코드가 붙은 원문과 요약이 남는다.</p>'
         '<p class="lede">요약은 원문에 있는 말만 쓰고, 내 할 일을 따로 뽑으며, '
         '원문에 직접 물어볼 수 있다.</p>')


def _gate(heading: str, form: str) -> str:
    return (topbar() + f'<main class="gate"><div><h1>{_e(heading)}</h1>{INTRO}</div>'
            f'{form}</main>')


def login(err: str = "") -> str:
    msg = f'<div class="msg fail">{_e(err)}</div>' if err else ""
    form = f"""<form class="sheet" method="post" action="/login">
  <h2>로그인</h2>
  {msg}
  <div><label for="u">아이디</label>
       <input id="u" name="username" type="text" autocomplete="username" required></div>
  <div><label for="p">비밀번호</label>
       <input id="p" name="password" type="password" autocomplete="current-password" required></div>
  <button class="primary" type="submit">입장</button>
  <p class="hint">승인된 계정만 입장할 수 있다. 계정이 없으면 <a href="/signup">가입 신청</a> 후
    관리자 승인을 기다린다.</p>
</form>"""
    return page("로그인 · AutoZoom", _gate("회의 속기록", form))


def signup(err: str = "") -> str:
    msg = f'<div class="msg fail">{_e(err)}</div>' if err else ""
    form = f"""<form class="sheet" method="post" action="/signup">
  <h2>가입 신청</h2>
  {msg}
  <div><label for="u">아이디</label>
       <input id="u" name="username" type="text" autocomplete="username" required></div>
  <div><label for="p">비밀번호</label>
       <input id="p" name="password" type="password" autocomplete="new-password" required></div>
  <button class="primary" type="submit">신청</button>
  <p class="hint">관리자가 승인해야 로그인된다. <a href="/login">로그인으로</a></p>
</form>"""
    return page("가입 신청 · AutoZoom", _gate("회의 속기록", form))


def notice(msg: str, ok: bool, link: str = "/login", link_text: str = "로그인으로") -> str:
    box = f"""<div class="sheet">
  <div class="msg {'ok' if ok else 'fail'}">{_e(msg)}</div>
  <p class="hint"><a href="{link}">{_e(link_text)}</a></p>
</div>"""
    return page("알림 · AutoZoom", _gate("회의 속기록", box))


USER_STATE_KO = {"pending": "승인 대기", "approved": "사용 중", "rejected": "거절됨"}


LOGIN_STATE_KO = {
    "idle": "대기", "running": "서버에서 로그인 중", "otp_required": "인증 코드 필요",
    "verifying": "인증 확인 중", "success": "로그인 완료", "failed": "로그인 실패",
    "busy": "회의 봇 사용 중",
}


def admin(users: list[dict], me: str, bot_status: dict | None = None) -> str:
    def actions(u: dict) -> str:
        buttons = []
        if u["status"] != "approved":
            buttons.append(("approve", "승인", "ghost"))
        if u["status"] != "rejected" and u["username"] != me:
            buttons.append(("reject", "거절", "ghost"))
        if u["username"] != me:
            buttons.append(("remove", "삭제", "ghost danger"))
        return "".join(
            f'<form method="post" action="/admin/{a}">'
            f'<input type="hidden" name="username" value="{_e(u["username"])}">'
            f'<button class="{cls}" type="submit">{label}</button></form> '
            for a, label, cls in buttons)

    rows = "".join(f"""<tr>
      <td class="num"><span class="state">{_e(USER_STATE_KO.get(u["status"], u["status"]))}</span></td>
      <td>{_e(u["username"])}{' · 관리자' if u.get("role") == "admin" else ''}</td>
      <td class="act">{actions(u)}</td></tr>""" for u in users)
    bot_status = bot_status or {"state": "idle", "message": "아직 로그인 작업을 시작하지 않았습니다."}
    state = str(bot_status.get("state") or "idle")
    state_name = LOGIN_STATE_KO.get(state, state)
    message = _e(bot_status.get("message") or "")
    active = state in {"running", "otp_required", "verifying"}
    login_button = "서버에서 로그인 중" if active else (
        "봇 계정 다시 로그인" if state == "success" else "봇 계정 로그인")
    otp = ""
    if state == "otp_required":
        otp = """
  <form class="retitle" method="post" action="/admin/zoom-login/otp">
    <div><label for="otp">인증 코드</label>
      <input id="otp" name="otp" type="text" inputmode="numeric" autocomplete="one-time-code"
             pattern="[0-9]{4,8}" maxlength="8" required></div>
    <button class="ghost" type="submit">인증 코드 전송</button>
  </form>"""
    body = topbar(me, True) + head("승인 관리", "가입 신청을 승인·거절하고 줌 봇 계정을 관리한다.",
                                   back="/") + f"""
<h2 class="sec">Zoom 봇 계정</h2>
<div class="inline">
  <form method="post" action="/admin/zoom-login">
    <button class="primary" type="submit"{' disabled' if active else ''}>{login_button}</button>
  </form>
  <div><span class="state live">{_e(state_name)}</span>
    <p class="hint">{message}</p>
    <p class="hint">로그인 창은 이 기기에 뜨지 않고 Autozoom 서버의 봇 브라우저에서 처리됩니다.</p></div>
</div>{otp}
{'<script>setTimeout(() => location.reload(), 2500)</script>' if active else ''}
<h2 class="sec">직접 로그인 (원격 화면)</h2>
<p class="hint">자동 로그인이 막힐 때 쓴다. 아래 화면이 서버의 봇 브라우저다.
  화면을 눌러 입력칸을 고르고, 입력창에 쓴 뒤 '입력'을 누른다. 로그인이 끝나면 '세션 저장'.</p>
<div class="inline">
  <button class="primary" id="rl-start" onclick="rlStart()">원격 로그인 열기</button>
  <span class="state" id="rl-msg"></span>
</div>
<div id="rl-panel" hidden>
  <img id="rl-screen" class="screen" alt="봇 브라우저 화면">
  <div class="inline">
    <input id="rl-text" type="text" placeholder="이메일·비밀번호·인증코드 입력 후 [입력]"
           onkeydown="if(event.key==='Enter'){{rlType();event.preventDefault()}}">
    <button class="ghost" onclick="rlType()">입력</button>
    <button class="ghost" onclick="rlKey('Enter')">Enter</button>
    <button class="ghost" onclick="rlKey('Tab')">Tab</button>
    <button class="ghost" onclick="rlKey('Backspace')">⌫</button>
    <button class="primary" onclick="rlSave()">세션 저장</button>
    <button class="ghost danger" onclick="rlStop()">닫기</button>
  </div>
</div>
<h2 class="sec"><span>계정<span class="count">{len(users)}명</span></span></h2>
<table><thead><tr><th>상태</th><th>아이디</th><th></th></tr></thead>
<tbody>{rows}</tbody></table>
<a class="back" href="/">← 목록으로</a>
<script>
let rlTimer = null;
async function rlStart(){{
  const b = document.getElementById('rl-start');
  b.disabled = true; b.textContent = '브라우저 여는 중…';
  const s = await (await fetch('/api/remote-login/start', {{method:'POST'}})).json();
  document.getElementById('rl-msg').textContent = s.message || '';
  b.disabled = false; b.textContent = '원격 로그인 열기';
  if (s.on) rlShow();
}}
function rlShow(){{
  document.getElementById('rl-panel').hidden = false;
  const img = document.getElementById('rl-screen');
  clearInterval(rlTimer);
  rlTimer = setInterval(async () => {{
    img.src = '/api/remote-login/screen.jpg?t=' + Date.now();
    const s = await (await fetch('/api/remote-login/status')).json();
    document.getElementById('rl-msg').textContent = s.message || '';
    if (!s.on) {{ clearInterval(rlTimer); document.getElementById('rl-panel').hidden = true; }}
  }}, 1000);
}}
async function rlEvent(ev){{ await fetch('/api/remote-login/event', {{method:'POST',
  headers:{{'Content-Type':'application/json'}}, body: JSON.stringify(ev)}}); }}
document.getElementById('rl-screen').addEventListener('click', e => {{
  const r = e.currentTarget.getBoundingClientRect();
  const k = 1280 / r.width;   // 이미지는 비율 유지로 줄어드니 x·y 축척이 같다
  rlEvent({{t:'click', x:(e.clientX - r.left) * k, y:(e.clientY - r.top) * k}});
}});
function rlType(){{
  const box = document.getElementById('rl-text');
  if (box.value) rlEvent({{t:'text', v: box.value}});
  box.value = '';
}}
function rlKey(k){{ rlEvent({{t:'key', v:k}}); }}
async function rlSave(){{ rlEvent({{t:'save'}}); }}
async function rlStop(){{ await fetch('/api/remote-login/stop', {{method:'POST'}}); }}
</script>"""
    return page("승인 관리 · AutoZoom", body)


def row(j: dict) -> str:
    title = j.get("title") or "제목 없음"
    if j["status"] in ACTIVE:
        act = (f'<button class="ghost" onclick="stop(\'{j["id"]}\')">'
               f'{"예약 취소" if j["status"] == "scheduled" else "중지"}</button>')
    else:
        act = (f'<button class="ghost danger" onclick="del(\'{j["id"]}\','
               f'{_json_str(title)})">삭제</button>')
    return f"""<tr>
  <td class="num">{status_html(j["status"])}</td>
  <td><a class="title" href="/jobs/{j['id']}">{_e(title)}</a>
      <span class="src">{_e(_source(j['url'])) if j.get('url') else '직접 녹음'}</span>
      <span class="when-sm">{_e(_when(j))}</span></td>
  <td class="num">{_e(_when(j))}</td>
  <td class="num">{_dur(j.get("duration_s"))}</td>
  <td class="act">{act}</td></tr>"""


def pagination(current_page: int, total: int) -> str:
    pages = max(1, (total + 4) // 5)
    if pages == 1:
        return ""
    start = ((current_page - 1) // 10) * 10 + 1
    end = min(start + 9, pages)
    links = []
    if start > 1:
        links.append(f'<a href="/?page={start - 1}" aria-label="이전 10페이지">이전</a>')
    for number in range(start, end + 1):
        if number == current_page:
            links.append(f'<span aria-current="page">{number}</span>')
        else:
            links.append(f'<a href="/?page={number}" aria-label="{number}페이지">{number}</a>')
    if end < pages:
        links.append(f'<a href="/?page={end + 1}" aria-label="다음 10페이지">다음</a>')
    return '<nav class="pagination" aria-label="기록 페이지">' + "".join(links) + '</nav>'


def index(jobs: list[dict], user: str = "", admin: bool = False,
          current_page: int = 1, total: int | None = None) -> str:
    if total is None:
        total = len(jobs)
    rows = "".join(row(j) for j in jobs)
    table = f"""<table><thead><tr>
      <th>진행</th><th>회의</th><th>예약·생성</th><th>길이</th><th></th>
    </tr></thead><tbody>{rows}</tbody></table>""" if jobs else \
        ('<div class="empty"><strong>아직 기록이 없다</strong>'
         '녹음을 시작하거나 회의 링크·파일을 넣으면 여기에 쌓인다.</div>')

    body = topbar(user, admin) + head("회의 속기록") + f"""
<main class="desk">
<section class="console" aria-label="새 기록">
<nav class="tabs">
  <button id="tb-rec" class="on" onclick="showTab('rec')">녹음</button>
  <button id="tb-zoom" onclick="showTab('zoom')">줌 봇</button>
  <button id="tb-media" onclick="showTab('media')">링크 전사</button>
  <button id="tb-file" onclick="showTab('file')">동영상 올리기</button>
</nav>
<section id="tab-rec" class="pane">
  <span id="rectime" class="clock">00:00</span>
  <button id="recbtn" class="recbtn" onclick="toggleRec()">● 녹음 시작</button>
  <div><label for="rectitle">제목</label>
    <input id="rectitle" type="text" maxlength="80" placeholder="선택"></div>
  <p class="hint">이 기기의 마이크로 바로 녹음한다. 정지하면 전사·요약·질의응답까지 그대로 이어진다.</p>
</section>
<section id="tab-zoom" hidden>
  <form class="pane" method="post" action="/jobs">
    <div>
      <label for="url">회의 링크</label>
      <input id="url" name="url" type="url" required
             placeholder="https://us05web.zoom.us/j/000000000?pwd=…">
      <p class="hint">Zoom·유튜브·단축 링크 모두 가능. 실제 주소를 확인해 Zoom이면 봇 참석, 영상이면 녹음·전사로 자동 처리한다</p>
    </div>
    <div>
      <label for="title">제목</label>
      <input id="title" name="title" type="text" placeholder="예: 주간 전략 회의" maxlength="80">
      <p class="hint">기록 목록에 표시된다. 나중에 바꿀 수 있다</p>
    </div>
    <div class="pair">
      <div>
        <label for="bot">입장 이름</label>
        <input id="bot" name="bot_name" type="text" placeholder="회의록봇" maxlength="30">
        <p class="hint">참가자에게 보이는 이름</p>
      </div>
      <div>
        <label for="at">입장 시각</label>
        <input id="at" name="scheduled_at" type="datetime-local">
        <p class="hint">비우면 즉시 입장</p>
      </div>
    </div>
    <button class="primary full" type="submit">봇 보내기</button>
  </form>
</section>
<section id="tab-media" hidden>
  <form class="pane" method="post" action="/media">
    <div>
      <label for="murl">영상 링크</label>
      <input id="murl" name="url" type="url" required
             placeholder="https://www.youtube.com/watch?v=…">
      <p class="hint">Zoom·유튜브·단축 링크 모두 가능. 라이브는 시작을 기다렸다가 녹음하며 원문을 실시간으로 채운다</p>
    </div>
    <div>
      <label for="mtitle">제목</label>
      <input id="mtitle" name="title" type="text" placeholder="비우면 영상 제목" maxlength="80">
    </div>
    <button class="primary full" type="submit">녹음·전사 시작</button>
  </form>
</section>
<section id="tab-file" class="pane" hidden>
  <input id="vfile" type="file" accept="video/*,audio/*" aria-label="올릴 파일">
  <div><label for="vtitle">제목</label>
    <input id="vtitle" type="text" maxlength="80" placeholder="비우면 파일 이름"></div>
  <button id="vbtn" class="primary full" onclick="upload()">전사·요약 시작</button>
  <p class="hint">회의를 찍은 동영상이나 녹음 파일을 그대로 올린다. 소리만 뽑아 전사하고
    요약·질의응답까지 이어진다. 큰 파일은 나눠서 올라가니 다 올라갈 때까지 이 창을 닫지 않는다.</p>
</section>
</section>
<section class="archive">
<h2 class="sec"><span>기록<span class="count">전체 {total}건</span></span></h2>
{table}
{pagination(current_page, total)}
</section>
</main>
<script>
function showTab(k){{
  for (const t of ['rec','zoom','media','file']){{
    document.getElementById('tab-'+t).hidden = t !== k;
    document.getElementById('tb-'+t).classList.toggle('on', t === k);
  }}
  history.replaceState(null, '', location.pathname + location.search + '#' + k);
  document.querySelectorAll('.pagination a').forEach(a => {{ a.hash = k; }});
}}
// 해시로 탭을 기억한다 — 10초 자동 새로고침에도 유지되고, 링크로 공유해도 그 탭이 열린다.
showTab(['zoom','media','file'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'rec');
let uploading = false;
async function upload(){{
  const f = document.getElementById('vfile').files[0];
  if(!f){{ alert('올릴 파일을 고르세요.'); return; }}
  const btn = document.getElementById('vbtn');
  const idle = () => {{ uploading = false; btn.disabled = false; btn.textContent = '전사·요약 시작'; }};
  const id = [...crypto.getRandomValues(new Uint8Array(16))]
             .map(b => b.toString(16).padStart(2,'0')).join('');
  const CH = 48 * 1024 * 1024;   // Cloudflare 프록시가 요청 하나를 100MB 에서 자른다
  uploading = true; btn.disabled = true;
  try {{
    for (let off = 0; off < f.size; off += CH) {{
      const last = off + CH >= f.size;
      btn.textContent = '올리는 중 ' + Math.min(100, Math.round(off * 100 / f.size)) + '%';
      const fd = new FormData();
      fd.append('chunk', f.slice(off, off + CH));
      fd.append('upload_id', id);
      fd.append('filename', f.name);
      fd.append('title', document.getElementById('vtitle').value
                         || f.name.replace(/\\.[^.]+$/, '').slice(0, 80));
      fd.append('last', last ? '1' : '0');
      const r = await fetch('/api/upload', {{method:'POST', body: fd}});
      const d = await r.json().catch(() => ({{}}));
      if (!d.ok) throw new Error(d.error || ('HTTP ' + r.status));
      if (d.id) {{ btn.textContent = '전사 시작…'; location.href = '/jobs/' + d.id; return; }}
    }}
  }} catch (e) {{ alert('업로드 실패: ' + e); }}
  idle();
}}
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
  if(!confirm('진행 중인 녹음·전사를 중지할까요?\\n시작 전이라면 이 기록은 삭제됩니다.')) return;
  await fetch('/api/jobs/'+id+'/stop',{{method:'POST'}});
  location.reload();
}}
async function del(id, title){{
  if(!confirm('['+title+'] 기록을 삭제할까요?\\n녹음·원문·요약이 모두 지워지고 되돌릴 수 없습니다.')) return;
  await fetch('/api/jobs/'+id,{{method:'DELETE'}});
  location.reload();
}}
const busy = {str(any(j['status'] in AUTO_REFRESH for j in jobs)).lower()};
let formDirty = false;
document.querySelectorAll('input, textarea, select').forEach(el => {{
  el.addEventListener('input', () => {{ formDirty = true; }});
  el.addEventListener('change', () => {{ formDirty = true; }});
}});
function editingForm() {{
  const el = document.activeElement;
  return formDirty || !!(el && el.matches('input, textarea, select'));
}}
// 실제 처리 중인 잡만 자동 갱신한다. 폼을 작성 중이면 사용자가 제출할 때까지 그대로 둔다.
if (busy) setInterval(()=>{{
  if(!(mr && mr.state === 'recording') && !uploading && !editingForm()) location.reload();
}}, 10000);
</script>"""
    return page("회의 속기록 · AutoZoom", body)


def detail(j: dict, user: str = "", admin: bool = False) -> str:
    title = j.get("title") or "제목 없음"
    parts = [topbar(user, admin), head(title, back="/")]
    src = _e(j["url"]) if j.get("url") else "직접 녹음"
    parts.append(f'<div class="meta">{status_html(j["status"])}<span>{_e(_when(j))}</span>'
                 f'<span>{_dur(j.get("duration_s"))}</span><span class="url">{src}</span></div>')
    if j.get("reason"):
        parts.append(f'<p class="reason">종료 사유 · {_e(j["reason"])}</p>')
    if j["status"] in ACTIVE:
        acts = (f'<button class="ghost" onclick="stop(\'{j["id"]}\')">'
                f'{"예약 취소" if j["status"] == "scheduled" else "녹음·전사 중지"}</button>')
    else:
        # 녹음은 남았는데 전사·요약만 넘어진 잡 — 다시 못 찍는 회의라 되돌릴 길을 둔다.
        again = (f'<button class="ghost" onclick="again(\'{j["id"]}\')">전사 다시 시도</button>'
                 if j["status"] in ("failed", "stopped") and j.get("wav_path") else "")
        acts = (f'{again}<button class="ghost danger" onclick="del(\'{j["id"]}\','
                f'{_json_str(title)})">기록 삭제</button>')
    # 제목 고치기 — JS 없이 폼 하나로 끝낸다(저장 후 이 화면으로 되돌아온다).
    parts.append(f"""<div class="tools">
  <form class="retitle" method="post" action="/jobs/{j['id']}/title">
    <div><label for="t">제목</label>
      <input id="t" name="title" type="text" maxlength="80" placeholder="제목 없음"
             value="{_e(j.get('title'))}"></div>
    <button class="ghost" type="submit">제목 저장</button></form>
  <div class="tools-act">{acts}</div>
</div>""")

    main = []
    if j.get("summary"):
        if j.get("coresight_slug"):
            action = (f'<span class="filed">Coresight 등재됨 · {_e(j["coresight_slug"])}</span>'
                      f'<button class="ghost" onclick="toCoresight(\'{j["id"]}\')">다시 올리기</button>')
        else:
            action = (f'<button class="ghost" onclick="toCoresight(\'{j["id"]}\')">'
                      f'Coresight에 올리기</button>')
        todo, rest = split_my_todo(j["summary"])
        main.append(f'<h2 class="sec">요약<span class="sec-act">{action}</span></h2>')
        main.append(my_todo_block(todo))
        main.append(f'<div class="summary">{md_to_html(rest)}</div>')
    main.append(qa_block(j))

    lines = transcript_html(j.get("transcript"))
    count = f'<span class="count">{lines.count("<p>")}줄</span>' if lines else ""
    body = (f'<div class="transcript">{lines}</div>' if lines else
            '<div class="empty">전사가 시작되면 원문이 타임코드와 함께 여기에 쌓인다.</div>')
    parts.append(f'<div class="paper"><div>{"".join(main)}</div>'
                 f'<aside class="source"><h2 class="sec"><span>원문{count}</span></h2>{body}</aside>'
                 f'</div>')
    parts.append('<details><summary>진행 로그</summary>'
                 f'<div class="log mono">{_e(j.get("log"))}</div></details>')
    parts.append('<a class="back" href="/">← 목록으로</a>')
    parts.append(f"""<script>
async function stop(id){{
  if(!confirm('진행 중인 녹음·전사를 중지할까요?\\n시작 전이라면 이 기록은 삭제됩니다.')) return;
  await fetch('/api/jobs/'+id+'/stop',{{method:'POST'}});
  location.href = '/';
}}
async function del(id, title){{
  if(!confirm('['+title+'] 기록을 삭제할까요?\\n녹음·원문·요약이 모두 지워지고 되돌릴 수 없습니다.')) return;
  await fetch('/api/jobs/'+id,{{method:'DELETE'}});
  location.href = '/';
}}
async function again(id){{
  const r = await fetch('/api/jobs/'+id+'/retry',{{method:'POST'}});
  const d = await r.json().catch(()=>({{}}));
  if(d.ok) location.reload();
  else alert('다시 시도할 수 없습니다: ' + (d.error||r.status));
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
let formDirty = false;
document.querySelectorAll('input, textarea, select').forEach(el => {{
  el.addEventListener('input', () => {{ formDirty = true; }});
  el.addEventListener('change', () => {{ formDirty = true; }});
}});
if ({str(j["status"] in AUTO_REFRESH).lower()}) setTimeout(()=>{{
  const el = document.activeElement;
  if (!formDirty && !(el && el.matches('input, textarea, select'))) location.reload();
}}, 10000);
</script>""")
    return page(f"{title} · AutoZoom", "".join(parts))
