## 问题一：WAL 模式是否允许多个写入者同时写入？

根据本次取证到的证据，**不支持“WAL 模式允许多个写入者同时写入”**；相反，证据表明 WAL 模式下写入者之间会互相阻塞。

- 一条来自 SQLite 用户论坛的片段明确写道：“Having said that, in SQLite's WAL mode readers do use a snapshot; writers block each other.”（在 SQLite 的 WAL 模式下，读者使用快照；写入者互相阻塞。）[证据 E466c832330bc](https://sqlite.org/forum/info/b4e8b29ae409cd198652c6b7e70b53b702f269e67e1d2573d627feeba37bbf85) 同一论坛的另一处片段给出了完全相同的表述 [证据 E6599b851e1f0](https://sqlite.org/forum/info/b4e8b29ae409cd198652c6b7e70b53b702f269e67e1d2573d627feeba37bbf85)。
- 另有论坛帖子转述了 WAL 的持久性特征：“The WAL journaling mode uses a write-ahead log instead of a rollback journal to implement transactions. The WAL journaling mode is persistent; after being set it stays in effect across multiple database connections and after closing and reopening the database.”（WAL 日志模式使用预写日志而非回滚日志来实现事务；该模式是持久的，设置后在多个数据库连接之间以及关闭并重新打开数据库后仍然有效。）[证据 E18f35134a079](https://sqlite.org/forum/forumpost/c4dbf6ca17) 该帖同时给出了官方文档地址 https://www.sqlite.org/wal.html [证据 E41073bac847b](https://sqlite.org/forum/info/b4e8b29ae409cd198652c6b7e70b53b702f269e67e1d2573d627feeba37bbf85)，但本次取证未抓取到该官方页面正文。

> 限制：上述支持性表述均来自 `sqlite.org/forum` 下的用户论坛帖子，属于用户论坛内容，不自动等同于官方文档；本次取证未获取到 `sqlite.org/wal.html` 官方文档中关于“同一时间只能有一个写入者”的原文，因此该结论目前只有论坛证据支撑，缺少官方文档原文引用。

## 问题二：开启 WAL 后 SQLITE_BUSY 是否仍可能发生？

根据本次取证到的证据，**开启 WAL 后 SQLITE_BUSY 仍可能发生**，至少在一个已取证的具体场景（崩溃恢复）中会发生。

- 论坛帖子引用了官方文档锚点 `wal.html#sometimes_queries_return_sqlite_busy_in_wal_mode`，并转述其内容：“If the last connection to a database crashed, then the first new connection to open the database will start a recovery process. An exclusive lock is held during recovery. So if a third database connection tries to jump in and query while the second connection is running recovery, the third connection will get an SQLITE_BUSY error.”（如果最后一个数据库连接崩溃，第一个新打开的连接将启动恢复过程；恢复期间持有排他锁。因此，如果第三个连接在第二个连接执行恢复时尝试查询，第三个连接将得到 SQLITE_BUSY 错误。）[证据 E0a2c6b7c5940](https://sqlite.org/forum/forumpost/4d93f49a04?raw=)
- 同一帖子在 WAL 语境下明确指向官方文档：“Something similar applies in WAL mode, according to the [documentation](https://www.sqlite.org/wal.html#sometimes_queries_return_sqlite_busy_in_wal_mode):” [证据 Ee790f355d0d8](https://sqlite.org/forum/forumpost/4d93f49a04?raw=) 该表述在另一 URL 变体下重复出现 [证据 Eff0997296273](https://sqlite.org/forum/forumpost/4d93f49a04?t=h&unf=)。

> 限制：上述关于 SQLITE_BUSY 的原文引用来自用户论坛对官方文档的转述，本次取证未直接抓取 `sqlite.org/wal.html` 官方页面正文；此外，证据仅覆盖“崩溃恢复期间持排他锁”这一种原因，未覆盖 WAL 模式下 SQLITE_BUSY 的其他可能原因（如检查点、写锁竞争），因此不能据此断言已穷尽所有情形。

## 总体证据缺口

> 限制：本次取证所选证据全部来自 `sqlite.org/forum` 用户论坛，未包含 `sqlite.org/wal.html` 官方文档正文；两个问题的结论目前均依赖论坛转述或论坛用户表述，缺少官方文档原文的直接引用。