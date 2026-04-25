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