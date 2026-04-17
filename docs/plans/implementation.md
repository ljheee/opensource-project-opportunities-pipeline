# GitHub 开源机会分析 Pipeline 实现计划

**For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps
use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个自动化 pipeline，每天发现 GitHub 上规模适中的开源项目，识别当前语言版本相对原版的功能差距，输出切实可行的贡献机会。

**Architecture:** GH Actions 负责 Stage 1（多源发现）和 Stage 2（调度决策），每天 UTC 01:00 自动运行并将结果 commit 回 repo；本地 Mac 手动运行 run.sh / run_bulk.sh，通过 `claude
--dangerously-skip-permissions` 执行 Stage 3（语义过滤）和 Stage 4（深层分析），最后 Stage 5 生成 Markdown 报告。SQLite 是唯一数据源，Markdown 报告是派生输出。

**Tech Stack:** Python 3.12, SQLite (sqlite3 内置), GitHub REST API (PyGitHub / requests), GitHub Actions, claude CLI (`--dangerously-skip-permissions`)

---

### Task 1: 项目初始化 + SQLite Schema

**Files:**
- Create: `pipeline/stages/__init__.py`
- Create: `pipeline/stages/init_db.py`
- Create: `pipeline/requirements.txt`
- Test: 运行 `python pipeline/stages/init_db.py` 后验证表结构

- [ ] **Step 1: 创建目录结构**

```bash
mkdir -p pipeline/stages pipeline/prompts pipeline/data/reports pipeline/.github/workflows
touch pipeline/stages/__init__.py
```

- [ ] **Step 2: 创建 requirements.txt**

```
requests==2.31.0
PyGitHub==2.3.0
```

- [ ] **Step 3: 编写 init_db.py**

```python
#!/usr/bin/env python3
"""初始化 SQLite 数据库，创建所有表。幂等：已存在的表不会被删除。"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'pipeline.db')

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id              TEXT PRIMARY KEY,
    name            TEXT,
    url             TEXT,
    language        TEXT,
    stars           INTEGER,
    open_issues     INTEGER,
    last_commit_at  TEXT,
    latest_release  TEXT,
    latest_release_at TEXT,
    topics          TEXT,
    description     TEXT,
    archived        INTEGER DEFAULT 0,
    source          TEXT,
    status          TEXT DEFAULT 'discovered',
    first_seen_at   TEXT,
    prev_stars       INTEGER,
    prev_open_issues INTEGER,
    last_fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS project_meta (
    project_id      TEXT PRIMARY KEY,
    canonical_name  TEXT,
    canonical_lang  TEXT,
    canonical_url   TEXT,
    canonical_stars INTEGER,
    peer_versions   TEXT,
    filter_status   TEXT DEFAULT 'pending',
    filter_reason   TEXT,
    filtered_at     TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      TEXT,
    task_date       TEXT,
    task_type       TEXT,
    trigger_reason  TEXT,
    status          TEXT DEFAULT 'pending',
    created_at      TEXT,
    started_at      TEXT,
    finished_at     TEXT
);

CREATE TABLE IF NOT EXISTS analyses (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       TEXT,
    task_id          INTEGER,
    analyzed_at      TEXT,
    release_version  TEXT,
    source_structure TEXT,
    canonical_gap    TEXT,
    peer_comparison  TEXT,
    overall_score    INTEGER
);

CREATE TABLE IF NOT EXISTS opportunities (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       TEXT,
    task_id          INTEGER,
    source_type      TEXT,
    source_ref       TEXT,
    title            TEXT,
    description      TEXT,
    canonical_status TEXT,
    peer_status      TEXT,
    value            TEXT,
    difficulty       TEXT,
    urgency          TEXT,
    impl_hint        TEXT,
    issue_number     INTEGER,
    issue_reactions  INTEGER,
    has_linked_pr    INTEGER,
    value_evidence       TEXT,
    difficulty_evidence  TEXT,
    urgency_evidence     TEXT,
    maintainer_evidence  TEXT,
    maintainer_note   TEXT,
    status           TEXT DEFAULT 'open',
    first_seen_at    TEXT,
    UNIQUE(project_id, source_type, source_ref)
);

CREATE TABLE IF NOT EXISTS discovery_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    TEXT,
    source        TEXT,
    raw_signal    TEXT,
    discovered_at TEXT
);
"""

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    print(f"DB initialized: {DB_PATH}")

if __name__ == '__main__':
    init_db()
```

- [ ] **Step 4: 运行并验证**

```bash
cd /path/to/github-opportunities
python pipeline/stages/init_db.py
sqlite3 pipeline/data/pipeline.db ".tables"
```

期望输出：`analyses  discovery_log  opportunities  project_meta  projects  tasks`

- [ ] **Step 5: Commit**

```bash
git add pipeline/stages/ pipeline/requirements.txt
git commit -m "feat: init pipeline project structure and SQLite schema"
```

---                                      
                                                                                                                                                                                    
### Task 2: discover.py — 多源发现候选项目                                                                                                                                        
                                                                                                                                                                                    
**Files:**                                                                                                                                                                          
- Create: `pipeline/stages/discover.py`                                                                                                                                             
- Test: `python pipeline/stages/discover.py --dry-run` 打印发现项目数，不写库                                                                                                       
                                                                                                                                                                                    
- [ ] **Step 1: 编写 discover.py 框架 + 常量定义**                                     
                                                                                                                                                                                    
```python                                                                              
#!/usr/bin/env python3     
"""Stage 1: 多源发现候选项目，写入 projects 表和 discovery_log 表。"""                                                                                                              
import os, json, time, sqlite3, argparse                                                                                                                                            
from datetime import datetime, timezone, timedelta                                                                                                                                  
import requests                                                                                                                                                                     
                                                                                       
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'pipeline.db')                                                                                                      
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')                                                                                                                                   
HEADERS = {'Authorization': f'token {GITHUB_TOKEN}', 'Accept': 'application/vnd.github+json'} if GITHUB_TOKEN else {}                                                               
                                                                                                                                                                                    
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
                                                                                                                                                                                    
- Step 2: 实现规则预过滤函数                                                                                                                                                        
                                                                                                                                                                                    
```python
def rule_filter(repo: dict) -> tuple[bool, str]:                                                                                                                                    
    """返回 (should_skip, reason)。"""                                                                                                                                              
    stale_cutoff = (datetime.now(timezone.utc) - timedelta(days=STALE_DAYS)).isoformat()                                                                                            
    pushed = repo.get('pushed_at', '') or ''                                                                                                                                        
    if repo.get('stargazers_count', 0) < STAR_MIN:                                                                                                                                  
        return True, f"stars_too_few:{repo['stargazers_count']}"                                                                                                                    
    if repo.get('stargazers_count', 0) > STAR_MAX:                                                                                                                                  
        return True, f"stars_too_many:{repo['stargazers_count']}"                                                                                                                   
    if repo.get('archived'):                                                                                                                                                        
        return True, "archived"                                                                                                                                                     
    if pushed and pushed < stale_cutoff:                                                                                                                                            
        return True, f"stale_since:{pushed[:10]}"                                                                                                                                   
    if repo.get('open_issues_count', 0) == 0:                                                                                                                                       
        return True, "no_open_issues"                                                                                                                                               
    if repo.get('fork'):                                                                                                                                                            
        return True, "is_fork"                                                                                                                                                      
    return False, ""                                                                                                                                                                
                                                                                                                                                                                    
```
- Step 3: 实现 GitHub Search API 调用（渠道1 + 渠道4）                                                                                                                              
                                                                                                                                                                                    
```python
def gh_search(query: str, per_page: int = 30) -> list[dict]:                                                                                                                        
    """调用 GitHub Search Repositories API，自动处理限流。"""                                                                                                                       
    url = "https://api.github.com/search/repositories"                                                                                                                              
    params = {"q": query, "sort": "stars", "order": "desc", "per_page": per_page}                                                                                                   
    try:                                                                                                                                                                            
        r = requests.get(url, headers=HEADERS, params=params, timeout=15)                                                                                                           
        if r.status_code == 429 or r.status_code == 403:                                                                                                                            
            print(f"  rate_limited: {query[:60]}")                                                                                                                                  
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
            query = f"topic:{topic} language:{lang}"                                                                                                                                
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
                query = f"{kw} in:name,description language:{lang}"                                                                                                                 
                repos = gh_search(query, per_page=10)                                                                                                                               
                for repo in repos:                                                                                                                                                  
                    skip, reason = rule_filter(repo)                                                                                                                                
                    if not skip:                                                                                                                                                    
                        results.append({"repo": repo, "source": "anchor",                                                                                                           
                                        "signal": f"{anchor['name']}/{kw}"})                                                                                                        
    return results                                                                                                                                                                  
                                                                                                                                                                                    
```
- Step 4: 实现 Trending 抓取（渠道2）和 Ecosystem 抓取（渠道3）                                                                                                                     
                                                                                                                                                                                    
```python
def discover_trending(dry_run: bool) -> list[dict]:                                                                                                                                 
    """渠道2: GitHub Trending（HTML 解析）。"""                                                                                                                                     
    results = []                                                                                                                                                                    
    for lang in TRENDING_LANGUAGES:                                                                                                                                                 
        for period in TRENDING_PERIODS:                                                                                                                                             
            url = f"https://github.com/trending/{lang}?since={period}"                                                                                                              
            try:                                                                                                                                                                    
                r = requests.get(url, timeout=15)                                                                                                                                   
                r.raise_for_status()                                                                                                                                                
                # 从 HTML 提取 repo 链接: /owner/repo                                                                                                                               
                import re                                                                                                                                                           
                repos_found = re.findall(r'href="/([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)"', r.text)                                                                                      
                seen = set()                                                                                                                                                        
                for full_name in repos_found[:25]:                                                                                                                                  
                    if full_name in seen or '/' not in full_name:                                                                                                                   
                        continue                                                                                                                                                    
                    seen.add(full_name)                                                                                                                                             
                    # 获取详情                                                                                                                                                      
                    api_url = f"https://api.github.com/repos/{full_name}"                                                                                                           
                    try:                                                                                                                                                            
                        rr = requests.get(api_url, headers=HEADERS, timeout=10)                                                                                                     
                        if rr.status_code != 200:                                                                                                                                   
                            continue                                                                                                                                                
                        repo = rr.json()                                                                                                                                            
                        skip, reason = rule_filter(repo)                                                                                                                            
                        if not skip:                                                                                                                                                
                            results.append({"repo": repo, "source": "trending",                                                                                                     
                                            "signal": f"{lang}/{period}"})                                                                                                          
                    except Exception:                                                                                                                                               
                        pass                                                                                                                                                        
                time.sleep(1)                                                                                                                                                       
            except Exception as e:                                                                                                                                                  
                print(f"  trending_error {lang}/{period}: {e}")                                                                                                                     
    return results                                                                                                                                                                  
                                                                                                                                                                                    
def discover_ecosystem(dry_run: bool) -> list[dict]:                                                                                                                                
    """渠道3: 知名 org 下的子项目。"""                                                                                                                                              
    results = []                                                                                                                                                                    
    for org in ECOSYSTEMS:                                                                                                                                                          
        url = f"https://api.github.com/orgs/{org}/repos"                                                                                                                            
        params = {"per_page": 100, "type": "public", "sort": "updated"}                                                                                                             
        try:                                                                                                                                                                        
            r = requests.get(url, headers=HEADERS, params=params, timeout=15)                                                                                                       
            r.raise_for_status()                                                                                                                                                    
            for repo in r.json():                                                                                                                                                   
                skip, reason = rule_filter(repo)                                                                                                                                    
                if not skip:                                                                                                                                                        
                    results.append({"repo": repo, "source": "ecosystem",                                                                                                            
                                    "signal": org})                                                                                                                                 
            time.sleep(0.5)                                                                                                                                                         
        except Exception as e:                                                                                                                                                      
            print(f"  ecosystem_error {org}: {e}")                                                                                                                                  
    return results                                                                                                                                                                  
                                                                                                                                                                                    
```
- Step 5: 实现写库函数和 main 入口                                                                                                                                                  
                                                                                                                                                                                    
```python
def upsert_project(conn: sqlite3.Connection, repo: dict, source: str, signal: str, dry_run: bool):                                                                                  
    now = datetime.now(timezone.utc).isoformat()                                                                                                                                    
    project_id = repo['full_name']                                                                                                                                                  
    topics = json.dumps(repo.get('topics', []))                                                                                                                                     
    release = None                                                                                                                                                                  
    release_at = None                                                                                                                                                               
    # 尝试获取最新 release                                                                                                                                                          
    try:                                                                                                                                                                            
        rr = requests.get(f"https://api.github.com/repos/{project_id}/releases/latest",                                                                                             
                          headers=HEADERS, timeout=10)                                                                                                                              
        if rr.status_code == 200:                                                                                                                                                   
            rel = rr.json()                                                                                                                                                         
            release = rel.get('tag_name')                                                                                                                                           
            release_at = rel.get('published_at')                                                                                                                                    
    except Exception:                                                                                                                                                               
        pass                                                                                                                                                                        
                                                                                                                                                                                    
    if dry_run:                                                                                                                                                                     
        print(f"  [dry] upsert {project_id} (source={source})")                                                                                                                     
        return                                                                                                                                                                      
                                                                                                                                                                                    
    conn.execute("""                                                                                                                                                                
        INSERT INTO projects (id, name, url, language, stars, open_issues,                                                                                                          
            last_commit_at, latest_release, latest_release_at, topics,                                                                                                              
            description, source, status, first_seen_at, last_fetched_at)                                                                                                            
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'discovered',?,?)                                                                                                                           
        ON CONFLICT(id) DO UPDATE SET                                                                                                                                               
            stars=excluded.stars,                                                                                                                                                   
            open_issues=excluded.open_issues,                                                                                                                                       
            last_commit_at=excluded.last_commit_at,                                                                                                                                 
            latest_release=excluded.latest_release,                                                                                                                                 
            latest_release_at=excluded.latest_release_at,                                                                                                                           
            last_fetched_at=excluded.last_fetched_at                                                                                                                                
    """, (                                                                                                                                                                          
        project_id, repo.get('name'), repo.get('html_url'),                                                                                                                         
        repo.get('language'), repo.get('stargazers_count'),                                                                                                                         
        repo.get('open_issues_count'), repo.get('pushed_at'),                                                                                                                       
        release, release_at, topics, repo.get('description'),                                                                                                                       
        source, now, now                                                                                                                                                            
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
                                                                                                                                                                                    
    if not args.dry_run:                                                                                                                                                            
        conn = sqlite3.connect(DB_PATH)                                                                                                                                             
        for item in all_results:                                                                                                                                                    
            upsert_project(conn, item['repo'], item['source'], item['signal'], False)                                                                                               
        conn.commit()                                                                                                                                                               
        conn.close()                                                                                                                                                                
                                                                                       
    # 统计去重后数量                                                                                                                                                                
    seen = set(item['repo']['full_name'] for item in all_results)                                                                                                                   
    print(f"发现候选项目（去重后）: {len(seen)}")                                                                                                                                   
                                                                                                                                                                                    
if __name__ == '__main__':                                                                                                                                                          
    main()                                                                                                                                                                          
                                                                                                                                                                                    
```
- Step 6: 验证 dry-run                                                                                                                                                              
                                                                                                                                                                                    
```python
GITHUB_TOKEN=your_pat python pipeline/stages/discover.py --dry-run                                                                                                                  
                                                                                                                                                                                    
期望：打印各渠道发现的项目名，无报错，最后输出去重后数量。                                                                                                                          
                                                                                                                                                                                    
```
- Step 7: Commit                         
                                                                                                                                                                                    
git add pipeline/stages/discover.py                                                                                                                                                 
git commit -m "feat: add Stage 1 discover.py with 4-source discovery"                                                                                                               
                                                                                                                                                                                    
---                                                                                                                                                                                 
Task 3: schedule.py — 调度决策                                                         
                                                                                                                                                                                    
Files:                                                                                                                                                                              
- Create: pipeline/stages/schedule.py                                                                                                                                               
- Test: python pipeline/stages/schedule.py --mode incremental --dry-run 打印今日任务清单                                                                                            
- Step 1: 编写 schedule.py 框架                                                                                                                                                     
                                                                                                                                                                                    
#!/usr/bin/env python3                                                                 
"""Stage 2: 调度决策，根据项目状态和变更情况生成今日 tasks。"""                                                                                                                     
import os, sqlite3, argparse                                                                                                                                                        
from datetime import datetime, timezone, timedelta
                                                                                                                                                                                    
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'pipeline.db')                                                                                                      
                                                                                                                                                                                    
MAX_TASKS = {                                                                                                                                                                       
    "triggered":     None,                                                                                                                                                          
    "incremental":   10,                                                                                                                                                            
    "bulk_first":    5,                                                                                                                                                             
    "bulk_followup": 3,                                                                                                                                                             
}                                                                                                                                                                                   
                                                                                       
def get_conn():                                                                                                                                                                     
    return sqlite3.connect(DB_PATH)                                                                                                                                                 
                                                                                                                                                                                    
def today():                                                                                                                                                                        
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')                                                                                                                          
                                                                                                                                                                                    
def days_since(iso_str: str) -> int:                                                                                                                                                
    if not iso_str:                                                                                                                                                                 
        return 9999                                                                                                                                                                 
    dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))                                                                                                                     
    return (datetime.now(timezone.utc) - dt).days                                                                                                                                   
                                                                                                                                                                                    
- Step 2: 实现 triggered 任务生成（Priority 1）                                                                                                                                     
                                                                                                                                                                                    
```python
def gen_triggered_tasks(conn, date, dry_run) -> int:                                                                                                                                
    """重大版本发布：active 项目 latest_release_at 有更新。"""                                                                                                                      
    cur = conn.execute("""                                                                                                                                                          
        SELECT p.id, p.latest_release, p.latest_release_at,                                                                                                                         
               MAX(t.finished_at) as last_analyzed                                                                                                                                  
        FROM projects p                                                                                                                                                             
        LEFT JOIN tasks t ON t.project_id = p.id AND t.status = 'done'                                                                                                              
        WHERE p.status = 'active'                                                                                                                                                   
          AND p.latest_release_at IS NOT NULL                                                                                                                                       
        GROUP BY p.id                                                                                                                                                               
    """)                                                                                                                                                                            
    count = 0                                                                                                                                                                       
    for row in cur.fetchall():                                                                                                                                                      
        pid, release, release_at, last_analyzed = row                                                                                                                               
        # 版本发布时间比上次分析时间新                                                                                                                                              
        if last_analyzed and release_at and release_at <= last_analyzed:                                                                                                            
            continue                                                                                                                                                                
        reason = f"new_release:{release}"                                                                                                                                           
        if dry_run:                                                                                                                                                                 
            print(f"  [triggered] {pid} — {reason}")                                                                                                                                
        else:                                                                                                                                                                       
            conn.execute("""                                                                                                                                                        
                INSERT INTO tasks (project_id, task_date, task_type, trigger_reason, status, created_at)                                                                            
                VALUES (?, ?, 'triggered', ?, 'pending', ?) 
                 """, (pid, date, reason, datetime.now(timezone.utc).isoformat()))                                                                                                       
        count += 1                                                                                                                                                                  
    return count                                                                                                                                                                    
                                                                                                                                                                                    
```
- Step 3: 实现 incremental / bulk 任务生成（Priority 2-3）                                                                                                                          
                                                                                                                                                                                    
```python
def gen_incremental_tasks(conn, date, dry_run) -> int:
    """对比 projects.prev_* 字段与当前值判断变化。"""
    cur = conn.execute("""
        SELECT p.id, p.stars, p.open_issues, p.last_commit_at,
               p.prev_stars, p.prev_open_issues,
               MAX(t.finished_at) as last_analyzed
        FROM projects p
        LEFT JOIN tasks t ON t.project_id = p.id AND t.status = 'done'
        WHERE p.status = 'active'
        GROUP BY p.id
    """)
    count = 0
    limit = MAX_TASKS['incremental']
    for row in cur.fetchall():
        if limit and count >= limit:
            break
        pid, stars, issues, commit_at, prev_stars, prev_issues, last_analyzed = row
        if days_since(last_analyzed) < 7:
            continue
        # prev_stars 为 NULL → 新项目首次进入 active，直接触发
        if prev_stars is None:
            reason = 'first_active'
        else:
            issues_delta   = abs((issues or 0) - (prev_issues or 0))
            stars_delta    = abs((stars  or 0) - (prev_stars  or 0))
            issues_changed = issues and issues_delta / max(prev_issues, 1) > 0.10
            stars_changed  = stars  and stars_delta  / max(prev_stars,  1) > 0.05
            commit_changed = commit_at and days_since(commit_at) < 7
            if not (issues_changed or stars_changed or commit_changed):
                continue
            reason = (f"issues_delta:+{issues_delta}" if issues_changed else
                      f"stars_delta:+{stars_delta}"   if stars_changed  else "new_commit")
        if dry_run:
            print(f"  [incremental] {pid} — {reason}")
        else:
            conn.execute("""
                INSERT INTO tasks (project_id, task_date, task_type, trigger_reason, status, created_at)
                VALUES (?, ?, 'incremental', ?, 'pending', ?)
            """, (pid, date, reason, datetime.now(timezone.utc).isoformat()))
        count += 1
    return count
                                                                                                                                                                                    
def gen_bulk_tasks(conn, date, batch_size, dry_run) -> int:
    """Priority 3: A 类（anchor/ecosystem 来源）bulk_first 任务。"""
    cur = conn.execute("""
        SELECT p.id
        FROM projects p
        WHERE p.status = 'bulk_pending'
          AND p.source IN ('anchor', 'ecosystem')
        ORDER BY p.stars DESC
        LIMIT ?
    """, (batch_size,))
    count = 0
    for row in cur.fetchall():
        pid = row[0]
        if dry_run:
            print(f"  [bulk_first] {pid}")
        else:
            conn.execute("""
                INSERT INTO tasks (project_id, task_date, task_type, trigger_reason, status, created_at)
                VALUES (?, ?, 'bulk_first', 'bulk_schedule', 'pending', ?)
            """, (pid, date, datetime.now(timezone.utc).isoformat()))
        count += 1
    return count

def gen_bulk_followup_tasks(conn, date, batch_size, dry_run) -> int:
    """Priority 4: B 类（非 anchor/ecosystem）bulk_followup 任务，仅在无 bulk_first 时触发。"""
    existing = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE task_date=? AND task_type='bulk_first'", (date,)
    ).fetchone()[0]
    if existing > 0:
        return 0
    cur = conn.execute("""
        SELECT p.id
        FROM projects p
        WHERE p.status = 'bulk_pending'
          AND p.source NOT IN ('anchor', 'ecosystem')
        ORDER BY p.stars DESC
        LIMIT ?
    """, (batch_size,))
    count = 0
    for row in cur.fetchall():
        pid = row[0]
        if dry_run:
            print(f"  [bulk_followup] {pid}")
        else:
            conn.execute("""
                INSERT INTO tasks (project_id, task_date, task_type, trigger_reason, status, created_at)
                VALUES (?, ?, 'bulk_followup', 'bulk_schedule', 'pending', ?)
            """, (pid, date, datetime.now(timezone.utc).isoformat()))
        count += 1
    return count
                                                                                                                                                                                    
```
- Step 4: 实现 main 入口                                                                                                                                                            
                                                                                                                                                                                    
```python
def main():                                                                                                                                                                         
    parser = argparse.ArgumentParser()                                                                                                                                              
    parser.add_argument('--mode', choices=['incremental', 'bulk_first'], default='incremental')                                                                                     
    parser.add_argument('--batch-size', type=int, default=5)                                                                                                                        
    parser.add_argument('--dry-run', action='store_true')                              
    args = parser.parse_args()                                                                                                                                                      
                                                                                       
    conn = get_conn()                                                                                                                                                               
    date = today()                                                                                                                                                                  
    total = 0                                                                                                                                                                       
                                                                                                                                                                                    
    if args.mode == 'incremental':                                                                                                                                                  
        n = gen_triggered_tasks(conn, date, args.dry_run)                                                                                                                           
        print(f"triggered:   {n}")                                                                                                                                                  
        total += n                                                                                                                                                                  
        n = gen_incremental_tasks(conn, date, args.dry_run)                                                                                                                         
        print(f"incremental: {n}")                                                                                                                                                  
        total += n                                                                                                                                                                  
    else:                                                                                                                                                                           
        n = gen_bulk_tasks(conn, date, args.batch_size, args.dry_run)
        print(f"bulk_first:     {n}")
        total += n
        n = gen_bulk_followup_tasks(conn, date, MAX_TASKS['bulk_followup'], args.dry_run)
        print(f"bulk_followup:  {n}")
        total += n
                                                                                                                                                                                    
    if not args.dry_run:                                                                                                                                                            
        conn.commit()                                                                                                                                                               
    conn.close()                                                                                                                                                                    
    print(f"今日任务合计: {total}")                                                                                                                                                 
                                                                                                                                                                                    
if __name__ == '__main__':                                                                                                                                                          
    main()                                                                                                                                                                          
                                                                                                                                                                                    
```
- [ ] **Step 5: 验证**

```bash
python pipeline/stages/schedule.py --mode incremental --dry-run
```

期望：打印任务分类和项目名，无报错，最后输出"今日任务合计: N"。

- [ ] **Step 6: Commit**

```bash
git add pipeline/stages/schedule.py
git commit -m "feat: add Stage 2 schedule.py with triggered/incremental/bulk logic"
```

---

### Task 4: report.py — 生成每日 Markdown 报告                      
                                                                                                                                                                                    
**Files:**                                                                                                                                                                          
- Create: `pipeline/stages/report.py`                                                                                                                                               
- Test: `python pipeline/stages/report.py --date 2026-04-15` 生成 `data/reports/2026-04-15.md`                                                                                      
                                                                                                                                                                                    
- [ ] **Step 1: 编写 report.py**                                                       
                                                                                                                                                                                    
```python                                                                              
#!/usr/bin/env python3                                                                                                                                                              
"""Stage 5: 读取 SQLite，生成当日 Markdown 摘要报告。"""                                                                                                                            
import os, sqlite3, json, argparse                                                                                                                                                  
from datetime import datetime, timezone                                                                                                                                             
                                                                                                                                                                                    
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'pipeline.db')         
REPORTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'reports')                                                                                                      
                                                                                                                                                                                    
def get_conn():                                                                                                                                                                     
    return sqlite3.connect(DB_PATH)                                                                                                                                                 
                                                                                                                                                                                    
def render_report(date: str) -> str:                                                                                                                                                
    conn = get_conn()                                                                                                                                                               
    conn.row_factory = sqlite3.Row                                                                                                                                                  
                                                                                                                                                                                    
    # 今日完成的任务                                                                                                                                                                
    tasks = conn.execute("""                                                                                                                                                        
        SELECT t.id, t.project_id, t.task_type, t.trigger_reason,                                                                                                                   
               p.stars, p.language, p.url,                                                                                                                                          
               m.canonical_name, m.canonical_lang                                                                                                                                   
        FROM tasks t                                                                                                                                                                
        JOIN projects p ON p.id = t.project_id                                                                                                                                      
        LEFT JOIN project_meta m ON m.project_id = t.project_id                                                                                                                     
        WHERE t.task_date = ? AND t.status = 'done'                                                                                                                                 
        ORDER BY p.stars DESC                                                                                                                                                       
    """, (date,)).fetchall()                                                                                                                                                        
                                                                                                                                                                                    
    # 今日发现的新机会（first_seen_at = today）                                                                                                                                     
    opps = conn.execute("""                                                                                                                                                         
        SELECT o.*, p.url as project_url, p.language                                                                                                                                
        FROM opportunities o                                                                                                                                                        
        JOIN projects p ON p.id = o.project_id                                                                                                                                      
        JOIN tasks t ON t.id = o.task_id                                                                                                                                            
        WHERE t.task_date = ?                                                                                                                                                       
          AND o.value IN ('high', 'medium')                                                                                                                                         
        ORDER BY                                                                                                                                                                    
          CASE o.value WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,                                                                                                          
          CASE o.urgency WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,                                                                                                        
          CASE o.difficulty WHEN 'low' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END                                                                                                       
    """, (date,)).fetchall()                                                                                                                                                        
                                                                                                                                                                                    
    # 全局统计                                                                                                                                                                      
    stats = conn.execute("""                                                                                                                                                        
        SELECT                                                                                                                                                                      
          (SELECT COUNT(*) FROM projects WHERE status != 'filtered_skip') as active_total,                                                                                          
          (SELECT COUNT(*) FROM projects WHERE status = 'bulk_pending')   as pending,                                                                                               
          (SELECT COUNT(*) FROM opportunities WHERE status = 'open')      as open_opps                                                                                              
    """).fetchone()                                                                                                                                                                 
                                                                                                                                                                                    
    conn.close()                                                                                                                                                                    
                                                                                                                                                                                    
    lines = [                                                                                                                                                                       
        f"# GitHub 开源机会分析报告 — {date}",                                                                                                                                      
        "",                                                                                                                                                                         
        "## 全局概览",                                                                                                                                                              
        "",                                                                                                                                                                         
        f"| 指标 | 数值 |",                                                                                                                                                         
        f"|------|------|",                                                            
        f"| 监控中项目 | {stats['active_total']} |",                                                                                                                                
        f"| 存量待分析 | {stats['pending']} |",                                                                                                                                     
        f"| 开放机会点 | {stats['open_opps']} |",                                                                                                                                   
        f"| 今日分析   | {len(tasks)} 个项目 |",                                                                                                                                    
        "",                                                                                                                                                                         
        "---",                                                                                                                                                                      
        "",                                                                                                                                                                         
        "## 今日分析项目",                                                                                                                                                          
        "",                                                                                                                                                                         
    ]                                                                                                                                                                               
                                                                                                                                                                                    
    for t in tasks:                                                                                                                                                                 
        canonical = f"{t['canonical_name']} ({t['canonical_lang']})" if t['canonical_name'] else "—"                                                                                
        lines += [                                                                                                                                                                  
            f"### [{t['project_id']}]({t['project_url']}) ⭐{t['stars']}",             
            f"- **语言**: {t['language']}  **原版**: {canonical}",                                                                                                                  
            f"- **触发**: `{t['task_type']}` — {t['trigger_reason']}",                                                                                                              
            "",                                                                                                                                                                     
        ]                                                                                                                                                                           
                                                                                                                                                                                    
    lines += [                                                                                                                                                                      
        "---",                                                                                                                                                                      
        "",                                                                                                                                                                         
        "## 高价值贡献机会",                                                                                                                                                        
        "",                                                                                                                                                                         
        "| 项目 | 标题 | 类型 | 价值 | 难度 | 紧迫 |",                                                                                                                              
        "|------|------|------|------|------|------|",                                                                                                                              
    ]                                                                                                                                                                               
                                                                                       
    for o in opps:                                                                                                                                                                  
        lines.append(                                                                  
            f"| [{o['project_id']}]({o['project_url']}) "                                                                                                                           
            f"| {o['title']} "                                                                                                                                                      
            f"| `{o['source_type']}` "                                                                                                                                              
            f"| {o['value']} "                                                                                                                                                      
            f"| {o['difficulty']} "                                                                                                                                                 
            f"| {o['urgency']} |"                                                                                                                                                   
        )                                                                                                                                                                           
                                                                                                                                                                                    
    lines += ["", "---", "", f"*生成时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*", ""]                                                                        
    return "\n".join(lines)                                                                                                                                                         
                                                                                                                                                                                    
def main():                                                                                                                                                                         
    parser = argparse.ArgumentParser()                                                                                                                                              
    parser.add_argument('--date', default=datetime.now(timezone.utc).strftime('%Y-%m-%d'))                                                                                          
    args = parser.parse_args()                                                         
                                                                                                                                                                                    
    os.makedirs(REPORTS_DIR, exist_ok=True)                                                                                                                                         
    content = render_report(args.date)                                                                                                                                              
    out_path = os.path.join(REPORTS_DIR, f"{args.date}.md")                                                                                                                         
    with open(out_path, 'w') as f:                                                                                                                                                  
        f.write(content)                                                                                                                                                            
    print(f"报告已生成: {out_path}")                                                                                                                                                
                                                                                                                                                                                    
if __name__ == '__main__':                                                                                                                                                          
    main()                                                                                                                                                                          
                                                                                                                                                                                    
- Step 2: 验证（数据库为空时也应正常生成）                                                                                                                                          
                                                                                                                                                                                    
python pipeline/stages/report.py --date 2026-04-15                                                                                                                                  
cat pipeline/data/reports/2026-04-15.md                                                                                                                                             
                                                                                                                                                                                    
期望：生成包含"全局概览"和"今日分析项目"的 Markdown 文件，无报错。                                                                                                                  
                                         
- Step 3: Commit                                                                                                                                                                    
                                                                                                                                                                                    
git add pipeline/stages/report.py                                                                                                                                                   
git commit -m "feat: add Stage 5 report.py for daily Markdown generation"                                                                                                           
                                                                                                                                                                                    
---                                                                                                                                                                                 
Task 5: prompts/filter.md — Claude Code 语义过滤指令                                   
                                                                                                                                                                                    
Files:                                                                                                                                                                              
- Create: pipeline/prompts/filter.md                                                                                                                                                
- Test: 内容完整自包含，无需额外验证步骤                                                                                                                                            
- Step 1: 编写 filter.md                                                                                                                                                            
                                                                                                                                                                                    
# Stage 3: 语义过滤任务                                                                
                                                                                                                                                                                    
你是一个开源项目分析专家。请按以下步骤处理 SQLite 数据库中待过滤的项目。                                                                                                            
                                         
## 数据库路径                                                                                                                                                                       
                                                                                                                                                                                    
```                                                                                                                                                                                 
/path/to/pipeline/data/pipeline.db                                                                                                                                                  
```                                                                                                                                                                                 
                                                                                                                                                                                    
（运行时由 run.sh 将此占位符替换为绝对路径）                                           
                                                                                                                                                                                    
## 输入                                                                                
                                                                                                                                                                                    
读取所有 `filter_status = 'pending'` 的项目：                                                                                                                                       
                                                                                                                                                                                    
```sql                                                                                                                                                                              
SELECT p.id, p.name, p.url, p.language, p.stars, p.description, p.topics, p.source                                                                                                  
FROM projects p                                                                        
JOIN project_meta m ON m.project_id = p.id                                                                                                                                          
WHERE m.filter_status = 'pending'                                                      
ORDER BY p.stars DESC;                                                                                                                                                              
```                                                                                    
                                                                                                                                                                                    
## 过滤规则（按顺序判断，命中即 skip）                                                 
                                                                                                                                                                                    
**跳过条件（filter_status = 'skip'）：**                                                                                                                                            
                                                                                                                                                                                    
1. **护城河判断**：该项目本身就是原版（Kafka、Redis、MySQL 本体）；已是所在领域当前语言的事实标准（zerolog、resty、pgx）；生态依赖极深（coredns、etcd、containerd）                 
2. **项目性质**：纯 CLI 工具（无库/服务组件属性）；纯示例/教程/脚手架；纯资源列表/awesome 系列；商业产品的开源 SDK/Agent                                                            
3. **场景限制**：游戏专用框架；区块链/Web3 专用；K8s 基础设施层（非应用层组件）；IoT 专用平台
                                                                                                                                                                                    
**保留条件（filter_status = 'keep'）：**                                               
- 是某个知名原版（Java/Python/C++/Scala）的其他语言移植版或替代实现                                                                                                                 
- 原版功能集丰富，当前语言版本存在明显功能差距                                         
- 有真实用户群体（stars >= 300，有 open issues 活动）                                                                                                                               
                                                                                                                                                                                    
## 输出                                                                                                                                                                             
                                                                                                                                                                                    
对每个项目执行以下 SQL：                                                                                                                                                            
                                                                                                                                                                                    
**跳过时：**                                                                                                                                                                        
```sql                                                                                                                                                                              
UPDATE project_meta                                                                                                                                                                 
SET filter_status = 'skip',                                                                                                                                                         
    filter_reason = '<具体原因>',                                                      
    filtered_at   = '<ISO8601 时间>'                                                                                                                                                
WHERE project_id = '<id>';                                                             

UPDATE projects                                                                        
SET status = 'filtered_skip'                                                           
WHERE id = '<id>';                                                                     
```                                                                                                                                                                                 
                                                                                                                                                                                    
**保留时：**                                                                                                                                                                        
```sql                                                                                                                                                                              
UPDATE project_meta                                                                                                                                                                 
SET filter_status    = 'keep',                                                                                                                                                      
    filter_reason    = '<保留理由>',                                                                                                                                                
    canonical_name   = '<原版项目名，如 Apache Sentinel>',                                                                                                                          
    canonical_lang   = '<原版语言，如 Java>',                                          
    canonical_url    = '<原版 GitHub URL>',                                                                                                                                         
    canonical_stars  = <原版 stars 数>,                                                                                                                                             
    peer_versions    = '<JSON: [{\"lang\":\"Rust\",\"url\":\"...\",\"stars\":1200,\"completeness_hint\":\"~60%\"}]>',                                                               
    filtered_at      = '<ISO8601 时间>'                                                                                                                                             
WHERE project_id = '<id>';                                                                                                                                                          
                                                                                                                                                                                    
UPDATE projects                                                                                                                                                                     
SET status = 'bulk_pending'                                                                                                                                                         
WHERE id = '<id>';                                                                                                                                                                  
```                                                                                                                                                                                 
                                                                                                                                                                                    
## 注意事项                                                                                                                                                                         
                                                                                                                                                                                    
- 无法访问项目页面时：`filter_status = 'skip'`, `filter_reason = 'fetch_failed'`，继续下一个                                                                                        
- 不确定时偏向保留（keep），宁可多分析一个                                                                                                                                          
- 每处理完一个项目立即写库，不要批量等待                                                                                                                                            
                                                                                                                                                                                    
- Step 2: 将 DB 路径占位符改为运行时替换                                               
                                                                                                                                                                                    
run.sh 中调用 filter.md 时，先用 sed 替换路径：                                        
                                                                                                                                                                                    
FILTER_PROMPT=$(sed "s|/path/to/pipeline/data/pipeline.db|$DB|g" "$PROMPTS/filter.md")                                                                                              
claude --dangerously-skip-permissions --print "$FILTER_PROMPT"                                                                                                                      
                                                                                                                                                                                    
- Step 3: Commit                                                                                                                                                                    
                                                                                       
git add pipeline/prompts/filter.md                                                                                                                                                  
git commit -m "feat: add Stage 3 filter.md prompt for Claude Code semantic filtering"                                                                                               
                                                                                                                                                                                    
---                                                                                                                                                                                 
Task 6: prompts/analyze.md — Claude Code 深层分析指令                                                                                                                               
                                                                                                                                                                                    
Files:                                                                                                                                                                              
- Create: pipeline/prompts/analyze.md                                                                                                                                               
- Test: 内容完整自包含，无需额外验证步骤                                                                                                                                            
- Step 1: 编写 analyze.md                                                                                                                                                           
                                                                                                                                                                                    
# Stage 4: 深层分析任务                                                                
                                                                                                                                                                                    
你是一个开源贡献机会分析专家，擅长识别"原版（Java/Python）已实现某功能，但其他语言移植版尚未实现或实现较差"的贡献机会。                                                             
                                                                                                                                                                                    
## 数据库路径                                                                                                                                                                       
                                                                                                                                                                                    
```                                                                                                                                                                                 
/path/to/pipeline/data/pipeline.db                                                                                                                                                  
```                                                                                                                                                                                 
                                                                                                                                                                                    
（运行时由 run.sh 将此占位符替换为绝对路径）                                           
                                                                                                                                                                                    
## 今日日期                                                                            
                                                                                                                                                                                    
```                                                                                    
ANALYSIS_DATE                                                                                                                                                                       
```                                                                                    
                                                                                                                                                                                    
（运行时替换）                                                                         
                                                                                                                                                                                    
## 输入                                                                                
                                                                                                                                                                                    
读取今日待分析任务：                                                                   
                                                                                                                                                                                    
```sql                                                                                 
SELECT t.id as task_id, t.project_id, t.task_type, t.trigger_reason,                                                                                                                
       p.url, p.language, p.stars, p.latest_release,                                   
       m.canonical_name, m.canonical_lang, m.canonical_url,                                                                                                                         
       m.peer_versions                                                                 
FROM tasks t                                                                                                                                                                        
JOIN projects p ON p.id = t.project_id                                                 
JOIN project_meta m ON m.project_id = t.project_id                                                                                                                                  
WHERE t.task_date = 'ANALYSIS_DATE'                                                                                                                                                 
  AND t.status IN ('pending', 'running')                                                                                                                                            
ORDER BY                                                                                                                                                                            
  CASE t.task_type WHEN 'triggered' THEN 0 WHEN 'incremental' THEN 1 ELSE 2 END,                                                                                                    
  p.stars DESC;                                                                                                                                                                     
```                                                                                                                                                                                 
                                                                                                                                                                                    
## 每个项目的分析流程                                                                                                                                                               
                                                                                                                                                                                    
对每个任务，按以下步骤执行：                                                                                                                                                        
                                                                                                                                                                                    
### Step 1: 标记开始                                                                                                                                                                
                                                                                                                                                                                    
```sql                                                                                 
UPDATE tasks   SET status = 'running',  started_at  = '<now>' WHERE id = <task_id>;                                                                                                 
UPDATE projects SET status = 'analyzing'                        WHERE id = '<project_id>';
```                                                                                                                                                                                 
                                                                                       
### Step 2: 抓取目标项目信息                                                                                                                                                        
                                                                                       
- WebFetch `<url>#readme` — 读取 README，提取功能列表                                                                                                                               
- WebFetch `https://github.com/<project_id>/releases` — 读取 CHANGELOG/发布说明                                                                                                     
- GitHub API: `GET /repos/<project_id>/issues?state=open&sort=reactions&per_page=20` — top 20 高反应 issue                                                                          
- GitHub API: `GET /repos/<project_id>/git/trees/HEAD?recursive=0` — 目录结构                                                                                                       
                                                                                       
### Step 3: 抓取原版信息                                                                                                                                                            
                                                                                       
- WebFetch `<canonical_url>#readme` — 原版 README                                                                                                                                   
- 提取原版功能全集（feature matrix）：列出所有核心功能模块                                                                                                                          
                                                                                                                                                                                    
### Step 4: 横向对比其他语言版本                                                                                                                                                    
                                                                                                                                                                                    
- 遍历 `peer_versions` JSON 数组，WebFetch 各版本 README                                                                                                                            
- 判断：目标版本 vs 原版 vs 其他语言版本，谁更领先/落后                                
- 记录各语言版本的功能完整度估算（百分比）                                                                                                                                          
                                                                                                                                                                                    
### Step 5: 源码结构分析                                                                                                                                                            
                                                                                                                                                                                    
- 对照目录结构，识别核心模块                                                           
- 发现原版有但目标版本完全缺失的模块（这是 feature_gap 类型机会的来源）                                                                                                             
                                                                                                                                                                                    
### Step 6: Issues 深度分析                                                                                                                                                         
                                                                                                                                                                                    
- 逐条读取 top issues 正文                                                                                                                                                          
- 跳过：issue 已有关联 PR（`has_linked_pr = 1`）                                       
- 分类：feature_request / bug / performance / security                                                                                                                              
- 对比：该功能原版是否已实现？其他语言版本是否已实现？                                                                                                                              
                                                                                                                                                                                    

### Step 6.5: Maintainer 意图分析

- GitHub API: `GET /repos/<project_id>/pulls?state=closed&per_page=50`
  搜索标题/描述含相关关键词的历史 PR：
  - merged → `maintainer_signal = welcoming`
  - closed without merge，maintainer 评论含拒绝语义 → `maintainer_signal = rejected`
  - closed without merge，无明确拒绝 → `maintainer_signal = neutral`
- 对已有 issue 的 opportunity，检查 issue 评论中 maintainer 回复（`author_association` 为 `OWNER`/`COLLABORATOR`/`MEMBER`）：
  - "PR welcome" / "good first issue" 标签 → `welcoming`
  - "won't fix" / "out of scope" / "by design" → `rejected`
  - 无明确表态 → `neutral`
- 将结果写入对应 opportunity 的 `maintainer_signal` / `maintainer_note`
- `maintainer_signal = rejected` → 同时将 `opportunities.status = 'obsolete'`
- `maintainer_signal = welcoming` → value 上调一级（low→medium，medium→high）

### Step 7: 写入分析结果                                                                                                                                                            
                                                                                       
**写入 analyses 表：**                                                                                                                                                              
                                                                                                                                                                                    
```sql                                                                                                                                                                              
INSERT INTO analyses (project_id, task_id, analyzed_at, release_version,                                                                                                            
    source_structure, canonical_gap, peer_comparison, overall_score)                                                                                                                
VALUES ('<project_id>', <task_id>, '<now>', '<latest_release>',                                                                                                                     
    '<源码结构 JSON>',                                                                 
    '<与原版差距的文字描述，2-3句>',                                                                                                                                                
    '<与其他语言版本横向对比，2-3句>',                                                 
    <1-10 综合评分>);                                                                                                                                                               
```                                                                                                                                                                                 
                                                                                                                                                                                    
**写入 opportunities 表（每个机会点）：**                                                                                                                                           
                                                                                                                                                                                    
```sql                                                                                                                                                                              
INSERT OR IGNORE INTO opportunities                                                                                                                                                 
    (project_id, task_id, source_type, source_ref, title, description,                                                                                                              
     canonical_status, peer_status, value, difficulty, urgency, impl_hint,                                                                                                          
     issue_number, issue_reactions, has_linked_pr,
     value_evidence, difficulty_evidence, urgency_evidence, maintainer_evidence,
     status, first_seen_at, last_seen_at)
VALUES                                                                                                                                                                              
    ('<project_id>', <task_id>,                                                        
     '<issue|feature_gap|security|performance|compatibility>',                                                                                                                      
     '<issue URL 或 "canonical:Java/v1.8.2" 或 "peer:Rust/src/xxx.rs">',                                                                                                            
     '<简短标题，< 60 字>',                                                                                                                                                         
     '<详细说明，包括背景、影响范围>',                                                                                                                                              
     '<原版怎么实现的，1-2句>',                                                                                                                                                     
     '<其他语言版本的状态，1-2句>',                                                                                                                                                 
     '<high|medium|low>',  -- value                                                                                                                                                 
     '<high|medium|low>',  -- difficulty                                                                                                                                            
     '<high|medium|low>',  -- urgency                                                                                                                                               
     '<涉及哪些文件，大概工作量>',                                                                                                                                                  
     <issue_number 或 NULL>,                                                                                                                                                        
     <reactions 数或 NULL>,                                                                                                                                                         
     <0 或 1>,
     '<{issue/feature_gap/...}_evidence JSON>',  -- value_evidence
     '<difficulty_evidence JSON>',
     '<urgency_evidence JSON>',
     '<maintainer_evidence JSON>',
     '<依据，如 closed PR #123>',              -- maintainer_note
     'open',                                                                                                                                                                        
     '<now>', '<now>');                                                                                                                                                             
                                                                                                                                                                                    
对已存在的机会（UNIQUE 冲突），只更新 `last_seen_at`：                                                                                                                              
                                                                                                                                                                                    
```sql                                                                                                                                                                              
UPDATE opportunities SET last_seen_at = '<now>'                                                                                                                                     
WHERE project_id = '<project_id>'                                                                                                                                                   
  AND source_type = '<type>'                                                                                                                                                        
  AND source_ref  = '<ref>';                                                           
```                                                                                                                                                                                 
                                                                                       
**标记完成：**                                                                                                                                                                      
                                                                                                                                                                                    
```sql                                                                                                                                                                              
UPDATE tasks    SET status = 'done',   finished_at = '<now>' WHERE id = <task_id>;                                                                                                  
UPDATE projects SET status = 'active'                         WHERE id = '<project_id>';                                                                                            
```                                                                                                                                                                                 
                                                                                       
## 评分标准                                                                                                                                                                         
                                                                                       
**value（贡献价值）：**                                                                                                                                                             
- `high`：原版已实现 + 其他语言版本也已实现 + issue 有呼声（reactions >= 5）                                                                                                        
- `medium`：原版已实现但其他语言版本也未实现，或 issue 呼声低                                                                                                                       
- `low`：纯推测性功能，无原版参照，无 issue 支撑                                                                                                                                    
                                                                                       
**difficulty（实现难度）：**                                                                                                                                                        
- `low`：有完整参考实现，改动 < 3 个文件                                               
- `medium`：有参考实现，需理解现有架构，改动 3~10 个文件                                                                                                                            
- `high`：无直接参照，需设计新架构，或涉及核心数据结构变更                                                                                                                          
                                                                                                                                                                                    
**urgency（紧迫度）：**                                                                                                                                                             
- `high`：security 类（CVE/不安全 API）或 performance 类（已有生产问题反馈）                                                                                                        
- `medium`：功能缺失但有 workaround                                                                                                                                                 
- `low`：纯增强型功能                                                                                                                                                               
                                                                                                                                                                                    
## 注意事项                                                                                                                                                                         
                                                                                                                                                                                    
- 每个项目分析完立即写库，不要等所有项目分析完再批量写                                                                                                                              
- API 超时或 404：`task.status = 'skipped'`，`project.status` 不变，继续下一个                                                                                                      
- 机会点宁少勿滥：只输出有明确参考实现或明确 issue 支撑的机会                                                                                                                       
- 每个项目输出机会点上限：10 个（取 value 最高的）
- LLM 只填 evidence 字段，不输出 value/difficulty/urgency/maintainer_signal，评分由 scoring.py 计算
- `maintainer_signal = rejected` 的机会点由 scoring.py 标记 `status = 'obsolete'`，不计入今日报告
                                                                                                                                                                                    
- Step 2: 更新 run.sh 中的占位符替换逻辑                                                                                                                                            
                                                                                       
ANALYZE_PROMPT=$(sed \                                                                                                                                                              
  -e "s|/path/to/pipeline/data/pipeline.db|$DB|g" \                                                                                                                                 
  -e "s|ANALYSIS_DATE|$DATE|g" \                                                                                                                                                    
  "$PROMPTS/analyze.md")                                                                                                                                                            
claude --dangerously-skip-permissions --print "$ANALYZE_PROMPT"                                                                                                                     
                                                                                                                                                                                    
- Step 3: Commit                                                                                                                                                                    
                                                                                                                                                                                    
git add pipeline/prompts/analyze.md                                                                                                                                                 
git commit -m "feat: add Stage 4 analyze.md prompt for Claude Code deep analysis"                                                                                                   
                                                                                                                                                                                    
---                                                                                                                                                                                 
Task 7: run.sh + run_bulk.sh — 运行入口脚本                                                                                                                                         
                                                                                                                                                                                    
Files:                                                                                                                                                                              
- Create: pipeline/run.sh                                                                                                                                                           
- Create: pipeline/run_bulk.sh                                                                                                                                                      
- Test: bash -n pipeline/run.sh 语法检查通过                                                                                                                                        
- Step 1: 编写 run.sh（日常增量）                                                                                                                                                   
                                       
#!/usr/bin/env bash                                                                                                                                                                 
set -euo pipefail                                                                                                                                                                   
                                         
PIPELINE_DIR="$(cd "$(dirname "$0")" && pwd)"                                                                                                                                       
DB="$PIPELINE_DIR/data/pipeline.db"                                                                                                                                                 
PROMPTS="$PIPELINE_DIR/prompts"                                                                                                                                                     
STAGES="$PIPELINE_DIR/stages"                                                                                                                                                       
DATE=$(date +%Y-%m-%d)                                                                                                                                                              
                                                                                                                                                                                    
echo "=== GitHub Opportunities Pipeline - $DATE ==="                                                                                                                                
                                                                                                                                                                                    
# 0. 初始化 DB（幂等）                                                                                                                                                              
python "$STAGES/init_db.py"                                                                                                                                                         
                                                                                                                                                                                    
# 1. 拉取最新状态                                                                                                                                                                   
echo "[0/4] git pull..."                                                                                                                                                            
git -C "$PIPELINE_DIR/.." pull --rebase                                                                                                                                             
                                                                                       
# 1. Stage 3: 语义过滤（先过滤，过滤后重新调度，再检查任务数）
FILTER_COUNT=$(sqlite3 "$DB" \
  "SELECT COUNT(*) FROM project_meta WHERE filter_status='pending';")

if [ "$FILTER_COUNT" -gt 0 ]; then
  echo "[1/4] Stage 3: 语义过滤 ($FILTER_COUNT 个)..."
  FILTER_PROMPT=$(sed "s|/path/to/pipeline/data/pipeline.db|$DB|g" "$PROMPTS/filter.md")
  claude --dangerously-skip-permissions --print "$FILTER_PROMPT"
  echo "[1/4] 重新调度..."
  python "$STAGES/schedule.py" --mode incremental
else
  echo "[1/4] Stage 3: 无待过滤项目，跳过。"
fi

# 检查今日是否有待分析任务（过滤+调度完成后再检查）
PENDING=$(sqlite3 "$DB" \
  "SELECT COUNT(*) FROM tasks WHERE task_date='$DATE' AND status='pending';")

if [ "$PENDING" -eq 0 ]; then
  echo "今日无待分析任务，退出。"
  exit 0
fi

echo "今日待分析任务：$PENDING 个"
                                                                                                                                                                                    
if [ "$FILTER_COUNT" -gt 0 ]; then                                                                                                                                                  
  echo "[1/4] Stage 3: 语义过滤 ($FILTER_COUNT 个)..."                                                                                                                              
  FILTER_PROMPT=$(sed "s|/path/to/pipeline/data/pipeline.db|$DB|g" "$PROMPTS/filter.md")
  claude --dangerously-skip-permissions --print "$FILTER_PROMPT"                                                                                                                    
else                                                                                                                                                                                
  echo "[1/4] Stage 3: 无待过滤项目，跳过。"                                                                                                                                        
fi                                                                                                                                                                                  
                                                                                                                                                                                    
# 3. Stage 4: 深层分析                                                                                                                                                              
echo "[2/4] Stage 4: 深层分析 ($PENDING 个任务)..."                                                                                                                                 
ANALYZE_PROMPT=$(sed \                                                                                                                                                              
  -e "s|/path/to/pipeline/data/pipeline.db|$DB|g" \                                                                                                                                 
  -e "s|ANALYSIS_DATE|$DATE|g" \                                                                                                                                                    
  "$PROMPTS/analyze.md")                                                                                                                                                            
claude --dangerously-skip-permissions --print "$ANALYZE_PROMPT"                                                                                                                     
                                                                                                                                                                                    
# 2.5. Stage 4.5: 规则化评分
echo "[2.5/4] scoring.py: 规则化评分..."
python "$STAGES/scoring.py"

# 4. Stage 5: 生成报告                                                                                                                                                              
echo "[3/4] Stage 5: 生成报告..."                                                                                                                                                   
python "$STAGES/report.py" --date "$DATE"                                                                                                                                           
                                                                                                                                                                                    
# 5. 推回 repo                                                                                                                                                                      
echo "[4/4] git push..."                                                                                                                                                            
git -C "$PIPELINE_DIR/.." add \                                                                                                                                                     
  pipeline/data/pipeline.db \                                                                                                                                                       
  "pipeline/data/reports/$DATE.md"                                                                                                                                                  
                                                                                                                                                                                    
git -C "$PIPELINE_DIR/.." diff --staged --quiet || \                                                                                                                                
  git -C "$PIPELINE_DIR/.." commit \                                                                                                                                                
    -m "feat: analysis report $DATE ($PENDING tasks)"                                                                                                                               
                                                                                                                                                                                    
git -C "$PIPELINE_DIR/.." push                                                                                                                                                      
                                                                                                                                                                                    

echo "=== 完成 ==="                                                                                                                                                                 
echo "报告：pipeline/data/reports/$DATE.md"                                                                                                                                         
                                                                                                                                                                                    
- Step 2: 编写 run_bulk.sh（首次存量）                                                 
                                         
#!/usr/bin/env bash                                                                                                                                                                 
set -euo pipefail                      
                                                                                                                                                                                    
PIPELINE_DIR="$(cd "$(dirname "$0")" && pwd)"                                                                                                                                       
DB="$PIPELINE_DIR/data/pipeline.db"                                                                                                                                                 
PROMPTS="$PIPELINE_DIR/prompts"                                                                                                                                                     
STAGES="$PIPELINE_DIR/stages"                                                                                                                                                       
BATCH_SIZE=${1:-5}                                                                                                                                                                  
DATE=$(date +%Y-%m-%d)                                                                                                                                                              
                                                                                                                                                                                    
echo "=== Bulk Analysis - $DATE (batch_size=$BATCH_SIZE) ==="                                                                                                                       
                                                                                                                                                                                    
python "$STAGES/init_db.py"                                                                                                                                                         
git -C "$PIPELINE_DIR/.." pull --rebase                                                                                                                                             
                                                                                                                                                                                    
TOTAL=$(sqlite3 "$DB" "SELECT COUNT(*) FROM projects WHERE status='bulk_pending';")                                                                                                 
DONE=$(sqlite3 "$DB" "SELECT COUNT(*) FROM projects WHERE status='active';")                                                                                                        
echo "存量进度：已完成 $DONE / 待分析 $TOTAL"                                                                                                                                       
                                                                                       
if [ "$TOTAL" -eq 0 ]; then                                                                                                                                                         
  echo "存量队列已清空，改用 run.sh。"                                                                                                                                              
  exit 0                                                                                                                                                                            
fi                                                                                                                                                                                  
                                                                                                                                                                                    
FILTER_COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM project_meta WHERE filter_status='pending';")                                                                                    
if [ "$FILTER_COUNT" -gt 0 ]; then                                                                                                                                                  
  echo "[1/3] Stage 3: 语义过滤 ($FILTER_COUNT 个)..."                                                                                                                              
  FILTER_PROMPT=$(sed "s|/path/to/pipeline/data/pipeline.db|$DB|g" "$PROMPTS/filter.md")
  claude --dangerously-skip-permissions --print "$FILTER_PROMPT"                                                                                                                    
fi                                                                                                                           
python "$STAGES/schedule.py" --mode bulk_first --batch-size "$BATCH_SIZE"                                                                                                           
                                                                                                                                                                                    
PENDING=$(sqlite3 "$DB" "SELECT COUNT(*) FROM tasks WHERE task_date='$DATE' AND status='pending';")                                                                                 
echo "[2/3] Stage 4: 深层分析 ($PENDING 个)..."                                                                                                                                     
ANALYZE_PROMPT=$(sed \                                                                                                                                                              
  -e "s|/path/to/pipeline/data/pipeline.db|$DB|g" \                                                                                                                                 
  -e "s|ANALYSIS_DATE|$DATE|g" \                                                                                                                                                    
  "$PROMPTS/analyze.md")                                                                                                                                                            
claude --dangerously-skip-permissions --print "$ANALYZE_PROMPT"                        
                                                                                                                                                                                    
echo "[2.5/3] scoring.py: 规则化评分..."
python "$STAGES/scoring.py"

echo "[3/3] 生成报告并推送..."                                                                                                                                                      
python "$STAGES/report.py" --date "$DATE"                                                                                                                                           
                                                                                                                                                                                    
git -C "$PIPELINE_DIR/.." add \                                                                                                                                                     
  pipeline/data/pipeline.db \                                                                                                                                                       
  "pipeline/data/reports/$DATE.md"                                                                                                                                                  
git -C "$PIPELINE_DIR/.." diff --staged --quiet || \                                                                                                                                
  git -C "$PIPELINE_DIR/.." commit \                                                                                                                                                
    -m "feat: bulk analysis $DATE ($PENDING tasks, $TOTAL remaining)"                                                                                                               
git -C "$PIPELINE_DIR/.." push                                                                                                                                                      
                                                                                                                                                                                    
REMAINING=$(sqlite3 "$DB" "SELECT COUNT(*) FROM projects WHERE status='bulk_pending';")                                                                                             
echo "=== 完成 === 本批: $PENDING | 剩余: $REMAINING"                                                                                                                               
                                                                                                                                                                                    
- Step 3: 验证语法                                                                                                                                                                  
                                                                                                                                                                                    
bash -n pipeline/run.sh && echo "run.sh OK"                                                                                                                                         
bash -n pipeline/run_bulk.sh && echo "run_bulk.sh OK"                                                                                                                               
chmod +x pipeline/run.sh pipeline/run_bulk.sh                                                                                                                                       
                                                                                                                                                                                    
- Step 4: Commit                                                                                                                                                                    
                                                                                                                                                                                    
git add pipeline/run.sh pipeline/run_bulk.sh                                                                                                                                        
git commit -m "feat: add run.sh and run_bulk.sh entry points"                                                                                                                       
                                                                                                                                                                                    
---                                                                                                                                                                                 
Task 8: GH Actions workflow                                                                                                                                                         
                                                                                                                                                                                    
Files:                                                                                                                                                                              
- Create: pipeline/.github/workflows/discover.yml                                                                                                                                   
- Step 1: 编写 discover.yml                                                                                                                                                         
                                                                                                                                                                                    
name: Daily Discover & Schedule                                                                                                                                                     
                                       
on:                                                                                                                                                                                 
  schedule:                                                                                                                                                                         
    - cron: '0 1 * * *'                
  workflow_dispatch:                                                                                                                                                                
    inputs:                                                                                                                                                                         
      mode:                                                                                                                                                                         
        description: 'bulk_first / incremental'                                                                                                                                     
        default: 'incremental'                                                                                                                                                      
                                                                                                                                                                                    
jobs:                                                                                                                                                                               
  discover:                                                                                                                                                                         
    runs-on: ubuntu-latest                                                                                                                                                          
    steps:                                                                                                                                                                          
      - uses: actions/checkout@v4                                                                                                                                                   
                                                                                                                                                                                    
      - uses: actions/setup-python@v5                                                                                                                                               
        with:                                                                          
          python-version: '3.12'                                                                                                                                                    
                                       
      - run: pip install -r pipeline/requirements.txt                                                                                                                               
                                                                                                                                                                                    
      - name: Init DB                                                                                                                                                               
        run: python pipeline/stages/init_db.py                                                                                                                                      
                                                                                                                                                                                    
      - name: Stage 1 - Discover                                                                                                                                                    
        env:                                                                                                                                                                        
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}                                                                                                                                 
        run: python pipeline/stages/discover.py                                        
                                                                                                                                                                                    
      - name: Stage 2 - Schedule                                                                                                                                                    
        run: |                                                                                                                                                                      
          python pipeline/stages/schedule.py \                                                                                                                                      
            --mode ${{ github.event.inputs.mode || 'incremental' }}                                                                                                                 
                                                                                                                                                                                    
      - name: Commit results                                                                                                                                                        
        run: |                                                                                                                                                                      
          git config user.name  "github-actions[bot]"                                                                                                                               
          git config user.email "github-actions[bot]@users.noreply.github.com"                                                                                                      
          git add pipeline/data/pipeline.db                                                                                                                                         
          git diff --staged --quiet || \                                                                                                                                            
            git commit -m "chore: daily discover $(date +%Y-%m-%d)"                                                                                                                 
          git push                                                                                                                                                                  
                                                                                                                                                                                    
- [ ] **Step 2: Commit**

```bash
git add pipeline/.github/workflows/discover.yml
git commit -m "feat: add GH Actions workflow for daily discover and schedule"
```

---

### Task 9: 收尾与端到端验证

**Files:**
- Create: `pipeline/.gitignore`
- Create: `pipeline/data/.gitkeep`
- Create: `pipeline/data/reports/.gitkeep`

- [ ] **Step 1: 创建 .gitignore 和占位文件**

```bash
printf '__pycache__/\n*.pyc\n.env\n' > pipeline/.gitignore
touch pipeline/data/.gitkeep pipeline/data/reports/.gitkeep
git add pipeline/data/.gitkeep pipeline/data/reports/.gitkeep pipeline/.gitignore
git commit -m "chore: add gitignore and data directory placeholders"
```

- [ ] **Step 2: 端到端冒烟测试**

```bash
# 本地验证全链路（不触发 GH Actions）
export GITHUB_TOKEN=your_pat
python pipeline/stages/init_db.py
python pipeline/stages/discover.py --dry-run
python pipeline/stages/schedule.py --mode incremental --dry-run
python pipeline/stages/report.py --date $(date +%Y-%m-%d)
echo "冒烟测试通过"
```

期望：三个脚本均无报错，report 生成一个 Markdown 文件。

补充真实写库验证（需要有效 GITHUB_TOKEN）：

```bash
# 插入一条测试项目，验证调度逻辑
sqlite3 pipeline/data/pipeline.db "
  INSERT OR IGNORE INTO projects (id, name, url, language, stars, open_issues, prev_stars, prev_open_issues, status, source, first_seen_at, last_fetched_at)
  VALUES ('test/smoke', 'smoke', 'https://github.com/test/smoke', 'Go', 500, 5, 480, 4, 'active', 'anchor', datetime('now'), datetime('now'));
  INSERT OR IGNORE INTO project_meta (project_id, filter_status) VALUES ('test/smoke', 'keep');
"
python pipeline/stages/schedule.py --mode incremental --dry-run
# 期望输出包含 test/smoke 的 incremental 任务
# 清理测试数据
sqlite3 pipeline/data/pipeline.db "DELETE FROM projects WHERE id='test/smoke'; DELETE FROM project_meta WHERE project_id='test/smoke';"
```

- [ ] **Step 3: 最终 Commit**

```bash
git add -A
git commit -m "chore: pipeline complete - ready for first run"
``` 



---

### Task 10: scoring.py — 规则化评分引擎

**Files:**
- Create: `pipeline/stages/scoring.py`
- Test: 插入含 evidence 的测试 opportunity，运行后验证 value/difficulty/urgency/maintainer_signal 正确写入

- [ ] **Step 1: 编写 scoring.py**

```python
#!/usr/bin/env python3
"""Stage 4.5: 读取 opportunities 表的 evidence JSON，按规则计算评分写回数据库。"""
import os, sqlite3, json
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'pipeline.db')

# ── 可配置阈值 ────────────────────────────────────────────────────────────────
REACTIONS_HIGH     = 5      # issue_reactions >= 此值 → value 贡献 high
LOC_HIGH           = 500    # canonical_impl_loc > 此值 → difficulty high
LOC_MEDIUM         = 200    # canonical_impl_loc 200-500 → difficulty medium
PR_AGE_DAYS        = 365    # similar_pr age_days < 此值才计入 maintainer 判断

REJECT_KEYWORDS    = ['out of scope', 'won\'t fix', 'wontfix', 'by design',
                      'not planned', 'not in scope', 'intentional']
WELCOME_KEYWORDS   = ['pr welcome', 'pull request welcome', 'good first issue',
                      'help wanted', 'contributions welcome']
HARD_KEYWORDS      = ['核心数据结构', '并发设计', '语言特性限制',
                      'core data structure', 'concurrency', 'language limitation']

# ── 规则函数 ──────────────────────────────────────────────────────────────────

def score_value(ve: dict, me: dict) -> str:
    canonical_url = ve.get('canonical_impl_url') or ''
    peer_urls     = ve.get('peer_impl_urls') or []
    reactions     = ve.get('issue_reactions') or 0

    if not canonical_url:
        base = 'low'
    elif peer_urls and reactions >= REACTIONS_HIGH:
        base = 'high'
    else:
        base = 'medium'

    # maintainer_signal 修正
    signal = score_maintainer_signal(me)
    if signal == 'welcoming':
        base = {'low': 'medium', 'medium': 'high', 'high': 'high'}[base]
    return base


def score_difficulty(de: dict) -> str:
    canonical_url = de.get('canonical_impl_url') or ''
    loc           = de.get('canonical_impl_loc') or 0
    why_hard      = (de.get('why_hard') or '').lower()

    if not canonical_url:
        return 'high'

    if loc > LOC_HIGH:
        base = 'high'
    elif loc >= LOC_MEDIUM:
        base = 'medium'
    else:
        base = 'low'

    # why_hard 关键词上调一级
    if any(kw in why_hard for kw in [k.lower() for k in HARD_KEYWORDS]):
        base = {'low': 'medium', 'medium': 'high', 'high': 'high'}[base]
    return base


def score_urgency(ue: dict, source_type: str) -> str:
    cve_id          = ue.get('cve_id') or ''
    has_prod_signal = bool(ue.get('has_prod_signal'))
    has_workaround  = bool(ue.get('has_workaround'))

    if cve_id:
        return 'high'
    if has_prod_signal and not has_workaround:
        return 'high'
    if has_prod_signal and has_workaround:
        return 'medium'
    if not has_prod_signal and not has_workaround:
        return 'medium'
    return 'low'


def score_maintainer_signal(me: dict) -> str:
    similar_prs    = me.get('similar_prs') or []
    welcome_labels = me.get('welcome_labels') or []
    responses      = me.get('maintainer_responses') or []

    signals = []

    for pr in similar_prs:
        age = pr.get('age_days', 9999)
        if age > PR_AGE_DAYS:
            continue
        comment = (pr.get('maintainer_comment') or '').lower()
        if pr.get('merged'):
            signals.append(('welcoming', age))
        elif any(kw in comment for kw in REJECT_KEYWORDS):
            signals.append(('rejected', age))

    for resp in responses:
        body = (resp.get('body_quote') or '').lower()
        if any(kw in body for kw in WELCOME_KEYWORDS):
            signals.append(('welcoming', 0))
        elif any(kw in body for kw in REJECT_KEYWORDS):
            signals.append(('rejected', 0))

    if any(lbl.lower() in ['help wanted', 'good first issue'] for lbl in welcome_labels):
        signals.append(('welcoming', 0))

    if not signals:
        return 'unknown'

    # 取 age_days 最小（最新）的信号
    signals.sort(key=lambda x: x[1])
    return signals[0][0]


# ── 主流程 ────────────────────────────────────────────────────────────────────

def run():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT id, source_type,
               value_evidence, difficulty_evidence,
               urgency_evidence, maintainer_evidence
        FROM opportunities
        WHERE value IS NULL
    """).fetchall()

    print(f"待评分机会点：{len(rows)} 个")
    now = datetime.now(timezone.utc).isoformat()

    for row in rows:
        try:
            ve = json.loads(row['value_evidence']      or '{}')
            de = json.loads(row['difficulty_evidence'] or '{}')
            ue = json.loads(row['urgency_evidence']    or '{}')
            me = json.loads(row['maintainer_evidence'] or '{}')
        except json.JSONDecodeError:
            print(f"  SKIP {row['id']}: evidence JSON 解析失败")
            continue

        signal     = score_maintainer_signal(me)
        value      = score_value(ve, me)
        difficulty = score_difficulty(de)
        urgency    = score_urgency(ue, row['source_type'])
        status     = 'obsolete' if signal == 'rejected' else 'open'

        conn.execute("""
            UPDATE opportunities
            SET value=?, difficulty=?, urgency=?, maintainer_signal=?, status=?
            WHERE id=?
        """, (value, difficulty, urgency, signal, status, row['id']))

        print(f"  [{row['id']}] value={value} difficulty={difficulty} "
              f"urgency={urgency} signal={signal} status={status}")

    conn.commit()
    conn.close()
    print("评分完成")


if __name__ == '__main__':
    run()
```

- [ ] **Step 2: 验证**

```bash
# 插入测试 opportunity（含 evidence）
sqlite3 pipeline/data/pipeline.db "
  INSERT OR IGNORE INTO projects (id, name, url, language, stars, open_issues, status, source, first_seen_at, last_fetched_at)
  VALUES ('test/score', 'score', 'https://github.com/test/score', 'Go', 500, 5, 'active', 'anchor', datetime('now'), datetime('now'));
  INSERT OR IGNORE INTO project_meta (project_id, filter_status) VALUES ('test/score', 'keep');
  INSERT OR IGNORE INTO tasks (project_id, task_date, task_type, status, created_at)
  VALUES ('test/score', date('now'), 'bulk_first', 'done', datetime('now'));
  INSERT INTO opportunities
    (project_id, task_id, source_type, source_ref, title,
     value_evidence, difficulty_evidence, urgency_evidence, maintainer_evidence,
     status, first_seen_at, last_seen_at)
  VALUES (
    'test/score', last_insert_rowid(), 'feature_gap', 'canonical:Java/v1.0', 'Test gap',
    '{\"canonical_impl_url\":\"https://github.com/x/y/blob/main/Foo.java\",\"canonical_impl_loc\":150,\"peer_impl_urls\":[\"https://github.com/x/y-rust/blob/main/foo.rs\"],\"issue_reactions\":8}',
    '{\"canonical_impl_url\":\"https://github.com/x/y/blob/main/Foo.java\",\"canonical_impl_loc\":150}',
    '{\"has_prod_signal\":false,\"has_workaround\":true}',
    '{\"similar_prs\":[],\"welcome_labels\":[\"help wanted\"],\"maintainer_responses\":[]}',
    NULL, datetime('now'), datetime('now')
  );
"
python3 pipeline/stages/scoring.py
sqlite3 pipeline/data/pipeline.db "SELECT id, value, difficulty, urgency, maintainer_signal, status FROM opportunities WHERE project_id='test/score';"
# 期望：value=high（canonical+peer+reactions>=5，welcoming 上调）difficulty=low（loc=150）urgency=low（无 prod，有 workaround）signal=welcoming
# 清理
sqlite3 pipeline/data/pipeline.db "DELETE FROM opportunities WHERE project_id='test/score'; DELETE FROM tasks WHERE project_id='test/score'; DELETE FROM project_meta WHERE project_id='test/score'; DELETE FROM projects WHERE id='test/score';"
```

- [ ] **Step 3: Commit**

```bash
git add pipeline/stages/scoring.py
git commit -m "feat: add scoring.py rule-based evidence evaluator"
```
