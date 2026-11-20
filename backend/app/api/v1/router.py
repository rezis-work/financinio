from fastapi import APIRouter

from app.api.v1 import (
    accounts,
    advisor,
    auth,
    budgets,
    categories,
    dashboard,
    ingestion,
    recurring,
    transactions,
    wealth,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(accounts.router)
api_router.include_router(categories.router)
api_router.include_router(transactions.router)
api_router.include_router(dashboard.router)
api_router.include_router(ingestion.router)
api_router.include_router(budgets.router)
api_router.include_router(recurring.router)
api_router.include_router(wealth.router)
api_router.include_router(advisor.router)
