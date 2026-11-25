from fastapi import APIRouter

from app.api.v1 import (
    account_data,
    accounts,
    admin,
    advisor,
    auth,
    budgets,
    categories,
    dashboard,
    emails,
    ingestion,
    markets,
    news,
    recurring,
    transactions,
    voice,
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
api_router.include_router(markets.router)
api_router.include_router(news.router)
api_router.include_router(voice.router)
api_router.include_router(emails.router)
api_router.include_router(advisor.router)
api_router.include_router(account_data.router)
api_router.include_router(admin.router)
