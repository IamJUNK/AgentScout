## 问题一：WAL 是否允许多个写入者同时写入？

**不允许。** SQLite 官方文档明确指出，WAL 模式下同一时刻只能有一个写入者。

官方原文：

> "Writers merely append new content to the end of the WAL file. Because writers do nothing that would interfere with the actions of readers, writers and readers can run at the same time. **However, since there is only one WAL file, there can only be one writer at a time.**"
> [证据 E2d66cd6a9320](https://www.sqlite.org/wal.html)

WAL 带来的并发优势是**读写互不阻塞**，而非多写并发：

> "writers do not block readers and readers do not block writers."
> [证据 Eb6313e658b8e](https://www.sqlite.org/wal.html)

因此，WAL 允许多个**读取者**与一个**写入者**并发，但写入者之间仍是串行的。

## 问题二：开启 WAL 后 SQLITE_BUSY 是否仍可能发生？

**仍可能发生。** 官方文档专门设有章节说明这一点。

官方原文：

> "The second advantage of WAL-mode is that writers do not block readers and readers do not block writers. This is mostly true. **But there are some obscure cases where a query against a WAL-mode database can return SQLITE_BUSY, so applications should be prepared for that happenstance.**"
> [证据 E07344e57d9ec](https://www.sqlite.org/wal.html)

文档给出的具体场景之一是**最后一个连接关闭时的清理过程**：

> "When the last connection to a particular database is closing, that connection will acquire an exclusive lock for a short time while it cleans up the WAL and shared-memory files. **If a separate attempt is made to open and query the database while the first connection is still in the middle of its cleanup process, the second connection might get an SQLITE_BUSY error.**"
> [证据 E2d66cd6a9320](https://www.sqlite.org/wal.html)

另一个场景是**崩溃恢复**：若最后一个连接崩溃，第一个新连接打开数据库时会启动恢复过程并持有排他锁，此时其他连接查询会得到 SQLITE_BUSY（该段为论坛帖转引官方文档内容）：

> "If the last connection to a database crashed, then the first new connection to open the database will start a recovery process. An exclusive lock is held during recovery. So if a third database connection tries to jump in and query while the second connection is running recovery, the third connection will get an SQLITE_BUSY error."
> [证据 E1fd73a7fb547](https://sqlite.org/forum/forumpost/4d93f49a04?t=h&unf=)

## 证据与限制说明

- 两问的核心结论均来自 SQLite 官方文档页面 `sqlite.org/wal.html`（证据 E2d66cd6a9320、E07344e57d9ec、Eb6313e658b8e），可直接支撑回答。
- 恢复场景的原文（E1fd73a7fb547）来自 SQLite 用户论坛帖子，该帖转引了官方文档内容，**并非直接抓取自官方文档页面**；其表述与官方文档一致，但严格来说属于二手转引，建议以官方 `wal.html` 原文为准。
- 证据中未包含官方文档对 SQLITE_BUSY 全部触发条件的完整列举，上述仅为文档明确提及的部分场景；实际应用中还可能存在其他边界情况，本回答未作穷尽性断言。