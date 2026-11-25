import html
import logging
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.finance import Category, Transaction
from app.models.planning import FinancialGoal, NetWorthSnapshot, RecurringItem
from app.models.user import User
from app.services.financial_health_service import compute_financial_health_profile
from app.services.planning_service import enrich_goal, get_net_worth_overview

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


def _fmt_money(amount: Decimal | float | str, currency: str) -> str:
    val = float(Decimal(str(amount)))
    ccy = (currency or "USD").upper()
    sym = {"USD": "$", "EUR": "€", "GBP": "£", "GEL": "₾"}.get(ccy, f"{ccy} ")
    sign = "-" if val < 0 else ""
    abs_val = abs(val)
    if sym.endswith(" "):
        return f"{sign}{sym}{abs_val:,.2f}"
    return f"{sign}{sym}{abs_val:,.2f}"


def _esc(text: Any) -> str:
    return html.escape(str(text or ""))


def _wrap_email_shell(
    *,
    badge: str,
    title: str,
    subtitle: str,
    preheader: str,
    body_html: str,
    frontend_url: str,
) -> str:
    base = frontend_url.rstrip("/")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{_esc(title)}</title>
</head>
<body style="margin:0;padding:0;background-color:#020617;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">{_esc(preheader)}</div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#020617;padding:28px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;background-color:#0f172a;border:1px solid #1e293b;border-radius:20px;overflow:hidden;">
          <!-- Header -->
          <tr>
            <td style="padding:28px 28px 20px 28px;background:linear-gradient(135deg,#064e3b 0%,#0f172a 55%,#0c4a6e 100%);border-bottom:1px solid #1e293b;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                <tr>
                  <td>
                    <span style="display:inline-block;padding:4px 10px;border-radius:999px;background-color:rgba(16,185,129,0.16);border:1px solid rgba(52,211,153,0.35);color:#6ee7b7;font-size:11px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;">
                      {_esc(badge)}
                    </span>
                  </td>
                  <td align="right" style="color:#94a3b8;font-size:12px;font-weight:700;letter-spacing:0.02em;">
                    FINANCINIO
                  </td>
                </tr>
              </table>
              <h1 style="margin:14px 0 6px 0;font-size:24px;line-height:1.25;color:#ffffff;font-weight:800;letter-spacing:-0.02em;">
                {_esc(title)}
              </h1>
              <p style="margin:0;font-size:13px;line-height:1.5;color:#cbd5e1;">
                {_esc(subtitle)}
              </p>
            </td>
          </tr>

          <!-- Main Body -->
          <tr>
            <td style="padding:24px 28px;">
              {body_html}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:18px 28px 24px 28px;background-color:#020617;border-top:1px solid #1e293b;text-align:center;">
              <p style="margin:0 0 8px 0;font-size:11px;color:#64748b;line-height:1.5;">
                Sent by <strong style="color:#94a3b8;">Luna · Financinio Personal CFO</strong>. Educational financial insights grounded in your private ledger.
              </p>
              <a href="{base}/settings" style="color:#34d399;font-size:11px;text-decoration:none;font-weight:600;">
                Manage Email Digest Preferences →
              </a>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


async def build_weekly_briefing_digest(
    db: AsyncSession, user: User
) -> dict[str, Any]:
    """Build Monday Morning 'Luna CFO Weekly Briefing' digest from real Neon ledger data."""
    settings = get_settings()
    today = date.today()
    week_ago = today - timedelta(days=7)
    next_week = today + timedelta(days=7)
    ccy = user.base_currency

    health = await compute_financial_health_profile(db, user)
    hs = health["health_score"]
    cf = health["cash_flow_ratios"]

    txs = (
        await db.scalars(
            select(Transaction).where(
                Transaction.user_id == user.id,
                Transaction.parent_transaction_id.is_(None),
                Transaction.is_transfer.is_(False),
                Transaction.occurred_at >= week_ago,
                Transaction.occurred_at <= today,
            )
        )
    ).all()

    week_inflow = Decimal("0.00")
    week_outflow = Decimal("0.00")
    for tx in txs:
        if tx.direction == "inflow":
            week_inflow += tx.base_amount
        else:
            week_outflow += tx.base_amount
    week_net = week_inflow - week_outflow

    recurring_rows = (
        await db.scalars(
            select(RecurringItem)
            .where(
                RecurringItem.user_id == user.id,
                RecurringItem.is_active.is_(True),
                RecurringItem.direction == "outflow",
                RecurringItem.next_due_date <= next_week,
            )
            .order_by(RecurringItem.next_due_date.asc())
            .limit(6)
        )
    ).all()

    upcoming_bills = []
    for item in recurring_rows:
        days_left = (item.next_due_date - today).days
        if days_left < 0:
            due_label = f"Overdue {abs(days_left)}d"
            due_color = "#fb7185"
        elif days_left == 0:
            due_label = "Due Today"
            due_color = "#fbbf24"
        else:
            due_label = f"In {days_left}d"
            due_color = "#94a3b8"
        upcoming_bills.append(
            {
                "merchant": item.merchant_name,
                "amount": _fmt_money(item.amount, item.currency),
                "due_date": item.next_due_date.isoformat(),
                "due_label": due_label,
                "due_color": due_color,
            }
        )

    first_name = (user.full_name or "there").split()[0]
    net_color = "#34d399" if week_net >= 0 else "#fb7185"
    score_color = "#34d399" if hs["overall"] >= 75 else ("#fbbf24" if hs["overall"] >= 50 else "#fb7185")

    bills_html = ""
    if upcoming_bills:
        rows_html = "".join(
            f"""<tr>
              <td style="padding:10px 12px;border-bottom:1px solid #1e293b;color:#f8fafc;font-size:13px;font-weight:600;">{_esc(b['merchant'])}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #1e293b;color:{b['due_color']};font-size:12px;font-weight:600;">{_esc(b['due_label'])}</td>
              <td align="right" style="padding:10px 12px;border-bottom:1px solid #1e293b;color:#f8fafc;font-size:13px;font-weight:700;font-family:monospace;">{_esc(b['amount'])}</td>
            </tr>"""
            for b in upcoming_bills
        )
        bills_html = f"""
        <div style="margin-top:20px;">
          <div style="font-size:11px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;color:#94a3b8;margin-bottom:8px;">
            Bills Due This Week ({len(upcoming_bills)})
          </div>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#020617;border:1px solid #1e293b;border-radius:12px;overflow:hidden;">
            {rows_html}
          </table>
        </div>"""
    else:
        bills_html = """
        <div style="margin-top:20px;padding:14px 16px;background-color:#020617;border:1px solid #1e293b;border-radius:12px;font-size:13px;color:#94a3b8;">
          No recurring bills due in the next 7 days — clear cash-flow runway ahead.
        </div>"""

    luna_q = quote(
        "Walk me through my Monday Morning CFO Weekly Briefing: summarize my last 7 days cash flow, upcoming bills this week, and give me my #1 concrete money move today."
    )
    cta_url = f"{settings.frontend_url.rstrip('/')}/advisor?q={luna_q}"

    body_html = f"""
      <p style="margin:0 0 18px 0;font-size:14px;color:#cbd5e1;line-height:1.6;">
        Good morning, <strong style="color:#ffffff;">{_esc(first_name)}</strong> — here is your 30-second Monday CFO snapshot for the last 7 days.
      </p>

      <!-- 2x2 KPI Grid -->
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
        <tr>
          <td width="50%" style="padding:0 6px 10px 0;">
            <div style="padding:14px 16px;background-color:#020617;border:1px solid #1e293b;border-radius:14px;">
              <div style="font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.05em;">7-Day Net Cash Flow</div>
              <div style="font-size:20px;font-weight:800;color:{net_color};margin-top:4px;font-family:monospace;">
                {'+' if week_net > 0 else ''}{_esc(_fmt_money(week_net, ccy))}
              </div>
              <div style="font-size:11px;color:#64748b;margin-top:4px;">
                In {_esc(_fmt_money(week_inflow, ccy))} · Out {_esc(_fmt_money(week_outflow, ccy))}
              </div>
            </div>
          </td>
          <td width="50%" style="padding:0 0 10px 6px;">
            <div style="padding:14px 16px;background-color:#020617;border:1px solid #1e293b;border-radius:14px;">
              <div style="font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.05em;">Financial Health Score</div>
              <div style="font-size:20px;font-weight:800;color:{score_color};margin-top:4px;font-family:monospace;">
                {hs['overall']}/100 <span style="font-size:12px;color:#cbd5e1;font-family:sans-serif;">({hs['grade']})</span>
              </div>
              <div style="font-size:11px;color:#64748b;margin-top:4px;">
                Runway: {cf['emergency_runway_months']} mo · Savings {cf['savings_rate_pct']}%
              </div>
            </div>
          </td>
        </tr>
      </table>

      <!-- Safe to Spend Strip -->
      <div style="padding:14px 16px;background-color:rgba(6,182,212,0.08);border:1px solid rgba(34,211,238,0.28);border-radius:14px;margin-top:4px;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
          <tr>
            <td style="font-size:12px;color:#a5f3fc;font-weight:600;">Remaining Safe-to-Spend This Month</td>
            <td align="right" style="font-size:17px;font-weight:800;color:#ffffff;font-family:monospace;">
              {_esc(_fmt_money(cf['safe_to_spend_remaining_this_month'], ccy))}
            </td>
          </tr>
        </table>
      </div>

      {bills_html}

      <!-- Luna's #1 Priority Action -->
      <div style="margin-top:20px;padding:16px 18px;background:linear-gradient(135deg,rgba(16,185,129,0.12),rgba(139,92,246,0.10));border:1px solid rgba(52,211,153,0.3);border-radius:14px;">
        <div style="font-size:11px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;color:#6ee7b7;margin-bottom:6px;">
          Luna's #1 Move This Week
        </div>
        <div style="font-size:14px;color:#ffffff;line-height:1.55;font-weight:500;">
          {_esc(hs['top_priority'])}
        </div>
      </div>

      <!-- Primary CTA -->
      <div style="margin-top:24px;text-align:center;">
        <a href="{cta_url}" style="display:inline-block;padding:13px 26px;background-color:#10b981;color:#020617;font-size:14px;font-weight:800;text-decoration:none;border-radius:12px;">
          Open Briefing in Luna →
        </a>
      </div>
    """

    subject = f"Luna Weekly Briefing · Health {hs['overall']}/100 · Net {'+' if week_net >= 0 else ''}{_fmt_money(week_net, ccy)}"
    preheader = f"Safe-to-spend: {_fmt_money(cf['safe_to_spend_remaining_this_month'], ccy)} · {len(upcoming_bills)} bills due this week."

    return {
        "digest_type": "weekly",
        "subject": subject,
        "preheader": preheader,
        "html": _wrap_email_shell(
            badge="Monday CFO Briefing",
            title="Your Weekly Financial Pulse",
            subtitle=f"{week_ago.strftime('%b %d')} – {today.strftime('%b %d, %Y')} · Prepared by Luna Personal CFO",
            preheader=preheader,
            body_html=body_html,
            frontend_url=settings.frontend_url,
        ),
        "metrics": {
            "week_inflow": f"{week_inflow:.2f}",
            "week_outflow": f"{week_outflow:.2f}",
            "week_net": f"{week_net:.2f}",
            "health_score": hs["overall"],
            "safe_to_spend": cf["safe_to_spend_remaining_this_month"],
            "upcoming_bills_count": len(upcoming_bills),
        },
    }


async def build_monthly_wrapped_digest(
    db: AsyncSession, user: User
) -> dict[str, Any]:
    """Build Monthly 'CFO Wrapped' Financial Report (1st of every month)."""
    settings = get_settings()
    today = date.today()
    ccy = user.base_currency

    # Report on the completed previous month when near start of month (days 1-10), or current month otherwise
    if today.day <= 10:
        last_day_prev = date(today.year, today.month, 1) - timedelta(days=1)
        period_start = date(last_day_prev.year, last_day_prev.month, 1)
        period_end = last_day_prev
    else:
        period_start = date(today.year, today.month, 1)
        period_end = today

    period_label = period_start.strftime("%B %Y")

    categories = {
        c.id: c.name
        for c in (await db.scalars(select(Category).where(Category.user_id == user.id))).all()
    }
    txs = (
        await db.scalars(
            select(Transaction).where(
                Transaction.user_id == user.id,
                Transaction.parent_transaction_id.is_(None),
                Transaction.is_transfer.is_(False),
                Transaction.occurred_at >= period_start,
                Transaction.occurred_at <= period_end,
            )
        )
    ).all()

    month_in = Decimal("0.00")
    month_out = Decimal("0.00")
    cat_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for tx in txs:
        if tx.direction == "inflow":
            month_in += tx.base_amount
        else:
            month_out += tx.base_amount
            cname = categories.get(tx.category_id, "Uncategorized") if tx.category_id else "Uncategorized"
            cat_totals[cname] += tx.base_amount

    month_net = month_in - month_out
    savings_rate = round(float((month_net / month_in) * Decimal("100")), 1) if month_in > 0 else 0.0

    top_3_cats = sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)[:3]

    nw = await get_net_worth_overview(db, user)
    snaps = (
        await db.scalars(
            select(NetWorthSnapshot)
            .where(NetWorthSnapshot.user_id == user.id)
            .order_by(NetWorthSnapshot.snapshot_date.desc())
            .limit(2)
        )
    ).all()
    nw_delta = Decimal("0.00")
    if len(snaps) >= 2:
        nw_delta = snaps[0].net_worth - snaps[1].net_worth
    elif len(snaps) == 1:
        nw_delta = nw.current_net_worth - snaps[0].net_worth

    goals = (
        await db.scalars(select(FinancialGoal).where(FinancialGoal.user_id == user.id))
    ).all()
    enriched_goals = sorted([enrich_goal(g) for g in goals], key=lambda g: g.progress_pct, reverse=True)
    milestones_hit = [g for g in enriched_goals if g.progress_pct >= 50.0]

    # Biggest Win narrative
    if savings_rate >= 20:
        biggest_win = f"You saved {savings_rate}% of your income in {period_label} — beating the 20% CFP wealth-building benchmark!"
    elif milestones_hit:
        top_g = milestones_hit[0]
        biggest_win = f"Your '{top_g.name}' goal reached {top_g.progress_pct:.0f}% funded ({_fmt_money(top_g.current_amount, ccy)} / {_fmt_money(top_g.target_amount, ccy)})!"
    elif month_net > 0:
        biggest_win = f"You finished {period_label} cash-flow positive by +{_fmt_money(month_net, ccy)}."
    else:
        biggest_win = f"You tracked {len(txs)} transactions in {period_label} — consistent tracking is the #1 habit of high-net-worth builders."

    # Render Top 3 Categories bars
    cat_bars_html = ""
    if top_3_cats and month_out > 0:
        bar_items = []
        colors = ["#10b981", "#22d3ee", "#a78bfa"]
        for idx, (cname, cval) in enumerate(top_3_cats):
            pct = min(100, int(round(float((cval / month_out) * Decimal("100")))))
            bar_items.append(
                f"""<div style="margin-bottom:12px;">
                  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:5px;">
                    <tr>
                      <td style="font-size:13px;color:#f8fafc;font-weight:600;">{_esc(cname)}</td>
                      <td align="right" style="font-size:12px;color:#cbd5e1;font-family:monospace;">{_esc(_fmt_money(cval, ccy))} ({pct}%)</td>
                    </tr>
                  </table>
                  <div style="height:7px;background-color:#1e293b;border-radius:999px;overflow:hidden;">
                    <div style="height:7px;width:{max(6, pct)}%;background-color:{colors[idx % 3]};border-radius:999px;"></div>
                  </div>
                </div>"""
            )
        cat_bars_html = f"""
        <div style="margin-top:20px;padding:16px 18px;background-color:#020617;border:1px solid #1e293b;border-radius:14px;">
          <div style="font-size:11px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;color:#94a3b8;margin-bottom:12px;">
            Top 3 Spending Categories
          </div>
          {''.join(bar_items)}
        </div>"""

    # Render Goal Milestones
    goals_html = ""
    if enriched_goals:
        g_rows = "".join(
            f"""<tr>
              <td style="padding:10px 12px;border-bottom:1px solid #1e293b;color:#f8fafc;font-size:13px;font-weight:600;">{_esc(g.name)}</td>
              <td align="right" style="padding:10px 12px;border-bottom:1px solid #1e293b;color:#6ee7b7;font-size:12px;font-weight:700;font-family:monospace;">{g.progress_pct:.0f}%</td>
              <td align="right" style="padding:10px 12px;border-bottom:1px solid #1e293b;color:#94a3b8;font-size:12px;font-family:monospace;">{_esc(_fmt_money(g.current_amount, ccy))} / {_esc(_fmt_money(g.target_amount, ccy))}</td>
            </tr>"""
            for g in enriched_goals[:4]
        )
        goals_html = f"""
        <div style="margin-top:20px;">
          <div style="font-size:11px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;color:#94a3b8;margin-bottom:8px;">
            Goal Milestones
          </div>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#020617;border:1px solid #1e293b;border-radius:12px;overflow:hidden;">
            {g_rows}
          </table>
        </div>"""

    first_name = (user.full_name or "there").split()[0]
    imports_url = f"{settings.frontend_url.rstrip('/')}/imports"
    dashboard_url = f"{settings.frontend_url.rstrip('/')}/"
    sr_color = "#34d399" if savings_rate >= 20 else ("#fbbf24" if savings_rate > 0 else "#fb7185")

    body_html = f"""
      <p style="margin:0 0 18px 0;font-size:14px;color:#cbd5e1;line-height:1.6;">
        Hey <strong style="color:#ffffff;">{_esc(first_name)}</strong> — your <strong style="color:#ffffff;">{_esc(period_label)} CFO Wrapped</strong> is ready.
      </p>

      <!-- Net Worth & Savings Rate Hero -->
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
        <tr>
          <td width="50%" style="padding:0 6px 10px 0;">
            <div style="padding:14px 16px;background-color:#020617;border:1px solid #1e293b;border-radius:14px;">
              <div style="font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.05em;">Current Net Worth</div>
              <div style="font-size:20px;font-weight:800;color:#ffffff;margin-top:4px;font-family:monospace;">
                {_esc(_fmt_money(nw.current_net_worth, ccy))}
              </div>
              <div style="font-size:11px;color:{'#34d399' if nw_delta >= 0 else '#fb7185'};margin-top:4px;font-family:monospace;">
                {'+' if nw_delta >= 0 else ''}{_esc(_fmt_money(nw_delta, ccy))} vs prior snapshot
              </div>
            </div>
          </td>
          <td width="50%" style="padding:0 0 10px 6px;">
            <div style="padding:14px 16px;background-color:#020617;border:1px solid #1e293b;border-radius:14px;">
              <div style="font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.05em;">Savings Rate</div>
              <div style="font-size:20px;font-weight:800;color:{sr_color};margin-top:4px;font-family:monospace;">
                {savings_rate:.1f}%
              </div>
              <div style="font-size:11px;color:#64748b;margin-top:4px;">
                In {_esc(_fmt_money(month_in, ccy))} · Out {_esc(_fmt_money(month_out, ccy))}
              </div>
            </div>
          </td>
        </tr>
      </table>

      <!-- Biggest Win -->
      <div style="margin-top:8px;padding:16px 18px;background:linear-gradient(135deg,rgba(16,185,129,0.14),rgba(6,182,212,0.10));border:1px solid rgba(52,211,153,0.35);border-radius:14px;">
        <div style="font-size:11px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;color:#6ee7b7;margin-bottom:5px;">
          Biggest Win of {_esc(period_label)}
        </div>
        <div style="font-size:14px;color:#ffffff;line-height:1.55;font-weight:500;">
          {_esc(biggest_win)}
        </div>
      </div>

      {cat_bars_html}
      {goals_html}

      <!-- BOG Statement Reminder CTA -->
      <div style="margin-top:22px;padding:16px 18px;background-color:rgba(249,115,22,0.09);border:1px solid rgba(251,146,60,0.32);border-radius:14px;text-align:center;">
        <div style="font-size:13px;font-weight:700;color:#fed7aa;margin-bottom:6px;">
          Ready to close out {_esc(period_label)} cleanly?
        </div>
        <div style="font-size:12px;color:#cbd5e1;margin-bottom:14px;line-height:1.5;">
          Drop your fresh Bank of Georgia PDF statement (ანგარიშიდან ამონაწერი) for 0-token deterministic balance math.
        </div>
        <a href="{imports_url}" style="display:inline-block;padding:12px 22px;background-color:#f97316;color:#ffffff;font-size:13px;font-weight:800;text-decoration:none;border-radius:11px;margin-right:8px;">
          Upload BOG PDF Statement →
        </a>
        <a href="{dashboard_url}" style="display:inline-block;padding:12px 18px;background-color:#1e293b;color:#e2e8f0;font-size:13px;font-weight:700;text-decoration:none;border-radius:11px;">
          Open Dashboard
        </a>
      </div>
    """

    subject = f"Your {period_label} CFO Wrapped · Net Worth {_fmt_money(nw.current_net_worth, ccy)} · {savings_rate:.0f}% Saved"
    preheader = f"Biggest win, Top 3 spending categories, goal milestones, and your fresh {period_label} statement checklist."

    return {
        "digest_type": "monthly",
        "subject": subject,
        "preheader": preheader,
        "html": _wrap_email_shell(
            badge="Monthly CFO Wrapped",
            title=f"{period_label} Financial Wrapped",
            subtitle="Net worth, savings rate, top categories & goal milestones from your Neon ledger",
            preheader=preheader,
            body_html=body_html,
            frontend_url=settings.frontend_url,
        ),
        "metrics": {
            "period": period_label,
            "net_worth": f"{nw.current_net_worth:.2f}",
            "net_worth_delta": f"{nw_delta:.2f}",
            "month_inflow": f"{month_in:.2f}",
            "month_outflow": f"{month_out:.2f}",
            "savings_rate_pct": savings_rate,
            "top_categories": [{"name": k, "amount": f"{v:.2f}"} for k, v in top_3_cats],
            "milestones_count": len(milestones_hit),
        },
    }


async def send_via_resend(*, to_email: str, subject: str, html_body: str) -> str:
    """Send an HTML email via Resend REST API and return the Resend message ID."""
    settings = get_settings()
    if not settings.resend_api_key:
        raise RuntimeError(
            "RESEND_API_KEY is not configured on the server yet. Add your Resend API key to send live emails."
        )

    async with httpx.AsyncClient(timeout=12.0) as client:
        resp = await client.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.email_from,
                "to": [to_email],
                "subject": subject,
                "html": html_body,
            },
        )
        if resp.status_code >= 400:
            detail = resp.text[:300]
            try:
                err_json = resp.json()
                detail = str(err_json.get("message") or err_json.get("error") or detail)
            except Exception:
                pass
            raise RuntimeError(f"Resend API error ({resp.status_code}): {detail}")

        data = resp.json()
        return str(data.get("id") or "")
