# Docker 与生产部署

## 服务结构

Caddy 同时提供 React 构建产物和反向代理。浏览器用同一个域名访问静态页面和 `/api/v1`。FastAPI 处理在线请求，Worker 消费后台队列，两者共享私有简历卷。MySQL 仅连接内部数据库网络。一次性的 `migrate` 容器先运行 `alembic upgrade head`，成功后 API 和 Worker 才启动。每个 Compose 项目有自己的命名卷。

| 服务 | 运行内容 | 端口 |
| --- | --- | --- |
| frontend | Caddy、React 静态文件、同源 API 代理 | 本机 8080，生产 80 和 443 |
| api | FastAPI、Cookie 鉴权和业务接口 | 容器内 8000 |
| worker | 已有 AI 队列和文件清理 | 无监听端口 |
| db | MySQL 8.4 | 容器内 3306 |
| migrate | 一次性 Alembic 迁移 | 无监听端口 |

参考 [Compose 服务配置](https://docs.docker.com/reference/compose-file/services/) 和 [Caddy 自动 HTTPS](https://caddyserver.com/docs/automatic-https)。

## 本地与测试

原生 PowerShell 启动方式见[开发文档](LOCAL_DEVELOPMENT.md#本地启动)。Docker 方式需要 Linux 容器引擎和 Compose 2.24.4 或更新版本。首次启动会拉取 Python、Node、Caddy 和 MySQL 基础镜像。Windows 上 Docker 管理自己的容器和数据库卷位置，项目目录仍在 D 盘。可在 Docker 的磁盘设置中查看其实际存储位置。

在项目根目录创建本地环境文件，并为数据库应用账号、管理员和 JWT 分别填写新随机值。示例留空，缺少必填配置时 Compose 会退出。可为每个值分别运行 `python -c "import secrets; print(secrets.token_hex(32))"`，并将输出直接填入本地文件。可选模型配置留空时仍能验证登录、档案、首页和本地业务。

```powershell
Copy-Item deploy/local/.env.example deploy/local/.env
docker compose --env-file deploy/local/.env config --quiet
docker compose --env-file deploy/local/.env up --build -d
docker compose --env-file deploy/local/.env ps -a
docker compose --env-file deploy/local/.env exec -T frontend caddy validate --config /etc/caddy/Caddyfile
```

打开 [容器版驾驶舱](http://127.0.0.1:8080/) 和 [就绪探针](http://127.0.0.1:8080/ready)。使用 8080，与现有 Vite 的 5173 以及本地 MySQL 端口互相独立。

测试环境从 `deploy/test/.env.example` 复制到同目录 `.env`，单独生成测试凭据。只使用合成数据，模型配置留空，并确认启动终端没有继承真实密钥。测试项目使用独立的名字、代理网段和 8081 端口。

```powershell
docker compose -p career-copilot-test --env-file deploy/test/.env up --build -d
```

## 配置项

| 变量 | 用途 |
| --- | --- |
| `APP_ENV` | 本地 development，测试 test。生产覆盖文件固定为 production，认证 Cookie 启用 Secure |
| `DB_NAME`、`DB_USER`、`DB_PASSWORD` | MySQL 应用账号和数据库，首次启动建库并授权 |
| `MYSQL_ROOT_PASSWORD` | 只注入数据库容器的管理员密码 |
| `JWT_SECRET`、`JWT_MINUTES` | 签发令牌的独立随机密钥与有效时间，默认 30 分钟 |
| `PUBLIC_HOST`、`IMAGE_TAG` | 生产域名和本次镜像版本。域名只填主机名，镜像标签用发布号或 Git 提交 |
| `LOCAL_PORT` | 本地 HTTP 端口，默认 8080，测试模板用 8081 |
| `PROXY_SUBNET`、`PROXY_IP`、`PROXY_DYNAMIC_RANGE` | 代理网络、Caddy 固定地址和动态地址池。固定地址需在同一子网内且不占用动态池。API 只信任该代理地址的转发头 |
| `DB_POOL_SIZE`、`DB_MAX_OVERFLOW`、`DB_POOL_RECYCLE_SECONDS` | 每个 Python 进程的连接池基数、临时连接上限和回收时间。生产示例为 5、5、1800 秒 |
| `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`、`TAVILY_API_KEY` | 可选外部服务。模型使用经授权的 HTTPS 服务，数据传输仍由业务确认流程控制 |
| `WORKER_CONCURRENCY`、`WORKER_HEARTBEAT_MAX_AGE` | 后台并发和就绪心跳超时，默认 2 个并发、300 秒 |

连接池用量按 API 与 Worker 进程数累加。生产模板各一个进程，应用最多约 20 条池连接，再留出迁移、备份、监控和管理连接。上线前通过 `SHOW GLOBAL STATUS LIKE 'Threads_connected';` 与 `SHOW VARIABLES LIKE 'max_connections';` 检查余量。将生产环境文件放在非公开位置并限制其读取权限。排错使用 `config --quiet`，展开配置会包含数据库密码和 API Key。

## 生产启动和更新

在 Linux 主机准备真实 DNS、可从公网到达的 80/443，以及可以续签 HTTPS 证书的 Caddy 持久卷。生产覆盖文件默认使用 `career-copilot-prod` 项目名，与本地卷分开。填好生产模板后，在根目录执行以下命令。全部检查先在预生产确认。存在历史数据的实例更新前先备份。需要维护窗口时，先停止前端、API 和 Worker，再执行部署，避免旧进程读写迁移中的表。

```bash
cp deploy/production/.env.example deploy/production/.env
chmod 600 deploy/production/.env
# 编辑上述文件，填写 PUBLIC_HOST、IMAGE_TAG 与独立的密码和密钥。
compose=(docker compose --env-file deploy/production/.env -f compose.yaml -f compose.production.yaml)
"${compose[@]}" config --quiet
"${compose[@]}" up --build -d
"${compose[@]}" ps -a
"${compose[@]}" logs --tail=80 migrate
"${compose[@]}" exec -T frontend caddy validate --config /etc/caddy/Caddyfile
"${compose[@]}" exec -T api alembic current
"${compose[@]}" exec -T api alembic check
```

从外部网络请求 `https://<域名>/health` 和 `https://<域名>/ready`，验证证书、HTTP 跳转 HTTPS、直接刷新 React 子路由，以及注册登录后可读取驾驶舱。检查 MySQL 和 API 的容器端口只在内部使用。应用账号的 MySQL 权限限定在本数据库，首次初始化和迁移需要该库的 DDL 权限。后续发版保留旧标签和镜像，避免覆盖可回滚版本。

已有库用 `SHOW INDEX FROM job_positions;`、`SHOW INDEX FROM job_applications;`、`SHOW INDEX FROM job_matches;` 核对索引，并用目标环境的代表性数据运行关键查询的 `EXPLAIN`。修改旧卷对应账号的密码时，需通过 MySQL 账号管理同步调整，变更初始化环境变量只影响新卷。

## 备份和恢复

数据库和私有简历文件必须成对归档。建议在低流量时段按日执行，并在每次生产变更前额外备份。备份目录存放在应用卷之外，配置加密的异机副本、访问权限和保留周期。包含简历的备份不可分享给无权人员。

```bash
"${compose[@]}" stop frontend api worker
bash deploy/backup.sh /secure/career-backups --env-file deploy/production/.env -f compose.yaml -f compose.production.yaml
# 只有成功输出目录且 SHA256SUMS 齐全的快照可用于恢复。
"${compose[@]}" start api worker frontend
```

同一窗口内禁止运行额外迁移或其他写入者。备份脚本检查业务进程已停止，再导出事务一致的 MySQL 逻辑快照并归档简历卷，最后写入校验文件。参考 [MySQL 逻辑备份](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html)。

恢复先在全新项目名和数据卷中演练，使用与快照匹配的应用版本。演练项目需使用独立代理网段，页面启动前确保与宿主机端口和其他实例无冲突。以下 `restore` 数组使用本地 Compose，以测试专用示例配置隔离恢复环境。只从已验证来源导入 SQL 和归档。

```bash
(cd "$backup" && sha256sum -c SHA256SUMS)
export PROXY_SUBNET=172.30.62.0/24 PROXY_IP=172.30.62.2 PROXY_DYNAMIC_RANGE=172.30.62.128/25 LOCAL_PORT=8082
restore=(docker compose -p career-restore --env-file deploy/test/.env -f compose.yaml)
"${restore[@]}" up -d --wait db
"${restore[@]}" build api
"${restore[@]}" exec -T db sh -ec 'MYSQL_PWD="$MYSQL_PASSWORD" exec mysql -u "$MYSQL_USER" "$MYSQL_DATABASE"' < "$backup/database.sql"
"${restore[@]}" run --no-deps --rm -T --entrypoint tar api -xzf - --no-same-owner -C /data/resumes < "$backup/resumes.tar.gz"
"${restore[@]}" run --no-deps --rm -T migrate alembic current
```

检查数据库版本、关键表行数、简历文件以及测试账号登录，再决定切流。生产真实资料的恢复演练使用受控环境和独立凭据，关闭外部 AI 配置。已恢复的等待中任务要人工核对后再开启联网 Worker。

## 日志、监控和回滚

- `/health` 检查 API 进程，`/ready` 检查数据库和完整 Worker 心跳。监控连续失败和 5xx，并在相同时间段查 `docker compose logs --tail=100 api worker frontend`。应用失败日志带请求 ID。生产关闭 Uvicorn 访问日志，避免把查询参数作为常规日志保留。
- 用 `docker stats --no-stream`、`docker system df` 和主机磁盘监控观察 CPU、内存、磁盘与数据库卷。服务日志滚动保留。接入现有告警渠道后测试 503、CPU/内存和磁盘阈值，也检查每日备份是否成功。
- `migrate` 退出非零时先查其日志和 `alembic current`。API 正常但 `/ready` 返回 503 时查看数据库检查结果和 Worker 日志。Caddy 证书失败时核对 DNS、IPv4/IPv6 和 80/443。浏览器登录后仍跳回登录页时检查公网 HTTPS、Cookie 和同源路径。
- 应用回滚前在数据库副本上验证旧镜像读写当前表结构。兼容时可暂时覆盖 `IMAGE_TAG`，用 `up -d --no-deps --no-build api worker frontend` 切换到保留的旧镜像。涉及不兼容迁移时在隔离环境恢复配对的数据库与文件，验收后再切换。恢复旧快照会丢失快照之后的写入，切换前必须确认影响范围。
