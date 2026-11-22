# FastAPI 学习手册

## 模块 2 · 文件上传

### 业务与场景

求职者上传有文本层的 PDF 或 DOCX。系统先本地保存和解析，用户核对片段后才触发模型提取。用于从简历原文构建可追溯的证据。

### 技术与代码路径

[职业画像页](../../frontend/src/pages/CareerProfilePage.tsx) → [career.ts](../../frontend/src/services/career.ts) → [resumes.py 端点](../../backend/app/api/v1/endpoints/resumes.py) → [上传落盘](../../backend/app/services/resume_storage.py)、[解析器](../../backend/app/services/resume_parser.py)、[后台 Worker](../../backend/app/resume_worker.py)。FastAPI 根据方法和路径选处理函数，通过类型声明提取文件、用户和数据库 Session。`UploadFile` 是请求中的文件对象，浏览器以 `FormData` 发送，同时由浏览器附加 multipart 边界。

### 核心代码与逐段解释

[源码 · resumes.py:21](../../backend/app/api/v1/endpoints/resumes.py#L21)

```python
@router.post("/upload", status_code=201, response_model=ResumeRead)
def upload_resume(file: Annotated[UploadFile, File()], user: CurrentUser, db: Database):
    return create_resume(db, user.id, file)
```

装饰器指定方法、状态码和响应字段。FastAPI 从表单中获得 `file`，从依赖中取得用户。以认证主体创建记录，可避免前端指派归属。

[源码 · resume_storage.py:25](../../backend/app/services/resume_storage.py#L25)

```python
    key = uuid4().hex
    destination = storage_path(key)
    size = 0
    with upload.file as stream:
        try:
            with destination.open("xb") as target:
                while chunk := stream.read(64 * 1024):
                    size += len(chunk)
                    if size > MAX_FILE_BYTES:
                        raise ApiError(413, "FILE_TOO_LARGE", "简历文件最多 10 MB")
                    target.write(chunk)
            if not size:
                raise ApiError(422, "EMPTY_RESUME_FILE", "简历文件为空")
            with destination.open("rb") as stored:
                validate_file(stored, file_type)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
    return key, name, file_type, size
```

私有文件以随机键标识，原文件名用于显示。每次读 64 KiB，累计大小，到 10 MiB 上限就拒绝。文件写完后检查签名和类型；失败路径清理文件。上传端点还受外层请求大小限制。数据库记录写入失败也有服务层文件清理。

### 输入、输出与完整流程

输入表单文件 → 扩展名、长度和内容初步检查 → 随机键落盘 → 保存 `Resume` 元数据并返回 201 → 浏览器提交本地解析任务 → Worker 用 PDF 文本层或 DOCX 段落和表格抽取内容 → 保存有块编号、位置和文本的版本 → 浏览器核对、隐藏敏感块并主动确认 → 才发送结构化提取。PDF 页数和解压资源、DOCX ZIP 结构、总块数及文字长度均另有限制。

### 设计原因与常见异常

文件名和浏览器声明类型都可能有误，所以还要看内容签名和文档结构。将解析任务与 AI 提取分开后，用户可以看到和选择要发送的范围。常见异常为 413 超上限、415 不支持或扩展名不符、无文字层、加密 PDF、损坏文档、文件丢失，以及重复任务或版本冲突。无文字层时可改用含文字的文件，当前解析不含 OCR。

### 面试、练习和参考答案

- [技术面试 · 文件上传](CODE_INTERVIEW_QUESTIONS.md#文件上传)
- [练习 M02](CODE_EXERCISES.md#m02-文件上传) · [独立核对答案](CODE_EXERCISES_ANSWERS.md#m02-文件上传)
