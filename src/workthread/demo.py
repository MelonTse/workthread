"""Clearly synthetic example.org mailbox and simulated AI adapter."""

import datetime as dt
from .core import uid, now, dumps
from .mail import Sync
from .ai import Bridge

PLAIN = (
    b"TEXT",
    b"PLAIN",
    (b"CHARSET", b"UTF-8"),
    None,
    None,
    b"8BIT",
    100,
    4,
    None,
    None,
)
ATTACHMENT = (
    b"APPLICATION",
    b"PDF",
    (b"NAME", b"demo.pdf"),
    None,
    None,
    b"BASE64",
    999999,
    None,
    (b"ATTACHMENT", (b"FILENAME", b"demo.pdf")),
)


class FakeIMAP:
    def __init__(self, account=None):
        self.requests = []
        self.folder = "INBOX"
        self.validity = 100
        self.fail_uid = None

    def list_folders(self):
        return [((), b"/", "INBOX"), ((b"\\Sent",), b"/", "Sent")]

    def select_folder(self, name, readonly=True):
        assert readonly
        self.folder = name
        return {b"UIDVALIDITY": self.validity}

    def search(self, criteria):
        return [1, 2] if self.folder == "INBOX" else [3]

    def fetch(self, uids, items):
        n = uids[0]
        self.requests.append((n, items))
        if n == self.fail_uid:
            raise OSError("synthetic failure")
        bodies = {
            1: "Please confirm the delivery schedule for Project Aurora. We need an update this week.",
            2: "Please also include the inspection checklist for Project Aurora.",
            3: "Thank you. I have shared the current schedule. The final delivery date is still pending.",
        }
        subjects = {
            1: "Project Aurora schedule",
            2: "Re: Project Aurora schedule",
            3: "Re: Project Aurora schedule",
        }
        references = (
            ""
            if n == 1
            else "In-Reply-To: <synthetic-1@example.org>\r\nReferences: <synthetic-1@example.org>\r\n"
        )
        sender = (
            "Local User <local@example.org>"
            if n == 3
            else "Demo Contact <contact@example.org>"
        )
        to = (
            "Demo Contact <contact@example.org>"
            if n == 3
            else "Local User <local@example.org>"
        )
        header = f"From: {sender}\r\nTo: {to}\r\nCc: Demo Team <team@example.org>\r\nSubject: {subjects[n]}\r\nMessage-ID: <synthetic-{n}@example.org>\r\nDate: Wed, 04 Nov 2026 09:00:00 +0800\r\n{references}\r\n".encode()
        if "BODYSTRUCTURE" in items:
            return {
                n: {
                    b"BODY[HEADER]": header,
                    b"BODYSTRUCTURE": (PLAIN, ATTACHMENT, b"MIXED", None, None),
                    b"INTERNALDATE": dt.datetime.now(dt.timezone.utc),
                    b"FLAGS": (),
                }
            }
        assert items == ["BODY.PEEK[1]"], (
            "forbidden attachment or whole-message request"
        )
        return {n: {b"BODY[1]": bodies[n].encode()}}

    def logout(self):
        pass


def seed(store):
    if store.setting("demo_seeded"):
        return
    with store.db() as c:
        c.execute(
            "INSERT INTO mail_accounts VALUES (?,?,?,?,?,?,?,?)",
            (
                "demo",
                "合成演示邮箱",
                "imap.example.org",
                993,
                "local@example.org",
                "synthetic",
                dumps([]),
                0,
            ),
        )
    Sync(store, lambda a: FakeIMAP()).run("demo")
    with store.db() as c:
        c.execute(
            "INSERT INTO customers VALUES (?,?,?)",
            ("demo-customer", "示例客户 · Example Co.", 1),
        )
        c.execute(
            "INSERT INTO contacts VALUES (?,?,?,?)",
            ("demo-contact", "Demo Contact", "contact@example.org", "demo-customer"),
        )
        c.execute(
            "INSERT INTO cases VALUES (?,?,?,?,?,?)",
            ("demo-case", "Aurora 交付确认", "demo-customer", "project", "待确认", 1),
        )
    t = store.create_todo(
        {
            "raw_input": "确认 Aurora 项目交付日期，并取得客户书面确认",
            "title": "确认 Aurora 交付日期",
            "no_due_date": True,
            "customer_id": "demo-customer",
            "case_id": "demo-case",
            "priority": "high",
            "status": "in_progress",
            "completion_criteria": "客户确认最终交付日期",
        },
        key="demo-main",
    )
    store.progress(
        t["todo_id"],
        {"content": "已整理当前交付安排，等待最终日期", "occurred_at": now()},
    )
    store.knowledge(
        {
            "scope": "personal",
            "content": "英文邮件先回应核心问题，再列出行动和待确认事项。",
            "confirmed": True,
        }
    )
    store.knowledge(
        {
            "scope": "customer",
            "subject_id": "demo-customer",
            "content": "示例要求：交付沟通同时提供检查清单。",
            "confirmed": True,
        }
    )
    j = Bridge(store).prepare()[0]
    Bridge(store).import_result(simulated_result(j))
    store.set_setting("demo_seeded", True)


def simulated_result(job):
    r = {
        k: job[k]
        for k in (
            "schema_version",
            "workspace_id",
            "workspace_epoch",
            "job_id",
            "input_sha256",
        )
    }
    r.update(
        outcome="completed",
        reviewed_todo_ids=job["scope"]["todo_ids"],
        operations=[],
        warnings=["SIMULATED: 合成演示结果，并非真实 WorkBuddy 执行"],
    )
    mails = job["context"]["messages"]
    todos = job["context"]["todos"]
    if mails:
        m = mails[0]
        evidence = [{"message_id": m["message_id"], "quote": m["body_text"][:60]}]
        r["operations"].append(
            {
                "operation_id": uid(),
                "type": "mail_analysis",
                "payload": {
                    "message_ids": [x["message_id"] for x in mails],
                    "work_type": "交付协调（合成示例）",
                    "stage": "等待最终日期",
                    "summary": "已经回复当前安排；最终交付日期仍待确认。",
                    "advice": "核对最终日期，并向客户提供检查清单。",
                },
                "evidence": evidence,
            }
        )
        r["operations"].append(
            {
                "operation_id": uid(),
                "type": "create_draft",
                "payload": {
                    "message_id": m["message_id"],
                    "subject": "Re: Project Aurora schedule",
                    "body": "Dear Demo Contact,\n\nThank you for your message. We are checking the final delivery date and will share the inspection checklist with the next update.\n\nBest regards",
                },
                "evidence": evidence,
            }
        )
        r["operations"].append(
            {
                "operation_id": uid(),
                "type": "create_todo",
                "payload": {
                    "title": "准备 Aurora 检查清单",
                    "description": "合成邮件提出的后续工作",
                    "action_key": "prepare-checklist",
                    "completion_criteria": "检查清单已核对并提交",
                },
                "evidence": evidence,
            }
        )
        if todos:
            r["operations"].append(
                {
                    "operation_id": uid(),
                    "type": "append_progress",
                    "todo_id": todos[0]["todo_id"],
                    "expected_revision": todos[0]["revision"],
                    "payload": {
                        "content": "模拟 AI 对账：已有回复，最终日期仍在等待确认。"
                    },
                    "evidence": evidence,
                }
            )
    return r
