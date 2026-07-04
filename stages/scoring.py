#!/usr/bin/env python3
"""Stage 4.5: 读取 opportunities 表的 evidence JSON，按规则计算评分写回数据库。"""
import os, re, sqlite3, json

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'pipeline.db')

# ── 可配置阈值 ────────────────────────────────────────────────────────────────
REACTIONS_HIGH  = 5
LOC_HIGH        = 500
LOC_MEDIUM      = 200
PR_AGE_DAYS     = 365
PROJECT_ADOPTION_STARS = 500  # 认为项目具备基本 adoption 门槛的 star 数

REJECT_KEYWORDS  = ["out of scope", "won't fix", "won\u2019t fix", "wontfix", "wont fix",
                    "by design", "not planned", "not in scope", "intentional"]
WELCOME_KEYWORDS = ["pr welcome", "pull request welcome", "good first issue",
                    "help wanted", "contributions welcome",
                    "happy to accept", "would welcome", "feel free to",
                    "looking forward to", "not saying no", "sounds good",
                    "please go ahead", "go ahead and"]
HARD_KEYWORDS    = ["核心数据结构", "并发设计", "语言特性限制",
                    "core data structure", "concurrency", "language limitation"]
EASY_KEYWORDS    = ["ui", "docs", "documentation", "example", "examples",
                    "config", "configuration", "logging", "error message",
                    "typo", "wording", "comment", "readme",
                    "display", "font", "color", "placeholder", "validation message"]

LEVEL_UP = {"low": "medium", "medium": "high", "high": "high"}


def _contains_phrase(text: str, phrase: str) -> bool:
    """Word-boundary aware phrase match to avoid false positives like 'unintentional' matching 'intentional'.

    For non-ASCII phrases (e.g. Chinese keywords like '核心数据结构'), Python's \\w matches Unicode
    characters, so (?!\\w) would fail when the keyword is immediately followed by another CJK
    character — which is always the case in Chinese text (no word-separating spaces).
    Use simple substring search for non-ASCII phrases; word-boundary regex for ASCII-only phrases.
    """
    if not text or not phrase:
        return False
    if not phrase.isascii():
        # Non-ASCII (CJK etc.): substring match is correct — Chinese text has no word separators
        return phrase in text
    pattern = r'(?<!\w)' + re.escape(phrase) + r'(?!\w)'
    return bool(re.search(pattern, text))


_NEGATION_RE = re.compile(
    r'\b(?:no|not|never|without|don\'t|doesn\'t|won\'t|cannot|can\'t)\s+$',
    re.IGNORECASE
)


def _matches_any(text: str, keywords: list) -> bool:
    return any(_contains_phrase(text, kw) for kw in keywords)


def _matches_welcome(text: str) -> bool:
    """Like _matches_any(text, WELCOME_KEYWORDS) but guards against negation prefixes.

    Prevents false positives such as "no pr welcome" or "not contributions welcome"
    being classified as a welcoming maintainer signal.  For each match position the
    20 characters immediately preceding the match are checked; if they end with a
    negation word the match is discarded.
    """
    if not text:
        return False
    lowered = text.lower()
    for kw in WELCOME_KEYWORDS:
        # WELCOME_KEYWORDS are all ASCII — use word-boundary regex
        pattern = r'(?<!\w)' + re.escape(kw) + r'(?!\w)'
        for m in re.finditer(pattern, lowered):
            prefix = lowered[max(0, m.start() - 20):m.start()]
            if _NEGATION_RE.search(prefix):
                continue  # negated phrase — skip
            return True
    return False


def _extract_explicit_difficulty(why_hard):
    """Parse explicit difficulty hints written by the LLM in why_hard.

    Examples: "Hard because: ...", "Medium difficulty", "straightforward change".
    Returns 'high', 'medium', 'low', or None.
    """
    if not why_hard:
        return None
    text = why_hard.lower()

    high_hints = ["hard because", "high difficulty", "very difficult", "challenging"]
    for hint in high_hints:
        pattern = r'(?<!\w)' + re.escape(hint) + r'(?!\w)'
        for m in re.finditer(pattern, text):
            prefix = text[max(0, m.start() - 20):m.start()]
            if not _NEGATION_RE.search(prefix):
                return "high"

    medium_hints = ["medium because", "moderate", "medium difficulty"]
    for hint in medium_hints:
        pattern = r'(?<!\w)' + re.escape(hint) + r'(?!\w)'
        for m in re.finditer(pattern, text):
            prefix = text[max(0, m.start() - 20):m.start()]
            if not _NEGATION_RE.search(prefix):
                return "medium"

    low_hints = ["low because", "low difficulty", "straightforward", "simple change"]
    for hint in low_hints:
        pattern = r'(?<!\w)' + re.escape(hint) + r'(?!\w)'
        for m in re.finditer(pattern, text):
            prefix = text[max(0, m.start() - 20):m.start()]
            if not _NEGATION_RE.search(prefix):
                return "low"

    return None


def _to_bool(v) -> bool:
    """Coerce an evidence bool field to Python bool.
    LLM may write strings like 'unknown'/'unclear'/'maybe'/'possibly'/'partial' which should
    all be treated as False (no confirmed signal). Only explicit affirmative strings (not in
    the exclusion set) are treated as True — e.g. 'yes', 'true', 'True', '1'."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() not in (
            "false", "0", "no", "null", "none",
            # uncertainty / hedging phrases LLM commonly outputs
            "unknown", "unclear", "n/a", "maybe", "possibly", "partial",
            "not sure", "uncertain", "depends", "sometimes", "likely", "probably",
            "",
        )
    return bool(v)


# ── 规则函数 ──────────────────────────────────────────────────────────────────

def _to_list(v) -> list:
    """Coerce a value to list; non-list types (str, int, None) become []."""
    return v if isinstance(v, list) else []


def score_maintainer_signal(me: dict) -> str:
    similar_prs    = _to_list(me.get("similar_prs"))
    welcome_labels = _to_list(me.get("welcome_labels"))
    responses      = _to_list(me.get("maintainer_responses"))

    signals = []
    for pr in similar_prs:
        if not isinstance(pr, dict):
            continue
        raw_age = pr.get("age_days")  # None 表示 LLM 未填，保守地不过滤
        try:
            age = int(raw_age) if raw_age is not None else None
        except (ValueError, TypeError):
            age = None
        if age is not None and age > PR_AGE_DAYS:
            continue
        comment = (pr.get("maintainer_comment") or "").lower()
        age_for_sort = age if age is not None else 9999
        if _to_bool(pr.get("merged")):
            signals.append(("welcoming", age_for_sort))
        elif _matches_any(comment, REJECT_KEYWORDS):
            signals.append(("rejected", age_for_sort))

    for resp in responses:
        if not isinstance(resp, dict):
            continue
        body = (resp.get("body_quote") or "").lower()
        # Use independent `if` (not `elif`) so a body containing both welcome and reject
        # keywords produces two signals.  The final sort gives rejected higher priority
        # (PRIORITY=0 < welcoming=1), so the correct outcome still surfaces even when
        # both signals are present in the same response.
        if _matches_welcome(body):
            signals.append(("welcoming", 0))
        if _matches_any(body, REJECT_KEYWORDS):
            signals.append(("rejected", 0))

    _WELCOME_LABELS = {"help wanted", "help-wanted", "good first issue", "good-first-issue",
                       "enhancement", "feature-request", "feature request", "accepted",
                       "pr welcome", "contributions welcome"}
    if any(isinstance(lbl, str) and lbl.lower() in _WELCOME_LABELS for lbl in welcome_labels):
        signals.append(("welcoming", 0))

    if not signals:
        return "unknown"
    # 优先级：rejected > welcoming；同类型内取最新（age_days 最小）
    _PRIORITY = {"rejected": 0, "welcoming": 1}
    signals.sort(key=lambda x: (_PRIORITY.get(x[0], 2), x[1]))
    return signals[0][0]


def _clean_url(raw) -> str:
    """Normalize a URL field: treat None, empty string, and LLM placeholder strings as absent."""
    if not raw:
        return ""
    s = str(raw).strip()
    # LLM 常见无效占位符：null/none/n/a/unknown/—/- 以及以 "https://github.com/..." 结尾的模板字符串
    if s.lower() in ("null", "none", "n/a", "unknown", "—", "-", ""):
        return ""
    # 模板未填写（含尖括号占位符，如 "<canonical_impl_url>"）
    if s.startswith("<") and s.endswith(">"):
        return ""
    return s


def _project_is_adopted(stars, canonical_url):
    """判断项目是否具备基本 adoption/生态价值。

    标准：
    - stars >= PROJECT_ADOPTION_STARS，或
    - 有已知的 canonical_url（说明是知名框架的移植/替代实现）
    """
    try:
        if stars is not None and int(stars) >= PROJECT_ADOPTION_STARS:
            return True
    except (ValueError, TypeError):
        pass
    return bool(_clean_url(canonical_url))


def score_value(ve: dict, signal: str, source_type: str = "", project_adopted: bool = False) -> str:
    canonical_url = _clean_url(ve.get("canonical_impl_url"))
    try:
        reactions = int(ve.get("issue_reactions") or 0)
    except (ValueError, TypeError):
        reactions = 0

    if not canonical_url:
        # 无原版参照：高呼声 issue 仍可达 medium，welcoming 可再上调
        base = "medium" if reactions >= REACTIONS_HIGH else "low"
    elif reactions >= REACTIONS_HIGH:
        # 原版有实现 + 高呼声 → high
        base = "high"
    else:
        # 原版有实现，低呼声 → medium
        base = "medium"

    if signal == "welcoming":
        base = LEVEL_UP[base]

    # security / issue / performance 类若真实影响生产环境且项目具备 adoption，value 不应低于 medium
    if source_type in ("security", "issue", "performance") and project_adopted:
        has_prod = _to_bool(ve.get("has_prod_signal"))
        if has_prod and base == "low":
            base = "medium"

    return base


def score_difficulty(de: dict) -> str:
    canonical_url = _clean_url(de.get("canonical_impl_url"))
    try:
        loc = int(de.get("canonical_impl_loc") or 0)
    except (ValueError, TypeError):
        loc = 0
    why_hard       = (de.get("why_hard") or "").lower()
    approach_file  = (de.get("target_approach_file") or "").lower()

    has_hard = _matches_any(why_hard, HARD_KEYWORDS)
    has_easy = _matches_any(why_hard, EASY_KEYWORDS)
    explicit = _extract_explicit_difficulty(why_hard)

    if canonical_url:
        # loc=0 表示"未能确定行数"（analyze.md 规定无法确定时填 0），
        # 不能当作"很短的实现"处理，保守地视为 medium。
        # loc<0 属于无效值（LLM 写入错误），同样保守地视为 medium（未知行数）。
        if loc <= 0:
            base = "medium"
        elif loc > LOC_HIGH:
            base = "high"
        elif loc >= LOC_MEDIUM:
            base = "medium"
        else:
            base = "low"
    else:
        # 无 canonical 参考时，根据 why_hard / approach_file / 显式提示做更细粒度判断
        if has_hard or explicit == "high":
            base = "high"
        elif has_easy or approach_file or explicit == "medium":
            base = "medium"
        elif explicit == "low":
            base = "low"
        else:
            base = "high"  # 信息不足，保守处理

    if has_easy and base != "low":
        base = {"high": "medium", "medium": "low", "low": "low"}[base]
    if has_hard:
        base = LEVEL_UP[base]

    # LLM 在 why_hard 里写的显式难度提示（如 "Hard because"）是强信号
    if explicit == "high":
        base = LEVEL_UP[base]
    elif explicit == "medium" and base == "low":
        base = "medium"
    elif explicit == "low" and base == "high":
        base = "medium"

    return base


def score_urgency(ue: dict, source_type: str = "") -> str:
    cve = ue.get("cve_id")
    if cve and str(cve).lower() not in ("null", "none", "0", "n/a", "unknown", ""):
        return "high"
    # security 类即使无 CVE 也视为 high（analyze.md 评分标准：security 类 → high urgency）
    if source_type == "security":
        return "high"

    has_prod   = _to_bool(ue.get("has_prod_signal"))
    has_around = _to_bool(ue.get("has_workaround"))
    # performance 类有生产信号 → high，无论是否有 workaround（workaround 只是临时方案）
    if source_type == "performance" and has_prod:
        return "high"
    if has_prod and not has_around:
        return "high"
    if has_prod and has_around:
        return "medium"
    if not has_prod and has_around:
        return "medium"  # 功能缺失但有 workaround
    return "low"


# ── 主流程 ────────────────────────────────────────────────────────────────────

def run():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        rows = conn.execute("""
            SELECT o.id, o.project_id, o.source_type,
                   o.value_evidence, o.difficulty_evidence,
                   o.urgency_evidence, o.maintainer_evidence,
                   p.stars AS project_stars,
                   m.canonical_url AS project_canonical_url
            FROM opportunities o
            JOIN projects p ON p.id = o.project_id
            LEFT JOIN project_meta m ON m.project_id = o.project_id
            WHERE o.value IS NULL AND o.status = 'open'
        """).fetchall()

        print(f"待评分机会点：{len(rows)} 个")

        scored = 0
        for row in rows:
            try:
                ve = json.loads(row["value_evidence"]      or "{}")
                de = json.loads(row["difficulty_evidence"] or "{}")
                ue = json.loads(row["urgency_evidence"]    or "{}")
                me = json.loads(row["maintainer_evidence"] or "{}")
            except (json.JSONDecodeError, ValueError):
                print(f"  SKIP {row['id']}: evidence JSON 解析失败")
                continue
            # Ensure all evidence fields are dicts; non-dict valid JSON (list, str, int) → {}
            if not isinstance(ve, dict): ve = {}
            if not isinstance(de, dict): de = {}
            if not isinstance(ue, dict): ue = {}
            if not isinstance(me, dict): me = {}

            try:
                project_adopted = _project_is_adopted(
                    row["project_stars"], row["project_canonical_url"]
                )
                signal     = score_maintainer_signal(me)
                value      = score_value(ve, signal, row["source_type"] or "", project_adopted)
                difficulty = score_difficulty(de)
                urgency    = score_urgency(ue, row["source_type"] or "")
                status     = "obsolete" if signal == "rejected" else "open"
            except Exception as e:
                print(f"  SKIP {row['id']}: 评分计算异常 {e}")
                continue

            try:
                conn.execute("""
                    UPDATE opportunities
                    SET value=?, difficulty=?, urgency=?, maintainer_signal=?, status=?
                    WHERE id=?
                """, (value, difficulty, urgency, signal, status, row["id"]))
            except Exception as e:
                print(f"  SKIP {row['id']}: 写库失败 {e}")
                continue

            print(f"  [{row['id']}] {row['source_type']} "
                  f"value={value} difficulty={difficulty} urgency={urgency} signal={signal}")

            scored += 1
            # 每 100 条批量提交一次：避免进程意外终止（SIGKILL/OOM）导致全量回滚
            if scored % 100 == 0:
                conn.commit()

        conn.commit()  # 提交最后一批（不足 100 条的尾部）
    finally:
        conn.close()
    print("评分完成")


if __name__ == "__main__":
    run()
