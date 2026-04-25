A 类和 B 类是互斥的。
  - A 类 = 有明确原版的移植版/替代实现
  - B 类 = 原创项目（无明确原版）
A，B都发生在Stage 3: Filter阶段；满足A或B的，才进入Stage 4: Analyze。
Stage 4: Analyze 阶段如何区分，当前项目 符合A还是B呢？需要针对性的对A、B做不同维度的深度分析吧？目前只有A。


```
sqlite3 data/pipeline.db "
  SELECT p.id, p.language, p.stars, a.overall_score, a.canonical_gap                                                   
  FROM projects p
  JOIN analyses a ON a.project_id = p.id
  WHERE p.status = 'analyzed'
  ORDER BY a.overall_score DESC;
  "
```


```
sqlite3 data/pipeline.db "SELECT t.id, t.project_id, t.task_date, t.status, t.started_at, t.finished_at FROM tasks t WHERE t.status = 'done' ORDER BY t.finished_at DESC LIMIT 5;"

sqlite3 data/pipeline.db "SELECT t.id,t.project_id,t.finished_at,COUNT(o.id) as opp_count,GROUP_CONCAT(DISTINCT o.source_type) as types,GROUP_CONCAT(DISTINCT o.value) as value_levels, SUM(CASE WHEN o.source_type = 'feature_gap' THEN 1 ELSE 0 END) as feature_gaps, SUM(CASE WHEN json_extract(o.value_evidence, '$.canonical_impl_url') != '' THEN 1 ELSE 0 END) as canon_ok FROM tasks t LEFT JOIN opportunities o ON o.project_id = t.project_id AND o.status = 'open' WHERE t.status = 'done' GROUP BY t.id, t.project_id, t.finished_at ORDER BY t.finished_at DESC LIMIT 10;"
```