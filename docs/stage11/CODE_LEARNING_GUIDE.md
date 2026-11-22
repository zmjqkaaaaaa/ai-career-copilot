# AI Career Copilot 核心代码学习手册

阶段 11.5 · 从界面操作反查 Python、FastAPI、SQL 与 LLM

## 从一次真实操作开始

选择一份已确认的简历和一份已确认的 JD，在岗位匹配页提交。先用浏览器 Network 找到请求，再回到仓库按这个顺序查。你已经会 Python 和 SQL，可以把 React 当成发请求和显示结果的界面层。

1. [前端页面](../../frontend/src/pages/JobMatchingPage.tsx) 准备用户选择，[jobs.ts](../../frontend/src/services/jobs.ts) 封装请求。
2. [岗位路由](../../backend/app/api/v1/endpoints/jobs.py) 确认身份、岗位版本和输入，在服务层取候选人证据。
3. [规则评分](../../backend/app/services/job_matching_service.py) 返回状态、分值及覆盖率，[岗位模型](../../backend/app/models/job.py) 保存报告和差距。
4. 在页面换一个已确认的简历版本，再匹配同一份 JD。独立说明哪些输入变了，哪些结果可以比较，以及为什么仅凭分数不足以解释改进。练习使用合成材料。

## 八个模块的阅读地图

| 顺序 | 模块 | 学完后能够解释 |
| --- | --- | --- |
| 1 | [用户认证](PYTHON_BACKEND_GUIDE.md#模块-1--用户认证) | 登录与业务数据归属分别检查什么 |
| 2 | [文件上传](FASTAPI_GUIDE.md#模块-2--文件上传) | 文件如何收取、验证、落盘、解析，以及何时外发 |
| 3 | [LLM 接入](LLM_APPLICATION_GUIDE.md#模块-3--llm-接入) | 一次模型调用如何配置、发送、计量和失败 |
| 4 | [结构化输出](LLM_APPLICATION_GUIDE.md#模块-4--结构化输出) | JSON 格式、Pydantic 契约和证据校验各负责什么 |
| 5 | [岗位匹配](LLM_APPLICATION_GUIDE.md#模块-5--岗位匹配) | JD 模型解析和规则评分如何衔接 |
| 6 | [GitHub 项目理解](PYTHON_BACKEND_GUIDE.md#模块-6--github-项目理解) | Git 提交、代码证据和讲解引用如何对应 |
| 7 | [模拟面试](PYTHON_BACKEND_GUIDE.md#模块-7--模拟面试) | 模型给建议与后端推进会话各发生在哪一步 |
| 8 | [数据库](SQL_DATABASE_GUIDE.md#模块-8--数据库) | 用真实表解释 ORM、JOIN、事务、索引和迁移 |

每个模块都附短代码节录、逐段解释、输入输出、执行流程、设计理由和常见异常。代码块按文件和符号取自当前项目。SQL 演练、示意数据与修改练习另行标记。完整架构和 ER 图参见 [系统架构](SYSTEM_ARCHITECTURE.md) 与 [数据库设计](DATABASE_DESIGN.md)。

## 如何自测

- 先独立完成 [题册](CODE_EXERCISES.md)。每个模块有 5 道基础、5 道读代码、3 道场景和 2 道修改题。修改题可用伪代码或写在独立练习区。
- 完成一组再看 [参考答案](CODE_EXERCISES_ANSWERS.md)，从“说出定义”进阶到“指出项目中的函数、说明取舍并给出反例测试”。
- 用 [技术面试问题](CODE_INTERVIEW_QUESTIONS.md) 做口头演练。把结论落实到一个文件、一种输入和一个失败例子。
- 数据库演练用合成数据和独立测试库。LLM 演练先使用固定响应，模型或外部服务是否可用另做专项验收。

课程理解等级以实际作答衡量。阅读文档后可自评为已接触，能沿项目指出代码位置并解释一次完整调用才达到 Level 3；还能提出有验证方法的取舍才达到 Level 4。
