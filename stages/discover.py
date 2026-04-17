#!/usr/bin/env python3
"""Stage 1: 多源发现候选项目，写入 projects 表和 discovery_log 表。"""
from __future__ import annotations
import os, json, time, sqlite3, argparse, re
from datetime import datetime, timezone, timedelta
import requests

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'pipeline.db')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
HEADERS = {'Accept': 'application/vnd.github+json'}
if GITHUB_TOKEN:
    HEADERS['Authorization'] = f'Bearer {GITHUB_TOKEN}'

STAR_MIN, STAR_MAX = 300, 15000
STALE_DAYS = 180

TOPICS = [
    "microservices", "rate-limiting", "circuit-breaker",
    "job-scheduler", "service-discovery", "message-queue",
    "distributed-tracing", "orm", "cache", "workflow",
    "rpc", "configuration", "load-balancer", "actor-model",
    "distributed-lock", "task-queue", "event-driven"
]
LANGUAGES = ["Go", "Rust", "Python", "TypeScript"]

TRENDING_LANGUAGES = ["go", "rust", "python", "typescript"]
TRENDING_PERIODS = ["weekly", "monthly"]

ECOSYSTEMS = [
    "apache", "alibaba", "cloudwego", "go-kratos", "asynkron",
    "nats-io", "connectrpc", "temporal-io", "cadence-workflow", "uber-go",
]

ANCHORS = [
    {"name": "Apache Sentinel",   "lang": "Java",   "keywords": ["sentinel", "rate-limit", "circuit-breaker"]},
    {"name": "Resilience4j",      "lang": "Java",   "keywords": ["resilience4j", "circuit-breaker", "retry"]},
    {"name": "Hystrix",           "lang": "Java",   "keywords": ["hystrix", "circuit-breaker"]},
    {"name": "Failsafe",          "lang": "Java",   "keywords": ["failsafe", "retry", "circuit-breaker"]},
    {"name": "Bucket4j",          "lang": "Java",   "keywords": ["bucket4j", "rate-limit", "token-bucket"]},
    {"name": "Guava RateLimiter", "lang": "Java",   "keywords": ["rate-limiter", "token-bucket", "leaky-bucket"]},
    {"name": "Apache Dubbo",      "lang": "Java",   "keywords": ["dubbo", "rpc"]},
    {"name": "Apache Thrift",     "lang": "C++",    "keywords": ["thrift", "rpc"]},
    {"name": "Tars",              "lang": "C++",    "keywords": ["tars", "tarscpp", "rpc"]},
    {"name": "SOFARPC",           "lang": "Java",   "keywords": ["sofarpc", "rpc"]},
    {"name": "Finagle",           "lang": "Scala",  "keywords": ["finagle", "rpc"]},
    {"name": "Cap'n Proto",       "lang": "C++",    "keywords": ["capnproto", "capnp", "rpc"]},
    {"name": "Akka",              "lang": "Scala",  "keywords": ["akka", "actor"]},
    {"name": "Erlang/OTP",        "lang": "Erlang", "keywords": ["erlang", "otp", "actor", "gen-server"]},
    {"name": "Microsoft Orleans", "lang": "C#",     "keywords": ["orleans", "virtual-actor", "grain"]},
    {"name": "Proto.Actor",       "lang": "C#",     "keywords": ["proto-actor", "protoactor"]},
    {"name": "Quartz Scheduler",  "lang": "Java",   "keywords": ["quartz", "job-scheduler", "cron"]},
    {"name": "XXL-JOB",           "lang": "Java",   "keywords": ["xxl-job", "distributed-job"]},
    {"name": "Elastic-Job",       "lang": "Java",   "keywords": ["elastic-job", "shardingsphere-elasticjob"]},
    {"name": "Airflow",           "lang": "Python", "keywords": ["airflow", "dag", "workflow-scheduler"]},
    {"name": "Prefect",           "lang": "Python", "keywords": ["prefect", "workflow", "dataflow"]},
    {"name": "Temporal",          "lang": "Go",     "keywords": ["temporal", "workflow", "durable-execution"]},
    {"name": "Cadence",           "lang": "Go",     "keywords": ["cadence", "workflow", "uber"]},
    {"name": "Camunda",           "lang": "Java",   "keywords": ["camunda", "workflow", "bpmn"]},
    {"name": "Activiti",          "lang": "Java",   "keywords": ["activiti", "workflow", "bpmn"]},
    {"name": "Flowable",          "lang": "Java",   "keywords": ["flowable", "workflow", "bpmn"]},
    {"name": "Drools",            "lang": "Java",   "keywords": ["drools", "rule-engine", "kie"]},
    {"name": "Easy Rules",        "lang": "Java",   "keywords": ["easy-rules", "rule-engine"]},
    {"name": "Caffeine Cache",    "lang": "Java",   "keywords": ["caffeine", "local-cache"]},
    {"name": "Hazelcast",         "lang": "Java",   "keywords": ["hazelcast", "distributed-cache", "imdg"]},
    {"name": "Ehcache",           "lang": "Java",   "keywords": ["ehcache", "cache"]},
    {"name": "JetCache",          "lang": "Java",   "keywords": ["jetcache", "multilevel-cache"]},
    {"name": "Spring Cache",      "lang": "Java",   "keywords": ["spring-cache", "cache-abstraction"]},
    {"name": "MyBatis",           "lang": "Java",   "keywords": ["mybatis", "orm", "sql-mapper"]},
    {"name": "Hibernate",         "lang": "Java",   "keywords": ["hibernate", "orm", "jpa"]},
    {"name": "jOOQ",              "lang": "Java",   "keywords": ["jooq", "sql-builder", "type-safe-sql"]},
    {"name": "JDBI",              "lang": "Java",   "keywords": ["jdbi", "sql", "fluent"]},
    {"name": "SQLAlchemy",        "lang": "Python", "keywords": ["sqlalchemy", "orm"]},
    {"name": "Apache RocketMQ",   "lang": "Java",   "keywords": ["rocketmq", "message-queue"]},
    {"name": "Apache Pulsar",     "lang": "Java",   "keywords": ["pulsar", "message-queue", "streaming"]},
    {"name": "Kafka Streams",     "lang": "Java",   "keywords": ["kafka-streams", "stream-processing"]},
    {"name": "Celery",            "lang": "Python", "keywords": ["celery", "task-queue", "distributed-task"]},
    {"name": "Flink",             "lang": "Java",   "keywords": ["flink", "stream-processing", "datastream"]},
    {"name": "Apollo Config",     "lang": "Java",   "keywords": ["apollo", "config-center", "apolloconfig"]},
    {"name": "Nacos",             "lang": "Java",   "keywords": ["nacos", "service-discovery", "config"]},
    {"name": "Spring Cloud Config","lang": "Java",  "keywords": ["spring-config", "config-server"]},
    {"name": "Consul",            "lang": "Go",     "keywords": ["consul", "service-discovery", "kv-store"]},
    {"name": "Spring Cloud",      "lang": "Java",   "keywords": ["spring-cloud", "microservices"]},
    {"name": "Micronaut",         "lang": "Java",   "keywords": ["micronaut", "microservices"]},
    {"name": "Quarkus",           "lang": "Java",   "keywords": ["quarkus", "microservices"]},
    {"name": "Vert.x",            "lang": "Java",   "keywords": ["vertx", "reactive", "microservices"]},
    {"name": "ServiceComb",       "lang": "Java",   "keywords": ["servicecomb", "java-chassis", "microservices"]},
    {"name": "Apache SkyWalking", "lang": "Java",   "keywords": ["skywalking", "apm", "tracing"]},
    {"name": "Zipkin",            "lang": "Java",   "keywords": ["zipkin", "distributed-tracing"]},
    {"name": "Pinpoint",          "lang": "Java",   "keywords": ["pinpoint", "apm", "tracing"]},
    {"name": "Seata",             "lang": "Java",   "keywords": ["seata", "distributed-transaction", "saga"]},
    {"name": "Atomikos",          "lang": "Java",   "keywords": ["atomikos", "distributed-transaction", "xa"]},
    {"name": "Alibaba Canal",     "lang": "Java",   "keywords": ["canal", "binlog", "cdc", "mysql-replication"]},
    {"name": "Debezium",          "lang": "Java",   "keywords": ["debezium", "cdc", "change-data-capture"]},
]


def rule_filter(repo: dict) -> tuple[bool, str]:
    """返回 (should_skip, reason)。"""
    stale_cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_DAYS)
    pushed = repo.get('pushed_at', '') or ''
    stars = repo.get('stargazers_count', 0)
    if stars < STAR_MIN:
        return True, f"stars_too_few:{stars}"
    if stars > STAR_MAX:
        return True, f"stars_too_many:{stars}"
    if repo.get('archived'):
        return True, "archived"
    if pushed:
        try:
            pushed_dt = datetime.fromisoformat(pushed.replace('Z', '+00:00'))
            if pushed_dt.tzinfo is None:
                pushed_dt = pushed_dt.replace(tzinfo=timezone.utc)
            if pushed_dt < stale_cutoff:
                return True, f"stale_since:{pushed[:10]}"
        except (ValueError, TypeError):
            pass  # 格式异常时保守地不过滤
    # open_issues_count 包含 PR 数，纯 0 才过滤；has_issues=False 说明关闭了 Issues 功能，不过滤
    if repo.get('open_issues_count', 0) == 0 and repo.get('has_issues', True):
        return True, "no_open_issues"
    if repo.get('fork'):
        return True, "is_fork"
    return False, ""


def gh_search(query: str, per_page: int = 30) -> list[dict]:
    """调用 GitHub Search Repositories API，自动处理限流。"""
    url = "https://api.github.com/search/repositories"
    params = {"q": query, "sort": "stars", "order": "desc", "per_page": per_page}
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=15)
        if r.status_code == 429 or r.status_code == 403:
            reason = r.json().get('message', '') if r.headers.get('content-type', '').startswith('application/json') else ''
            print(f"  rate_limited({r.status_code}): {query[:60]}" + (f" — {reason}" if reason else ""))
            time.sleep(60)  # 触发限流后等待 60 秒再继续，避免后续请求连续命中限流
            return []
        r.raise_for_status()
        time.sleep(2)  # Search API: 30 req/min
        return r.json().get('items', [])
    except Exception as e:
        print(f"  search_error: {e}")
        return []


def discover_topics(dry_run: bool) -> list[dict]:
    """渠道1: GitHub Topics × Languages。"""
    results = []
    for topic in TOPICS:
        for lang in LANGUAGES:
            query = f"topic:{topic} language:{lang} stars:{STAR_MIN}..{STAR_MAX}"
            repos = gh_search(query)
            for repo in repos:
                skip, reason = rule_filter(repo)
                if not skip:
                    results.append({"repo": repo, "source": "github_topic",
                                    "signal": f"{topic}/{lang}"})
                elif dry_run:
                    print(f"  skip({reason}): {repo['full_name']}")
    return results


def discover_anchors(dry_run: bool) -> list[dict]:
    """渠道4: 原版锚点反向发现。"""
    results = []
    for anchor in ANCHORS:
        for kw in anchor['keywords']:
            for lang in LANGUAGES:
                query = f"{kw} in:name,description language:{lang} stars:{STAR_MIN}..{STAR_MAX}"
                repos = gh_search(query, per_page=10)
                for repo in repos:
                    skip, reason = rule_filter(repo)
                    if not skip:
                        results.append({"repo": repo, "source": "anchor",
                                        "signal": f"{anchor['name']}/{kw}"})
                    elif dry_run:
                        print(f"  skip({reason}): {repo['full_name']}")
    return results


def discover_trending(dry_run: bool) -> list[dict]:
    """渠道2: GitHub Trending（HTML 解析）。"""
    # GitHub 非 repo 路径的一级前缀，用于过滤导航/功能页链接
    _NON_REPO_PREFIXES = {
        "features", "marketplace", "login", "logout", "settings", "explore",
        "notifications", "issues", "pulls", "sponsors", "about", "pricing",
        "enterprise", "topics", "collections", "events", "apps", "contact",
        "security", "organizations", "new", "codespaces", "copilot",
    }

    results = []
    for lang in TRENDING_LANGUAGES:
        for period in TRENDING_PERIODS:
            url = f"https://github.com/trending/{lang}?since={period}"
            try:
                r = requests.get(url, timeout=15)
                r.raise_for_status()
                # 提取所有 /owner/repo 形式的链接，去重后过滤非 repo 路径
                raw = re.findall(r'href="/([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)"', r.text)
                seen: set[str] = set()
                repo_names: list[str] = []
                for full_name in raw:
                    if full_name in seen:
                        continue
                    seen.add(full_name)
                    owner = full_name.split("/")[0]
                    if owner in _NON_REPO_PREFIXES:
                        continue
                    repo_names.append(full_name)
                    if len(repo_names) >= 25:
                        break

                if not repo_names:
                    print(f"  WARN: trending {lang}/{period} 解析到 0 个项目，HTML 结构可能已变化")
                    continue
                for full_name in repo_names:
                    api_url = f"https://api.github.com/repos/{full_name}"
                    try:
                        rr = requests.get(api_url, headers=HEADERS, timeout=10)
                        if rr.status_code in (429, 403):
                            time.sleep(60)
                            continue
                        if rr.status_code != 200:
                            continue
                        repo = rr.json()
                        skip, reason = rule_filter(repo)
                        if not skip:
                            results.append({"repo": repo, "source": "trending",
                                            "signal": f"{lang}/{period}"})
                    except Exception:
                        pass
                    time.sleep(0.5)  # 每个 repo API 请求后 sleep，避免触发 rate limit
            except Exception as e:
                print(f"  trending_error {lang}/{period}: {e}")
    return results


def discover_ecosystem(dry_run: bool) -> list[dict]:
    """渠道3: 知名 org 下的子项目。"""
    results = []
    for org in ECOSYSTEMS:
        page = 1
        while True:
            url = f"https://api.github.com/orgs/{org}/repos"
            params = {"per_page": 100, "type": "public", "sort": "updated", "page": page}
            try:
                r = requests.get(url, headers=HEADERS, params=params, timeout=15)
                if r.status_code in (429, 403):
                    print(f"  ecosystem_rate_limited({r.status_code}): {org} page={page}, sleeping 60s")
                    time.sleep(60)
                    break  # skip remaining pages of this org to avoid hammering the API
                r.raise_for_status()
                repos = r.json()
                if not repos:
                    break
                for repo in repos:
                    skip, reason = rule_filter(repo)
                    if not skip:
                        results.append({"repo": repo, "source": "ecosystem",
                                        "signal": org})
                if len(repos) < 100:
                    break  # 最后一页
                page += 1
                time.sleep(0.5)
            except Exception as e:
                print(f"  ecosystem_error {org} page={page}: {e}")
                break
    return results


def upsert_project(conn: sqlite3.Connection, repo: dict, source: str, signal: str, dry_run: bool):
    if dry_run:
        print(f"  [dry] upsert {repo['full_name']} (source={source})")
        return

    now = datetime.now(timezone.utc).isoformat()
    project_id = repo['full_name']
    topics = json.dumps(repo.get('topics') or [])
    release = None
    release_at = None
    # 尝试获取最新 release（429/403 时跳过，不阻塞写库）
    try:
        rr = requests.get(f"https://api.github.com/repos/{project_id}/releases/latest",
                          headers=HEADERS, timeout=10)
        if rr.status_code == 200:
            rel = rr.json()
            release = rel.get('tag_name')
            release_at = rel.get('published_at')
            time.sleep(0.3)
        elif rr.status_code in (429, 403):
            time.sleep(60)  # rate limited — back off before next upsert
        # 404 and other errors: skip silently, no sleep needed
    except Exception:
        pass

    conn.execute("""
        INSERT INTO projects (id, name, url, language, stars, open_issues,
            last_commit_at, latest_release, latest_release_at, topics,
            description, archived, source, status, first_seen_at,
            prev_stars, prev_open_issues, last_fetched_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'discovered',?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            -- prev_* 不由 discover 更新：discover 每天运行，若每天都刷新 prev_*，
            -- schedule.py 看到的 delta 只是"昨天到今天"的变化，而非"上次分析到今天"。
            -- prev_* 由 analyze.md 在任务完成时更新（Step 7 完成标记后），作为分析基准快照。
            -- 首次插入时 prev_* 为 NULL（VALUES 中传 NULL），触发 schedule.py 的 first_active 逻辑。
            prev_stars       = projects.prev_stars,
            prev_open_issues = projects.prev_open_issues,
            stars            = excluded.stars,
            open_issues      = excluded.open_issues,
            archived         = excluded.archived,
            last_commit_at   = excluded.last_commit_at,
            latest_release    = COALESCE(excluded.latest_release,    projects.latest_release),
            latest_release_at = COALESCE(excluded.latest_release_at, projects.latest_release_at),
            last_fetched_at  = excluded.last_fetched_at,
            name             = excluded.name,
            url              = excluded.url,
            language         = excluded.language,
            description      = excluded.description,
            topics           = excluded.topics,
            -- source 按优先级升级：anchor(0) > ecosystem(1) > github_topic(2) > trending(3)
            -- 只有新来源优先级更高时才覆盖，避免低优先级渠道降级已有高优先级记录
            source           = CASE
                WHEN excluded.source = 'anchor'                                        THEN 'anchor'
                WHEN excluded.source = 'ecosystem'   AND projects.source != 'anchor'   THEN 'ecosystem'
                WHEN excluded.source = 'github_topic' AND projects.source NOT IN ('anchor','ecosystem') THEN 'github_topic'
                ELSE projects.source
            END
    """, (
        project_id, repo.get('name'), repo.get('html_url'),
        repo.get('language'), repo.get('stargazers_count'),
        repo.get('open_issues_count'), repo.get('pushed_at'),
        release, release_at, topics, repo.get('description'),
        1 if repo.get('archived') else 0,
        source, now, None, None, now
    ))
    conn.execute("""
        INSERT INTO project_meta (project_id, filter_status)
        VALUES (?, 'pending')
        ON CONFLICT(project_id) DO NOTHING
    """, (project_id,))
    conn.execute("""
        INSERT INTO discovery_log (project_id, source, raw_signal, discovered_at)
        VALUES (?, ?, ?, ?)
    """, (project_id, source, signal, now))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    all_results = []
    print("渠道1: Topics...")
    all_results += discover_topics(args.dry_run)
    print("渠道2: Trending...")
    all_results += discover_trending(args.dry_run)
    print("渠道3: Ecosystem...")
    all_results += discover_ecosystem(args.dry_run)
    print("渠道4: Anchors...")
    all_results += discover_anchors(args.dry_run)

    print(f"\n发现候选项目（去重前）: {len(all_results)}")

    # 按 project_id 去重：同一项目保留优先级最高的渠道（anchor > ecosystem > github_topic > trending）
    _SOURCE_PRIORITY: dict[str, int] = {"anchor": 0, "ecosystem": 1, "github_topic": 2, "trending": 3}
    seen_ids: dict[str, dict] = {}
    for item in all_results:
        pid = item['repo']['full_name']
        new_pri = _SOURCE_PRIORITY.get(item['source'], 99)
        if pid not in seen_ids or new_pri < _SOURCE_PRIORITY.get(seen_ids[pid]['source'], 99):
            seen_ids[pid] = item

    print(f"发现候选项目（去重后）: {len(seen_ids)}")

    if not args.dry_run:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH)
            for i, item in enumerate(seen_ids.values(), 1):
                upsert_project(conn, item['repo'], item['source'], item['signal'], False)
                if i % 100 == 0:
                    conn.commit()
            conn.commit()
        finally:
            if conn is not None:
                conn.close()


if __name__ == '__main__':
    main()
