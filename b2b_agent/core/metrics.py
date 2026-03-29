"""Calculs de métriques depuis la DB."""

from .db import get_conn


def get_campaign_metrics() -> dict:
    """Calcule les KPIs principaux de la campagne.

    Returns:
        dict avec sent, replies, bounces, meetings, rates, ab_results
    """
    conn = get_conn()

    # Comptages par statut
    total = conn.execute("SELECT COUNT(*) as cnt FROM prospects").fetchone()["cnt"]
    sent = conn.execute(
        "SELECT COUNT(*) as cnt FROM prospects WHERE status IN ('contacted', 'replied', 'meeting_booked', 'not_interested')"
    ).fetchone()["cnt"]
    replied = conn.execute(
        "SELECT COUNT(*) as cnt FROM prospects WHERE status = 'replied'"
    ).fetchone()["cnt"]
    bounced = conn.execute(
        "SELECT COUNT(*) as cnt FROM prospects WHERE status = 'bounced'"
    ).fetchone()["cnt"]
    meetings = conn.execute(
        "SELECT COUNT(*) as cnt FROM prospects WHERE status = 'meeting_booked'"
    ).fetchone()["cnt"]

    # Taux
    reply_rate = (replied / sent * 100) if sent > 0 else 0
    bounce_rate = (bounced / (sent + bounced) * 100) if (sent + bounced) > 0 else 0
    meeting_rate = (meetings / sent * 100) if sent > 0 else 0

    # A/B testing
    ab_results = {}
    ab_rows = conn.execute("""
        SELECT ab_variant, COUNT(*) as total,
            SUM(CASE WHEN status = 'replied' THEN 1 ELSE 0 END) as replies
        FROM prospects
        WHERE ab_variant IS NOT NULL AND status IN ('contacted', 'replied', 'meeting_booked', 'not_interested')
        GROUP BY ab_variant
    """).fetchall()

    for row in ab_rows:
        variant = row["ab_variant"]
        t = row["total"]
        r = row["replies"]
        ab_results[variant] = {
            "total": t,
            "replies": r,
            "rate": round(r / t * 100, 1) if t > 0 else 0,
        }

    conn.close()

    return {
        "total_prospects": total,
        "sent": sent,
        "replied": replied,
        "bounced": bounced,
        "meetings": meetings,
        "reply_rate": round(reply_rate, 1),
        "bounce_rate": round(bounce_rate, 1),
        "meeting_rate": round(meeting_rate, 1),
        "ab_results": ab_results,
    }
