"""Bounded mail pages over the entire local archive; no mail server access."""

import math


def mail_page(store, params):
    def number(name, default, low, high):
        try:
            value = int(params.get(name, default))
        except (ValueError, TypeError):
            raise ValueError(f"无效的邮件分页参数：{name}") from None
        if not low <= value <= high:
            raise ValueError(f"邮件分页参数超出范围：{name}")
        return value

    page = number("page", 1, 1, 2**31 - 1)
    size = number("page_size", 50, 1, 100)
    query = params.get("q", "").strip()
    if len(query) > 500:
        raise ValueError("搜索内容不能超过 500 字")
    with store.read_db() as c:
        # Counts and page contents must describe the same committed snapshot.
        current_total, latest = c.execute(
            "SELECT count(*),coalesce(max(rowid),0) FROM messages"
        ).fetchone()
        snapshot = number("snapshot", latest, 0, 2**63 - 1)
        snapshot = min(snapshot, latest)
        where, values = "m.rowid<=?", [snapshot]
        if query:
            if len(query) < 3:
                literal = (
                    "%"
                    + query.replace("\\", "\\\\")
                    .replace("%", "\\%")
                    .replace("_", "\\_")
                    + "%"
                )
                where += " AND (m.subject LIKE ? ESCAPE '\\' OR m.body_text LIKE ? ESCAPE '\\')"
                values += [literal, literal]
            else:
                where += " AND m.message_id IN (SELECT message_id FROM message_fts WHERE message_fts MATCH ?)"
                values.append('"' + query.replace('"', '""') + '"')
        total = c.execute(
            "SELECT count(*) FROM messages m WHERE " + where, values
        ).fetchone()[0]
        pages = max(1, math.ceil(total / size))
        page = min(page, pages)
        rows = c.execute(
            "SELECT m.message_id,m.subject,m.date,m.sender,m.recipients,m.in_reply_to,"
            "substr(m.body_text,1,100) AS preview FROM messages m WHERE "
            + where
            + " ORDER BY m.internal_date DESC,m.rowid DESC LIMIT ? OFFSET ?",
            (*values, size, (page - 1) * size),
        )
        return {
            "items": [dict(r) for r in rows],
            "total": total,
            "current_total": current_total,
            "page": page,
            "pages": pages,
            "page_size": size,
            "snapshot": snapshot,
            "new_count": c.execute(
                "SELECT count(*) FROM messages WHERE rowid>?", (snapshot,)
            ).fetchone()[0],
        }
