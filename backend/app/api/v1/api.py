from fastapi import APIRouter

from app.api.v1.endpoints import applications, auth, career, code_projects, dashboard, discovery, interviews, jobs, learning, profiles, resumes, users

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(profiles.router)
router.include_router(resumes.router)
router.include_router(resumes.jobs_router)
router.include_router(career.router)
router.include_router(jobs.router)
router.include_router(discovery.router)
router.include_router(code_projects.router)
router.include_router(interviews.router)
router.include_router(learning.router)
router.include_router(applications.router)
router.include_router(dashboard.router)
